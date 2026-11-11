# Part 3: HTTP Request Parsing

## Overview
Parse raw HTTP/1.1 requests into a structured format for processing.

---

## TODO List

### 1. Request Line Parsing
- [ ] Parse the first line: `METHOD URI HTTP/1.1\r\n`
- [ ] Extract the HTTP method (GET, POST, DELETE — minimum required)
- [ ] Extract the Request-URI (path + optional query string)
- [ ] Extract and validate the HTTP version (must be `HTTP/1.1`)
- [ ] Decode percent-encoded characters in the URI (e.g., `%20` → space)
- [ ] Separate the URI path from the query string (split on `?`)
- [ ] Reject malformed request lines with `400 Bad Request`

### 2. Header Parsing
- [ ] Parse headers: `Header-Name: value\r\n`
- [ ] Headers are case-insensitive (normalize to lowercase or handle both)
- [ ] Handle multi-line header values (continuation lines starting with space/tab)
- [ ] Detect end of headers: empty line `\r\n\r\n`
- [ ] Store headers in a `std::map<std::string, std::string>`
- [ ] Handle duplicate headers (concatenate with `,` or take last)

### 3. Key Headers to Extract
- [ ] `Host` — required in HTTP/1.1 (used for virtual hosting)
- [ ] `Content-Length` — size of the body in bytes
- [ ] `Transfer-Encoding` — check for `chunked`
- [ ] `Content-Type` — MIME type of the body (important for POST/CGI)
- [ ] `Connection` — `keep-alive` or `close`
- [ ] `Cookie` — pass to CGI if present

### 4. Body Reading
- [ ] If `Content-Length` is present, read exactly that many bytes
- [ ] If `Transfer-Encoding: chunked`, implement chunked decoding:
  - Read chunk size (hex) + `\r\n`
  - Read chunk data + `\r\n`
  - Repeat until chunk size is `0`
- [ ] Enforce `client_max_body_size` — return `413 Payload Too Large` if exceeded
- [ ] If no body expected (GET, DELETE), ensure no body is required

### 5. Data Structure
- [ ] Create an `HttpRequest` class/struct with:
  - `method` (string)
  - `uri` (string — full URI)
  - `path` (string — decoded path portion)
  - `query` (string — query string portion)
  - `version` (string)
  - `headers` (map)
  - `body` (string/vector)

### 6. Validation
- [ ] Return `400 Bad Request` for malformed requests
- [ ] Return `405 Method Not Allowed` if method not in location's `allow_methods`
- [ ] Return `501 Not Implemented` for unknown methods
- [ ] Return `505 HTTP Version Not Supported` if version != `HTTP/1.1`
- [ ] Return `411 Length Required` if POST with no Content-Length or Transfer-Encoding
