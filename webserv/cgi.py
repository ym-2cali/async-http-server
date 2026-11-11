"""CGI/1.1 execution with non-blocking pipes driven by the main poll loop."""
import os
import subprocess
import time

from . import SERVER_SOFTWARE
from .protocol import HttpError, HttpResponse

CGI_TIMEOUT = float(os.environ.get("WEBSERV_CGI_TIMEOUT", 10))
CHUNK = 65536


class CgiProcess:
    def __init__(self, req, script: str, script_url: str, path_info: str,
                 interpreter: str | None, client_ip: str, server_port: int):
        script = os.path.abspath(script)
        if interpreter and not os.access(interpreter, os.X_OK):
            raise HttpError(502, f"CGI interpreter {interpreter} is not executable")
        if not interpreter and not os.access(script, os.X_OK):
            raise HttpError(403, "CGI script is not executable")

        host = req.headers.get("host", "").rsplit(":", 1)[0]
        env = {
            "GATEWAY_INTERFACE": "CGI/1.1",
            "SERVER_SOFTWARE": SERVER_SOFTWARE,
            "SERVER_PROTOCOL": "HTTP/1.1",
            "SERVER_NAME": host or "localhost",
            "SERVER_PORT": str(server_port),
            "REQUEST_METHOD": req.method,
            "REQUEST_URI": req.target,
            "QUERY_STRING": req.query,
            "SCRIPT_NAME": script_url,
            "SCRIPT_FILENAME": script,
            "PATH_INFO": path_info,
            "PATH_TRANSLATED": os.path.dirname(script) + path_info if path_info else "",
            "CONTENT_LENGTH": str(len(req.body)),
            "CONTENT_TYPE": req.headers.get("content-type", ""),
            "REMOTE_ADDR": client_ip,
            "REDIRECT_STATUS": "200",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        for name, value in req.headers.items():
            key = "HTTP_" + name.upper().replace("-", "_")
            if key not in ("HTTP_CONTENT_LENGTH", "HTTP_CONTENT_TYPE"):
                env[key] = value

        argv = [interpreter, script] if interpreter else [script]
        try:
            self.proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=os.path.dirname(script), env=env, close_fds=True)
        except OSError as e:
            raise HttpError(502, f"cannot start CGI: {e.strerror}") from None

        self.stdin_fd = self.proc.stdin.fileno()
        self.stdout_fd = self.proc.stdout.fileno()
        os.set_blocking(self.stdin_fd, False)
        os.set_blocking(self.stdout_fd, False)
        self.pending = memoryview(req.body)
        self.output = bytearray()
        self.started = time.monotonic()
        self.stdin_open = True
        self.stdout_open = True
        if not self.pending:
            self.close_stdin()

    # ---- driven by the server's poll loop -------------------------------- #

    def write_ready(self) -> bool:
        """Push more of the request body. Returns True once stdin is closed."""
        try:
            n = os.write(self.stdin_fd, self.pending[:CHUNK])
        except BlockingIOError:
            return False
        except OSError:            # script exited without reading its input
            self.close_stdin()
            return True
        self.pending = self.pending[n:]
        if not self.pending:
            self.close_stdin()
            return True
        return False

    def read_ready(self) -> bool:
        """Collect output. Returns True at EOF (the script is finished)."""
        try:
            data = os.read(self.stdout_fd, CHUNK)
        except BlockingIOError:
            return False
        except OSError:
            data = b""
        if data:
            self.output += data
            return False
        self.close_stdout()
        try:
            self.proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        return True

    def timed_out(self) -> bool:
        return time.monotonic() - self.started > CGI_TIMEOUT

    def kill(self):
        self.close_stdin()
        self.close_stdout()
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()

    def close_stdin(self):
        if self.stdin_open:
            self.stdin_open = False
            self.proc.stdin.close()

    def close_stdout(self):
        if self.stdout_open:
            self.stdout_open = False
            self.proc.stdout.close()

    # ---- output -> HTTP response ----------------------------------------- #

    def response(self) -> HttpResponse:
        raw = bytes(self.output)
        candidates = [(i, n) for i, n in ((raw.find(b"\r\n\r\n"), 4), (raw.find(b"\n\n"), 2)) if i != -1]
        if not candidates:
            raise HttpError(502, "CGI script produced no headers")
        end, sep_len = min(candidates)
        head, body = raw[:end].decode("latin-1"), raw[end + sep_len:]

        status, content_type, extra = None, "text/html; charset=utf-8", {}
        for line in head.splitlines():
            name, sep, value = line.partition(":")
            if not sep:
                raise HttpError(502, "malformed CGI header")
            name, value = name.strip(), value.strip()
            lname = name.lower()
            if lname == "status":
                code = value.split(" ", 1)[0]
                if not code.isdigit():
                    raise HttpError(502, "invalid CGI Status header")
                status = int(code)
            elif lname == "content-type":
                content_type = value
            elif lname != "content-length":
                extra[name] = value
        if status is None:
            status = 302 if "Location" in extra else 200

        resp = HttpResponse(status, body, content_type)
        resp.headers.update(extra)
        return resp
