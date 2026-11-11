#!/usr/bin/env python3
"""End-to-end tests for webserv.

Builds a throw-away site + config in a temp directory, starts the server and
exercises it over raw sockets.

    python3 tests/test_webserv.py
"""
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  \033[32mPASS\033[0m {name}")
    else:
        failed += 1
        print(f"  \033[31mFAIL\033[0m {name} {detail}")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def raw(port, data: bytes, timeout=3.0) -> bytes:
    """Send raw bytes, read until the server closes or the response is complete."""
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.sendall(data)
    out = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            out += chunk
            if complete(out):
                break
    except socket.timeout:
        pass
    s.close()
    return out


def complete(resp: bytes) -> bool:
    head, sep, body = resp.partition(b"\r\n\r\n")
    if not sep:
        return False
    for line in head.split(b"\r\n")[1:]:
        if line.lower().startswith(b"content-length:"):
            return len(body) >= int(line.split(b":")[1])
    return b" 204 " in head.split(b"\r\n")[0]


def request(port, method, path, body=b"", headers=None, host="localhost"):
    h = {"Host": host, "Connection": "close", **(headers or {})}
    if body and "Transfer-Encoding" not in h:
        h["Content-Length"] = str(len(body))
    head = f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in h.items()) + "\r\n"
    return parse(raw(port, head.encode() + body))


def parse(resp: bytes):
    head, _, body = resp.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    try:
        status = int(lines[0].split(" ")[1])
    except (IndexError, ValueError):
        return 0, {}, resp
    headers = {}
    for line in lines[1:]:
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    return status, headers, body


def build_site(tmp, port, port2):
    www = os.path.join(tmp, "www")
    for d in ("errors", "uploads", "cgi-bin", "files/sub", "noindex", "small"):
        os.makedirs(os.path.join(www, d))
    os.makedirs(os.path.join(tmp, "other"))
    write = lambda p, s: open(os.path.join(tmp, p), "w").write(s)
    write("www/index.html", "<h1>home</h1>")
    write("www/errors/404.html", "custom-404-page")
    write("www/files/a.txt", "file a")
    write("www/files/sub/b.css", "body{}")
    write("www/noindex/x.txt", "x")
    write("other/index.html", "other-vhost")
    write("www/cgi-bin/echo.py",
          "import os,sys\n"
          "n=int(os.environ.get('CONTENT_LENGTH') or 0)\n"
          "body=sys.stdin.read(n)\n"
          "print('Content-Type: text/plain')\nprint('X-Cgi: yes')\nprint()\n"
          "print('method='+os.environ['REQUEST_METHOD'])\n"
          "print('query='+os.environ['QUERY_STRING'])\n"
          "print('path_info='+os.environ['PATH_INFO'])\n"
          "print('len='+str(n))\nprint('body='+body)\n")
    write("www/cgi-bin/status.py", "print('Status: 201 Created')\nprint('Content-Type: text/plain')\nprint()\nprint('made')\n")
    write("www/cgi-bin/broken.py", "import sys\nsys.exit(3)\n")
    write("www/cgi-bin/loop.py", "while True:\n    pass\n")
    conf = f"""
# test configuration
server {{
    listen 127.0.0.1:{port};
    server_name localhost;
    root {www};
    error_page 404 /errors/404.html;
    client_max_body_size 1m;

    location / {{ allow_methods GET; }}
    location /files {{ allow_methods GET DELETE; autoindex on; }}
    location /uploads {{ allow_methods GET POST DELETE; upload_dir {www}/uploads; autoindex on; }}
    location /small {{ allow_methods POST; upload_dir {www}/small; client_max_body_size 100; }}
    location /cgi-bin {{ allow_methods GET POST; cgi_extension .py; cgi_path {sys.executable}; }}
    location /old {{ return 301 /files/; }}
}}
server {{
    listen 127.0.0.1:{port};
    server_name other.test;
    root {os.path.join(tmp, "other")};
}}
server {{
    listen 127.0.0.1:{port2};
    root {os.path.join(tmp, "other")};
}}
"""
    path = os.path.join(tmp, "test.conf")
    write("test.conf", conf)
    return path, www


def start(conf, env=None):
    p = subprocess.Popen([sys.executable, "-m", "webserv", conf], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         env={**os.environ, **(env or {})})
    time.sleep(0.6)
    return p


def config_errors(tmp):
    print("configuration")
    cases = {
        "missing listen": "server { root /tmp; }",
        "unknown directive": "server { listen 9999; foo bar; }",
        "missing semicolon": "server { listen 9999 }",
        "bad port": "server { listen 70000; }",
        "bad method": "server { listen 9999; location / { allow_methods PUT; } }",
        "unbalanced braces": "server { listen 9999;",
    }
    for name, text in cases.items():
        path = os.path.join(tmp, "bad.conf")
        open(path, "w").write(text)
        r = subprocess.run([sys.executable, "-m", "webserv", path], cwd=ROOT, capture_output=True, timeout=5)
        check(f"rejects config: {name}", r.returncode == 1 and b"config error" in r.stderr)
    r = subprocess.run([sys.executable, "-m", "webserv", "/nonexistent.conf"], cwd=ROOT, capture_output=True, timeout=5)
    check("rejects missing config file", r.returncode == 1)


def run(port, port2, www):
    print("static files")
    st, h, b = request(port, "GET", "/")
    check("GET / serves index", st == 200 and b == b"<h1>home</h1>" and "text/html" in h.get("content-type", ""))
    st, h, b = request(port, "GET", "/files/sub/b.css")
    check("MIME type from extension", st == 200 and h.get("content-type") == "text/css")
    st, h, b = request(port, "GET", "/nope")
    check("404 uses custom error page", st == 404 and b == b"custom-404-page")
    st, h, _ = request(port, "GET", "/files")
    check("directory without slash -> 301", st == 301 and h.get("location") == "/files/")
    st, _, b = request(port, "GET", "/files/")
    check("autoindex lists entries", st == 200 and b"a.txt" in b and b"sub/" in b)
    st, _, _ = request(port, "GET", "/noindex/")
    check("no index + autoindex off -> 403", st == 403)
    st, _, b = request(port, "GET", "/files/a%2Etxt")
    check("percent-decoded path", st == 200 and b == b"file a")
    st, _, b = request(port, "GET", "/../../../../etc/passwd")
    check("path traversal blocked", st in (403, 404) and b"root:" not in b)
    st, _, b = request(port, "GET", "/%2e%2e/%2e%2e/etc/passwd")
    check("encoded path traversal blocked", st in (403, 404) and b"root:" not in b)
    st, h, _ = request(port, "GET", "/old")
    check("configured redirect -> 301", st == 301 and h.get("location") == "/files/")

    print("protocol errors")
    st, h, _ = request(port, "DELETE", "/index.html")
    check("method not allowed -> 405 + Allow", st == 405 and h.get("allow") == "GET")
    st, _, _ = request(port, "PUT", "/")
    check("unknown method -> 501", st == 501)
    st, _, _ = parse(raw(port, b"GET / HTTP/2.0\r\nHost: x\r\n\r\n"))
    check("unsupported version -> 505", st == 505)
    st, _, _ = parse(raw(port, b"GET / HTTP/1.1\r\n\r\n"))
    check("missing Host -> 400", st == 400)
    st, _, _ = parse(raw(port, b"GARBAGE\r\n\r\n"))
    check("malformed request line -> 400", st == 400)
    st, _, _ = parse(raw(port, b"POST /uploads HTTP/1.1\r\nHost: x\r\n\r\n"))
    check("POST without length -> 411", st == 411)
    st, _, _ = request(port, "POST", "/small", b"x" * 101)
    check("body over location limit -> 413", st == 413)
    st, _, _ = request(port, "POST", "/uploads", b"x" * (1024 * 1024 + 1))
    check("body over server limit -> 413", st == 413)
    chunked = b"".join(f"{40:x}\r\n".encode() + b"y" * 40 + b"\r\n" for _ in range(4)) + b"0\r\n\r\n"
    st, _, _ = request(port, "POST", "/small", chunked, {"Transfer-Encoding": "chunked"})
    check("chunked body over limit -> 413", st == 413)
    st, _, _ = parse(raw(port, b"GET /" + b"a" * 9000 + b" HTTP/1.1\r\nHost: x\r\n\r\n"))
    check("huge URI -> 414", st == 414)

    print("upload / delete")
    st, h, _ = request(port, "POST", "/uploads/note.txt", b"hello upload", {"Content-Type": "text/plain"})
    check("raw POST upload -> 201 + Location", st == 201 and h.get("location") == "/uploads/note.txt")
    st, _, b = request(port, "GET", "/uploads/note.txt")
    check("uploaded file is served back", st == 200 and b == b"hello upload")
    blob = os.urandom(300_000)
    st, _, _ = request(port, "POST", "/uploads/blob.bin", blob)
    st2, _, b = request(port, "GET", "/uploads/blob.bin")
    check("300KB binary upload round-trips intact", st == 201 and b == blob)
    boundary = "----webservtest"
    form = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"../../evil.txt\"\r\n"
            f"Content-Type: text/plain\r\n\r\nmultipart content\r\n--{boundary}--\r\n").encode()
    st, h, _ = request(port, "POST", "/uploads", form, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    check("multipart upload -> 201", st == 201)
    check("multipart filename is sanitised", os.path.isfile(os.path.join(www, "uploads", "evil.txt"))
          and not os.path.exists(os.path.join(www, "..", "evil.txt")))
    body = b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
    st, _, _ = request(port, "POST", "/uploads/chunk.txt", body, {"Transfer-Encoding": "chunked"})
    _, _, b = request(port, "GET", "/uploads/chunk.txt")
    check("chunked upload is de-chunked", st == 201 and b == b"hello world")
    st, _, _ = request(port, "DELETE", "/uploads/note.txt")
    check("DELETE -> 204", st == 204)
    st, _, _ = request(port, "GET", "/uploads/note.txt")
    check("deleted file is gone -> 404", st == 404)
    st, _, _ = request(port, "DELETE", "/uploads/note.txt")
    check("DELETE missing file -> 404", st == 404)

    print("CGI")
    st, h, b = request(port, "GET", "/cgi-bin/echo.py/extra/path?x=1&y=2")
    check("CGI GET: query string + PATH_INFO", st == 200 and b"query=x=1&y=2" in b and b"path_info=/extra/path" in b)
    check("CGI headers forwarded", h.get("x-cgi") == "yes" and h.get("content-type") == "text/plain")
    st, _, b = request(port, "POST", "/cgi-bin/echo.py", b"a=1&b=2", {"Content-Type": "application/x-www-form-urlencoded"})
    check("CGI POST body on stdin", st == 200 and b"len=7" in b and b"body=a=1&b=2" in b)
    st, _, b = request(port, "POST", "/cgi-bin/echo.py", b"3\r\nabc\r\n0\r\n\r\n", {"Transfer-Encoding": "chunked"})
    check("CGI gets un-chunked body with CONTENT_LENGTH", st == 200 and b"len=3" in b and b"body=abc" in b)
    st, _, b = request(port, "POST", "/cgi-bin/echo.py", b"z" * 200_000)
    check("CGI large POST body (200KB) via non-blocking pipe", st == 200 and b"len=200000" in b)
    st, _, b = request(port, "GET", "/cgi-bin/status.py")
    check("CGI Status header sets response code", st == 201 and b"made" in b)
    st, _, _ = request(port, "GET", "/cgi-bin/broken.py")
    check("CGI with no output -> 502", st == 502)
    st, _, _ = request(port, "GET", "/cgi-bin/missing.py")
    check("missing CGI script -> 404", st == 404)
    t0 = time.time()
    st, _, _ = request(port, "GET", "/cgi-bin/loop.py")
    check("runaway CGI killed -> 504", st == 504 and time.time() - t0 < 6)
    st, _, _ = request(port, "GET", "/")
    check("server still healthy after CGI failures", st == 200)

    print("virtual hosts / ports")
    _, _, b = request(port, "GET", "/", host="other.test")
    check("Host header selects virtual server", b == b"other-vhost")
    _, _, b = request(port, "GET", "/", host="unknown.test")
    check("unknown Host falls back to first server", b == b"<h1>home</h1>")
    _, _, b = request(port2, "GET", "/")
    check("second port serves its own server", b == b"other-vhost")

    print("connections")
    s = socket.create_connection(("127.0.0.1", port), timeout=3)
    s.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
    r1 = s.recv(65536)
    s.sendall(b"GET /files/a.txt HTTP/1.1\r\nHost: x\r\n\r\n")
    r2 = s.recv(65536)
    s.close()
    check("keep-alive: two requests on one connection", b"200 OK" in r1 and r2.endswith(b"file a"))
    s = socket.create_connection(("127.0.0.1", port), timeout=3)
    s.sendall(b"GET /files/a.txt HTTP/1.1\r\nHost: x\r\n\r\nGET /files/sub/b.css HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    data = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    s.close()
    check("pipelined requests both answered in order", data.count(b"HTTP/1.1 200") == 2
          and data.index(b"file a") < data.index(b"body{}"))
    s = socket.create_connection(("127.0.0.1", port), timeout=3)
    for byte in b"GET /files/a.txt HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n":
        s.send(bytes([byte]))
        time.sleep(0.002)
    data = s.recv(65536)
    s.close()
    check("request trickled byte-by-byte", data.endswith(b"file a"))

    slow = socket.create_connection(("127.0.0.1", port), timeout=3)
    slow.sendall(b"GET / HTTP/1.1\r\n")                      # never finishes
    t0 = time.time()
    st, _, _ = request(port, "GET", "/files/a.txt")
    check("slow client does not block others", st == 200 and time.time() - t0 < 1)
    slow.close()
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(b"POST /uploads/x HTTP/1.1\r\nHost: x\r\nContent-Length: 1000\r\n\r\npartial")
    s.close()

    results = []

    def worker():
        results.append(request(port, "GET", "/files/a.txt")[0])

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("100 concurrent clients all get 200", results.count(200) == 100, str(results.count(200)))


def main():
    tmp = tempfile.mkdtemp(prefix="webserv-test-")
    try:
        config_errors(tmp)
        port, port2 = free_port(), free_port()
        conf, www = build_site(tmp, port, port2)
        server = start(conf, {"WEBSERV_CGI_TIMEOUT": "2"})
        try:
            run(port, port2, www)
        finally:
            server.send_signal(signal.SIGINT)
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        check("clean shutdown on SIGINT", server.returncode == 0, server.stderr.read().decode()[-500:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
