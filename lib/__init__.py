"""BriefDesk library modules.

This package contains the modular components of the BriefDesk server:
- config: Constants, paths, logging, and default prompts
- utils: Generic utility functions
- cache: Meeting prep cache management
- slack: Slack API integration
- atlassian: Atlassian (Jira/Confluence) and MCP integration
- google_services: Google Calendar and Drive integration
- cli: devsai CLI integration for AI-powered searches
- prefetch: Background prefetching system
- history: Browser history and bookmarks search
- ai_search: Fast AI-powered search via Node.js service (keeps MCP connections warm)
"""

# Config exports
from .config import (
    logger, LOG_FILE,
    CONFIG_DIR, TOKEN_PATH, CREDENTIALS_PATH, MCP_CONFIG_PATH,
    CACHE_DIR, PREP_CACHE_FILE, PROMPTS_FILE,
    GOOGLE_DRIVE_PATHS,
    SAFARI_HISTORY, SAFARI_BOOKMARKS,
    CHROME_HISTORY, CHROME_BOOKMARKS,
    HELIUM_HISTORY, HELIUM_BOOKMARKS,
    DIA_HISTORY, DIA_BOOKMARKS,
    SCOPES, GOOGLE_API_AVAILABLE,
    CACHE_TTL, HUB_CACHE_TTL, PREP_CACHE_TTL, SUMMARY_CACHE_TTL,
    SLACK_USERS_CACHE_TTL, PREFETCH_INTERVAL, MAX_ACTIVITY_LOG,
    SLACK_WORKSPACE, DEFAULT_PROMPTS,
)

# Utils exports
from .utils import (
    extract_json_array, copy_db, cleanup_db,
    slack_ts_to_iso, is_night_hours, extract_domain,
    score_result, format_time_ago,
)

# Cache exports
from .cache import (
    load_custom_prompts, save_custom_prompts,
    get_prompt, set_custom_prompt, reset_prompt, get_all_prompts,
    save_prep_cache_to_disk, load_prep_cache_from_disk,
    get_meeting_cache, set_meeting_cache,
    is_cache_valid, has_cached_data, get_cached_data,
    cleanup_old_caches, get_all_cached_meetings, clear_meeting_cache,
    _meeting_prep_cache, _meeting_prep_cache_lock,
    _calendar_cache, _hub_cache,
)

# Slack exports
from .slack import (
    get_slack_tokens, reset_slack_tokens, slack_api_call,
    slack_get_users, slack_get_unread_counts, slack_ts_to_iso,
    slack_get_conversations_fast, slack_get_conversations_with_unread,
    slack_get_conversation_history_direct,
    slack_get_threads, slack_get_thread_replies,
    slack_send_message_direct, slack_get_dm_channel_for_user,
    slack_find_user_by_username, slack_mark_conversation_read,
    _slack_tokens, _slack_users_cache,
)

# Atlassian exports
from .atlassian import (
    load_mcp_config, load_config,
    get_atlassian_process, call_atlassian_tool, call_mcp_tool,
    extract_mcp_content,
    search_atlassian, get_jira_context, search_confluence,
    list_atlassian_tools,
    _atlassian_process, _atlassian_initialized, _atlassian_msg_id,
    _atlassian_lock, _mcp_config_cache,
)

# Google exports
from .google_services import (
    authenticate_google, get_google_credentials,
    get_calendar_events_standalone, get_meeting_by_id, get_meeting_info,
    search_google_drive,
)

# CLI exports
from .cli import (
    extract_meeting_keywords,
    call_cli_for_source, call_cli_for_meeting_summary,
)

# Prefetch exports
from .prefetch import (
    configure_cli_functions,
    add_prefetch_activity, update_prefetch_status, get_prefetch_status,
    check_services_auth, prefetch_meeting_data,
    set_force_aggressive_prefetch, get_force_aggressive_prefetch,
    background_prefetch_loop, start_prefetch_thread, stop_prefetch_thread,
    is_prefetch_running, get_prefetch_thread_status,
    _prefetch_status, _prefetch_status_lock,
    _prefetch_thread, _prefetch_running, _force_aggressive_prefetch,
)

# History exports
from .history import (
    search_history, search_bookmarks, search_browser_history,
    search_chrome_bookmarks, search_helium_bookmarks,
    search_dia_bookmarks, search_safari_bookmarks,
    search_chrome_history, search_helium_history,
    search_dia_history, search_safari_history,
)

# AI Search exports (fast AI-powered search via Node.js service)
from .ai_search import (
    is_search_service_available, get_service_status,
    ai_search, ai_query, parse_search_results,
)
