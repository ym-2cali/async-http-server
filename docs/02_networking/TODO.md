# Part 2: Networking & Socket Management

## Overview
Set up TCP sockets, bind to ports, and manage connections using a single `poll()` (or equivalent) event loop.

---

## TODO List

### 1. Socket Creation & Binding
- [ ] Create TCP sockets with `socket(AF_INET, SOCK_STREAM, 0)`
- [ ] Set `SO_REUSEADDR` option on each socket
- [ ] Set sockets to non-blocking mode (`fcntl` with `O_NONBLOCK`)
- [ ] Bind each socket to the host:port from the config (`bind()`)
- [ ] Start listening on each socket (`listen()`)
- [ ] Support multiple ports (one socket per `listen` directive)

### 2. Event Loop (poll / epoll / kqueue / select)
- [ ] Use `poll()` (or `epoll`/`kqueue`/`select`) — only ONE allowed
- [ ] Initialize `pollfd` array with all listening sockets
- [ ] Loop: call `poll()` and iterate over ready file descriptors
- [ ] Distinguish between listening sockets (accept) and client sockets (read/write)
- [ ] Handle `POLLIN` (ready to read) events
- [ ] Handle `POLLOUT` (ready to write) events
- [ ] Handle `POLLERR` / `POLLHUP` (error/hangup) events

### 3. Accepting Connections
- [ ] On `POLLIN` for a listening socket → call `accept()`
- [ ] Set the new client socket to non-blocking
- [ ] Add the new client fd to the `pollfd` array
- [ ] Store client state (reading request / writing response)

### 4. Reading from Clients
- [ ] On `POLLIN` for a client socket → call `recv()` / `read()`
- [ ] Accumulate data in a per-client buffer
- [ ] Detect when the full HTTP request has been received:
  - Headers end at `\r\n\r\n`
  - If `Content-Length` header present, read that many body bytes
  - If `Transfer-Encoding: chunked`, handle chunked reading
- [ ] Pass the complete raw request to the HTTP parser

### 5. Writing to Clients
- [ ] On `POLLOUT` for a client socket → call `send()` / `write()`
- [ ] Handle partial sends (track bytes sent, resume on next POLLOUT)
- [ ] After full response is sent:
  - If `Connection: close` → close the socket
  - If `Connection: keep-alive` → reset client state for next request

### 6. Timeout & Cleanup
- [ ] Implement a client timeout (e.g., 60 seconds of inactivity)
- [ ] Periodically check for idle clients and close them
- [ ] On close: remove fd from `pollfd` array, free client resources
- [ ] Handle `SIGPIPE` (ignore it, handle write errors via return value)

### 7. Virtual Host Routing
- [ ] After parsing the request, read the `Host` header
- [ ] Match the `Host` header + port to the correct `ServerConfig`
- [ ] If no match, use the first/default server for that port

### 8. Constraints
- [ ] The server must NEVER block (all I/O non-blocking)
- [ ] The server must NEVER crash
- [ ] Only one `poll()` (or equivalent) for ALL I/O (sockets + CGI pipes)
- [ ] No `read`/`write` without going through `poll()` first
