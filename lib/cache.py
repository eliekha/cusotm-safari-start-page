"""Cache management and prompt handling for BriefDesk."""

import json
import os
import time
import threading

from .config import (
    logger, PREP_CACHE_FILE, PROMPTS_FILE,
    PREP_CACHE_TTL, SUMMARY_CACHE_TTL, DEFAULT_PROMPTS
)

# =============================================================================
# Global State
# =============================================================================

# Meeting prep cache: {meeting_id: {source: {data: [...], timestamp: ...}}}
_meeting_prep_cache = {}
_meeting_prep_cache_lock = threading.Lock()

# Custom prompts cache
_custom_prompts = {}

# Calendar cache
_calendar_cache = {"data": None, "timestamp": 0}

# Hub cache
_hub_cache = {
    "mentions": {"data": None, "timestamp": 0},
    "meeting_prep": {"data": None, "timestamp": 0, "meeting_id": None}
}

# =============================================================================
# Custom Prompts
# =============================================================================

def load_custom_prompts():
    """Load custom prompts from disk."""
    global _custom_prompts
    try:
        if os.path.exists(PROMPTS_FILE):
            with open(PROMPTS_FILE, 'r') as f:
                _custom_prompts = json.load(f)
    except Exception as e:
        logger.error(f"Error loading custom prompts: {e}")
        _custom_prompts = {}


def save_custom_prompts():
    """Save custom prompts to disk."""
    try:
        with open(PROMPTS_FILE, 'w') as f:
            json.dump(_custom_prompts, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving custom prompts: {e}")


def get_prompt(source):
    """Get prompt for a source, using custom if available."""
    if source in _custom_prompts and _custom_prompts[source]:
        return _custom_prompts[source]
    return DEFAULT_PROMPTS.get(source, '')


def set_custom_prompt(source, prompt):
    """Set a custom prompt for a source."""
    global _custom_prompts
    if prompt:
        _custom_prompts[source] = prompt
    elif source in _custom_prompts:
        del _custom_prompts[source]
    save_custom_prompts()


def reset_prompt(source):
    """Reset a prompt to its default."""
    global _custom_prompts
    if source in _custom_prompts:
        del _custom_prompts[source]
        save_custom_prompts()


def get_all_prompts():
    """Get all prompts with their current values and defaults."""
    result = {}
    for source in DEFAULT_PROMPTS:
        result[source] = {
            'current': get_prompt(source),
            'default': DEFAULT_PROMPTS[source],
            'is_custom': _custom_prompts.get(source, '')
        }
    return result

# =============================================================================
# Meeting Prep Cache
# =============================================================================

def save_prep_cache_to_disk():
    """Save the meeting prep cache to disk for persistence."""
    try:
        with _meeting_prep_cache_lock:
            cache_data = {}
            for meeting_id, sources in _meeting_prep_cache.items():
                cache_data[meeting_id] = {}
                for source, data in sources.items():
                    if isinstance(data, dict):
                        cache_data[meeting_id][source] = data
                    else:
                        cache_data[meeting_id][source] = data
            
            with open(PREP_CACHE_FILE, 'w') as f:
                json.dump(cache_data, f, indent=2, default=str)
        logger.debug(f"Saved prep cache to disk ({len(cache_data)} meetings)")
    except Exception as e:
        logger.error(f"Error saving prep cache: {e}")


def load_prep_cache_from_disk():
    """Load the meeting prep cache from disk."""
    global _meeting_prep_cache
    try:
        if os.path.exists(PREP_CACHE_FILE):
            with open(PREP_CACHE_FILE, 'r') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    with _meeting_prep_cache_lock:
                        _meeting_prep_cache = loaded
                    # Count valid entries
                    valid_count = sum(1 for m in loaded.values() 
                                     if isinstance(m, dict) and any(
                                         isinstance(s, dict) and s.get('data') is not None 
                                         for s in m.values() if isinstance(s, dict)
                                     ))
                    logger.info(f"Loaded prep cache from disk ({valid_count} meetings with data)")
    except Exception as e:
        logger.error(f"Error loading prep cache: {e}")


def get_meeting_cache(meeting_id):
    """Get or create cache entry for a meeting."""
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            _meeting_prep_cache[meeting_id] = {
                'jira': {'data': None, 'timestamp': 0},
                'confluence': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        return _meeting_prep_cache[meeting_id]


def set_meeting_cache(meeting_id, source, data):
    """Set cache data for a meeting source."""
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            _meeting_prep_cache[meeting_id] = {
                'jira': {'data': None, 'timestamp': 0},
                'confluence': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        _meeting_prep_cache[meeting_id][source] = {
            'data': data,
            'timestamp': time.time()
        }
    # Save to disk after update
    save_prep_cache_to_disk()


def is_cache_valid(meeting_id, source):
    """Check if cache for a meeting/source is still valid (within TTL)."""
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            return False
        cache = _meeting_prep_cache[meeting_id].get(source, {})
        if cache.get('data') is None:
            return False
        ttl = SUMMARY_CACHE_TTL if source == 'summary' else PREP_CACHE_TTL
        return (time.time() - cache.get('timestamp', 0)) < ttl


def has_cached_data(meeting_id, source):
    """Check if there's any cached data (regardless of TTL)."""
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            return False
        cache = _meeting_prep_cache[meeting_id].get(source, {})
        return cache.get('data') is not None


def get_cached_data(meeting_id, source):
    """Get cached data for a meeting/source."""
    with _meeting_prep_cache_lock:
        if meeting_id not in _meeting_prep_cache:
            return None
        cache = _meeting_prep_cache[meeting_id].get(source, {})
        return cache.get('data')


def cleanup_old_caches():
    """Remove cache entries older than 24 hours."""
    cutoff = time.time() - (24 * 60 * 60)  # 24 hours ago
    removed = 0
    
    with _meeting_prep_cache_lock:
        meetings_to_remove = []
        for meeting_id, sources in _meeting_prep_cache.items():
            if not isinstance(sources, dict):
                meetings_to_remove.append(meeting_id)
                continue
            
            # Check if all sources are expired
            all_expired = True
            for source, data in sources.items():
                if isinstance(data, dict) and data.get('timestamp', 0) > cutoff:
                    all_expired = False
                    break
            
            if all_expired:
                meetings_to_remove.append(meeting_id)
        
        for meeting_id in meetings_to_remove:
            del _meeting_prep_cache[meeting_id]
            removed += 1
    
    if removed > 0:
        logger.info(f"Cleaned up {removed} old cache entries")
        save_prep_cache_to_disk()
    
    return removed


def get_all_cached_meetings():
    """Get list of all meeting IDs in cache."""
    with _meeting_prep_cache_lock:
        return list(_meeting_prep_cache.keys())


def clear_meeting_cache(meeting_id):
    """Clear all cached data for a specific meeting."""
    with _meeting_prep_cache_lock:
        if meeting_id in _meeting_prep_cache:
            del _meeting_prep_cache[meeting_id]
    save_prep_cache_to_disk()

# =============================================================================
# Initialize
# =============================================================================

# Load caches on module import
load_custom_prompts()
load_prep_cache_from_disk()
