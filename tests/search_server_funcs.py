"""
Auto-generated test helper module - ALL 70 FUNCTIONS
"""
import json
import os
import re
import sys
import time
import threading
import subprocess
import tempfile
import shutil
import csv
import select
import traceback
import pickle
import glob
import logging
from io import StringIO
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote, quote
from collections import defaultdict
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.error

logger = logging.getLogger('briefdesk')

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    Credentials = None
    InstalledAppFlow = None
    Request = None
    build = None
    HttpError = None

class SearchHandler:
    pass

def save_prep_cache_to_disk(): pass
def save_custom_prompts(): pass

_meeting_prep_cache = {}
_meeting_prep_cache_lock = threading.Lock()
_custom_prompts = {}
_custom_prompts_lock = threading.Lock()
_prefetch_status = {"running": False, "last_run": None, "meetings_processed": 0, "current_meeting": None, "mode": "day", "mode_reason": "weekday daytime", "force_aggressive": False, "day_mode_note": None, "activity_log": []}
_prefetch_status_lock = threading.Lock()
_prefetch_running = False
_prefetch_thread = None
_force_aggressive_prefetch = False
_slack_users_cache = {"users": {}, "timestamp": 0}
_slack_tokens = None
_atlassian_process = None
_atlassian_initialized = False
_atlassian_msg_id = 0
_atlassian_lock = threading.Lock()
_mcp_config_cache = None

PREP_CACHE_TTL = 14400
SUMMARY_CACHE_TTL = 21600
SLACK_USERS_CACHE_TTL = 300
MCP_CONFIG_PATH = os.path.expanduser("~/.cursor/mcp.json")
TOKEN_PATH = "token.json"
CREDENTIALS_PATH = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/drive.readonly"]
CACHE_DIR = os.path.expanduser("~/.briefdesk_cache")
PREP_CACHE_FILE = os.path.join(CACHE_DIR, "meeting_prep_cache.json")
PROMPTS_FILE = os.path.join(CACHE_DIR, "custom_prompts.json")

DEFAULT_PROMPTS = {
    'jira': """Find Jira tickets related to this meeting.

{meeting_context}

Use mcp_atlassian_search with keywords extracted from the meeting title, attendees, or description.
Try multiple searches if needed (individual words, related terms).
Return up to 5 Jira issues (URLs containing /browse/) as JSON: [{{"title":"...","key":"PROJ-123","url":"https://..."}}]
Return [] only if search returns nothing.""",

    'confluence': """Find Confluence pages related to this meeting.

{meeting_context}

Use mcp_atlassian_search with keywords extracted from the meeting title, attendees, or description.
Try multiple searches if needed (individual words, related terms).
Return up to 5 Confluence pages (URLs containing /wiki/) as JSON: [{{"title":"...","url":"https://..."}}]
Return [] only if search returns nothing.""",

    'slack': """Find Slack messages related to this meeting.

{meeting_context}

Use mcp_slack_search_messages with keywords extracted from the meeting title, attendees, or description.

IMPORTANT: The Slack search results include a "permalink" field with the direct URL to each message.
Use that permalink directly - do NOT try to construct the URL yourself.

Return up to 5 messages as JSON array:
[{{"title":"message preview...","channel":"#channel-name","user":"Name","url":"THE_PERMALINK_FROM_SEARCH_RESULT"}}]

Return [] only if nothing found.""",

    'gmail': """Find Gmail emails related to this meeting.

{meeting_context}

Use the gmail_list_emails tool with a query parameter to search. Gmail query syntax examples:
- from:john@example.com
- to:jane@example.com  
- subject:quarterly review
- keyword1 keyword2

Try searches like:
1. Search for meeting-related keywords from the title
2. Search for emails from attendees if their email addresses are known

Return up to 5 relevant emails as JSON array:
[{{"subject":"...","from":"...","date":"...","url":"https://mail.google.com/mail/u/0/#inbox/MESSAGE_ID"}}]

Return [] only if nothing found.""",

    'drive': """Search Google Drive for files related to: {meeting_title}

Execute this EXACT shell command using run_command:
find "{drive_path}" -iname "*{keywords}*" -type f 2>/dev/null | head -5

DO NOT run ls or any other command. Run the find command above.

After getting file paths from find, output ONLY this JSON array format:
[{{"name":"filename.ext","path":"/full/path/to/file"}}]

Return [] if find returns no results.""",

    'summary': """You are preparing a meeting brief. Generate a comprehensive summary for this meeting.

{meeting_context}

## Your Task

Search and READ content from multiple sources to prepare for this meeting:

1. **Jira** - Use mcp_atlassian_search to find related tickets. Read the ticket details.
2. **Confluence** - Use mcp_atlassian_search to find related pages. Read the page content.
3. **Slack** - Use mcp_slack_search_messages to find recent relevant discussions.
4. **Gmail** - Use gmail_list_emails and gmail_read_email to find and read relevant emails.
5. **Google Drive** - If there are relevant files, use read_file to read them (files are in ~/Library/CloudStorage/GoogleDrive-*/My Drive/).

## Output Format

After gathering information, provide a concise meeting prep summary in this format:

```
## Meeting Brief: [Meeting Title]

### Key Context
[2-3 sentences summarizing the main topic/purpose based on what you found]

### Recent Activity
- [Bullet points of relevant recent discussions, decisions, or updates you found]

### Open Items
- [Any pending tasks, open questions, or action items found in Jira/emails/Slack]

### Talking Points
- [Suggested topics to discuss based on your research]
```

If a source returns nothing relevant, skip it. Focus on providing actionable insights.

Return ONLY the formatted summary text, nothing else."""
}

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


# ============================================================================
# Direct Slack API (replaces MCP for panel features)
# ============================================================================

import requests as slack_requests  # Using requests library for better SSL handling

# Slack tokens (loaded from MCP config)
_slack_tokens = None
_slack_users_cache = {"data": None, "timestamp": 0}
SLACK_USERS_CACHE_TTL = 300  # 5 minutes

def get_slack_tokens():
    """Load Slack tokens from MCP config."""
    global _slack_tokens
    if _slack_tokens:
        return _slack_tokens
    
    config = load_mcp_config()
    slack_config = config.get('slack', {})
    env_vars = slack_config.get('env', {})
    
    _slack_tokens = {
        'xoxc': env_vars.get('SLACK_MCP_XOXC_TOKEN', ''),
        'xoxd': env_vars.get('SLACK_MCP_XOXD_TOKEN', '')
    }
    return _slack_tokens

def slack_api_call(method, params=None, post_data=None):
    """Make a direct Slack API call using requests library.
    
    Args:
        method: API method (e.g., 'conversations.list')
        params: Query parameters dict
        post_data: POST body dict (will use POST if provided)
    
    Returns:
        Parsed JSON response or error dict
    """
    tokens = get_slack_tokens()
    if not tokens.get('xoxc'):
        return {'ok': False, 'error': 'No Slack token configured'}
    
    url = f'https://slack.com/api/{method}'
    
    headers = {
        'Authorization': f'Bearer {tokens["xoxc"]}',
        'Content-Type': 'application/json; charset=utf-8',
        'Cookie': f'd={tokens["xoxd"]}'
    }
    
    try:
        if post_data:
            response = slack_requests.post(url, params=params, json=post_data, headers=headers, timeout=30)
        else:
            response = slack_requests.get(url, params=params, headers=headers, timeout=30)
        
        response.raise_for_status()
        return response.json()
    except slack_requests.exceptions.HTTPError as e:
        return {'ok': False, 'error': f'HTTP {e.response.status_code}: {e.response.reason}'}
    except slack_requests.exceptions.RequestException as e:
        return {'ok': False, 'error': f'Request error: {str(e)}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def slack_get_users():
    """Get all workspace users with caching."""
    global _slack_users_cache
    
    now = time.time()
    if _slack_users_cache['data'] and (now - _slack_users_cache['timestamp']) < SLACK_USERS_CACHE_TTL:
        return _slack_users_cache['data']
    
    users_map = {}
    cursor = None
    
    while True:
        params = {'limit': 200}
        if cursor:
            params['cursor'] = cursor
        
        result = slack_api_call('users.list', params)
        
        if not result.get('ok'):
            break
        
        for user in result.get('members', []):
            user_id = user.get('id')
            users_map[user_id] = {
                'id': user_id,
                'name': user.get('real_name') or user.get('name', ''),
                'username': user.get('name', ''),
                'display_name': user.get('profile', {}).get('display_name', ''),
                'avatar': user.get('profile', {}).get('image_48', '')
            }
        
        # Check for pagination
        cursor = result.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break
    
    _slack_users_cache = {'data': users_map, 'timestamp': now}
    return users_map

def slack_get_unread_counts():
    """Get unread counts using client.counts API (internal Slack API).
    
    Returns dict with:
        - ims: list of {id, has_unreads, mention_count}
        - channels: list of {id, has_unreads, mention_count}
        - mpims: list of group DMs
        - threads: {has_unreads, mention_count}
    """
    result = slack_api_call('client.counts', post_data={})
    
    if not result.get('ok'):
        return {'ims': [], 'channels': [], 'mpims': [], 'threads': {}}
    
    return {
        'ims': result.get('ims', []),
        'channels': result.get('channels', []),
        'mpims': result.get('mpims', []),
        'threads': result.get('threads', {})
    }

def slack_ts_to_iso(ts):
    """Convert Slack timestamp to ISO format."""
    if not ts:
        return ''
    try:
        # Slack ts is Unix timestamp with microseconds (e.g., 1769780915.474229)
        ts_float = float(ts)
        dt = datetime.fromtimestamp(ts_float)
        return dt.isoformat()
    except (ValueError, TypeError):
        return ''

def slack_get_conversations_fast(limit=20, unread_only=False):
    """Get conversations sorted by date descending.
    
    Args:
        limit: Max items to return (default 20)
        unread_only: If True, only return items with unreads
    
    Returns:
        List of conversations sorted by date descending
    """
    conversations = []
    users = slack_get_users()  # Cached
    seen_ids = set()
    
    # Get unread info from client.counts
    counts_data = slack_get_unread_counts()
    
    # Build lookups for ALL items (to get timestamps)
    all_ims = {im['id']: im for im in counts_data.get('ims', [])}
    all_mpims = {m['id']: m for m in counts_data.get('mpims', [])}
    all_channels = {ch['id']: ch for ch in counts_data.get('channels', [])}
    
    # 1. Add Threads
    threads = counts_data.get('threads', {})
    thread_unreads = threads.get('mention_count', 0) or (1 if threads.get('has_unreads') else 0)
    thread_ts = threads.get('latest', '')
    
    # Only add threads if it has unreads OR we're in recent mode
    if thread_unreads > 0 or not unread_only:
        if thread_unreads > 0 or thread_ts:  # Has activity
            conversations.append({
                'channel_id': 'threads',
                'name': 'Threads',
                'username': '',
                'type': 'thread',
                'unread_count': thread_unreads,
                'is_member': True,
                'latest_ts': slack_ts_to_iso(thread_ts) if thread_ts else '',
                'latest_message': f'{thread_unreads} unread replies' if thread_unreads > 0 else '',
                'icon': 'thread'
            })
            seen_ids.add('threads')
    
    # 2. Get DMs with unreads (these might not be in conversations.list)
    unread_dm_ids = [id for id, info in all_ims.items() 
                    if info.get('has_unreads') or info.get('mention_count', 0) > 0]
    unread_dm_ids += [id for id, info in all_mpims.items() 
                     if info.get('has_unreads') or info.get('mention_count', 0) > 0]
    
    for dm_id in unread_dm_ids[:20]:
        if dm_id in seen_ids:
            continue
        
        info = slack_api_call('conversations.info', {'channel': dm_id})
        if not info.get('ok'):
            continue
        
        ch = info.get('channel', {})
        seen_ids.add(dm_id)
        
        # Get unread info
        unread_info = all_ims.get(dm_id) or all_mpims.get(dm_id) or {}
        unread = unread_info.get('mention_count', 0) or (1 if unread_info.get('has_unreads') else 0)
        latest_ts = unread_info.get('latest', '')
        
        if not latest_ts:
            updated = ch.get('updated', 0)
            if updated:
                latest_ts = str(updated / 1000 if updated > 1e12 else updated)
        
        # Determine type and name
        if ch.get('is_im'):
            user_id = ch.get('user', '')
            user_info = users.get(user_id, {})
            name = user_info.get('real_name') or user_info.get('name') or user_id
            conv_type = 'dm'
        elif ch.get('is_mpim'):
            name = ch.get('name', '').replace('mpdm-', '').replace('-1', '')
            conv_type = 'group_dm'
        else:
            continue
        
        conversations.append({
            'channel_id': dm_id,
            'name': name,
            'username': users.get(ch.get('user', ''), {}).get('name', '') if ch.get('is_im') else '',
            'type': conv_type,
            'unread_count': unread,
            'is_member': True,
            'latest_ts': slack_ts_to_iso(latest_ts) if latest_ts else '',
            'latest_message': '',
            'icon': 'dm' if conv_type == 'dm' else 'group'
        })
    
    # 3. Get recent DMs from conversations.list (for recent activity without unreads)
    if not unread_only:
        for conv_type_str in ['im', 'mpim']:
            result = slack_api_call('conversations.list', {
                'types': conv_type_str,
                'limit': 30,
                'exclude_archived': 'true'
            })
            if not result.get('ok'):
                continue
            
            for conv in result.get('channels', []):
                conv_id = conv.get('id', '')
                if conv_id in seen_ids:
                    continue
                seen_ids.add(conv_id)
                
                # Get unread info
                unread_info = all_ims.get(conv_id) or all_mpims.get(conv_id) or {}
                unread = unread_info.get('mention_count', 0) or (1 if unread_info.get('has_unreads') else 0)
                
                # Get timestamp
                latest_ts = unread_info.get('latest', '')
                if not latest_ts:
                    updated = conv.get('updated', 0)
                    if updated:
                        latest_ts = str(updated / 1000 if updated > 1e12 else updated)
                
                # Determine name
                if conv.get('is_im'):
                    user_id = conv.get('user', '')
                    user_info = users.get(user_id, {})
                    name = user_info.get('real_name') or user_info.get('name') or user_id
                    ctype = 'dm'
                else:
                    name = conv.get('name', '').replace('mpdm-', '').replace('-1', '')
                    ctype = 'group_dm'
                
                conversations.append({
                    'channel_id': conv_id,
                    'name': name,
                    'username': users.get(conv.get('user', ''), {}).get('name', '') if conv.get('is_im') else '',
                    'type': ctype,
                    'unread_count': unread,
                    'is_member': True,
                    'latest_ts': slack_ts_to_iso(latest_ts) if latest_ts else '',
                    'latest_message': '',
                    'icon': 'dm' if ctype == 'dm' else 'group'
                })
    
    # 4. Get channels
    if unread_only:
        # Only channels with unreads
        unread_channel_ids = [id for id, info in all_channels.items() 
                             if info.get('has_unreads') or info.get('mention_count', 0) > 0]
        
        for ch_id in unread_channel_ids[:15]:
            if ch_id in seen_ids:
                continue
            
            info = slack_api_call('conversations.info', {'channel': ch_id})
            if not info.get('ok'):
                continue
            
            ch = info.get('channel', {})
            seen_ids.add(ch_id)
            
            ch_info = all_channels.get(ch_id, {})
            unread = ch_info.get('mention_count', 0) or (1 if ch_info.get('has_unreads') else 0)
            latest_ts = ch_info.get('latest', '')
            
            conversations.append({
                'channel_id': ch_id,
                'name': f"#{ch.get('name', ch_id)}",
                'username': '',
                'type': 'channel',
                'unread_count': unread,
                'is_member': ch.get('is_member', True),
                'latest_ts': slack_ts_to_iso(latest_ts) if latest_ts else '',
                'latest_message': '',
                'icon': 'channel'
            })
    else:
        # Recent channels
        result = slack_api_call('conversations.list', {
            'types': 'public_channel,private_channel',
            'limit': 30,
            'exclude_archived': 'true'
        })
        if result.get('ok'):
            for conv in result.get('channels', []):
                conv_id = conv.get('id', '')
                if conv_id in seen_ids:
                    continue
                seen_ids.add(conv_id)
                
                ch_info = all_channels.get(conv_id, {})
                unread = ch_info.get('mention_count', 0) or (1 if ch_info.get('has_unreads') else 0)
                
                latest_ts = ch_info.get('latest', '')
                if not latest_ts:
                    updated = conv.get('updated', 0)
                    if updated:
                        latest_ts = str(updated / 1000 if updated > 1e12 else updated)
                
                conversations.append({
                    'channel_id': conv_id,
                    'name': f"#{conv.get('name', '')}",
                    'username': '',
                    'type': 'channel',
                    'unread_count': unread,
                    'is_member': conv.get('is_member', True),
                    'latest_ts': slack_ts_to_iso(latest_ts) if latest_ts else '',
                    'latest_message': '',
                    'icon': 'channel'
                })
    
    # 5. Sort ALL by timestamp descending (most recent first)
    # But keep Threads at top if it has unreads
    def sort_key(item):
        # Threads with unreads always first (sort key starts with 'Z' which is > 'A' for reverse=True)
        if item.get('channel_id') == 'threads' and item.get('unread_count', 0) > 0:
            return 'Z_9999-99-99'  # Will sort first with reverse=True
        # Everything else by timestamp descending  
        return 'A_' + (item.get('latest_ts', '') or '0000-00-00')
    
    conversations.sort(key=sort_key, reverse=True)
    
    return conversations[:limit]



# Keep old function name for compatibility

def slack_get_conversations_with_unread(types='im,mpim', limit=50):
    """Wrapper for backwards compatibility."""
    return slack_get_conversations_fast(limit=limit, unread_only=False)

def slack_get_conversation_history_direct(channel_id, limit=30):
    """Get message history using direct API.
    
    Args:
        channel_id: Slack channel/DM ID (starts with C, D, or G)
        limit: Max messages to fetch
    
    Returns:
        List of messages with user info
    """
    users = slack_get_users()
    
    result = slack_api_call('conversations.history', {
        'channel': channel_id,
        'limit': limit
    })
    
    if not result.get('ok'):
        error = result.get('error', 'Failed to fetch history')
        # Handle channel_not_found for @username style IDs
        if error == 'channel_not_found' and channel_id.startswith('@'):
            return {'status': 'error', 'message': f'Cannot find channel for {channel_id}. Try opening from Slack first.'}
        return {'status': 'error', 'message': error}
    
    messages = []
    my_user_id = None
    
    # Try to get current user ID
    auth_result = slack_api_call('auth.test')
    if auth_result.get('ok'):
        my_user_id = auth_result.get('user_id')
    
    for msg in result.get('messages', []):
        user_id = msg.get('user', '')
        user_info = users.get(user_id, {})
        
        is_me = user_id == my_user_id if my_user_id else False
        
        messages.append({
            'text': msg.get('text', ''),
            'user': user_info.get('name') or user_info.get('username') or user_id,
            'user_id': user_id,
            'timestamp': slack_ts_to_iso(msg.get('ts', '')),
            'ts': msg.get('ts', ''),
            'is_me': is_me,
            'thread_ts': msg.get('thread_ts'),
            'reply_count': msg.get('reply_count', 0)
        })
    
    # Reverse to show oldest first (API returns newest first)
    messages.reverse()
    
    return messages

def slack_get_threads(limit=20):
    """Get subscribed thread replies.
    
    Returns:
        List of thread items with replies
    """
    users = slack_get_users()
    
    # Get subscribed threads 
    result = slack_api_call('subscriptions.thread.getView', post_data={
        'limit': limit,
        'current_index': 0
    })
    
    threads = []
    items = result.get('threads', [])
    
    for item in items[:limit]:
        # Get root message - contains channel, thread_ts, text, user, etc.
        root = item.get('root_msg', {})
        
        # Extract channel_id and thread_ts from root_msg
        channel_id = root.get('channel', '')
        thread_ts = root.get('thread_ts') or root.get('ts', '')
        
        # Get unread replies
        unread_replies = item.get('unread_replies', [])
        latest_reply = unread_replies[-1] if unread_replies else {}  # Last reply is most recent
        
        root_user_id = root.get('user', '')
        root_user = users.get(root_user_id, {})
        reply_user_id = latest_reply.get('user', '')
        reply_user = users.get(reply_user_id, {})
        
        # Extract text
        root_text = root.get('text', '')
        
        threads.append({
            'channel_id': channel_id,
            'thread_ts': thread_ts,
            'root_text': root_text[:100] if root_text else '',
            'root_user': root_user.get('name') or root_user.get('username') or root_user_id,
            'reply_count': root.get('reply_count', 0),
            'unread_count': len(unread_replies),
            'latest_reply_text': latest_reply.get('text', '')[:100] if latest_reply else '',
            'latest_reply_user': reply_user.get('name') or reply_user.get('username') or reply_user_id,
            'latest_reply_ts': latest_reply.get('ts', '')
        })
    
    return threads

def slack_get_thread_replies(channel_id, thread_ts, limit=50):
    """Get replies to a thread.
    
    Args:
        channel_id: Channel containing the thread
        thread_ts: Thread timestamp (parent message ts)
        limit: Max replies to fetch
    
    Returns:
        List of messages in the thread
    """
    users = slack_get_users()
    
    result = slack_api_call('conversations.replies', {
        'channel': channel_id,
        'ts': thread_ts,
        'limit': limit
    })
    
    if not result.get('ok'):
        return {'status': 'error', 'message': result.get('error', 'Failed to fetch thread')}
    
    messages = []
    
    # Get current user ID
    auth_result = slack_api_call('auth.test')
    my_user_id = auth_result.get('user_id') if auth_result.get('ok') else None
    
    for msg in result.get('messages', []):
        user_id = msg.get('user', '')
        user_info = users.get(user_id, {})
        
        is_me = user_id == my_user_id if my_user_id else False
        is_root = msg.get('ts') == thread_ts
        
        messages.append({
            'text': msg.get('text', ''),
            'user': user_info.get('name') or user_info.get('username') or user_id,
            'user_id': user_id,
            'timestamp': slack_ts_to_iso(msg.get('ts', '')),
            'ts': msg.get('ts', ''),
            'is_me': is_me,
            'is_root': is_root,
            'reply_count': msg.get('reply_count', 0)
        })
    
    return messages

def slack_send_message_direct(channel_id, text, thread_ts=None):
    """Send a message using direct API.
    
    Args:
        channel_id: Slack channel/DM ID
        text: Message text
        thread_ts: Optional thread timestamp for replies
    
    Returns:
        API response
    """
    post_data = {
        'channel': channel_id,
        'text': text
    }
    
    if thread_ts:
        post_data['thread_ts'] = thread_ts
    
    result = slack_api_call('chat.postMessage', post_data=post_data)
    
    if not result.get('ok'):
        return {'success': False, 'error': result.get('error', 'Failed to send message')}
    
    return {
        'success': True,
        'ts': result.get('ts'),
        'channel': result.get('channel')
    }

def slack_get_dm_channel_for_user(user_id):
    """Open/get DM channel for a user.
    
    Args:
        user_id: Slack user ID
    
    Returns:
        Channel ID or error
    """
    result = slack_api_call('conversations.open', post_data={'users': user_id})
    
    if not result.get('ok'):
        return {'error': result.get('error', 'Failed to open DM')}
    
    return {'channel_id': result.get('channel', {}).get('id')}

def slack_find_user_by_username(username):
    """Find a user by their username.
    
    Args:
        username: Username (without @)
    
    Returns:
        User info dict or None
    """
    users = slack_get_users()
    username_lower = username.lower().lstrip('@')
    
    for user_id, user_info in users.items():
        if user_info.get('username', '').lower() == username_lower:
            return user_info
    
    return None

def slack_mark_conversation_read(channel_id, ts):
    """Mark a conversation as read up to a timestamp.
    
    Args:
        channel_id: Slack channel ID
        ts: Timestamp to mark as read
    
    Returns:
        API response
    """
    result = slack_api_call('conversations.mark', post_data={
        'channel': channel_id,
        'ts': ts
    })
    
    return {'success': result.get('ok', False)}


# ============================================================================
# MCP Integration Functions (kept for AI-powered searches)
# ============================================================================

# Global persistent Atlassian MCP process
_atlassian_process = None
_atlassian_lock = threading.Lock()
_atlassian_msg_id = 0
_atlassian_initialized = False

def load_mcp_config():
    """Load MCP server configuration."""
    try:
        if os.path.exists(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, 'r') as f:
                return json.load(f).get('mcpServers', {})
    except:
        pass
    return {}

def get_atlassian_process():
    """Get or create persistent Atlassian MCP process."""
    global _atlassian_process, _atlassian_initialized, _atlassian_msg_id
    
    with _atlassian_lock:
        # Check if process is still running
        if _atlassian_process and _atlassian_process.poll() is None:
            return _atlassian_process
        
        # Start new process
        config = load_mcp_config()
        server_config = config.get('atlassian')
        if not server_config:
            return None
        
        command = server_config.get('command')
        args = server_config.get('args', [])
        
        if not command:
            return None
        
        try:
            env = os.environ.copy()
            env['PATH'] = '/usr/local/bin:/usr/bin:/bin:' + env.get('PATH', '')
            
            _atlassian_process = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0
            )
            
            _atlassian_initialized = False
            _atlassian_msg_id = 0
            
            # Wait a moment for the process to start
            time.sleep(2)
            
            # Initialize MCP session
            _atlassian_msg_id += 1
            init_request = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": _atlassian_msg_id,
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "safari-start-page", "version": "1.0.0"}
                }
            }
            
            _atlassian_process.stdin.write((json.dumps(init_request) + '\n').encode())
            _atlassian_process.stdin.flush()
            
            # Read initialization response (may take a moment for OAuth)
            response_line = _atlassian_process.stdout.readline().decode().strip()
            if response_line:
                try:
                    response = json.loads(response_line)
                    if 'result' in response:
                        _atlassian_initialized = True
                        # Send initialized notification
                        _atlassian_process.stdin.write((json.dumps({
                            "jsonrpc": "2.0", 
                            "method": "notifications/initialized"
                        }) + '\n').encode())
                        _atlassian_process.stdin.flush()
                except json.JSONDecodeError:
                    pass
            
            return _atlassian_process
            
        except Exception as e:
            print(f"Failed to start Atlassian MCP: {e}")
            return None

def call_atlassian_tool(tool_name, arguments, timeout=15):
    """Call an Atlassian MCP tool using the persistent process."""
    global _atlassian_msg_id
    
    proc = get_atlassian_process()
    if not proc or proc.poll() is not None:
        return {"error": "Atlassian MCP not available"}
    
    if not _atlassian_initialized:
        return {"error": "Atlassian MCP not initialized"}
    
    with _atlassian_lock:
        try:
            _atlassian_msg_id += 1
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": _atlassian_msg_id,
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            proc.stdin.write((json.dumps(request) + '\n').encode())
            proc.stdin.flush()
            
            # Read response with timeout
            ready, _, _ = select.select([proc.stdout], [], [], timeout)
            if ready:
                response_line = proc.stdout.readline().decode().strip()
                if response_line:
                    response = json.loads(response_line)
                    if 'error' in response:
                        return {"error": response['error']}
                    return response.get('result', {})
            
            return {"error": "Atlassian MCP timeout"}
            
        except Exception as e:
            return {"error": f"Atlassian MCP error: {e}"}

def call_mcp_tool(server_name, tool_name, arguments):
    """Call an MCP tool via subprocess and return the result."""
    config = load_mcp_config()
    server_config = config.get(server_name)
    if not server_config:
        return {"error": f"MCP server '{server_name}' not configured"}
    
    command = server_config.get('command')
    args = server_config.get('args', [])
    env_vars = server_config.get('env', {})
    
    if not command:
        return {"error": f"No command specified for MCP server '{server_name}'"}
    
    # Build the MCP request
    mcp_request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": 1,
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    
    try:
        # Set up environment
        env = os.environ.copy()
        env.update(env_vars)
        # Ensure PATH includes node
        if 'PATH' not in env_vars:
            env['PATH'] = '/usr/local/bin:/usr/bin:/bin:' + env.get('PATH', '')
        
        # Use shell pipe approach which works better with stdio MCP servers
        full_cmd = f'echo {repr(json.dumps(mcp_request))} | {command} {" ".join(args)}'
        
        proc = subprocess.Popen(
            full_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        
        stdout, stderr = proc.communicate(timeout=30)
        
        # Parse response - may have multiple JSON objects, get the last valid one with result/error
        response_text = stdout.decode().strip()
        result = None
        
        for line in response_text.split('\n'):
            line = line.strip()
            if line and line.startswith('{'):
                try:
                    parsed = json.loads(line)
                    if 'result' in parsed or 'error' in parsed:
                        result = parsed
                except json.JSONDecodeError:
                    continue
        
        if result:
            if 'error' in result:
                return {"error": result['error']}
            return result.get('result', {})
        
        # If no result found, return raw stdout for debugging
        return {"error": f"No valid MCP response. stdout={response_text[:200]}"}
        
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"error": "MCP call timed out"}
    except Exception as e:
        return {"error": str(e)}

def parse_slack_csv(csv_text):
    """Parse Slack's CSV-formatted response into a list of dicts."""
    if not csv_text:
        return []
    
    lines = csv_text.strip().split('\n')
    if len(lines) < 2:
        return []
    
    # Parse header
    headers = lines[0].split(',')
    results = []
    
    for line in lines[1:]:
        if not line.strip():
            continue
        # Simple CSV parsing (doesn't handle all edge cases but works for most)
        values = []
        current = ''
        in_quotes = False
        for char in line:
            if char == '"' and not in_quotes:
                in_quotes = True
            elif char == '"' and in_quotes:
                in_quotes = False
            elif char == ',' and not in_quotes:
                values.append(current.strip().strip('"'))
                current = ''
            else:
                current += char
        values.append(current.strip().strip('"'))
        
        if len(values) >= len(headers):
            item = {}
            for i, h in enumerate(headers):
                item[h.lower()] = values[i] if i < len(values) else ''
            results.append(item)
    
    return results

def extract_mcp_content(result):
    """Extract text content from MCP tool result."""
    if not result:
        return None
    
    # Check for content array (standard MCP format)
    if 'content' in result and isinstance(result['content'], list):
        for item in result['content']:
            if isinstance(item, dict) and item.get('type') == 'text':
                return item.get('text', '')
    
    # Fallback - return as is
    return result


# Load config from file or environment variables

def load_config():
    config = {"slack_workspace": "your-workspace", "atlassian_domain": "your-domain.atlassian.net"}
    config_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json'),
        os.path.expanduser('~/.config/briefdesk/config.json')
    ]
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    config.update(json.load(f))
                break
            except: pass
    # Environment variables override config file
    config['slack_workspace'] = os.environ.get("SLACK_WORKSPACE", config.get('slack_workspace', 'your-workspace'))
    config['atlassian_domain'] = os.environ.get("ATLASSIAN_DOMAIN", config.get('atlassian_domain', 'your-domain.atlassian.net'))
    return config

_config = load_config()
SLACK_WORKSPACE = _config['slack_workspace']
ATLASSIAN_DOMAIN = _config['atlassian_domain']

def format_slack_channel(channel, sender_name=''):
    """Format Slack channel name, resolving DMs to show user names."""
    if not channel:
        return ''
    
    # Remove leading # if present
    ch = channel.lstrip('#')
    
    # DM channels start with D or are user IDs (U...)
    if ch.startswith('D') or ch.startswith('U'):
        # It's a DM - show as "DM with [name]" or just "DM"
        if sender_name and sender_name != ch:
            return f"DM with {sender_name}"
        return "DM"
    
    # MPDM (multi-person DM) channels
    if ch.startswith('mpdm-') or 'mpdm' in ch.lower():
        return "Group DM"
    
    # Regular channel - keep the # prefix
    return f"#{ch}"

def build_slack_url(channel_id, msg_id):
    """Build a Slack URL to a specific message."""
    if not channel_id or not msg_id:
        return None
    
    # Remove # prefix from channel
    ch = channel_id.lstrip('#')
    # Remove dot from message ID (1769817144.201689 -> p1769817144201689)
    msg_ts = msg_id.replace('.', '')
    
    return f"https://{SLACK_WORKSPACE}.slack.com/archives/{ch}/p{msg_ts}"

def format_slack_message(m):
    """Format a Slack message dict with all needed fields."""
    realname = m.get('realname', '')
    username = m.get('username', '')
    sender = realname or username
    channel_raw = m.get('channel', '').lstrip('#')
    channel_display = format_slack_channel(m.get('channel', ''), sender)
    msg_id = m.get('msgid', '')
    thread_ts = m.get('threadts', '')
    
    return {
        'title': m.get('text', '')[:100], 
        'channel': channel_display,
        'channel_id': channel_raw,
        'msg_id': msg_id,
        'thread_ts': thread_ts,
        'time': m.get('time', ''), 
        'from': sender,
        'username': username,  # Added for @username lookups
        'slack_url': build_slack_url(channel_raw, msg_id)
    }

def get_slack_mentions(limit=20, unread_only=False, show_conversations=True):
    """Get Slack conversations - fast version.
    
    Args:
        limit: Max number of items to return
        unread_only: If True, only return items with unread messages
        show_conversations: If True, return conversation objects (always True now)
    
    Returns:
        List of items with proper typing (dm, group_dm, channel, thread)
    """
    # Use the fast function that minimizes API calls
    conversations = slack_get_conversations_fast(limit=limit, unread_only=unread_only)
    
    if isinstance(conversations, dict) and 'error' in conversations:
        return conversations
    
    # Convert to the expected format
    result = []
    for conv in conversations:
        result.append({
            'type': 'conversation',
            'name': conv.get('name', ''),
            'username': conv.get('username', ''),
            'channel_id': conv.get('channel_id', ''),
            'latest_message': conv.get('latest_message', ''),
            'time': conv.get('latest_ts', ''),  # ISO format
            'unread_count': conv.get('unread_count', 0),
            'conv_type': conv.get('type', 'dm'),
            'icon': conv.get('icon', 'dm')
        })
    
    return result

def search_slack_for_context(query, limit=5):
    """Search Slack for messages related to a query."""
    result = call_mcp_tool('slack', 'conversations_search_messages', {
        'search_query': query,
        'limit': limit
    })
    
    if isinstance(result, dict) and 'error' not in result:
        content = extract_mcp_content(result)
        if content:
            messages = parse_slack_csv(content)
            return [format_slack_message(m) for m in messages]
    
    return result if isinstance(result, list) else []

def send_slack_reply(channel_id, thread_ts, message):
    """Send a reply to a Slack message."""
    args = {
        'channel_id': channel_id,
        'payload': message,
        'content_type': 'text/plain'
    }
    
    # If there's a thread_ts, reply in thread
    if thread_ts:
        args['thread_ts'] = thread_ts
    
    result = call_mcp_tool('slack', 'conversations_add_message', args)
    return result

def get_slack_conversations(limit=20):
    """Get list of DMs and group DMs with unread counts using direct API."""
    return slack_get_conversations_with_unread(types='im,mpim', limit=limit)

def get_conversation_history(channel_id, limit='20'):
    """Get message history using direct API.
    
    Handles both channel IDs (D..., C...) and @username format.
    """
    limit_int = int(limit) if isinstance(limit, str) else limit
    
    # If it's a @username, find the DM channel first
    if channel_id.startswith('@'):
        username = channel_id[1:]
        user_info = slack_find_user_by_username(username)
        
        if not user_info:
            return {'status': 'error', 'message': f'User @{username} not found'}
        
        # Open/get the DM channel
        dm_result = slack_get_dm_channel_for_user(user_info['id'])
        if 'error' in dm_result:
            return {'status': 'error', 'message': dm_result['error']}
        
        channel_id = dm_result['channel_id']
    
    # Now fetch history with the actual channel ID
    result = slack_get_conversation_history_direct(channel_id, limit=limit_int)
    
    # Direct API returns list or error dict
    if isinstance(result, dict) and 'status' in result:
        return result  # Error response
    
    return result  # List of messages

def send_slack_message(channel_id, message, thread_ts=None):
    """Send a message using direct API.
    
    Handles both channel IDs and @username format.
    """
    # If it's a @username, find the DM channel first
    if channel_id.startswith('@'):
        username = channel_id[1:]
        user_info = slack_find_user_by_username(username)
        
        if not user_info:
            return {'success': False, 'error': f'User @{username} not found'}
        
        # Open/get the DM channel
        dm_result = slack_get_dm_channel_for_user(user_info['id'])
        if 'error' in dm_result:
            return {'success': False, 'error': dm_result['error']}
        
        channel_id = dm_result['channel_id']
    
    return slack_send_message_direct(channel_id, message, thread_ts)

def search_atlassian(query, limit=5):
    """Search both Jira and Confluence using Rovo unified search."""
    result = call_atlassian_tool('search', {'query': query})
    
    if isinstance(result, dict) and 'error' not in result:
        jira_items = []
        confluence_items = []
        
        content = result.get('content', [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    text = item.get('text', '')
                    # The response may be JSON-formatted
                    try:
                        data = json.loads(text)
                        results = data.get('results', [])
                        for r in results[:limit*2]:
                            ari = r.get('id', '')
                            title = r.get('title', '')
                            url = r.get('url', '')
                            
                            # Determine if Jira or Confluence based on ARI
                            if ':jira:' in ari or ':issue/' in ari:
                                # Extract issue key from title or generate from ARI
                                key_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', title)
                                key = key_match.group(1) if key_match else ''
                                jira_items.append({
                                    'title': title[:150],
                                    'key': key,
                                    'url': url or (f'https://{ATLASSIAN_DOMAIN}/browse/{key}' if key else ''),
                                    'ari': ari
                                })
                            elif ':confluence:' in ari or ':page/' in ari:
                                confluence_items.append({
                                    'title': title[:150],
                                    'space': r.get('space', {}).get('name', ''),
                                    'url': url or '',
                                    'ari': ari
                                })
                    except json.JSONDecodeError:
                        # Fallback to line-based parsing
                        lines = text.strip().split('\n')
                        for line in lines[:limit*2]:
                            line = line.strip()
                            if not line:
                                continue
                            key_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', line)
                            if key_match:
                                key = key_match.group(1)
                                jira_items.append({
                                    'title': line[:150],
                                    'key': key,
                                    'url': f'https://{ATLASSIAN_DOMAIN}/browse/{key}'
                                })
        
        return {
            'jira': jira_items[:limit],
            'confluence': confluence_items[:limit]
        }
    
    return {'jira': [], 'confluence': [], 'error': result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'}

def get_jira_context(query, limit=5):
    """Search Jira for issues related to a query."""
    result = search_atlassian(query, limit)
    if isinstance(result, dict):
        return result.get('jira', [])
    return []

def search_confluence(query, limit=5):
    """Search Confluence for pages related to a query."""
    result = search_atlassian(query, limit)
    if isinstance(result, dict):
        return result.get('confluence', [])
    return []

def list_atlassian_tools():
    """List available Atlassian MCP tools - useful for debugging."""
    global _atlassian_msg_id
    
    proc = get_atlassian_process()
    if not proc or proc.poll() is not None:
        return {"error": "Atlassian MCP not available"}
    
    with _atlassian_lock:
        try:
            _atlassian_msg_id += 1
            request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": _atlassian_msg_id,
                "params": {}
            }
            
            proc.stdin.write((json.dumps(request) + '\n').encode())
            proc.stdin.flush()
            
            ready, _, _ = select.select([proc.stdout], [], [], 10)
            if ready:
                response_line = proc.stdout.readline().decode().strip()
                if response_line:
                    response = json.loads(response_line)
                    return response.get('result', {})
            
            return {"error": "Timeout listing tools"}
        except Exception as e:
            return {"error": str(e)}

def search_google_drive(query, max_results=5):
    """Search local Google Drive folders for files matching query."""
    results = []
    query_lower = query.lower()
    # Filter out short common words that match too many files
    query_words = [w for w in query_lower.split() if len(w) > 3]
    
    if not query_words:
        logger.warning(f"[Drive] No valid search words in query: {query}")
        return results
    
    # Dynamically find Google Drive paths (in case they changed since startup)
    drive_paths = [
        *[p for p in glob.glob(os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*/My Drive"))],
        *[p for p in glob.glob(os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*/Shared drives"))]
    ]
    
    logger.debug(f"[Drive] Searching for '{query_words}' in {len(drive_paths)} paths")
    
    for drive_path in drive_paths:
        if not os.path.exists(drive_path):
            continue
        
        try:
            logger.debug(f"[Drive] Searching path: {drive_path}")
            file_count = 0
            # Search for files with matching names
            for root, dirs, files in os.walk(drive_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for file in files:
                    if file.startswith('.'):
                        continue
                    
                    file_count += 1
                    file_lower = file.lower()
                    # Check if any query word is in filename
                    if any(word in file_lower for word in query_words):
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, drive_path)
                        
                        # Get file info
                        try:
                            stat = os.stat(full_path)
                            modified = datetime.fromtimestamp(stat.st_mtime)
                        except:
                            modified = None
                        
                        results.append({
                            'name': file,
                            'path': rel_path,
                            'full_path': full_path,
                            'modified': modified.isoformat() if modified else None,
                            'drive': 'My Drive' if 'My Drive' in drive_path else 'Shared drives'
                        })
                        
                        logger.debug(f"[Drive] Found match: {file}")
                        
                        if len(results) >= max_results:
                            logger.info(f"[Drive] Found {len(results)} results after checking {file_count} files")
                            return results
            
            logger.debug(f"[Drive] Checked {file_count} files in {drive_path}")
        except Exception as e:
            logger.error(f"[Drive] Error searching {drive_path}: {e}")
            continue
    
    logger.info(f"[Drive] Search complete: {len(results)} results for query '{query_words}'")
    return results

def extract_meeting_keywords(event):
    """Extract search keywords from a calendar event."""
    keywords = []
    
    title = event.get('title', '')
    description = event.get('description', '')
    attendees = event.get('attendees', [])
    
    # Add title words (skip common meeting words)
    skip_words = {'meeting', 'call', 'sync', 'weekly', 'daily', 'standup', 'stand-up', 
                  '1:1', '1-1', 'one', 'on', 'with', 'and', 'the', 'for', 'to', 'a', 'an'}
    title_words = [w.strip().lower() for w in re.split(r'[\s\-/:|]+', title) if len(w) > 2]
    keywords.extend([w for w in title_words if w not in skip_words])
    
    # Extract project names, ticket IDs from description
    if description:
        # Look for Jira-style ticket IDs
        tickets = re.findall(r'\b([A-Z]+-\d+)\b', description)
        keywords.extend(tickets)
        
        # Look for URLs with project names
        urls = re.findall(r'https?://[^\s<>"]+', description)
        for url in urls:
            if 'jira' in url or 'confluence' in url:
                # Extract project key from Jira/Confluence URLs
                match = re.search(r'/([A-Z]+-\d+)', url)
                if match:
                    keywords.append(match.group(1))
    
    # Add attendee names (for Slack search)
    for attendee in attendees:
        name = attendee.get('name', '')
        if name and '@' not in name:
            keywords.append(name.split()[0])  # First name only
    
    return list(set(keywords))

def call_cli_for_source(source, meeting_title, attendees_str, description='', timeout=60, max_retries=2):
    """Call the CLI to search a specific source for meeting context.
    
    Includes retry logic for reliability.
    """
    # Use direct devsai binary (faster than npx which checks/downloads every time)
    devsai_path = os.path.expanduser('~/.local/share/devsai/devsai.sh')
    if not os.path.exists(devsai_path):
        # Fallback to npx if local copy doesn't exist
        devsai_path = shutil.which('devsai') or os.path.expanduser('~/.nvm/versions/node/v20.18.0/bin/devsai')
    
    # Build meeting context for the AI
    meeting_context = f"Meeting: {meeting_title}"
    if attendees_str:
        meeting_context += f"\nAttendees: {attendees_str}"
    if description:
        meeting_context += f"\nDescription: {description[:300]}"
    
    # Get prompt template (custom or default)
    prompt_template = get_prompt(source)
    if not prompt_template:
        return []
    
    # Handle drive-specific variables
    if source == 'drive':
        drive_paths = glob.glob(os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*"))
        main_paths = [p for p in drive_paths if '(' not in p]
        drive_path_str = main_paths[0] if main_paths else (drive_paths[0] if drive_paths else None)
        if not drive_path_str:
            return []
        title_words = [w for w in meeting_title.replace('-', ' ').replace(':', ' ').split() if len(w) > 3]
        keywords = title_words[0] if title_words else 'meeting'
        prompt = prompt_template.format(
            meeting_context=meeting_context,
            meeting_title=meeting_title,
            drive_path=drive_path_str,
            keywords=keywords
        )
    else:
        # Standard variable substitution
        prompt = prompt_template.format(
            meeting_context=meeting_context,
            meeting_title=meeting_title,
            drive_path='',
            keywords=''
        )
    
    last_error = None
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.info(f"[CLI] Retry {attempt + 1}/{max_retries} for {source}")
            logger.info(f"[CLI] Starting {source} call for meeting: {meeting_title[:50]}")
            
            env = os.environ.copy()
            # Add common Node.js paths
            nvm_path = os.path.expanduser('~/.nvm/versions/node/v20.18.0/bin')
            env['PATH'] = nvm_path + ':' + env.get('PATH', '')
            # Prevent interactive OAuth prompts
            env['CI'] = 'true'
            env['BROWSER'] = 'false'
            
            # Run from project dir to use local .devsai.json config
            project_dir = os.path.expanduser('~/.local/share/briefdesk')
            
            logger.debug(f"[CLI] devsai_path: {devsai_path}, cwd: {project_dir}")
            
            proc = subprocess.Popen(
                [devsai_path, '-p', prompt, '--max-iterations', '3', '-m', 'anthropic-claude-4-5-haiku'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=project_dir
            )
            
            stdout, stderr = proc.communicate(timeout=timeout)
            # devsai outputs to stderr, combine both for parsing
            output = (stdout.decode() + stderr.decode()).strip()
            
            logger.debug(f"[CLI] {source} output length: {len(output)}")
            logger.debug(f"[CLI] {source} output preview: {output[:300] if output else '(empty)'}")
            
            # Try to extract JSON array from output
            result = extract_json_array(output)
            if result is not None:
                logger.info(f"[CLI] {source} returned {len(result)} items")
                return result
            
            # If no JSON found but no error, return empty (don't retry for empty results)
            if output and 'error' not in output.lower():
                logger.info(f"[CLI] {source} returned empty (no JSON array found)")
                return []
            
            last_error = "No JSON array found in output"
            
        except subprocess.TimeoutExpired:
            proc.kill()
            last_error = f'timeout after {timeout}s'
            logger.error(f"[CLI] {source} {last_error} (attempt {attempt + 1}/{max_retries})")
        except Exception as e:
            last_error = str(e)
            logger.error(f"[CLI] {source} exception: {e} (attempt {attempt + 1}/{max_retries})")
    
    # All retries failed
    logger.error(f"[CLI] {source} failed after {max_retries} attempts: {last_error}")
    return {'error': f'{source} search failed: {last_error}'}

def call_cli_for_meeting_summary(meeting_title, attendees_str, attendee_emails, description='', timeout=90):
    """Call the CLI to generate a comprehensive meeting prep summary.
    
    This searches all sources, READS the actual content, and generates a summary.
    """
    # Use direct devsai binary (faster than npx)
    devsai_path = os.path.expanduser('~/.local/share/devsai/devsai.sh')
    if not os.path.exists(devsai_path):
        devsai_path = shutil.which('devsai') or os.path.expanduser('~/.nvm/versions/node/v20.18.0/bin/devsai')
    
    # Build meeting context
    meeting_context = f"Meeting: {meeting_title}"
    if attendees_str:
        meeting_context += f"\nAttendees: {attendees_str}"
    if attendee_emails:
        meeting_context += f"\nAttendee emails: {', '.join(attendee_emails[:5])}"
    if description:
        meeting_context += f"\nDescription: {description[:500]}"
    
    # Get prompt template (custom or default)
    prompt_template = get_prompt('summary')
    prompt = prompt_template.format(
        meeting_context=meeting_context,
        meeting_title=meeting_title,
        drive_path='',
        keywords=''
    )
    
    try:
        env = os.environ.copy()
        # Add common Node.js paths
        nvm_path = os.path.expanduser('~/.nvm/versions/node/v20.18.0/bin')
        env['PATH'] = nvm_path + ':' + env.get('PATH', '')
        # Prevent interactive OAuth prompts
        env['CI'] = 'true'
        env['BROWSER'] = 'false'
        
        project_dir = os.path.dirname(os.path.abspath(__file__))
        
        proc = subprocess.Popen(
            [devsai_path, '-p', prompt, '--max-iterations', '8', '-m', 'anthropic-claude-4-5-haiku'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=project_dir
        )
        
        stdout, stderr = proc.communicate(timeout=timeout)
        # devsai outputs to stderr, combine both
        output = (stdout.decode() + stderr.decode()).strip()
        
        # Strip ANSI color codes from CLI output
        output = re.sub(r'\x1b\[[0-9;]*m', '', output)
        
        # Filter out CLI progress/status messages
        filtered_lines = []
        skip_patterns = [
            'Connecting to MCP',
            'MCP server(s) connected',
            '[mcp_',
            '✓ Output delivered',
            'Output delivered',
            '✓ MCP',
            'Loading MCP',
            'Starting MCP',
        ]
        for line in output.split('\n'):
            line_stripped = line.strip()
            if not any(pattern in line_stripped for pattern in skip_patterns):
                filtered_lines.append(line)
        output = '\n'.join(filtered_lines).strip()
        
        # Return the summary text
        if output:
            return {'summary': output, 'status': 'success'}
        else:
            return {'summary': '', 'status': 'empty', 'stderr': stderr.decode()[:500] if stderr else ''}
            
    except subprocess.TimeoutExpired:
        proc.kill()
        return {'summary': '', 'status': 'timeout'}
    except Exception as e:
        return {'summary': '', 'status': 'error', 'error': str(e)}

def get_meeting_info():
    """Get the next upcoming meeting info (for prep endpoints)."""
    try:
        # Import here to avoid issues if calendar not set up
        handler = SearchHandler(None, None, None)
        calendar_data = handler.get_upcoming_events_google(minutes_ahead=180, limit=1)
        events = calendar_data.get('events', [])
        
        if not events:
            return None
        
        event = events[0]
        attendees = event.get('attendees', [])
        attendee_names = [a.get('name', a.get('email', '')) for a in attendees if a.get('name') or a.get('email')]
        
        return {
            'event': event,
            'title': event.get('title', ''),
            'attendees_str': ', '.join(attendee_names[:5]) if attendee_names else '',
            'description': event.get('description', '')[:200] if event.get('description') else ''
        }
    except:
        return None


# Multi-meeting cache for prep endpoints
# Structure: { meeting_id: { 'jira': {...}, 'confluence': {...}, ... } }
_meeting_prep_cache = {}
_meeting_prep_cache_lock = threading.Lock()
PREP_CACHE_TTL = 14400  # 4 hours for individual source data (prefetch keeps it fresh)
SUMMARY_CACHE_TTL = 21600  # 6 hours for summaries (expensive to generate)
PREFETCH_INTERVAL = 600  # 10 minutes between prefetch cycles (must be < TTL)
PREP_CACHE_FILE = os.path.expanduser('~/.local/share/briefdesk/prep_cache.json')
PROMPTS_FILE = os.path.expanduser('~/.local/share/briefdesk/prompts.json')

# Default prompts for each source - users can override these
# Available variables: {meeting_context}, {meeting_title}, {drive_path}, {keywords}
DEFAULT_PROMPTS = {
    'jira': """Find Jira tickets related to this meeting.

{meeting_context}

Use mcp_atlassian_search with keywords extracted from the meeting title, attendees, or description.
Try multiple searches if needed (individual words, related terms).
Return up to 5 Jira issues (URLs containing /browse/) as JSON: [{{"title":"...","key":"PROJ-123","url":"https://..."}}]
Return [] only if search returns nothing.""",

    'confluence': """Find Confluence pages related to this meeting.

{meeting_context}

Use mcp_atlassian_search with keywords extracted from the meeting title, attendees, or description.
Try multiple searches if needed (individual words, related terms).
Return up to 5 Confluence pages (URLs containing /wiki/) as JSON: [{{"title":"...","url":"https://..."}}]
Return [] only if search returns nothing.""",

    'slack': """Find Slack messages related to this meeting.

{meeting_context}

Use mcp_slack_search_messages with keywords extracted from the meeting title, attendees, or description.

IMPORTANT: The Slack search results include a "permalink" field with the direct URL to each message.
Use that permalink directly - do NOT try to construct the URL yourself.

Return up to 5 messages as JSON array:
[{{"title":"message preview...","channel":"#channel-name","user":"Name","url":"THE_PERMALINK_FROM_SEARCH_RESULT"}}]

Return [] only if nothing found.""",

    'gmail': """Find Gmail emails related to this meeting.

{meeting_context}

Use the gmail_list_emails tool with a query parameter to search. Gmail query syntax examples:
- from:john@example.com
- to:jane@example.com  
- subject:quarterly review
- keyword1 keyword2

Try searches like:
1. Search for meeting-related keywords from the title
2. Search for emails from attendees if their email addresses are known

Return up to 5 relevant emails as JSON array:
[{{"subject":"...","from":"...","date":"...","url":"https://mail.google.com/mail/u/0/#inbox/MESSAGE_ID"}}]

Return [] only if nothing found.""",

    'drive': """Search Google Drive for files related to: {meeting_title}

Execute this EXACT shell command using run_command:
find "{drive_path}" -iname "*{keywords}*" -type f 2>/dev/null | head -5

DO NOT run ls or any other command. Run the find command above.

After getting file paths from find, output ONLY this JSON array format:
[{{"name":"filename.ext","path":"/full/path/to/file"}}]

Return [] if find returns no results.""",

    'summary': """You are preparing a meeting brief. Generate a comprehensive summary for this meeting.

{meeting_context}

## Your Task

Search and READ content from multiple sources to prepare for this meeting:

1. **Jira** - Use mcp_atlassian_search to find related tickets. Read the ticket details.
2. **Confluence** - Use mcp_atlassian_search to find related pages. Read the page content.
3. **Slack** - Use mcp_slack_search_messages to find recent relevant discussions.
4. **Gmail** - Use gmail_list_emails and gmail_read_email to find and read relevant emails.
5. **Google Drive** - If there are relevant files, use read_file to read them (files are in ~/Library/CloudStorage/GoogleDrive-*/My Drive/).

## Output Format

After gathering information, provide a concise meeting prep summary in this format:

```
## Meeting Brief: [Meeting Title]

### Key Context
[2-3 sentences summarizing the main topic/purpose based on what you found]

### Recent Activity
- [Bullet points of relevant recent discussions, decisions, or updates you found]

### Open Items
- [Any pending tasks, open questions, or action items found in Jira/emails/Slack]

### Talking Points
- [Suggested topics to discuss based on your research]
```

If a source returns nothing relevant, skip it. Focus on providing actionable insights.

Return ONLY the formatted summary text, nothing else."""
}

# Custom prompts storage
_custom_prompts = {}
_custom_prompts_lock = threading.Lock()

def load_custom_prompts():
    """Load custom prompts from disk."""
    global _custom_prompts
    try:
        if os.path.exists(PROMPTS_FILE):
            with open(PROMPTS_FILE, 'r') as f:
                _custom_prompts = json.load(f)
            print(f"[Prompts] Loaded {len(_custom_prompts)} custom prompts", flush=True)
    except Exception as e:
        print(f"[Prompts] Error loading: {e}", flush=True)
        _custom_prompts = {}

def save_custom_prompts():
    """Save custom prompts to disk."""
    try:
        os.makedirs(os.path.dirname(PROMPTS_FILE), exist_ok=True)
        with _custom_prompts_lock:
            with open(PROMPTS_FILE, 'w') as f:
                json.dump(_custom_prompts, f, indent=2)
        print(f"[Prompts] Saved {len(_custom_prompts)} custom prompts", flush=True)
    except Exception as e:
        print(f"[Prompts] Error saving: {e}", flush=True)

def get_prompt(source):
    """Get prompt for a source, using custom if available, else default."""
    with _custom_prompts_lock:
        if source in _custom_prompts and _custom_prompts[source]:
            return _custom_prompts[source]
    return DEFAULT_PROMPTS.get(source, '')

def set_custom_prompt(source, prompt):
    """Set a custom prompt for a source. Pass empty string to reset to default."""
    global _custom_prompts
    with _custom_prompts_lock:
        if prompt and prompt.strip():
            _custom_prompts[source] = prompt.strip()
        elif source in _custom_prompts:
            del _custom_prompts[source]
    save_custom_prompts()

def get_all_prompts():
    """Get all prompts with their current values and whether they're customized."""
    result = {}
    with _custom_prompts_lock:
        for source in DEFAULT_PROMPTS:
            is_custom = source in _custom_prompts and _custom_prompts[source]
            result[source] = {
                'current': _custom_prompts.get(source) if is_custom else DEFAULT_PROMPTS[source],
                'default': DEFAULT_PROMPTS[source],
                'is_custom': is_custom
            }
    return result

def save_prep_cache_to_disk():
    """Save the prep cache to disk for persistence across restarts."""
    try:
        with _meeting_prep_cache_lock:
            cache_copy = dict(_meeting_prep_cache)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(PREP_CACHE_FILE), exist_ok=True)
        
        # Write atomically using temp file
        temp_file = PREP_CACHE_FILE + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump(cache_copy, f)
        os.replace(temp_file, PREP_CACHE_FILE)
        
    except Exception as e:
        logger.error(f"[Cache] Failed to save prep cache to disk: {e}")

def load_prep_cache_from_disk():
    """Load the prep cache from disk on startup."""
    global _meeting_prep_cache
    try:
        if os.path.exists(PREP_CACHE_FILE):
            with open(PREP_CACHE_FILE, 'r') as f:
                loaded = json.load(f)
            
            # Validate and load into memory
            with _meeting_prep_cache_lock:
                _meeting_prep_cache = loaded
            
            # Count valid (non-expired) entries
            import time
            now = time.time()
            valid_meetings = 0
            valid_sources = 0
            for meeting_id, sources in loaded.items():
                has_valid = False
                for source, data in sources.items():
                    if isinstance(data, dict) and 'timestamp' in data:
                        ttl = SUMMARY_CACHE_TTL if source == 'summary' else PREP_CACHE_TTL
                        if now - data['timestamp'] < ttl:
                            valid_sources += 1
                            has_valid = True
                if has_valid:
                    valid_meetings += 1
            
            print(f"[Cache] Loaded prep cache from disk: {valid_meetings} meetings, {valid_sources} valid sources", flush=True)
            return True
    except json.JSONDecodeError as e:
        logger.error(f"[Cache] Corrupted cache file, starting fresh: {e}")
    except Exception as e:
        logger.error(f"[Cache] Failed to load prep cache from disk: {e}")
    return False

# Prefetch activity status tracking
_prefetch_status = {
    'running': False,
    'current_meeting': None,
    'current_source': None,
    'last_cycle_start': None,
    'meetings_in_queue': 0,
    'meetings_processed': 0,
    'activity_log': []  # List of recent activities (max 50)
}
_prefetch_status_lock = threading.Lock()
MAX_ACTIVITY_LOG = 50

def add_prefetch_activity(activity_type, message, meeting=None, source=None, status='info', items=None):
    """Add an activity entry to the prefetch status log."""
    import time
    with _prefetch_status_lock:
        entry = {
            'timestamp': time.time(),
            'type': activity_type,
            'message': message,
            'meeting': meeting[:40] if meeting else None,
            'source': source,
            'status': status,  # info, success, error, warning
            'items': items
        }
        _prefetch_status['activity_log'].insert(0, entry)
        # Keep only last N entries
        _prefetch_status['activity_log'] = _prefetch_status['activity_log'][:MAX_ACTIVITY_LOG]

def update_prefetch_status(**kwargs):
    """Update prefetch status fields."""
    with _prefetch_status_lock:
        _prefetch_status.update(kwargs)

def get_prefetch_status():
    """Get current prefetch status."""
    with _prefetch_status_lock:
        return dict(_prefetch_status)

# Legacy cache (for backward compatibility during transition)
_prep_cache = {
    'jira': {'data': None, 'meeting_id': None, 'timestamp': 0},
    'confluence': {'data': None, 'meeting_id': None, 'timestamp': 0},
    'drive': {'data': None, 'meeting_id': None, 'timestamp': 0},
    'slack': {'data': None, 'meeting_id': None, 'timestamp': 0},
    'gmail': {'data': None, 'meeting_id': None, 'timestamp': 0},
    'summary': {'data': None, 'meeting_id': None, 'timestamp': 0}
}

def get_meeting_cache(meeting_id):
    """Get or create cache entry for a meeting."""
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            _meeting_prep_cache[meeting_id] = {
                'jira': {'data': None, 'timestamp': 0},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        return _meeting_prep_cache[meeting_id]

def set_meeting_cache(meeting_id, source, data):
    """Set cache data for a specific meeting and source."""
    import time
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            _meeting_prep_cache[meeting_id] = {
                'jira': {'data': None, 'timestamp': 0},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        _meeting_prep_cache[meeting_id][source] = {
            'data': data,
            'timestamp': time.time()
        }
    # Persist to disk (outside lock to avoid blocking)
    save_prep_cache_to_disk()

def is_cache_valid(meeting_id, source):
    """Check if cache for a meeting/source is still valid (for prefetch decisions)."""
    import time
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            return False
        cache = _meeting_prep_cache[meeting_id].get(source, {})
        if cache.get('data') is None:
            return False
        ttl = SUMMARY_CACHE_TTL if source == 'summary' else PREP_CACHE_TTL
        return (time.time() - cache.get('timestamp', 0)) < ttl

def has_cached_data(meeting_id, source):
    """Check if any cached data exists (ignoring TTL)."""
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            return False
        cache = _meeting_prep_cache[meeting_id].get(source, {})
        return cache.get('data') is not None

def get_cached_data(meeting_id, source):
    """Get cached data for a meeting/source (ignoring TTL - always return if exists)."""
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            return None
        cache = _meeting_prep_cache[meeting_id].get(source, {})
        return cache.get('data')

def get_meeting_by_id(event_id):
    """Fetch a specific calendar event by ID from Google Calendar."""
    if not GOOGLE_API_AVAILABLE:
        return None
    
    if not os.path.exists(TOKEN_PATH):
        return None
    
    try:
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
        
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)
        
        service = build('calendar', 'v3', credentials=creds)
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        
        if not event:
            return None
        
        # Format attendees
        attendees = []
        for a in event.get('attendees', []):
            attendees.append({
                'name': a.get('displayName', ''),
                'email': a.get('email', ''),
                'self': a.get('self', False)
            })
        
        return {
            'id': event.get('id'),
            'title': event.get('summary', 'No title'),
            'start': event.get('start', {}).get('dateTime', event.get('start', {}).get('date', '')),
            'end': event.get('end', {}).get('dateTime', event.get('end', {}).get('date', '')),
            'description': event.get('description', ''),
            'location': event.get('location', ''),
            'attendees': attendees,
            'htmlLink': event.get('htmlLink', '')
        }
    except Exception as e:
        logger.error(f"[Calendar] Error fetching event {event_id}: {e}")
        return None

def cleanup_old_caches():
    """Remove cache entries for meetings more than 3 hours old."""
    import time
    with _meeting_prep_cache_lock:
        cutoff = time.time() - (3 * 60 * 60)  # 3 hours
        to_remove = []
        for meeting_id, cache in _meeting_prep_cache.items():
            # Check the oldest timestamp
            timestamps = [v.get('timestamp', 0) for k, v in cache.items() if isinstance(v, dict) and 'timestamp' in v]
            if timestamps and max(timestamps) < cutoff:
                to_remove.append(meeting_id)
        for meeting_id in to_remove:
            del _meeting_prep_cache[meeting_id]
        if to_remove:
            logger.debug(f"[Cache] Cleaned up {len(to_remove)} old meeting caches")


# Background pre-caching system
_prefetch_thread = None
_prefetch_running = False

def check_services_auth():
    """Check which services are authenticated (for prefetch to avoid triggering OAuth)."""
    auth_status = {
        'atlassian': False,
        'slack': False,
        'gmail': False
    }
    
    # Check Atlassian auth by looking for mcp-remote tokens
    mcp_auth_path = os.path.expanduser('~/.mcp-auth')
    if os.path.exists(mcp_auth_path):
        # Look in mcp-remote subdirectories for tokens.json files
        for subdir in os.listdir(mcp_auth_path):
            subdir_path = os.path.join(mcp_auth_path, subdir)
            if os.path.isdir(subdir_path):
                for f in os.listdir(subdir_path):
                    if f.endswith('_tokens.json'):
                        token_path = os.path.join(subdir_path, f)
                        try:
                            with open(token_path, 'r') as tf:
                                token_data = json.load(tf)
                                # Check if token is valid (has access_token and not expired)
                                if token_data.get('access_token'):
                                    auth_status['atlassian'] = True
                                    break
                        except:
                            pass
            if auth_status['atlassian']:
                break
    
    # Check Slack auth by looking for token in local .devsai.json config
    local_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.devsai.json')
    try:
        if os.path.exists(local_config_path):
            with open(local_config_path, 'r') as f:
                local_config = json.load(f).get('mcpServers', {})
                slack_config = local_config.get('slack', {})
                env = slack_config.get('env', {})
                if env.get('SLACK_MCP_XOXC_TOKEN') or env.get('SLACK_BOT_TOKEN') or env.get('SLACK_TOKEN'):
                    auth_status['slack'] = True
    except:
        pass
    
    # Also check global config
    if not auth_status['slack']:
        config = load_mcp_config()
        if config and 'slack' in config:
            slack_config = config['slack']
            env = slack_config.get('env', {})
            if env.get('SLACK_MCP_XOXC_TOKEN') or env.get('SLACK_BOT_TOKEN') or env.get('SLACK_TOKEN'):
                auth_status['slack'] = True
    
    # Check Gmail auth - look for both credentials and tokens
    gmail_dir = os.path.expanduser('~/.gmail-mcp')
    if os.path.exists(gmail_dir):
        # Check for gcp-oauth.keys.json (OAuth client) and credentials.json (user tokens)
        has_creds = os.path.exists(os.path.join(gmail_dir, 'gcp-oauth.keys.json'))
        has_tokens = os.path.exists(os.path.join(gmail_dir, 'credentials.json'))
        if has_creds and has_tokens:
            auth_status['gmail'] = True
    
    return auth_status

def prefetch_meeting_data(meeting):
    """Pre-fetch all data for a single meeting."""
    import time
    meeting_id = meeting.get('id') or meeting.get('title')
    title = meeting.get('title', '')
    
    logger.info(f"[Prefetch] Starting prefetch for: {title[:50]}... (meeting_id={meeting_id})")
    
    attendees = meeting.get('attendees', [])
    attendee_emails = [a.get('email', '') for a in attendees if a.get('email')]
    attendee_names = [a.get('name', a.get('email', '')) for a in attendees]
    attendees_str = ', '.join(attendee_names[:5])
    description = meeting.get('description', '')[:200] if meeting.get('description') else ''
    
    # Store meeting info (do this first, before any fetches)
    get_meeting_cache(meeting_id)  # Ensure cache entry exists
    with _meeting_prep_cache_lock:
        _meeting_prep_cache[meeting_id]['meeting_info'] = {
            'title': title,
            'attendees_str': attendees_str,
            'attendee_emails': attendee_emails,
            'description': description
        }
    
    # Check auth status to avoid triggering OAuth dialogs from background
    auth_status = check_services_auth()
    logger.info(f"[Prefetch] Auth status: atlassian={auth_status.get('atlassian')}, slack={auth_status.get('slack')}, gmail={auth_status.get('gmail')}")
    
    # Determine which sources we can safely fetch
    sources_to_fetch = []
    
    for source in ['drive']:  # Drive doesn't need OAuth, always fetch
        if not is_cache_valid(meeting_id, source):
            sources_to_fetch.append(source)
    
    # Only fetch these if authenticated (to avoid OAuth popups)
    if auth_status.get('atlassian'):
        for source in ['jira', 'confluence']:
            if not is_cache_valid(meeting_id, source):
                sources_to_fetch.append(source)
    else:
        logger.info("[Prefetch] Skipping Jira/Confluence - not authenticated")
    
    if auth_status.get('slack'):
        if not is_cache_valid(meeting_id, 'slack'):
            sources_to_fetch.append('slack')
    else:
        logger.info("[Prefetch] Skipping Slack - not authenticated")
    
    if auth_status.get('gmail'):
        if not is_cache_valid(meeting_id, 'gmail'):
            sources_to_fetch.append('gmail')
    else:
        logger.info("[Prefetch] Skipping Gmail - not authenticated")
    
    # Fetch sources SEQUENTIALLY to avoid overloading CLI/MCP servers
    logger.info(f"[Prefetch] Sources to fetch (sequential): {sources_to_fetch}")
    
    for source in sources_to_fetch:
        if not _prefetch_running:
            break
        try:
            update_prefetch_status(current_source=source)
            add_prefetch_activity('fetch_start', f'Fetching {source}...', meeting=title, source=source, status='info')
            logger.info(f"[Prefetch] Starting {source}...")
            
            # All sources use CLI (Drive uses find command, others use MCPs)
            # Drive gets longer timeout since file search can take time
            timeout = 90 if source == 'drive' else 60
            result = call_cli_for_source(source, title, attendees_str, description, timeout=timeout)
            
            if isinstance(result, list):
                logger.info(f"[Prefetch] {source} for '{title[:30]}': {len(result)} items")
                set_meeting_cache(meeting_id, source, result)
                add_prefetch_activity('fetch_complete', f'{source}: {len(result)} items', meeting=title, source=source, status='success', items=len(result))
            else:
                logger.warning(f"[Prefetch] {source} returned non-list: {type(result)}")
                set_meeting_cache(meeting_id, source, [])
                error_msg = result.get('error', 'Unknown error') if isinstance(result, dict) else str(type(result))
                add_prefetch_activity('fetch_error', f'{source}: {error_msg}', meeting=title, source=source, status='error')
        except Exception as e:
            logger.error(f"[Prefetch] Error fetching {source}: {e}")
            set_meeting_cache(meeting_id, source, [])
            add_prefetch_activity('fetch_error', f'{source}: {str(e)[:50]}', meeting=title, source=source, status='error')
        
        # Small delay between sources to avoid overwhelming CLI
        time.sleep(2)
    
    update_prefetch_status(current_source=None)
    
    # Only fetch summary if we have some data sources authenticated
    if auth_status.get('atlassian') or auth_status.get('slack') or auth_status.get('gmail'):
        if not is_cache_valid(meeting_id, 'summary'):
            try:
                result = call_cli_for_meeting_summary(title, attendees_str, attendee_emails, description, timeout=120)
                if result.get('status') == 'success':
                    set_meeting_cache(meeting_id, 'summary', result)
                    logger.info(f"[Prefetch] Summary for '{title[:30]}': generated")
                else:
                    set_meeting_cache(meeting_id, 'summary', {'summary': '', 'status': 'empty'})
            except Exception as e:
                logger.error(f"[Prefetch] Error fetching summary: {e}")
                set_meeting_cache(meeting_id, 'summary', {'summary': '', 'status': 'error'})
    else:
        logger.info("[Prefetch] Skipping summary - no authenticated sources")
    
    logger.info(f"[Prefetch] Completed for: {title[:50]}")

def get_calendar_events_standalone(minutes_ahead=120, limit=5):
    """Standalone function to get calendar events (for prefetch thread)."""
    if not GOOGLE_API_AVAILABLE:
        return []
    
    if not os.path.exists(TOKEN_PATH):
        return []
    
    try:
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
        
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)
        
        service = build('calendar', 'v3', credentials=creds)
        
        now = datetime.utcnow()
        # Only include meetings from 30 mins ago (to catch ongoing ones) to future
        # This ensures we prioritize upcoming meetings over old ones
        time_min = (now - timedelta(minutes=30)).isoformat() + 'Z'
        time_max = (now + timedelta(minutes=minutes_ahead)).isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=limit,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        raw_events = events_result.get('items', [])
        
        # Process events - filter out ended meetings and all-day events
        processed = []
        for event in raw_events:
            if len(processed) >= limit:
                break
                
            title = event.get('summary', 'No title')
            start = event.get('start', {})
            start_time = start.get('dateTime', start.get('date', ''))
            
            # Skip all-day events
            if 'T' not in start_time:
                continue
            
            # Skip meetings that have already ended
            end = event.get('end', {})
            end_time = end.get('dateTime', end.get('date', ''))
            if end_time and 'T' in end_time:
                try:
                    # Parse the end time and compare with local time
                    # Google Calendar returns times with timezone offset (e.g., -05:00 for EST)
                    end_str = end_time.replace('Z', '+00:00')
                    end_dt_aware = datetime.fromisoformat(end_str)
                    local_now = datetime.now().astimezone()
                    if (end_dt_aware - local_now).total_seconds() < 0:
                        continue  # Meeting already ended
                except:
                    pass  # If parsing fails, include the meeting
            
            attendees = []
            for a in event.get('attendees', []):
                attendees.append({
                    'email': a.get('email', ''),
                    'name': a.get('displayName', a.get('email', '')),
                    'self': a.get('self', False)
                })
            
            processed.append({
                'id': event.get('id', ''),
                'title': event.get('summary', 'No title'),
                'start': start_time,
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'link': event.get('hangoutLink', event.get('htmlLink', '')),
                'attendees': attendees
            })
        
        return processed
        
    except Exception as e:
        print(f"[Calendar] Error getting events: {e}", flush=True)
        return []

def is_night_hours():
    """Check if current time is during night hours (10pm - 6am) or weekend - best time for prefetch."""
    from datetime import datetime
    now = datetime.now()
    hour = now.hour
    is_weekend = now.weekday() >= 5  # Saturday = 5, Sunday = 6
    is_night = hour >= 22 or hour < 6
    return is_night or is_weekend

# Global flag to force aggressive prefetch (can be toggled via API)
_force_aggressive_prefetch = False

def set_force_aggressive_prefetch(action):
    """Set the force aggressive prefetch flag."""
    global _force_aggressive_prefetch
    if action == "on":
        _force_aggressive_prefetch = True
    elif action == "off":
        _force_aggressive_prefetch = False
    else:
        _force_aggressive_prefetch = not _force_aggressive_prefetch

def background_prefetch_loop():
    """Background loop that pre-fetches data for upcoming meetings."""
    global _prefetch_running
    import time
    import sys
    
    print("[Prefetch] Background prefetch thread started", flush=True)
    
    while _prefetch_running:
        try:
            is_night = is_night_hours() or _force_aggressive_prefetch
            mode = "force-all" if _force_aggressive_prefetch else ("aggressive" if is_night else "day (skipping cached)")
            
            # Aggressive/force modes: no limit. Day mode: limit to 30 to reduce load
            meeting_limit = 500 if is_night else 30
            print(f"[Prefetch] Starting prefetch cycle... [{mode}] (limit: {meeting_limit})", flush=True)
            
            # Get upcoming meetings for next 7 days using standalone function
            try:
                events = get_calendar_events_standalone(minutes_ahead=10080, limit=meeting_limit)
                print(f"[Prefetch] Calendar returned {len(events)} events for week", flush=True)
            except Exception as cal_err:
                print(f"[Prefetch] Calendar error: {cal_err}", flush=True)
                events = []
            
            if events:
                print(f"[Prefetch] Found {len(events)} upcoming meetings to prefetch", flush=True)
                add_prefetch_activity('cycle_start', f'Found {len(events)} meetings [{mode}]', status='info')
                update_prefetch_status(meetings_in_queue=len(events), meetings_processed=0, last_cycle_start=time.time())
                
                meetings_processed_total = 0
                batch_size = 5
                has_uncached_meetings = False
                
                for i, meeting in enumerate(events):
                    if not _prefetch_running:
                        break
                    
                    meeting_id = meeting.get('id') or meeting.get('title')
                    meeting_title = meeting.get('title', 'unknown')
                    
                    # During day: only fetch if data is MISSING (not just expired)
                    # During night/weekend: refresh expired data too (full refresh)
                    # Force mode: refresh everything regardless of TTL
                    if _force_aggressive_prefetch:
                        # Force mode: refresh ALL meetings (ignore TTL completely)
                        needs_fetch = True
                    elif is_night:
                        # Night/weekend mode: refresh if TTL expired
                        needs_fetch = not all(
                            is_cache_valid(meeting_id, source) 
                            for source in ['jira', 'confluence', 'slack', 'gmail', 'drive', 'summary']
                        )
                    else:
                        # Day mode: only fetch if data is completely missing
                        needs_fetch = not all(
                            has_cached_data(meeting_id, source) 
                            for source in ['jira', 'confluence', 'slack', 'gmail', 'drive', 'summary']
                        )
                    
                    if needs_fetch:
                        has_uncached_meetings = True
                        print(f"[Prefetch] Processing meeting {meetings_processed_total + 1}: {meeting_title[:40]}", flush=True)
                        update_prefetch_status(current_meeting=meeting_title, running=True)
                        add_prefetch_activity('meeting_start', f'Processing meeting', meeting=meeting_title, status='info')
                        prefetch_meeting_data(meeting)
                        meetings_processed_total += 1
                        update_prefetch_status(meetings_processed=meetings_processed_total)
                        add_prefetch_activity('meeting_complete', f'Completed', meeting=meeting_title, status='success')
                        
                        # Shorter pauses at night, longer during day
                        pause_between = 3 if is_night else 5
                        if i < len(events) - 1:
                            print(f"[Prefetch] Waiting {pause_between}s before next meeting...", flush=True)
                            time.sleep(pause_between)
                        
                        # Batch pause
                        batch_pause = 15 if is_night else 30
                        if meetings_processed_total % batch_size == 0 and i < len(events) - 1:
                            print(f"[Prefetch] Batch of {batch_size} done, {batch_pause}s pause...", flush=True)
                            add_prefetch_activity('batch_pause', f'Short pause after {meetings_processed_total} meetings', status='info')
                            time.sleep(batch_pause)
                    else:
                        print(f"[Prefetch] Skipping '{meeting_title[:30]}' - already cached", flush=True)
                        add_prefetch_activity('meeting_skip', f'Already cached', meeting=meeting_title, status='info')
                
                update_prefetch_status(current_meeting=None, running=False)
                cleanup_old_caches()
                
                # Wait times: shorter at night for faster refresh cycles
                if has_uncached_meetings:
                    wait_time = 30 if is_night else 60
                    print(f"[Prefetch] Cycle complete, processed {meetings_processed_total} meetings. Waiting {wait_time}s...", flush=True)
                else:
                    wait_time = 300 if is_night else PREFETCH_INTERVAL  # 5 min at night, 10 min during day
                    print(f"[Prefetch] All meetings cached. Waiting {wait_time}s...", flush=True)
            else:
                print("[Prefetch] No upcoming meetings found in next 7 days", flush=True)
                wait_time = PREFETCH_INTERVAL
            
        except Exception as e:
            print(f"[Prefetch] Error in prefetch loop: {e}", flush=True)
            wait_time = 60
        
        # Wait before next prefetch cycle
        for _ in range(wait_time):
            if not _prefetch_running:
                break
            time.sleep(1)
    
    print("[Prefetch] Background prefetch thread stopped")

def start_prefetch_thread():
    """Start the background prefetch thread."""
    global _prefetch_thread, _prefetch_running
    
    if _prefetch_thread is not None and _prefetch_thread.is_alive():
        return  # Already running
    
    _prefetch_running = True
    _prefetch_thread = threading.Thread(target=background_prefetch_loop, daemon=True)
    _prefetch_thread.start()
    print("[Prefetch] Started background prefetch thread")

def stop_prefetch_thread():
    """Stop the background prefetch thread."""
    global _prefetch_running
    _prefetch_running = False

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

def authenticate_google():
    """Run OAuth flow to authenticate with Google Calendar."""
    if not GOOGLE_API_AVAILABLE:
        print("Error: Google API libraries not installed.")
        print("Run: pip3 install google-auth-oauthlib google-api-python-client")
        return False
    
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"Error: Credentials file not found at {CREDENTIALS_PATH}")
        print("\nTo set up Google Calendar:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project and enable Google Calendar API")
        print("3. Create OAuth 2.0 credentials (Desktop app)")
        print("4. Download the JSON and save it as:")
        print(f"   {CREDENTIALS_PATH}")
        return False
    
    print("Starting Google OAuth flow...")
    print("A browser window will open. Please authorize the app.")
    
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open(TOKEN_PATH, 'wb') as token:
        pickle.dump(creds, token)
    
    print(f"\nSuccess! Token saved to {TOKEN_PATH}")
    print("You can now use the calendar feature.")
    return True

from socketserver import ThreadingMixIn

