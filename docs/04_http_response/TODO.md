# Part 4: HTTP Response Building & Serving

## Overview
Build and send proper HTTP/1.1 responses based on the parsed request.

---

## TODO List

### 1. Response Structure
- [ ] Build the status line: `HTTP/1.1 <status_code> <reason>\r\n`
- [ ] Add response headers after the status line
- [ ] Add `\r\n` separator between headers and body
- [ ] Append the response body (file content, error page, directory listing, etc.)

### 2. Required Response Headers
- [ ] `Content-Type` — set based on file extension (MIME type mapping)
- [ ] `Content-Length` — length of the body in bytes
- [ ] `Connection` — `keep-alive` or `close`
- [ ] `Date` — current date/time in HTTP format
- [ ] `Server` — server name (e.g., `webserv/1.0`)

### 3. MIME Type Mapping
- [ ] `.html` → `text/html`
- [ ] `.css` → `text/css`
- [ ] `.js` → `application/javascript`
- [ ] `.json` → `application/json`
- [ ] `.png` → `image/png`
- [ ] `.jpg` / `.jpeg` → `image/jpeg`
- [ ] `.gif` → `image/gif`
- [ ] `.ico` → `image/x-icon`
- [ ] `.txt` → `text/plain`
- [ ] Default → `application/octet-stream`

### 4. Status Codes to Support
- [ ] `200 OK`
- [ ] `201 Created` (for successful POST/upload)
- [ ] `204 No Content` (for successful DELETE)
- [ ] `301 Moved Permanently` (redirect)
- [ ] `302 Found` (redirect)
- [ ] `400 Bad Request`
- [ ] `403 Forbidden`
- [ ] `404 Not Found`
- [ ] `405 Method Not Allowed`
- [ ] `408 Request Timeout`
- [ ] `413 Payload Too Large`
- [ ] `500 Internal Server Error`
- [ ] `501 Not Implemented`
- [ ] `505 HTTP Version Not Supported`

### 5. GET Request Handling
- [ ] Resolve the URI path to a filesystem path using `root` + URI
- [ ] If path is a directory:
  - Try to serve the `index` file(s) from config
  - If no index and `autoindex on` → generate directory listing page
  - If no index and `autoindex off` → `403 Forbidden`
- [ ] If path is a file → read and serve it with correct MIME type
- [ ] If path doesn't exist → `404 Not Found`

### 6. POST Request Handling
- [ ] Handle file uploads (save body to `upload_dir` from config)
- [ ] If CGI is configured for this extension → forward to CGI handler
- [ ] Return `201 Created` on successful upload
- [ ] Return `413` if body exceeds `client_max_body_size`

### 7. DELETE Request Handling
- [ ] Resolve the URI to a filesystem path
- [ ] If file exists → delete it, return `204 No Content`
- [ ] If file doesn't exist → `404 Not Found`
- [ ] If no permission → `403 Forbidden`

### 8. Redirections
- [ ] If location has a `return` directive → send redirect response
- [ ] Set `Location` header to the redirect target
- [ ] Use the configured status code (301, 302, etc.)

### 9. Error Pages
- [ ] For each error status, generate a default HTML error page
- [ ] If `error_page` is configured, serve the custom error page file
- [ ] Error pages must always be valid HTML
