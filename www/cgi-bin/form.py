#!/usr/bin/env python3
import html
import os
import sys
from urllib.parse import parse_qs

length = int(os.environ.get("CONTENT_LENGTH") or 0)
body = sys.stdin.read(length) if length else ""
fields = parse_qs(body)

print("Content-Type: text/html; charset=utf-8")
print()
print("<h1>Form received</h1><ul>")
for key, values in fields.items():
    for value in values:
        print(f"<li>{html.escape(key)} = {html.escape(value)}</li>")
print(f"</ul><p>{length} bytes read from stdin</p>")
