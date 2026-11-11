# Part 1: Configuration File Parsing

## Overview
Parse an NGINX-like configuration file to configure the web server.

---

## TODO List

### 1. Tokenizer / Lexer
- [x ] Read the config file into a string
- [ ] Split into tokens (words, `{`, `}`, `;`, newlines)
- [ ] Handle comments (lines starting with `#`)
- [ ] Handle quoted strings (preserve spaces inside quotes)
- [ ] Track line numbers for error reporting

### 2. Parser
- [ ] Parse the top-level `server { }` blocks (multiple allowed)
- [ ] Parse `location { }` blocks inside each server block
- [ ] Validate matching braces `{` and `}`
- [ ] Validate each directive ends with `;`
- [ ] Reject unknown directives with clear error messages
- [ ] Handle nested contexts properly (server → location)

### 3. Server Block Directives
- [ ] `listen` — port (and optional host) to bind to
- [ ] `server_name` — virtual host name(s)
- [ ] `root` — default root directory for the server
- [ ] `index` — default index file(s)
- [ ] `error_page` — custom error pages (e.g., `error_page 404 /404.html`)
- [ ] `client_max_body_size` — max allowed request body size
- [ ] `location` — location block (sub-context, not a simple directive)

### 4. Location Block Directives
- [ ] `root` — root directory for this location
- [ ] `index` — index file(s) for this location
- [ ] `autoindex` — enable/disable directory listing (`on` / `off`)
- [ ] `allow_methods` — allowed HTTP methods (GET, POST, DELETE)
- [ ] `cgi_extension` — file extensions to handle as CGI (e.g., `.py`, `.php`)
- [ ] `cgi_path` — path to the CGI interpreter
- [ ] `upload_dir` — directory to store uploaded files
- [ ] `return` — HTTP redirection (e.g., `return 301 /newpath`)

### 5. Data Structures
- [ ] Create a `ServerConfig` struct/class to hold server-level settings
- [ ] Create a `LocationConfig` struct/class to hold location-level settings
- [ ] Store a `std::vector<ServerConfig>` for multiple virtual servers
- [ ] Each `ServerConfig` holds a `std::vector<LocationConfig>`
- [ ] Set sensible defaults for all optional fields

### 6. Validation
- [ ] At least one `server` block must exist
- [ ] Each server must have a `listen` directive
- [ ] Port numbers must be valid (1–65535)
- [ ] `client_max_body_size` must be a valid number (support `m`/`M` suffix for MB)
- [ ] Paths must not be empty
- [ ] `autoindex` must be `on` or `off`
- [ ] `allow_methods` must only contain GET, POST, DELETE
- [ ] No duplicate `listen` + `server_name` combinations
- [ ] Location paths must start with `/`

### 7. Error Handling
- [ ] Print clear error message with line number on parse failure
- [ ] Exit cleanly if config file is invalid
- [ ] Handle missing config file (use a default or error out)
