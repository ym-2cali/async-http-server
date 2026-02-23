# Part 6: Static File Serving & Directory Listing

## Overview
Serve static files from the filesystem and generate directory listings.

---

## TODO List

### 1. Path Resolution
- [ ] Combine `root` (from config) + request URI to get filesystem path
- [ ] Resolve `..` and `.` in the path (canonicalize)
- [ ] **Security**: Ensure resolved path doesn't escape the `root` directory (path traversal prevention)
- [ ] Check if the resolved path is a file or a directory

### 2. Serving Files
- [ ] Open the file in binary mode
- [ ] Read the file content
- [ ] Determine MIME type from the file extension
- [ ] Build and return the HTTP response with file as body
- [ ] Handle large files efficiently (avoid loading entirely into memory if possible)

### 3. Index File Resolution
- [ ] If the path is a directory, try each `index` file from config in order
- [ ] If an index file exists → serve it
- [ ] If no index file found → check `autoindex` setting
- [ ] If path is a directory and doesn't end with `/` → redirect with `301` to `path/`

### 4. Directory Listing (autoindex)
- [ ] If `autoindex on` in the location config:
  - Open the directory with `opendir()` / `readdir()`
  - Generate an HTML page listing all files and subdirectories
  - Each entry is a clickable link (`<a href="...">`)
  - Show file sizes and last modification dates (optional but nice)
- [ ] If `autoindex off` → return `403 Forbidden`

### 5. File Upload (POST)
- [ ] Determine the upload directory from `upload_dir` config
- [ ] Create the upload directory if it doesn't exist
- [ ] Save the request body as a file
- [ ] Handle `multipart/form-data` content type (parse boundaries)
- [ ] Generate a filename (or extract from multipart headers)
- [ ] Return `201 Created` with the file path/info

### 6. File Deletion (DELETE)
- [ ] Resolve the URI to a filesystem path
- [ ] Verify the file exists
- [ ] Verify the server has permission to delete
- [ ] Call `unlink()` or `std::remove()`
- [ ] Return `204 No Content` on success
- [ ] Return appropriate error codes on failure
