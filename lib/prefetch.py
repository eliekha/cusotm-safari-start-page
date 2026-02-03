"""Background prefetch system for BriefDesk meeting data."""

import json
import os
import threading
import time

from .config import logger, PREFETCH_INTERVAL, MAX_ACTIVITY_LOG
from .cache import (
    get_meeting_cache, set_meeting_cache, is_cache_valid,
    has_cached_data, save_prep_cache_to_disk, cleanup_old_caches,
    set_meeting_info,
    _meeting_prep_cache, _meeting_prep_cache_lock
)
from .google_services import get_calendar_events_standalone
from .atlassian import load_mcp_config
from .utils import is_night_hours

# =============================================================================
# Global State
# =============================================================================

# Prefetch status tracking
_prefetch_status = {
    'running': False,
    'current_meeting': None,
    'current_source': None,
    'meetings_in_queue': 0,
    'meetings_processed': 0,
    'last_cycle_start': None,
    'activity_log': []
}
_prefetch_status_lock = threading.Lock()

# Thread management
_prefetch_thread = None
_prefetch_running = False

# Force aggressive prefetch mode (can be toggled via API)
_force_aggressive_prefetch = False

# CLI function references (set via configure_cli_functions)
_call_cli_for_source = None
_call_cli_for_meeting_summary = None

# =============================================================================
# Configuration
# =============================================================================

def configure_cli_functions(call_cli_for_source_fn, call_cli_for_meeting_summary_fn):
    """Configure the CLI functions for the prefetch module.
    
    This allows the prefetch module to be used before the CLI functions
    are extracted to a separate module.
    
    Args:
        call_cli_for_source_fn: Function to call CLI for a specific source
        call_cli_for_meeting_summary_fn: Function to call CLI for meeting summary
    """
    global _call_cli_for_source, _call_cli_for_meeting_summary
    _call_cli_for_source = call_cli_for_source_fn
    _call_cli_for_meeting_summary = call_cli_for_meeting_summary_fn
    logger.info("[Prefetch] CLI functions configured")


def _ensure_cli_configured():
    """Ensure CLI functions are configured before use."""
    if _call_cli_for_source is None or _call_cli_for_meeting_summary is None:
        raise RuntimeError(
            "CLI functions not configured. Call configure_cli_functions() first."
        )


# =============================================================================
# Activity Logging
# =============================================================================

def add_prefetch_activity(activity_type, message, meeting=None, source=None, status='info', items=None):
    """Add an activity entry to the prefetch status log.
    
    Args:
        activity_type: Type of activity (e.g., 'fetch_start', 'fetch_complete')
        message: Human-readable message
        meeting: Meeting title (truncated to 40 chars)
        source: Data source (jira, confluence, etc.)
        status: Status level (info, success, error, warning)
        items: Number of items fetched (optional)
    """
    with _prefetch_status_lock:
        entry = {
            'timestamp': time.time(),
            'type': activity_type,
            'message': message,
            'meeting': meeting[:40] if meeting else None,
            'source': source,
            'status': status,
            'items': items
        }
        _prefetch_status['activity_log'].insert(0, entry)
        # Keep only last N entries
        _prefetch_status['activity_log'] = _prefetch_status['activity_log'][:MAX_ACTIVITY_LOG]


def update_prefetch_status(**kwargs):
    """Update prefetch status fields.
    
    Args:
        **kwargs: Key-value pairs to update in the status dict
    """
    with _prefetch_status_lock:
        _prefetch_status.update(kwargs)


def get_prefetch_status():
    """Get current prefetch status.
    
    Returns:
        dict: Copy of the current prefetch status
    """
    with _prefetch_status_lock:
        return dict(_prefetch_status)


# =============================================================================
# Service Authentication Check
# =============================================================================

def check_services_auth():
    """Check which services are authenticated (for prefetch to avoid triggering OAuth).
    
    Returns:
        dict: Authentication status for each service (atlassian, slack, gmail, drive)
    """
    auth_status = {
        'atlassian': False,
        'slack': False,
        'gmail': False,
        'drive': False,  # True = gdrive MCP available (API mode), False = local fallback
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
                                # Check if token is valid (has access_token)
                                if token_data.get('access_token'):
                                    auth_status['atlassian'] = True
                                    break
                        except Exception:
                            pass
            if auth_status['atlassian']:
                break
    
    # Check Slack auth by looking for token in local .devsai.json config
    local_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.devsai.json')
    try:
        if os.path.exists(local_config_path):
            with open(local_config_path, 'r') as f:
                local_config = json.load(f).get('mcpServers', {})
                slack_config = local_config.get('slack', {})
                env = slack_config.get('env', {})
                if env.get('SLACK_MCP_XOXC_TOKEN') or env.get('SLACK_BOT_TOKEN') or env.get('SLACK_TOKEN'):
                    auth_status['slack'] = True
    except Exception:
        pass
    
    # Also check global MCP config
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
    
    # Check Google Drive MCP auth - gdrive MCP token in briefdesk config
    # If token exists, we use API mode; otherwise fallback to local filesystem search
    gdrive_token_path = os.path.expanduser('~/.local/share/briefdesk/google_drive_token.json')
    gdrive_mcp_path = os.path.expanduser('~/.local/share/briefdesk/gdrive-mcp/dist/index.js')
    if os.path.exists(gdrive_token_path) and os.path.exists(gdrive_mcp_path):
        auth_status['drive'] = True  # API mode available
    # Note: drive=False just means local fallback, drive still works
    
    return auth_status


# =============================================================================
# Meeting Data Prefetch
# =============================================================================

def prefetch_meeting_data(meeting):
    """Pre-fetch all data for a single meeting.
    
    Args:
        meeting: Meeting dict with id, title, attendees, description
    """
    global _prefetch_running
    
    _ensure_cli_configured()
    
    meeting_id = meeting.get('id') or meeting.get('title')
    title = meeting.get('title', '')
    
    logger.info(f"[Prefetch] Starting prefetch for: {title[:50]}... (meeting_id={meeting_id})")
    
    attendees = meeting.get('attendees', [])
    attendee_emails = [a.get('email', '') for a in attendees if a.get('email')]
    attendee_names = [a.get('name', a.get('email', '')) for a in attendees]
    attendees_str = ', '.join(attendee_names[:5])
    description = meeting.get('description', '')[:200] if meeting.get('description') else ''
    
    # Store meeting info for future refreshes (when meeting not in calendar view)
    set_meeting_info(meeting_id, title, attendees_str, attendee_emails, description)
    
    # Check auth status to avoid triggering OAuth dialogs from background
    auth_status = check_services_auth()
    drive_mode = "API" if auth_status.get('drive') else "local"
    logger.info(f"[Prefetch] Auth status: atlassian={auth_status.get('atlassian')}, "
                f"slack={auth_status.get('slack')}, gmail={auth_status.get('gmail')}, "
                f"drive={drive_mode}")
    
    # Determine which sources we can safely fetch
    sources_to_fetch = []
    
    # Drive doesn't need OAuth, always fetch
    for source in ['drive']:
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
            result = _call_cli_for_source(source, title, attendees_str, description, timeout=timeout, attendee_emails=attendee_emails)
            
            if isinstance(result, list):
                logger.info(f"[Prefetch] {source} for '{title[:30]}': {len(result)} items")
                set_meeting_cache(meeting_id, source, result)
                add_prefetch_activity('fetch_complete', f'{source}: {len(result)} items', 
                                     meeting=title, source=source, status='success', items=len(result))
            else:
                logger.warning(f"[Prefetch] {source} returned non-list: {type(result)}")
                set_meeting_cache(meeting_id, source, [])
                error_msg = result.get('error', 'Unknown error') if isinstance(result, dict) else str(type(result))
                add_prefetch_activity('fetch_error', f'{source}: {error_msg}', 
                                     meeting=title, source=source, status='error')
        except Exception as e:
            import traceback
            logger.error(f"[Prefetch] Error fetching {source}: {e}")
            logger.error(f"[Prefetch] Traceback: {traceback.format_exc()}")
            set_meeting_cache(meeting_id, source, [])
            add_prefetch_activity('fetch_error', f'{source}: {str(e)[:50]}', 
                                 meeting=title, source=source, status='error')
        
        # Small delay between sources to avoid overwhelming CLI
        time.sleep(2)
    
    update_prefetch_status(current_source=None)
    
    # Only fetch summary if we have some data sources authenticated
    if auth_status.get('atlassian') or auth_status.get('slack') or auth_status.get('gmail'):
        if not is_cache_valid(meeting_id, 'summary'):
            try:
                result = _call_cli_for_meeting_summary(title, attendees_str, attendee_emails, description, timeout=120)
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


# =============================================================================
# Force Aggressive Prefetch Mode
# =============================================================================

def set_force_aggressive_prefetch(action):
    """Set the force aggressive prefetch flag.
    
    Args:
        action: "on" to enable, "off" to disable, anything else to toggle
    """
    global _force_aggressive_prefetch
    if action == "on":
        _force_aggressive_prefetch = True
    elif action == "off":
        _force_aggressive_prefetch = False
    else:
        _force_aggressive_prefetch = not _force_aggressive_prefetch
    
    logger.info(f"[Prefetch] Force aggressive mode: {_force_aggressive_prefetch}")


def get_force_aggressive_prefetch():
    """Get the current force aggressive prefetch flag value."""
    return _force_aggressive_prefetch


# =============================================================================
# Background Prefetch Loop
# =============================================================================

def background_prefetch_loop():
    """Background loop that pre-fetches data for upcoming meetings."""
    global _prefetch_running
    
    _ensure_cli_configured()
    
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
                update_prefetch_status(
                    meetings_in_queue=len(events), 
                    meetings_processed=0, 
                    last_cycle_start=time.time()
                )
                
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
                        add_prefetch_activity('meeting_start', 'Processing meeting', meeting=meeting_title, status='info')
                        prefetch_meeting_data(meeting)
                        meetings_processed_total += 1
                        update_prefetch_status(meetings_processed=meetings_processed_total)
                        add_prefetch_activity('meeting_complete', 'Completed', meeting=meeting_title, status='success')
                        
                        # Shorter pauses at night, longer during day
                        pause_between = 3 if is_night else 5
                        if i < len(events) - 1:
                            print(f"[Prefetch] Waiting {pause_between}s before next meeting...", flush=True)
                            time.sleep(pause_between)
                        
                        # Batch pause
                        batch_pause = 15 if is_night else 30
                        if meetings_processed_total % batch_size == 0 and i < len(events) - 1:
                            print(f"[Prefetch] Batch of {batch_size} done, {batch_pause}s pause...", flush=True)
                            add_prefetch_activity('batch_pause', 
                                                 f'Short pause after {meetings_processed_total} meetings', 
                                                 status='info')
                            time.sleep(batch_pause)
                    else:
                        print(f"[Prefetch] Skipping '{meeting_title[:30]}' - already cached", flush=True)
                        add_prefetch_activity('meeting_skip', 'Already cached', meeting=meeting_title, status='info')
                
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
        
        # Wait before next prefetch cycle (can be interrupted by force mode)
        for _ in range(wait_time):
            if not _prefetch_running:
                break
            if _force_aggressive_prefetch:
                print("[Prefetch] Force mode detected, starting new cycle immediately", flush=True)
                break
            time.sleep(1)
    
    print("[Prefetch] Background prefetch thread stopped", flush=True)


# =============================================================================
# Thread Management
# =============================================================================

def start_prefetch_thread():
    """Start the background prefetch thread.
    
    Note: configure_cli_functions() must be called before starting the thread.
    """
    global _prefetch_thread, _prefetch_running
    
    if _prefetch_thread is not None and _prefetch_thread.is_alive():
        logger.info("[Prefetch] Thread already running")
        return
    
    _ensure_cli_configured()
    
    _prefetch_running = True
    _prefetch_thread = threading.Thread(target=background_prefetch_loop, daemon=True)
    _prefetch_thread.start()
    print("[Prefetch] Started background prefetch thread", flush=True)


def stop_prefetch_thread():
    """Stop the background prefetch thread."""
    global _prefetch_running
    _prefetch_running = False
    print("[Prefetch] Stop signal sent to prefetch thread", flush=True)


def is_prefetch_running():
    """Check if the prefetch thread is currently running.
    
    Returns:
        bool: True if prefetch thread is running
    """
    return _prefetch_running and _prefetch_thread is not None and _prefetch_thread.is_alive()


# =============================================================================
# Utility Functions
# =============================================================================

def get_prefetch_thread_status():
    """Get detailed status of the prefetch thread.
    
    Returns:
        dict: Thread status including running state and current activity
    """
    status = get_prefetch_status()
    status['thread_alive'] = _prefetch_thread is not None and _prefetch_thread.is_alive()
    status['force_aggressive'] = _force_aggressive_prefetch
    return status
