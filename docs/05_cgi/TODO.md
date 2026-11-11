# Part 5: CGI (Common Gateway Interface)

## Overview
Execute CGI scripts (e.g., Python, PHP) and return their output as HTTP responses.

---

## TODO List

### 1. CGI Detection
- [ ] Check if the requested file's extension matches `cgi_extension` in the location config
- [ ] Verify the CGI script file exists and is readable
- [ ] Verify the CGI interpreter (`cgi_path`) exists and is executable

### 2. Environment Variables (CGI Spec)
- [ ] `REQUEST_METHOD` — GET, POST, DELETE
- [ ] `QUERY_STRING` — query string from the URI (after `?`)
- [ ] `CONTENT_TYPE` — from the request's `Content-Type` header
- [ ] `CONTENT_LENGTH` — from the request's `Content-Length` header
- [ ] `SCRIPT_NAME` — the path to the CGI script
- [ ] `SCRIPT_FILENAME` — absolute path to the CGI script
- [ ] `PATH_INFO` — extra path info after the script name
- [ ] `PATH_TRANSLATED` — translated PATH_INFO to filesystem path
- [ ] `SERVER_NAME` — server hostname
- [ ] `SERVER_PORT` — port number
- [ ] `SERVER_PROTOCOL` — `HTTP/1.1`
- [ ] `SERVER_SOFTWARE` — `webserv/1.0`
- [ ] `GATEWAY_INTERFACE` — `CGI/1.1`
- [ ] `REMOTE_ADDR` — client IP address
- [ ] `HTTP_COOKIE` — from the request's `Cookie` header
- [ ] `REDIRECT_STATUS` — set to `200` (needed by php-cgi)

### 3. Process Execution
- [ ] Use `fork()` to create a child process
- [ ] In the child:
  - Set up pipes for stdin and stdout
  - `dup2()` stdin pipe (for POST body)
  - `dup2()` stdout pipe (for CGI output)
  - Set environment variables with `execve()` env array
  - Execute: `execve(cgi_path, args, env)` (e.g., `/usr/bin/python3 script.py`)
  - `chdir()` to the script's directory before exec
- [ ] In the parent:
  - Write the request body to the child's stdin pipe (for POST)
  - Close the write end of stdin pipe
  - Read CGI output from the child's stdout pipe

### 4. Non-Blocking CGI I/O
- [ ] Add CGI pipes (stdin write, stdout read) to the `poll()` set
- [ ] Write POST body to CGI stdin via `poll()` POLLOUT — not all at once
- [ ] Read CGI output via `poll()` POLLIN — not all at once
- [ ] NEVER do blocking read/write on CGI pipes

### 5. CGI Output Parsing
- [ ] CGI outputs headers followed by `\r\n\r\n` then body
- [ ] Parse CGI headers (e.g., `Content-Type`, `Status`, `Location`)
- [ ] If CGI outputs a `Status:` header → use that as the HTTP status code
- [ ] If CGI outputs a `Location:` header → send a redirect response
- [ ] Build the final HTTP response from CGI headers + body

### 6. Timeout & Error Handling
- [ ] Implement a CGI execution timeout (e.g., 10-30 seconds)
- [ ] If timeout → `kill()` the child process, return `504 Gateway Timeout`
- [ ] If CGI crashes → return `502 Bad Gateway`
- [ ] If CGI script not found → return `404 Not Found`
- [ ] If interpreter not found → return `500 Internal Server Error`
- [ ] Use `waitpid()` with `WNOHANG` to avoid blocking — check via poll loop
- [ ] Collect zombie processes (`waitpid`)

### 7. Security
- [ ] Never execute arbitrary files — only configured extensions
- [ ] Validate the script path doesn't escape the root directory
- [ ] Don't pass sensitive server info through env variables
