
import json
import os
import time
import threading
import tempfile
import shutil
import sqlite3
import logging
from datetime import datetime
from urllib.parse import urlparse

# Create a logger stub
logger = logging.getLogger('prefetch_utils')
logger.setLevel(logging.DEBUG)

# Constants
PREP_CACHE_TTL = 14400  # 4 hours
SUMMARY_CACHE_TTL = 21600  # 6 hours
PREFETCH_INTERVAL = 600  # 10 minutes
MAX_ACTIVITY_LOG = 50
SLACK_WORKSPACE = 'test-workspace'
PREP_CACHE_FILE = '/tmp/test_prep_cache.json'

# Global state
_meeting_prep_cache = {}
_meeting_prep_cache_lock = threading.Lock()

_prefetch_status = {
    'running': False,
    'current_meeting': None,
    'current_source': None,
    'last_cycle_start': None,
    'meetings_in_queue': 0,
    'meetings_processed': 0,
    'activity_log': []
}
_prefetch_status_lock = threading.Lock()

_prefetch_thread = None
_prefetch_running = False
_force_aggressive_prefetch = False

# Stubs for disk operations (will be mocked in tests)
def save_prep_cache_to_disk():
    """Stub - mocked in tests."""
    pass

def load_mcp_config():
    """Stub - mocked in tests."""
    return {}

def call_cli_for_source(source, title, attendees_str, description, timeout=60):
    """Stub - mocked in tests."""
    return []

def call_cli_for_meeting_summary(title, attendees_str, attendee_emails, description, timeout=120):
    """Stub - mocked in tests."""
    return {'status': 'success', 'summary': ''}

def is_cache_valid(meeting_id, source):
    """Check if cache for a meeting/source is still valid."""
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

def get_calendar_events_standalone(minutes_ahead=120, limit=5):
    """Stub - mocked in tests."""
    return []

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

def extract_domain(url):
    """Extract domain from URL for matching."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace('www.', '')
    except:
        return ''

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

