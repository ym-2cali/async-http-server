# NGINX-like Config File — What to Parse (Reference)

## Overview
Your webserv config file follows a simplified NGINX syntax. Below is the full specification of what you need to parse.

---

## Config File Syntax Rules

| Rule | Example |
|------|---------|
| Comments start with `#` | `# this is a comment` |
| Directives end with `;` | `listen 8080;` |
| Blocks use `{ }` | `server { ... }` |
| Values separated by spaces | `error_page 404 /404.html;` |
| Strings can be quoted | `root "/var/www/my site";` |

---

## Full Config Structure

```nginx
# Top level — only server blocks allowed here

server {
    listen          <port>;                      # REQUIRED
    listen          <host>:<port>;               # Optional form
    server_name     <name1> [name2] [...];       # Virtual host names
    root            <path>;                      # Document root
    index           <file1> [file2] [...];       # Default index files
    error_page      <code> <path>;               # Custom error page
    client_max_body_size <size>;                  # Max body size (bytes or "1m")

    location <path> {
        root            <path>;                  # Override server root
        index           <file1> [file2] [...];   # Override index files
        autoindex       on | off;                # Directory listing
        allow_methods   <METHOD1> [METHOD2] ...; # Allowed HTTP methods
        cgi_extension   <ext1> [ext2] [...];     # CGI file extensions
        cgi_path        <interpreter_path>;      # Path to CGI binary
        upload_dir      <path>;                  # Upload directory
        return          <code> <url>;            # HTTP redirect
    }
}
```

---

## Directive-by-Directive Parsing Guide

### `listen`
```
listen 8080;
listen 127.0.0.1:8080;
listen 0.0.0.0:80;
```
- **Parse**: Extract host (optional, default `0.0.0.0`) and port (required)
- **Validate**: Port is 1–65535, is numeric
- **Store**: `std::string host`, `int port`

---

### `server_name`
```
server_name example.com;
server_name example.com www.example.com;
```
- **Parse**: One or more space-separated names
- **Use**: Match against the `Host` header in incoming requests
- **Store**: `std::vector<std::string>`

---

### `root`
```
root /var/www/html;
root ./www;
```
- **Parse**: A single directory path
- **Validate**: Path is not empty
- **Store**: `std::string`

---

### `index`
```
index index.html;
index index.html index.htm index.php;
```
- **Parse**: One or more filenames
- **Store**: `std::vector<std::string>`
- **Default**: `index.html` if not specified

---

### `error_page`
```
error_page 404 /errors/404.html;
error_page 500 502 503 /errors/50x.html;
```
- **Parse**: One or more status codes followed by a file path
- **Store**: `std::map<int, std::string>` mapping code→path

---

### `client_max_body_size`
```
client_max_body_size 1048576;    # bytes
client_max_body_size 1m;         # 1 megabyte
client_max_body_size 10M;        # 10 megabytes
```
- **Parse**: Number with optional `m`/`M`/`k`/`K` suffix
- **Convert**: Always store as bytes internally
- **Store**: `size_t`
- **Default**: 1MB if not specified

---

### `location`
```
location / { ... }
location /api { ... }
location /upload { ... }
```
- **Parse**: A path prefix followed by a block `{ ... }`
- **Match**: Use longest prefix match when routing requests
- **Store**: `std::vector<LocationConfig>` (ordered)

---

### `autoindex`
```
autoindex on;
autoindex off;
```
- **Parse**: Must be exactly `on` or `off`
- **Store**: `bool`
- **Default**: `off`

---

### `allow_methods`
```
allow_methods GET;
allow_methods GET POST;
allow_methods GET POST DELETE;
```
- **Parse**: One or more of: `GET`, `POST`, `DELETE`
- **Validate**: Reject any other method names
- **Store**: `std::set<std::string>` or bitmask
- **Default**: `GET` only

---

### `cgi_extension`
```
cgi_extension .py;
cgi_extension .py .php;
```
- **Parse**: One or more file extensions (with leading dot)
- **Store**: `std::vector<std::string>`

---

### `cgi_path`
```
cgi_path /usr/bin/python3;
cgi_path /usr/bin/php-cgi;
```
- **Parse**: Path to the CGI interpreter binary
- **Validate**: File exists and is executable
- **Store**: `std::string`

---

### `upload_dir`
```
upload_dir /var/www/uploads;
upload_dir ./uploads;
```
- **Parse**: A directory path for storing uploaded files
- **Store**: `std::string`

---

### `return`
```
return 301 https://example.com;
return 302 /new-location;
```
- **Parse**: A status code (3xx) and a URL/path
- **Store**: `int code`, `std::string url`

---

## Example Config File

```nginx
server {
    listen 8080;
    server_name localhost;
    root ./www;
    index index.html;
    error_page 404 /errors/404.html;
    error_page 500 /errors/500.html;
    client_max_body_size 10m;

    location / {
        allow_methods GET;
        autoindex off;
    }

    location /upload {
        allow_methods GET POST DELETE;
        upload_dir ./www/uploads;
        client_max_body_size 5m;
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

server {
    listen 8081;
    server_name other.localhost;
    root ./www2;
    index index.html;

    location / {
        allow_methods GET POST;
        autoindex on;
    }
}
```

---

## Data Structures Summary

```
ServerConfig:
├── host: string              (default: "0.0.0.0")
├── port: int                 (REQUIRED)
├── server_names: vector<string>
├── root: string              (default: "./www")
├── index: vector<string>     (default: ["index.html"])
├── error_pages: map<int, string>
├── client_max_body_size: size_t  (default: 1MB)
└── locations: vector<LocationConfig>

LocationConfig:
├── path: string              (REQUIRED, e.g., "/")
├── root: string              (inherits from server if empty)
├── index: vector<string>     (inherits from server if empty)
├── autoindex: bool           (default: false)
├── allow_methods: set<string> (default: {"GET"})
├── cgi_extensions: vector<string>
├── cgi_path: string
├── upload_dir: string
├── redirect_code: int        (0 if no redirect)
└── redirect_url: string
```
