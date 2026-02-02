"""
Test helper module that imports from lib/ modules.

This module re-exports everything from lib so tests can use:
    from search_server_funcs import function_name
    import search_server_funcs as funcs

The actual implementations are in lib/*.py
"""
import sys
import os

# Add parent directory to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Re-export standard library modules (for patching compatibility)
import json
import re
import time
import threading
import subprocess
import tempfile
import shutil
import pickle
import glob
import select
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote, quote

# Import os module (tests patch search_server_funcs.os)
import os

# Logger
logger = logging.getLogger('briefdesk')

# Google API imports (may not be available)
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

# ============================================================================
# Import everything from lib modules
# ============================================================================

# Config constants
from lib.config import (
    LOG_FILE,
    CONFIG_DIR, TOKEN_PATH, CREDENTIALS_PATH, MCP_CONFIG_PATH,
    CACHE_DIR, PREP_CACHE_FILE, PROMPTS_FILE,
    GOOGLE_DRIVE_PATHS,
    SAFARI_HISTORY, SAFARI_BOOKMARKS,
    CHROME_HISTORY, CHROME_BOOKMARKS,
    HELIUM_HISTORY, HELIUM_BOOKMARKS,
    DIA_HISTORY, DIA_BOOKMARKS,
    SCOPES,
    CACHE_TTL, HUB_CACHE_TTL, PREP_CACHE_TTL, SUMMARY_CACHE_TTL,
    SLACK_USERS_CACHE_TTL, PREFETCH_INTERVAL, MAX_ACTIVITY_LOG,
    SLACK_WORKSPACE, DEFAULT_PROMPTS,
)

# Utils functions
from lib.utils import (
    extract_json_array, copy_db, cleanup_db,
    slack_ts_to_iso, is_night_hours, extract_domain,
    score_result, format_time_ago,
)

# Cache functions and state
from lib.cache import (
    load_custom_prompts, save_custom_prompts,
    get_prompt, set_custom_prompt, reset_prompt, get_all_prompts,
    save_prep_cache_to_disk, load_prep_cache_from_disk,
    get_meeting_cache, set_meeting_cache,
    is_cache_valid, has_cached_data, get_cached_data,
    cleanup_old_caches, get_all_cached_meetings, clear_meeting_cache,
)
# Cache state variables - import the module to allow modification
import lib.cache as _cache_module
_meeting_prep_cache = _cache_module._meeting_prep_cache
_meeting_prep_cache_lock = _cache_module._meeting_prep_cache_lock
_custom_prompts = _cache_module._custom_prompts
_custom_prompts_lock = _cache_module._custom_prompts_lock

# Slack functions and state
from lib.slack import (
    get_slack_tokens, reset_slack_tokens, slack_api_call,
    slack_get_users, slack_get_unread_counts,
    slack_get_conversations_fast, slack_get_conversations_with_unread,
    slack_get_conversation_history_direct,
    slack_get_threads, slack_get_thread_replies,
    slack_send_message_direct, slack_get_dm_channel_for_user,
    slack_find_user_by_username, slack_mark_conversation_read,
)
# Slack state variables - import the module to allow modification
import lib.slack as _slack_module
_slack_tokens = _slack_module._slack_tokens
_slack_users_cache = _slack_module._slack_users_cache

# For patching - provide access to the internal requests used by slack functions
# The slack module uses urllib.request internally
slack_requests = _slack_module

# Atlassian/MCP functions and state
from lib.atlassian import (
    load_mcp_config, load_config,
    get_atlassian_process, call_atlassian_tool, call_mcp_tool,
    extract_mcp_content,
    search_atlassian, get_jira_context, search_confluence,
    list_atlassian_tools,
)
# Atlassian state variables
import lib.atlassian as _atlassian_module
_atlassian_process = _atlassian_module._atlassian_process
_atlassian_initialized = _atlassian_module._atlassian_initialized
_atlassian_msg_id = _atlassian_module._atlassian_msg_id
_atlassian_lock = _atlassian_module._atlassian_lock
_mcp_config_cache = _atlassian_module._mcp_config_cache

# Try to get ATLASSIAN_DOMAIN from config if available
try:
    ATLASSIAN_DOMAIN = _atlassian_module.ATLASSIAN_DOMAIN
except AttributeError:
    ATLASSIAN_DOMAIN = None

# Google services functions
from lib.google_services import (
    authenticate_google, get_google_credentials,
    get_calendar_events_standalone, get_meeting_by_id, get_meeting_info,
    search_google_drive,
)

# CLI functions
from lib.cli import (
    extract_meeting_keywords,
    call_cli_for_source, call_cli_for_meeting_summary,
)

# Prefetch functions and state
from lib.prefetch import (
    configure_cli_functions,
    add_prefetch_activity, update_prefetch_status, get_prefetch_status,
    check_services_auth, prefetch_meeting_data,
    set_force_aggressive_prefetch, get_force_aggressive_prefetch,
    background_prefetch_loop, start_prefetch_thread, stop_prefetch_thread,
    is_prefetch_running, get_prefetch_thread_status,
)
# Prefetch state variables
import lib.prefetch as _prefetch_module
_prefetch_status = _prefetch_module._prefetch_status
_prefetch_status_lock = _prefetch_module._prefetch_status_lock
_prefetch_thread = _prefetch_module._prefetch_thread
_prefetch_running = _prefetch_module._prefetch_running
_force_aggressive_prefetch = _prefetch_module._force_aggressive_prefetch

# History functions
from lib.history import (
    search_history, search_bookmarks, search_browser_history,
    search_chrome_bookmarks, search_helium_bookmarks,
    search_dia_bookmarks, search_safari_bookmarks,
    search_chrome_history, search_helium_history,
    search_dia_history, search_safari_history,
)

# ============================================================================
# Stub class for SearchHandler (not tested in unit tests)
# ============================================================================
class SearchHandler:
    """Stub SearchHandler class for test compatibility."""
    pass
