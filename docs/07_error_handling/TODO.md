# Part 7: Error Handling & Edge Cases

## Overview
Handle all error scenarios gracefully. The server must never crash.

---

## TODO List

### 1. Default Error Pages
- [ ] Generate a default HTML page for every supported error code
- [ ] Include the status code and reason phrase in the page
- [ ] Keep the default pages simple but valid HTML

### 2. Custom Error Pages
- [ ] Read `error_page` directives from the config
- [ ] Map status codes to custom HTML file paths
- [ ] If the custom error page file exists → serve it
- [ ] If the custom error page file is missing → fall back to default

### 3. Server Resilience
- [ ] The server must NEVER crash (handle all exceptions/errors)
- [ ] Handle `SIGPIPE` — ignore it, check `send()` return value instead
- [ ] Handle `SIGINT` / `SIGTERM` — graceful shutdown (close all sockets)
- [ ] Handle failed `malloc` / `new` — catch `std::bad_alloc`
- [ ] Handle failed system calls (`socket`, `bind`, `listen`, `accept`, `read`, `write`, `fork`, `execve`) — check return values

### 4. Edge Cases
- [ ] Incomplete requests (client disconnects mid-request)
- [ ] Very large headers (set a max header size, e.g., 8KB)
- [ ] Very large URIs (return `414 URI Too Long` if exceeded)
- [ ] Requests with no `Host` header → `400 Bad Request`
- [ ] Empty request body on POST when `Content-Length: 0`
- [ ] Simultaneous connections (test with many clients at once)
- [ ] Slow clients (trickle data byte by byte)
- [ ] Broken pipe (client closes connection before response is sent)

### 5. Resource Management
- [ ] Close all file descriptors properly (no fd leaks)
- [ ] Free all allocated memory (no memory leaks)
- [ ] Clean up zombie CGI processes
- [ ] Limit max number of simultaneous connections (optional but recommended)

### 6. Logging (Optional but Helpful)
- [ ] Log incoming requests (method, URI, status code, response time)
- [ ] Log errors with details (file, line, error message)
- [ ] Support different log levels (DEBUG, INFO, WARN, ERROR)
- [ ] Log to stdout/stderr or to a file
