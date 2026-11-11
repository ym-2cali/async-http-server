# Async HTTP Server

A non-blocking HTTP/1.1 web server written in Python (standard library only —
no `http.server`, no frameworks). It follows the 42 *webserv* specification:
a single `poll()` event loop drives every listening socket, client connection
and CGI pipe, and the server is configured with an nginx-like file.

## Features

- **Single event loop** — one `poll()` multiplexes listeners, clients and CGI
  pipes; no threads, no blocking I/O anywhere.
- **HTTP/1.1** — `GET`, `POST`, `DELETE`, keep-alive, pipelining, chunked
  transfer decoding, `Host`-based virtual servers, multiple ports.
- **Static files** — index files, MIME types, directory listing (autoindex),
  trailing-slash redirects, custom error pages.
- **Uploads** — raw bodies and `multipart/form-data`, filenames sanitised.
- **CGI/1.1** — scripts run with the full CGI environment (`QUERY_STRING`,
  `PATH_INFO`, `CONTENT_LENGTH`, `HTTP_*` …); the request body is streamed to
  the script and its output read back through non-blocking pipes. Runaway
  scripts are killed (`504`), crashing ones answered with `502`.
- **Hardening** — path-traversal and symlink-escape protection, header/URI
  size limits (`431`/`414`), per-location `client_max_body_size` (`413`),
  idle-client timeouts (`408`), graceful shutdown on `SIGINT`/`SIGTERM`.

## Usage

```sh
python3 -m webserv [config_file]        # defaults to config/default.conf
```

Then open <http://localhost:8080>.

## Configuration

```nginx
server {
    listen 8080;                         # [host:]port
    server_name localhost;
    root ./www;
    index index.html;
    error_page 404 /errors/404.html;
    client_max_body_size 10m;

    location / {
        allow_methods GET;
        autoindex off;
    }
    location /uploads {
        allow_methods GET POST DELETE;
        upload_dir ./www/uploads;
        autoindex on;
    }
    location /cgi-bin {
        allow_methods GET POST;
        cgi_extension .py;
        cgi_path /usr/bin/python3;
    }
    location /redirect {
        return 301 https://example.com;
    }
}
```

The full directive reference is in
[`docs/01_config_parsing/CONFIG_REFERENCE.md`](docs/01_config_parsing/CONFIG_REFERENCE.md).
Invalid configurations are rejected at startup with the offending line number.

## Tests

```sh
python3 tests/test_webserv.py
```

55 end-to-end checks over raw sockets: config validation, every status code,
path traversal, uploads (raw, multipart, chunked, 300 KB binary), CGI (query
string, `PATH_INFO`, POST bodies, timeouts, crashes), virtual hosts,
keep-alive, pipelining, byte-by-byte requests, slow clients and 100
concurrent connections.

## Architecture

```
webserv/
├── __main__.py   entry point
├── config.py     tokenizer + parser → ServerConfig / LocationConfig
├── protocol.py   incremental request parser, response serializer
├── handler.py    routing, static files, autoindex, uploads, DELETE, errors
├── cgi.py        CGI process with non-blocking stdin/stdout pipes
└── server.py     poll() loop, connection state machine, timeouts
```

Each connection moves through *read → (CGI) → write*. The parser is fed
whatever bytes arrive and only produces a request once it is complete, so slow
or fragmented clients never stall the loop. Responses are queued and flushed
when the socket is writable.
