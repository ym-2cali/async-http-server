"""Incremental HTTP/1.1 request parser and response builder."""
from email.utils import formatdate
from html import escape
from http import HTTPStatus
from urllib.parse import unquote

from . import SERVER_SOFTWARE

MAX_HEADER_SIZE = 8192
MAX_URI_LENGTH = 4096


class HttpError(Exception):
    def __init__(self, status: int, detail: str = ""):
        super().__init__(detail or reason(status))
        self.status = status


def reason(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Unknown"


class HttpRequest:
    def __init__(self):
        self.method = ""
        self.target = ""
        self.path = "/"
        self.query = ""
        self.version = ""
        self.headers: dict[str, str] = {}
        self.body = b""
        # filled by the server once the Host header is known
        self.server = None
        self.location = None

    @property
    def keep_alive(self) -> bool:
        conn = self.headers.get("connection", "").lower()
        if self.version == "HTTP/1.0":
            return conn == "keep-alive"
        return conn != "close"


class RequestParser:
    """Feed raw bytes; returns a complete HttpRequest once one is available.

    `on_headers(request)` is called as soon as the headers are parsed and must
    return the maximum body size allowed for that request (or raise HttpError).
    """

    def __init__(self, on_headers):
        self.on_headers = on_headers
        self.buf = bytearray()
        self.req = HttpRequest()
        self.state = "headers"
        self.max_body = 0
        self.expected = 0
        self.body = bytearray()

    def feed(self, data: bytes) -> HttpRequest | None:
        self.buf += data
        if self.state == "headers":
            end = self.buf.find(b"\r\n\r\n")
            if end == -1:
                if len(self.buf) > MAX_HEADER_SIZE:
                    raise HttpError(431 if b"\r\n" in self.buf else 414)
                return None
            self._parse_head(bytes(self.buf[:end]).decode("latin-1"))
            del self.buf[:end + 4]
            self.max_body = self.on_headers(self.req)
            self._start_body()
        if self.state == "body":
            need = self.expected - len(self.body)
            self.body += self.buf[:need]
            del self.buf[:need]
            if len(self.body) == self.expected:
                self.state = "done"
        if self.state == "chunked":
            self._parse_chunks()
        if self.state == "done":
            self.req.body = bytes(self.body)
            return self.req
        return None

    def leftover(self) -> bytes:
        """Bytes received after the current request (pipelining)."""
        return bytes(self.buf)

    # ------------------------------------------------------------------ #

    def _parse_head(self, head: str):
        lines = head.split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) != 3:
            raise HttpError(400, "malformed request line")
        method, target, version = parts
        if not method.isalpha() or not method.isupper():
            raise HttpError(400, "malformed method")
        if not version.startswith("HTTP/1."):
            raise HttpError(505 if version.startswith("HTTP/") else 400)
        if version not in ("HTTP/1.0", "HTTP/1.1"):
            raise HttpError(505)
        if len(target) > MAX_URI_LENGTH:
            raise HttpError(414)
        if not target.startswith("/"):
            raise HttpError(400, "request target must be an absolute path")

        req = self.req
        req.method, req.target, req.version = method, target, version
        path, _, req.query = target.partition("?")
        req.path = unquote(path)
        if "\x00" in req.path:
            raise HttpError(400, "null byte in path")

        last = None
        for line in lines[1:]:
            if line[:1] in (" ", "\t") and last:          # obsolete line folding
                req.headers[last] += " " + line.strip()
                continue
            name, sep, value = line.partition(":")
            if not sep or not name or name != name.strip():
                raise HttpError(400, "malformed header")
            last = name.lower()
            value = value.strip()
            req.headers[last] = f"{req.headers[last]}, {value}" if last in req.headers else value

        if version == "HTTP/1.1" and "host" not in req.headers:
            raise HttpError(400, "missing Host header")

    def _start_body(self):
        h = self.req.headers
        if "chunked" in h.get("transfer-encoding", "").lower():
            self.state = "chunked"
        elif "content-length" in h:
            cl = h["content-length"]
            if not cl.isdigit():
                raise HttpError(400, "invalid Content-Length")
            self.expected = int(cl)
            if self.expected > self.max_body:
                raise HttpError(413)
            self.state = "body" if self.expected else "done"
        elif self.req.method == "POST":
            raise HttpError(411)
        else:
            self.state = "done"

    def _parse_chunks(self):
        while True:
            eol = self.buf.find(b"\r\n")
            if eol == -1:
                if len(self.buf) > 1024:
                    raise HttpError(400, "chunk size line too long")
                return
            size_str = bytes(self.buf[:eol]).split(b";")[0].strip()
            try:
                size = int(size_str, 16)
            except ValueError:
                raise HttpError(400, "invalid chunk size") from None
            if size == 0:
                end = self.buf.find(b"\r\n\r\n", eol)        # skip optional trailers
                if end == -1:
                    return
                del self.buf[:end + 4]
                self.state = "done"
                return
            if len(self.buf) < eol + 2 + size + 2:
                return
            if self.buf[eol + 2 + size:eol + 4 + size] != b"\r\n":
                raise HttpError(400, "chunk not terminated by CRLF")
            self.body += self.buf[eol + 2:eol + 2 + size]
            del self.buf[:eol + 4 + size]
            if len(self.body) > self.max_body:
                raise HttpError(413)


class HttpResponse:
    def __init__(self, status: int = 200, body: bytes = b"", content_type: str = "text/html; charset=utf-8"):
        self.status = status
        self.body = body
        self.headers: dict[str, str] = {}
        if body or status not in (204, 304):
            self.headers["Content-Type"] = content_type

    def serialize(self, keep_alive: bool, head_only: bool = False) -> bytes:
        headers = {
            "Server": SERVER_SOFTWARE,
            "Date": formatdate(usegmt=True),
            **self.headers,
            "Content-Length": str(len(self.body)),
            "Connection": "keep-alive" if keep_alive else "close",
        }
        if self.status == 204:
            del headers["Content-Length"]
        head = f"HTTP/1.1 {self.status} {reason(self.status)}\r\n"
        head += "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n"
        return head.encode("latin-1") + (b"" if head_only else self.body)


def default_error_page(status: int, detail: str = "") -> bytes:
    title = f"{status} {reason(status)}"
    extra = f"<p>{escape(detail)}</p>" if detail and detail != reason(status) else ""
    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head>\n<body style=\"font-family:sans-serif;text-align:center\">"
        f"<h1>{title}</h1>{extra}<hr><p>{SERVER_SOFTWARE}</p></body></html>\n"
    ).encode()


MIME_TYPES = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".css": "text/css", ".js": "application/javascript", ".json": "application/json",
    ".txt": "text/plain; charset=utf-8", ".xml": "application/xml", ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".svg": "image/svg+xml", ".ico": "image/x-icon", ".webp": "image/webp",
    ".mp4": "video/mp4", ".mp3": "audio/mpeg", ".zip": "application/zip",
}


def mime_type(path: str) -> str:
    dot = path.rfind(".")
    return MIME_TYPES.get(path[dot:].lower(), "application/octet-stream") if dot != -1 else "application/octet-stream"
