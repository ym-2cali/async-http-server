"""Turns a parsed request into a response (or a running CGI process)."""
import os
import posixpath
import re
import time
from html import escape
from urllib.parse import quote

from .cgi import CgiProcess
from .config import KNOWN_METHODS
from .protocol import HttpError, HttpResponse, default_error_page, mime_type


def handle(req, client_ip: str, server_port: int):
    srv, loc = req.server, req.location

    if loc.redirect:
        code, url = loc.redirect
        resp = HttpResponse(code, default_error_page(code))
        resp.headers["Location"] = url
        return resp
    if req.method not in KNOWN_METHODS:
        raise HttpError(501)
    if req.method not in loc.methods:
        err = HttpError(405)
        err.headers = {"Allow": ", ".join(sorted(loc.methods))}
        raise err

    root = loc.root or srv.root
    url_path = normalize(req.path)
    fs_path = to_fs_path(root, url_path)

    cgi = find_cgi(loc, root, url_path)
    if cgi and req.method in ("GET", "POST"):
        script, script_url, path_info = cgi
        if not os.path.isfile(script):
            raise HttpError(404)
        return CgiProcess(req, script, script_url, path_info, loc.cgi_path, client_ip, server_port)

    if req.method == "GET":
        return get(req, srv, loc, fs_path)
    if req.method == "POST":
        if loc.upload_dir:
            return upload(req, loc, url_path)
        raise HttpError(403, "uploads are not enabled for this location")
    return delete(fs_path)


# --------------------------------------------------------------------------- #
#                                   paths                                     #
# --------------------------------------------------------------------------- #

def normalize(path: str) -> str:
    """Collapse '.', '..' and '//' — a leading '/' absorbs any '..' so the
    result can never climb above the document root."""
    norm = posixpath.normpath("/" + path.lstrip("/"))
    if path.endswith("/") and norm != "/":
        norm += "/"
    return norm


def to_fs_path(root: str, url_path: str) -> str:
    fs = os.path.join(root, url_path.lstrip("/"))
    real_root = os.path.realpath(root)
    real = os.path.realpath(fs)
    if real != real_root and not real.startswith(real_root + os.sep):
        raise HttpError(403, "path escapes document root")       # symlink escape
    return fs


def find_cgi(loc, root, url_path):
    """'/cgi-bin/app.py/extra/info' -> (fs script, '/cgi-bin/app.py', '/extra/info')"""
    if not loc.cgi_extensions:
        return None
    parts = url_path.split("/")
    for i, part in enumerate(parts):
        if any(part.endswith(ext) for ext in loc.cgi_extensions):
            script_url = "/".join(parts[:i + 1])
            path_info = "/" + "/".join(parts[i + 1:]) if i + 1 < len(parts) else ""
            return os.path.join(root, script_url.lstrip("/")), script_url, path_info
    return None


# --------------------------------------------------------------------------- #
#                                  methods                                    #
# --------------------------------------------------------------------------- #

def get(req, srv, loc, fs_path):
    if os.path.isdir(fs_path):
        if not req.path.endswith("/"):
            resp = HttpResponse(301, default_error_page(301))
            resp.headers["Location"] = quote(req.path) + "/" + (f"?{req.query}" if req.query else "")
            return resp
        for name in loc.index or srv.index:
            candidate = os.path.join(fs_path, name)
            if os.path.isfile(candidate):
                return serve_file(candidate)
        if loc.autoindex:
            return directory_listing(req.path, fs_path)
        raise HttpError(403, "directory listing is disabled")
    if not os.path.exists(fs_path):
        raise HttpError(404)
    return serve_file(fs_path)


def serve_file(path):
    try:
        with open(path, "rb") as f:
            body = f.read()
    except PermissionError:
        raise HttpError(403) from None
    except OSError:
        raise HttpError(404) from None
    return HttpResponse(200, body, mime_type(path))


def directory_listing(url_path, fs_path):
    try:
        entries = sorted(os.scandir(fs_path), key=lambda e: (not e.is_dir(), e.name.lower()))
    except OSError:
        raise HttpError(403) from None
    rows = ['<tr><td><a href="../">../</a></td><td></td><td></td></tr>'] if url_path != "/" else []
    for e in entries:
        name = e.name + ("/" if e.is_dir() else "")
        st = e.stat()
        size = "-" if e.is_dir() else f"{st.st_size:,}"
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
        rows.append(f'<tr><td><a href="{quote(name)}">{escape(name)}</a></td>'
                    f"<td>{mtime}</td><td align=\"right\">{size}</td></tr>")
    title = f"Index of {escape(url_path)}"
    body = (f"<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>{title}</title></head>"
            f"<body style=\"font-family:monospace\"><h1>{title}</h1><table cellpadding=\"4\">"
            + "".join(rows) + "</table></body></html>\n")
    return HttpResponse(200, body.encode())


def upload(req, loc, url_path):
    os.makedirs(loc.upload_dir, exist_ok=True)
    ctype = req.headers.get("content-type", "")
    saved = []

    if ctype.lower().startswith("multipart/form-data"):
        m = re.search(r'boundary="?([^";]+)"?', ctype)
        if not m:
            raise HttpError(400, "multipart body without boundary")
        for headers, data in parse_multipart(req.body, m.group(1).encode()):
            fm = re.search(r'filename="([^"]*)"', headers.get("content-disposition", ""))
            if fm and fm.group(1):
                saved.append(save(loc.upload_dir, fm.group(1), data))
        if not saved:
            raise HttpError(400, "no file found in form data")
    else:
        sub = url_path[len(loc.path.rstrip("/")):].strip("/")
        saved.append(save(loc.upload_dir, sub or "", req.body))

    base = loc.path.rstrip("/")
    links = "".join(f'<li><a href="{base}/{quote(n)}">{escape(n)}</a></li>' for n in saved)
    resp = HttpResponse(201, f"<!DOCTYPE html>\n<html><body><h1>201 Created</h1><ul>{links}</ul></body></html>\n".encode())
    resp.headers["Location"] = f"{base}/{quote(saved[0])}"
    return resp


def parse_multipart(body: bytes, boundary: bytes):
    for part in body.split(b"--" + boundary)[1:]:
        if part.startswith(b"--"):
            break
        part = part[2:] if part.startswith(b"\r\n") else part
        head, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        headers = {}
        for line in head.decode("latin-1").split("\r\n"):
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        yield headers, data


def save(directory: str, name: str, data: bytes) -> str:
    name = os.path.basename(name.replace("\\", "/")).strip()
    if name in ("", ".", ".."):
        name = f"upload_{int(time.time() * 1000)}.bin"
    try:
        with open(os.path.join(directory, name), "wb") as f:
            f.write(data)
    except OSError:
        raise HttpError(500, "could not store upload") from None
    return name


def delete(fs_path):
    if not os.path.exists(fs_path):
        raise HttpError(404)
    if os.path.isdir(fs_path):
        raise HttpError(403, "cannot delete a directory")
    try:
        os.remove(fs_path)
    except PermissionError:
        raise HttpError(403) from None
    except OSError:
        raise HttpError(500) from None
    return HttpResponse(204)


# --------------------------------------------------------------------------- #
#                                  errors                                     #
# --------------------------------------------------------------------------- #

def error_response(srv, err: HttpError) -> HttpResponse:
    body = None
    page = srv.error_pages.get(err.status) if srv else None
    if page:
        try:
            with open(os.path.join(srv.root, page.lstrip("/")), "rb") as f:
                body = f.read()
        except OSError:
            body = None
    resp = HttpResponse(err.status, body or default_error_page(err.status, str(err)))
    resp.headers.update(getattr(err, "headers", {}))
    return resp
