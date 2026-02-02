"""Browser history and bookmarks search for Safari, Chrome, Helium, and Dia."""

import json
import os
import plistlib
import sqlite3

from .config import (
    logger,
    SAFARI_HISTORY,
    SAFARI_BOOKMARKS,
    CHROME_HISTORY,
    CHROME_BOOKMARKS,
    HELIUM_HISTORY,
    HELIUM_BOOKMARKS,
    DIA_HISTORY,
    DIA_BOOKMARKS,
)
from .utils import copy_db, cleanup_db, extract_domain, score_result


# =============================================================================
# Bookmark Search Functions
# =============================================================================

def search_chrome_bookmarks(query):
    """Search Chrome bookmarks for matching entries."""
    results = []
    if not os.path.exists(CHROME_BOOKMARKS):
        return results
    
    try:
        with open(CHROME_BOOKMARKS, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error reading Chrome bookmarks: {e}")
        return results
    
    query_words = query.split()
    
    def traverse(node):
        if isinstance(node, dict):
            if node.get("type") == "url":
                title = node.get("name", "")
                url = node.get("url", "")
                title_lower = title.lower()
                url_lower = url.lower()
                domain = extract_domain(url)
                
                if (query in title_lower or 
                    query in url_lower or 
                    query in domain or
                    any(w in title_lower for w in query_words)):
                    results.append({"title": title, "url": url, "type": "bookmark"})
            for v in node.values():
                traverse(v)
        elif isinstance(node, list):
            for item in node:
                traverse(item)
    
    traverse(data)
    return results


def search_helium_bookmarks(query):
    """Search Helium bookmarks for matching entries."""
    results = []
    if not os.path.exists(HELIUM_BOOKMARKS):
        return results
    
    try:
        with open(HELIUM_BOOKMARKS, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error reading Helium bookmarks: {e}")
        return results
    
    query_words = query.split()
    
    def traverse(node):
        if isinstance(node, dict):
            if node.get("type") == "url":
                title = node.get("name", "")
                url = node.get("url", "")
                title_lower = title.lower()
                url_lower = url.lower()
                domain = extract_domain(url)
                
                if (query in title_lower or 
                    query in url_lower or 
                    query in domain or
                    any(w in title_lower for w in query_words)):
                    results.append({"title": title, "url": url, "type": "bookmark"})
            for v in node.values():
                traverse(v)
        elif isinstance(node, list):
            for item in node:
                traverse(item)
    
    traverse(data)
    return results


def search_dia_bookmarks(query):
    """Search Dia bookmarks for matching entries."""
    results = []
    if not os.path.exists(DIA_BOOKMARKS):
        return results
    
    try:
        with open(DIA_BOOKMARKS, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error reading Dia bookmarks: {e}")
        return results
    
    query_words = query.split()
    
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
                    any(w in title_lower for w in query_words)):
                    results.append({"title": title, "url": url, "type": "bookmark"})
            for v in node.values():
                traverse(v)
        elif isinstance(node, list):
            for item in node:
                traverse(item)
    
    traverse(data)
    return results


def search_safari_bookmarks(query):
    """Search Safari bookmarks (plist format) for matching entries."""
    results = []
    if not os.path.exists(SAFARI_BOOKMARKS):
        return results
    
    try:
        with open(SAFARI_BOOKMARKS, "rb") as f:
            plist = plistlib.load(f)
    except (plistlib.InvalidFileException, IOError) as e:
        logger.error(f"Error reading Safari bookmarks: {e}")
        return results
    
    query_words = query.split()
    
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
                    any(w in title_lower for w in query_words)):
                    results.append({"title": title, "url": url, "type": "bookmark"})
            for v in node.values():
                traverse(v)
        elif isinstance(node, list):
            for item in node:
                traverse(item)
    
    traverse(plist)
    return results


# =============================================================================
# History Search Functions
# =============================================================================

def _search_chromium_history(db_path, query, browser_name="Chrome"):
    """
    Generic Chromium-based history search (Chrome, Helium, Dia).
    These browsers use the same SQLite schema with a 'urls' table.
    """
    results = []
    tmp_path = copy_db(db_path)
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
    except sqlite3.Error as e:
        logger.error(f"Error searching {browser_name} history: {e}")
    finally:
        cleanup_db(tmp_path)
    
    return results


def search_chrome_history(query):
    """Search Chrome browser history."""
    return _search_chromium_history(CHROME_HISTORY, query, "Chrome")


def search_helium_history(query):
    """Search Helium browser history."""
    return _search_chromium_history(HELIUM_HISTORY, query, "Helium")


def search_dia_history(query):
    """Search Dia browser history."""
    return _search_chromium_history(DIA_HISTORY, query, "Dia")


def search_safari_history(query):
    """
    Search Safari browser history.
    Safari uses a different schema with history_items and history_visits tables.
    """
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
    except sqlite3.Error as e:
        logger.error(f"Error searching Safari history: {e}")
    finally:
        cleanup_db(tmp_path)
    
    return results


# =============================================================================
# Combined Search
# =============================================================================

def search_history(query, limit=10):
    """
    Search all browser history and bookmarks.
    
    Args:
        query: Search query string (case-insensitive)
        limit: Maximum number of results to return (default: 10)
    
    Returns:
        List of result dicts with keys: title, url, type, visit_count (for history)
        Results are deduplicated by URL and sorted by relevance score.
    """
    if not query:
        return []
    
    query = query.lower().strip()
    if not query:
        return []
    
    # Split query into words for multi-word matching
    query_words = [w for w in query.split() if len(w) > 1]
    
    results = []
    
    # Search all sources
    search_functions = [
        search_chrome_bookmarks,
        search_helium_bookmarks,
        search_dia_bookmarks,
        search_safari_bookmarks,
        search_chrome_history,
        search_helium_history,
        search_dia_history,
        search_safari_history,
    ]
    
    for search_fn in search_functions:
        try:
            results.extend(search_fn(query))
        except Exception as e:
            logger.warning(f"Error in {search_fn.__name__}: {e}")
    
    # Dedupe by URL, keeping bookmarks over history (bookmarks are more intentional)
    seen = {}
    for r in results:
        url = r.get('url', '')
        if url not in seen:
            seen[url] = r
        elif r.get('type') == 'bookmark':
            # Prefer bookmarks over history
            seen[url] = r
    
    unique = list(seen.values())
    
    # Score and sort results
    for r in unique:
        r['_score'] = score_result(r, query, query_words)
    
    unique.sort(key=lambda x: -x['_score'])
    
    # Remove internal score before returning
    for r in unique:
        del r['_score']
    
    return unique[:limit]


def search_bookmarks(query, limit=10):
    """
    Search only bookmarks (not history).
    
    Args:
        query: Search query string (case-insensitive)
        limit: Maximum number of results to return (default: 10)
    
    Returns:
        List of bookmark result dicts with keys: title, url, type
    """
    if not query:
        return []
    
    query = query.lower().strip()
    if not query:
        return []
    
    query_words = [w for w in query.split() if len(w) > 1]
    
    results = []
    
    search_functions = [
        search_chrome_bookmarks,
        search_helium_bookmarks,
        search_dia_bookmarks,
        search_safari_bookmarks,
    ]
    
    for search_fn in search_functions:
        try:
            results.extend(search_fn(query))
        except Exception as e:
            logger.warning(f"Error in {search_fn.__name__}: {e}")
    
    # Dedupe by URL
    seen = {}
    for r in results:
        url = r.get('url', '')
        if url not in seen:
            seen[url] = r
    
    unique = list(seen.values())
    
    # Score and sort
    for r in unique:
        r['_score'] = score_result(r, query, query_words)
    
    unique.sort(key=lambda x: -x['_score'])
    
    for r in unique:
        del r['_score']
    
    return unique[:limit]


def search_browser_history(query, limit=10):
    """
    Search only browser history (not bookmarks).
    
    Args:
        query: Search query string (case-insensitive)
        limit: Maximum number of results to return (default: 10)
    
    Returns:
        List of history result dicts with keys: title, url, type, visit_count
    """
    if not query:
        return []
    
    query = query.lower().strip()
    if not query:
        return []
    
    query_words = [w for w in query.split() if len(w) > 1]
    
    results = []
    
    search_functions = [
        search_chrome_history,
        search_helium_history,
        search_dia_history,
        search_safari_history,
    ]
    
    for search_fn in search_functions:
        try:
            results.extend(search_fn(query))
        except Exception as e:
            logger.warning(f"Error in {search_fn.__name__}: {e}")
    
    # Dedupe by URL
    seen = {}
    for r in results:
        url = r.get('url', '')
        if url not in seen:
            seen[url] = r
    
    unique = list(seen.values())
    
    # Score and sort
    for r in unique:
        r['_score'] = score_result(r, query, query_words)
    
    unique.sort(key=lambda x: -x['_score'])
    
    for r in unique:
        del r['_score']
    
    return unique[:limit]
