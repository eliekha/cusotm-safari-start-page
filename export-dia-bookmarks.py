#!/usr/bin/env python3
"""Export Dia browser bookmarks to Safari-compatible HTML format."""

import json
import os
from datetime import datetime

DIA_BOOKMARKS = os.path.expanduser("~/Library/Application Support/Dia/User Data/Default/Bookmarks")
OUTPUT_FILE = os.path.expanduser("~/Desktop/dia-bookmarks.html")

def convert_chrome_time(chrome_time):
    """Convert Chrome timestamp (microseconds since 1601) to Unix timestamp."""
    if not chrome_time or chrome_time == "0":
        return int(datetime.now().timestamp())
    try:
        return int((int(chrome_time) - 11644473600000000) / 1000000)
    except:
        return int(datetime.now().timestamp())

def process_node(node, depth=0):
    """Recursively process bookmarks, returning HTML."""
    html = ""
    indent = "    " * depth
    
    if node.get("type") == "url":
        title = node.get("name", "Untitled")
        url = node.get("url", "")
        add_date = convert_chrome_time(node.get("date_added"))
        html += f'{indent}<DT><A HREF="{url}" ADD_DATE="{add_date}">{title}</A>\n'
    
    elif node.get("type") == "folder":
        name = node.get("name", "Folder")
        if name not in ("bookmark_bar", "other", "synced"):  # Skip root folders' names
            html += f'{indent}<DT><H3>{name}</H3>\n'
            html += f'{indent}<DL><p>\n'
        else:
            html += f'{indent}<DL><p>\n'
        
        for child in node.get("children", []):
            html += process_node(child, depth + 1)
        
        if name not in ("bookmark_bar", "other", "synced"):
            html += f'{indent}</DL><p>\n'
        else:
            html += f'{indent}</DL><p>\n'
    
    return html

def export_bookmarks():
    if not os.path.exists(DIA_BOOKMARKS):
        print(f"❌ Dia bookmarks not found at: {DIA_BOOKMARKS}")
        print("   Make sure Dia browser is installed and has bookmarks.")
        return
    
    with open(DIA_BOOKMARKS, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    roots = data.get("roots", {})
    
    # Build HTML
    html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten.
     DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
"""
    
    # Process bookmark bar
    if "bookmark_bar" in roots:
        html += "    <DT><H3>Bookmarks Bar</H3>\n"
        html += process_node(roots["bookmark_bar"], 1)
    
    # Process other bookmarks
    if "other" in roots:
        html += "    <DT><H3>Other Bookmarks</H3>\n"
        html += process_node(roots["other"], 1)
    
    html += "</DL><p>\n"
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    
    # Count bookmarks
    count = html.count("<A HREF=")
    print(f"✅ Exported {count} bookmarks to: {OUTPUT_FILE}")
    print()
    print("To import into Safari:")
    print("  1. Open Safari")
    print("  2. File → Import From → Bookmarks HTML File...")
    print(f"  3. Select: {OUTPUT_FILE}")

if __name__ == "__main__":
    export_bookmarks()
