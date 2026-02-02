"""Generic utility functions for BriefDesk."""

import json
import os
import shutil
import tempfile
from datetime import datetime
from urllib.parse import urlparse


def extract_json_array(text):
    """
    Extract a JSON array from text that may contain extra content before/after.
    Uses bracket counting to find the correct array end.
    Returns the parsed array or None if not found.
    """
    # Find first '[' that starts a potential JSON array (skip lines with MCP tool output markers)
    start_idx = -1
    lines = text.split('\n')
    char_count = 0
    
    for line in lines:
        # Skip status lines that might contain brackets
        if any(skip in line for skip in ['MCP tool', 'Connecting to', 'connected', '✓ Output', 'Warning:']):
            char_count += len(line) + 1
            continue
        
        # Look for line starting with '[' (JSON array start)
        stripped = line.strip()
        if stripped.startswith('['):
            start_idx = char_count + line.index('[')
            break
        char_count += len(line) + 1
    
    if start_idx == -1:
        return None
    
    # Now find the matching closing bracket using bracket counting
    bracket_count = 0
    in_string = False
    escape_next = False
    end_idx = start_idx
    
    for i, char in enumerate(text[start_idx:], start=start_idx):
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == '[':
            bracket_count += 1
        elif char == ']':
            bracket_count -= 1
            if bracket_count == 0:
                end_idx = i + 1
                break
    
    if bracket_count != 0:
        return None
    
    json_str = text[start_idx:end_idx]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def copy_db(src):
    """Copy database to temp file to avoid locks. Also copies WAL/SHM for recent data."""
    if not os.path.exists(src):
        return None
    
    # Create temp directory to hold all db files
    tmp_dir = tempfile.mkdtemp()
    
    try:
        base_name = os.path.basename(src)
        tmp_path = os.path.join(tmp_dir, base_name)
        
        # Copy main database
        shutil.copy2(src, tmp_path)
        
        # Copy WAL file if exists (contains recent uncommitted changes)
        wal_src = src + "-wal"
        if os.path.exists(wal_src):
            shutil.copy2(wal_src, tmp_path + "-wal")
        
        # Copy SHM file if exists (shared memory index)
        shm_src = src + "-shm"
        if os.path.exists(shm_src):
            shutil.copy2(shm_src, tmp_path + "-shm")
        
        return tmp_path
    except Exception as e:
        # Clean up on error
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None


def cleanup_db(tmp_path):
    """Remove temporary database directory and all its files."""
    if tmp_path:
        tmp_dir = os.path.dirname(tmp_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def slack_ts_to_iso(ts):
    """Convert Slack timestamp (e.g., '1682441907.012379') to ISO format."""
    if not ts:
        return ''
    try:
        # Slack timestamps are Unix timestamps with microseconds after the dot
        timestamp = float(str(ts).split('.')[0])
        return datetime.fromtimestamp(timestamp).isoformat()
    except (ValueError, TypeError):
        return ''


def is_night_hours():
    """Check if current time is during night hours (10 PM - 6 AM)."""
    hour = datetime.now().hour
    return hour >= 22 or hour < 6


def extract_domain(url):
    """Extract domain from URL, removing www. prefix."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return ''


def score_result(result, query, query_words):
    """Score a search result based on relevance to the query."""
    score = 0
    title = result.get('title', '').lower()
    url = result.get('url', '').lower()
    query_lower = query.lower()
    
    # Exact match in title
    if query_lower in title:
        score += 100
    
    # All words present in title
    if all(word in title for word in query_words):
        score += 50
    
    # Words in URL
    words_in_url = sum(1 for word in query_words if word in url)
    score += words_in_url * 10
    
    # Visit count boost
    visit_count = result.get('visit_count', 0)
    if visit_count:
        score += min(visit_count, 50)  # Cap at 50
    
    # Recency boost (if timestamp available)
    if 'timestamp' in result:
        # More recent = higher score
        try:
            ts = datetime.fromisoformat(result['timestamp'].replace('Z', '+00:00'))
            days_ago = (datetime.now(ts.tzinfo) - ts).days
            if days_ago < 7:
                score += 20
            elif days_ago < 30:
                score += 10
        except Exception:
            pass
    
    return score


def format_time_ago(timestamp):
    """Format a timestamp as a human-readable 'time ago' string."""
    if not timestamp:
        return ''
    
    try:
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            dt = timestamp
        
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        
        seconds = diff.total_seconds()
        if seconds < 60:
            return 'just now'
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f'{minutes}m ago'
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f'{hours}h ago'
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f'{days}d ago'
        else:
            return dt.strftime('%b %d')
    except Exception:
        return ''
