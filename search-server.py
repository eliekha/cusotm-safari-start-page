#!/usr/bin/env python3
"""Local search server for Safari history, Dia browser history, and bookmarks."""

import json
import sqlite3
import plistlib
import os
import shutil
import tempfile
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Database paths
SAFARI_HISTORY = os.path.expanduser("~/Library/Safari/History.db")
SAFARI_BOOKMARKS = os.path.expanduser("~/Library/Safari/Bookmarks.plist")
DIA_HISTORY = os.path.expanduser("~/Library/Application Support/Dia/User Data/Default/History")
DIA_BOOKMARKS = os.path.expanduser("~/Library/Application Support/Dia/User Data/Default/Bookmarks")

def copy_db(src):
    """Copy database to temp file to avoid locks. Also copies WAL/SHM for recent data."""
    if not os.path.exists(src):
        return None
    
    # Create temp directory to hold all db files
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, "db.sqlite")
    
    try:
        # Copy main database
        shutil.copy2(src, tmp_path)
        
        # Copy WAL file if exists (contains recent uncommitted writes)
        wal_src = src + "-wal"
        if os.path.exists(wal_src):
            shutil.copy2(wal_src, tmp_path + "-wal")
        
        # Copy SHM file if exists (shared memory)
        shm_src = src + "-shm"
        if os.path.exists(shm_src):
            shutil.copy2(shm_src, tmp_path + "-shm")
        
        # Checkpoint WAL to merge recent writes into main database
        try:
            conn = sqlite3.connect(tmp_path)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except:
            pass  # If checkpoint fails, still try to use the database
        
        return tmp_path
    except:
        # Cleanup on failure
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

def cleanup_db(tmp_path):
    """Clean up temporary database files."""
    if tmp_path:
        tmp_dir = os.path.dirname(tmp_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)

def extract_domain(url):
    """Extract domain from URL for matching."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace('www.', '')
    except:
        return ''

def score_result(result, query, query_words):
    """Score a result based on relevance to query."""
    title = (result.get('title') or '').lower()
    url = (result.get('url') or '').lower()
    domain = extract_domain(url)
    
    score = 0
    
    # Exact title match (highest priority)
    if query == title:
        score += 100
    # Title starts with query
    elif title.startswith(query):
        score += 80
    # Query in title
    elif query in title:
        score += 60
    
    # Domain match (e.g., searching "github" matches github.com)
    if query == domain or query == domain.split('.')[0]:
        score += 90
    elif query in domain:
        score += 50
    
    # All query words present in title
    if query_words:
        words_in_title = sum(1 for w in query_words if w in title)
        score += words_in_title * 15
    
    # URL contains query
    if query in url:
        score += 20
    
    # Bookmarks get a boost
    if result.get('type') == 'bookmark':
        score += 30
    
    # Visit count boost (if available)
    visit_count = result.get('visit_count', 0)
    if visit_count > 0:
        score += min(visit_count, 50)  # Cap at 50 bonus points
    
    return score

class SearchHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/search":
            query = parse_qs(parsed.query).get("q", [""])[0].lower().strip()
            if not query:
                self.send_json([])
                return
            
            # Split query into words for multi-word matching
            query_words = [w for w in query.split() if len(w) > 1]
            
            results = []
            
            # Search all sources
            for search_fn in [
                self.search_dia_bookmarks,
                self.search_safari_bookmarks,
                self.search_dia_history,
                self.search_safari_history
            ]:
                try:
                    results.extend(search_fn(query))
                except:
                    pass
            
            # Dedupe by URL, keeping highest scored version
            seen = {}
            for r in results:
                url = r.get('url', '')
                if url not in seen:
                    seen[url] = r
                elif r.get('type') == 'bookmark':  # Prefer bookmarks
                    seen[url] = r
            
            unique = list(seen.values())
            
            # Score and sort results
            for r in unique:
                r['_score'] = score_result(r, query, query_words)
            
            unique.sort(key=lambda x: -x['_score'])
            
            # Remove internal score before sending
            for r in unique:
                del r['_score']
            
            self.send_json(unique[:10])
            
        elif parsed.path == "/debug":
            info = {
                "safari_history_exists": os.path.exists(SAFARI_HISTORY),
                "safari_bookmarks_exists": os.path.exists(SAFARI_BOOKMARKS),
                "dia_history_exists": os.path.exists(DIA_HISTORY),
                "dia_bookmarks_exists": os.path.exists(DIA_BOOKMARKS),
            }
            for name, path in [("safari_history", SAFARI_HISTORY), ("dia_history", DIA_HISTORY)]:
                try:
                    tmp = copy_db(path)
                    if tmp:
                        info[f"{name}_readable"] = True
                        cleanup_db(tmp)
                    else:
                        info[f"{name}_readable"] = False
                except Exception as e:
                    info[f"{name}_readable"] = str(e)
            self.send_json(info)
        else:
            self.send_error(404)
    
    def search_dia_bookmarks(self, query):
        results = []
        if not os.path.exists(DIA_BOOKMARKS):
            return results
        
        with open(DIA_BOOKMARKS, "r") as f:
            data = json.load(f)
        
        def traverse(node):
            if isinstance(node, dict):
                if node.get("type") == "url":
                    title = node.get("name", "")
                    url = node.get("url", "")
                    title_lower = title.lower()
                    url_lower = url.lower()
                    domain = extract_domain(url)
                    
                    # Match against query, title, URL, or domain
                    if (query in title_lower or 
                        query in url_lower or 
                        query in domain or
                        any(w in title_lower for w in query.split())):
                        results.append({"title": title, "url": url, "type": "bookmark"})
                for v in node.values():
                    traverse(v)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)
        
        traverse(data)
        return results
    
    def search_safari_bookmarks(self, query):
        results = []
        if not os.path.exists(SAFARI_BOOKMARKS):
            return results
        
        with open(SAFARI_BOOKMARKS, "rb") as f:
            plist = plistlib.load(f)
        
        def traverse(node):
            if isinstance(node, dict):
                if node.get("URLString"):
                    title = node.get("URIDictionary", {}).get("title", "") or node.get("Title", "")
                    url = node.get("URLString", "")
                    title_lower = title.lower()
                    url_lower = url.lower()
                    domain = extract_domain(url)
                    
                    if (query in title_lower or 
                        query in url_lower or 
                        query in domain or
                        any(w in title_lower for w in query.split())):
                        results.append({"title": title, "url": url, "type": "bookmark"})
                for v in node.values():
                    traverse(v)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)
        
        traverse(plist)
        return results
    
    def search_dia_history(self, query):
        results = []
        tmp_path = copy_db(DIA_HISTORY)
        if not tmp_path:
            return results
        
        try:
            conn = sqlite3.connect(tmp_path)
            cursor = conn.cursor()
            
            # Split query into words for better matching
            words = [w.strip() for w in query.split() if len(w.strip()) > 1]
            
            if len(words) > 1:
                # Multi-word query: match entries containing ALL words
                where_clauses = []
                params = []
                for word in words:
                    where_clauses.append("(url LIKE ? OR title LIKE ?)")
                    params.extend([f"%{word}%", f"%{word}%"])
                
                where_sql = " AND ".join(where_clauses)
                sql = f"""
                    SELECT url, title, visit_count, last_visit_time
                    FROM urls
                    WHERE {where_sql}
                    AND title != ''
                    AND length(title) > 2
                    ORDER BY visit_count DESC, last_visit_time DESC
                    LIMIT 20
                """
                cursor.execute(sql, params)
            else:
                # Single word query
                query_pattern = f"%{query}%"
                cursor.execute("""
                    SELECT url, title, visit_count, last_visit_time
                    FROM urls
                    WHERE (url LIKE ? OR title LIKE ?)
                    AND title != ''
                    AND length(title) > 2
                    ORDER BY visit_count DESC, last_visit_time DESC
                    LIMIT 20
                """, (query_pattern, query_pattern))
            
            for url, title, visit_count, _ in cursor.fetchall():
                if title and not title.startswith("http"):
                    results.append({
                        "title": title, 
                        "url": url, 
                        "type": "history",
                        "visit_count": visit_count or 0
                    })
            
            conn.close()
        finally:
            cleanup_db(tmp_path)
        
        return results
    
    def search_safari_history(self, query):
        results = []
        tmp_path = copy_db(SAFARI_HISTORY)
        if not tmp_path:
            return results
        
        try:
            conn = sqlite3.connect(tmp_path)
            cursor = conn.cursor()
            
            # Split query into words for better matching
            words = [w.strip() for w in query.split() if len(w.strip()) > 1]
            
            if len(words) > 1:
                # Multi-word query: match entries containing ALL words
                where_clauses = []
                params = []
                for word in words:
                    where_clauses.append("(hi.url LIKE ? OR hv.title LIKE ?)")
                    params.extend([f"%{word}%", f"%{word}%"])
                
                where_sql = " AND ".join(where_clauses)
                sql = f"""
                    SELECT hi.url, hv.title, hi.visit_count, MAX(hv.visit_time) as last_visit
                    FROM history_items hi
                    LEFT JOIN history_visits hv ON hi.id = hv.history_item
                    WHERE {where_sql}
                    AND hv.title IS NOT NULL
                    AND hv.title != ''
                    AND length(hv.title) > 2
                    GROUP BY hi.url
                    ORDER BY hi.visit_count DESC, last_visit DESC
                    LIMIT 20
                """
                cursor.execute(sql, params)
            else:
                # Single word query
                query_pattern = f"%{query}%"
                cursor.execute("""
                    SELECT hi.url, hv.title, hi.visit_count, MAX(hv.visit_time) as last_visit
                    FROM history_items hi
                    LEFT JOIN history_visits hv ON hi.id = hv.history_item
                    WHERE (hi.url LIKE ? OR hv.title LIKE ?)
                    AND hv.title IS NOT NULL
                    AND hv.title != ''
                    AND length(hv.title) > 2
                    GROUP BY hi.url
                    ORDER BY hi.visit_count DESC, last_visit DESC
                    LIMIT 20
                """, (query_pattern, query_pattern))
            
            for url, title, visit_count, _ in cursor.fetchall():
                if title and not title.startswith("http"):
                    results.append({
                        "title": title, 
                        "url": url, 
                        "type": "history",
                        "visit_count": visit_count or 0
                    })
            
            conn.close()
        finally:
            cleanup_db(tmp_path)
        
        return results
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 18765), SearchHandler)
    print("Search server running on http://127.0.0.1:18765")
    server.serve_forever()
