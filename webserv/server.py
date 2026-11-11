"""Single poll() event loop: listening sockets, clients and CGI pipes."""
import select
import signal
import socket
import sys
import time
import traceback

from . import handler
from .cgi import CgiProcess
from .protocol import HttpError, RequestParser

CLIENT_TIMEOUT = 60
READ_SIZE = 65536

POLLIN = select.POLLIN
POLLOUT = select.POLLOUT
POLLERR = select.POLLERR | select.POLLHUP | select.POLLNVAL


class Listener:
    def __init__(self, host, port, servers):
        self.host, self.port, self.servers = host, port, servers
        self.sock = None


class Connection:
    def __init__(self, sock, addr, listener):
        self.sock = sock
        self.fd = sock.fileno()
        self.ip = addr[0]
        self.listener = listener
        self.parser = RequestParser(self.on_headers)
        self.out = bytearray()
        self.close_after = False
        self.keep_alive = True
        self.last_active = time.monotonic()
        self.cgi: CgiProcess | None = None
        self.request = None

    def on_headers(self, req):
        """Pick the virtual server (Host header) and location, return the body limit."""
        host = req.headers.get("host", "").rsplit(":", 1)[0].lower()
        req.server = next((s for s in self.listener.servers if host in s.server_names),
                          self.listener.servers[0])
        req.location = req.server.match_location(handler.normalize(req.path))
        return req.location.client_max_body_size or req.server.client_max_body_size


class WebServer:
    def __init__(self, servers):
        self.poller = select.poll()
        self.listeners: dict[int, Listener] = {}
        self.clients: dict[int, Connection] = {}
        self.cgi_pipes: dict[int, Connection] = {}
        self.running = True

        groups: dict[tuple[str, int], list] = {}
        for srv in servers:
            groups.setdefault((srv.host, srv.port), []).append(srv)
        self.pending_listeners = [Listener(h, p, s) for (h, p), s in groups.items()]

    # ------------------------------------------------------------------ #
    #                              setup                                 #
    # ------------------------------------------------------------------ #

    def bind(self):
        for lst in self.pending_listeners:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((lst.host, lst.port))
            except OSError as e:
                sock.close()
                raise OSError(f"cannot bind {lst.host}:{lst.port}: {e.strerror}") from None
            sock.listen(128)
            sock.setblocking(False)
            lst.sock = sock
            self.listeners[sock.fileno()] = lst
            self.poller.register(sock.fileno(), POLLIN)
            names = ", ".join(n for s in lst.servers for n in s.server_names) or "default"
            log(f"listening on http://{lst.host}:{lst.port} ({names})")

    def stop(self, *_):
        self.running = False

    def run(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        while self.running:
            for fd, ev in self.poller.poll(1000):
                try:
                    if fd in self.listeners:
                        self.accept(self.listeners[fd])
                    elif fd in self.cgi_pipes:
                        self.on_cgi(fd, ev)
                    elif fd in self.clients:
                        self.on_client(self.clients[fd], ev)
                except Exception:                   # never let one request kill the server
                    traceback.print_exc()
                    if fd in self.clients:
                        self.close(self.clients[fd])
            self.check_timeouts()
        self.shutdown()

    def shutdown(self):
        for conn in list(self.clients.values()):
            self.close(conn)
        for lst in self.listeners.values():
            lst.sock.close()
        log("server stopped")

    # ------------------------------------------------------------------ #
    #                              clients                               #
    # ------------------------------------------------------------------ #

    def accept(self, lst):
        while True:
            try:
                sock, addr = lst.sock.accept()
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            sock.setblocking(False)
            conn = Connection(sock, addr, lst)
            self.clients[conn.fd] = conn
            self.poller.register(conn.fd, POLLIN)

    def on_client(self, conn, ev):
        if ev & POLLIN:
            try:
                data = conn.sock.recv(READ_SIZE)
            except BlockingIOError:
                return
            except OSError:
                data = b""
            if not data:
                self.close(conn)
                return
            conn.last_active = time.monotonic()
            self.feed(conn, data)
        elif ev & POLLERR:
            self.close(conn)
            return
        if ev & POLLOUT and conn.fd in self.clients:
            self.write(conn)

    def feed(self, conn, data):
        try:
            req = conn.parser.feed(data)
        except HttpError as e:
            srv = conn.parser.req.server or conn.listener.servers[0]
            self.respond(conn, handler.error_response(srv, e), conn.parser.req, keep_alive=False)
            return
        if req:
            self.dispatch(conn, req)

    def dispatch(self, conn, req):
        conn.request = req
        conn.keep_alive = req.keep_alive
        try:
            result = handler.handle(req, conn.ip, conn.listener.port)
        except HttpError as e:
            result = handler.error_response(req.server, e)
        except Exception:
            traceback.print_exc()
            result = handler.error_response(req.server, HttpError(500))

        if isinstance(result, CgiProcess):
            conn.cgi = result
            self.poller.modify(conn.fd, 0)           # wait for the script, not the client
            self.cgi_pipes[result.stdout_fd] = conn
            self.poller.register(result.stdout_fd, POLLIN)
            if result.stdin_open:
                self.cgi_pipes[result.stdin_fd] = conn
                self.poller.register(result.stdin_fd, POLLOUT)
        else:
            self.respond(conn, result, req, conn.keep_alive)

    def respond(self, conn, resp, req, keep_alive):
        conn.close_after = not keep_alive
        conn.out += resp.serialize(keep_alive)
        log(f'{conn.ip} "{req.method or "-"} {req.target or "-"}" {resp.status}')
        self.poller.modify(conn.fd, POLLOUT)

    def write(self, conn):
        try:
            n = conn.sock.send(conn.out)
        except BlockingIOError:
            return
        except OSError:
            self.close(conn)
            return
        del conn.out[:n]
        conn.last_active = time.monotonic()
        if conn.out:
            return
        if conn.close_after:
            self.close(conn)
            return
        # keep-alive: start a fresh parser, replaying any pipelined bytes
        leftover = conn.parser.leftover()
        conn.parser = RequestParser(conn.on_headers)
        conn.request = None
        self.poller.modify(conn.fd, POLLIN)
        if leftover:
            self.feed(conn, leftover)

    def close(self, conn):
        if conn.cgi:
            self.stop_cgi(conn)
        self.clients.pop(conn.fd, None)
        try:
            self.poller.unregister(conn.fd)
        except KeyError:
            pass
        conn.sock.close()

    # ------------------------------------------------------------------ #
    #                                CGI                                 #
    # ------------------------------------------------------------------ #

    def on_cgi(self, fd, ev):
        conn = self.cgi_pipes[fd]
        cgi = conn.cgi
        if fd == cgi.stdin_fd and cgi.stdin_open:
            if cgi.write_ready() or ev & POLLERR:
                self.drop_pipe(fd)
                cgi.close_stdin()
        elif fd == cgi.stdout_fd and cgi.stdout_open:
            if ev & (POLLIN | POLLERR) and cgi.read_ready():
                self.drop_pipe(fd)
                self.finish_cgi(conn)

    def drop_pipe(self, fd):
        self.cgi_pipes.pop(fd, None)
        try:
            self.poller.unregister(fd)
        except KeyError:
            pass

    def stop_cgi(self, conn):
        cgi = conn.cgi
        for fd in (cgi.stdin_fd, cgi.stdout_fd):
            if self.cgi_pipes.get(fd) is conn:
                self.drop_pipe(fd)
        cgi.kill()
        conn.cgi = None

    def finish_cgi(self, conn):
        cgi = conn.cgi
        self.stop_cgi(conn)
        try:
            resp = cgi.response()
        except HttpError as e:
            resp = handler.error_response(conn.request.server, e)
        self.respond(conn, resp, conn.request, conn.keep_alive)

    # ------------------------------------------------------------------ #

    def check_timeouts(self):
        now = time.monotonic()
        for conn in list(self.clients.values()):
            if conn.cgi:
                if conn.cgi.timed_out():
                    self.stop_cgi(conn)
                    self.respond(conn, handler.error_response(conn.request.server, HttpError(504)),
                                 conn.request, keep_alive=False)
            elif now - conn.last_active > CLIENT_TIMEOUT:
                if conn.parser.buf or conn.parser.state != "headers":
                    srv = conn.listener.servers[0]
                    self.respond(conn, handler.error_response(srv, HttpError(408)),
                                 conn.parser.req, keep_alive=False)
                    conn.last_active = now
                else:
                    self.close(conn)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stdout, flush=True)
