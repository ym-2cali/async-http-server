#!/usr/bin/env python3
import html
import os
from urllib.parse import parse_qs

params = parse_qs(os.environ.get("QUERY_STRING", ""))
name = params.get("name", ["world"])[0]

print("Content-Type: text/html; charset=utf-8")
print()
print(f"<h1>Hello, {html.escape(name)}!</h1>")
print(f"<p>method={os.environ['REQUEST_METHOD']} path_info={html.escape(os.environ.get('PATH_INFO', ''))}</p>")
