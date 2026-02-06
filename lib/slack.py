"""Slack integration functions for BriefDesk."""

import time
from datetime import datetime

try:
    import requests as slack_requests
except ImportError:
    slack_requests = None

from .config import logger, SLACK_USERS_CACHE_TTL, SLACK_WORKSPACE

# =============================================================================
# CSV Parsing and Formatting Utilities
# =============================================================================

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

# =============================================================================
# Global State
# =============================================================================

_slack_tokens = None
_slack_users_cache = {'data': None, 'timestamp': 0}

# =============================================================================
# Token Management
# =============================================================================

def get_slack_tokens():
    """Load Slack tokens from MCP config.
    
    Supports two authentication modes:
    - OAuth mode: Single xoxp- user token (preferred, via Slack OAuth)
    - Advanced/legacy mode: xoxc- + xoxd- browser session tokens
    
    Returns dict with either:
        {'xoxp': 'xoxp-...'} for OAuth mode, or
        {'xoxc': 'xoxc-...', 'xoxd': 'xoxd-...'} for legacy mode
    """
    global _slack_tokens
    if _slack_tokens:
        return _slack_tokens
    
    from .atlassian import load_mcp_config
    config = load_mcp_config()
    slack_config = config.get('slack', {})
    env_vars = slack_config.get('env', {})
    
    # Prefer OAuth xoxp- token if available
    xoxp = env_vars.get('SLACK_MCP_XOXP_TOKEN', '')
    if xoxp:
        _slack_tokens = {'xoxp': xoxp}
    else:
        # Fall back to legacy xoxc/xoxd tokens
        _slack_tokens = {
            'xoxc': env_vars.get('SLACK_MCP_XOXC_TOKEN', ''),
            'xoxd': env_vars.get('SLACK_MCP_XOXD_TOKEN', '')
        }
    return _slack_tokens


def reset_slack_tokens():
    """Reset cached tokens (for re-loading after config change)."""
    global _slack_tokens
    _slack_tokens = None

# =============================================================================
# API Calls
# =============================================================================

def slack_api_call(method, params=None, post_data=None, xoxc_token=None, xoxd_token=None):
    """Make a direct Slack API call using requests library.
    
    Supports both OAuth (xoxp-) and legacy (xoxc/xoxd) authentication.
    
    Args:
        method: API method (e.g., 'conversations.list')
        params: Query parameters dict
        post_data: POST body dict (will use POST if provided)
        xoxc_token: Optional override xoxc token (for testing)
        xoxd_token: Optional override xoxd token (for testing)
    
    Returns:
        Parsed JSON response or error dict
    """
    if not slack_requests:
        return {'ok': False, 'error': 'requests library not installed'}
    
    # Use override tokens if provided, otherwise load from config
    if xoxc_token and xoxd_token:
        headers = {
            'Authorization': f'Bearer {xoxc_token}',
            'Content-Type': 'application/json; charset=utf-8',
            'Cookie': f'd={xoxd_token}'
        }
    else:
        tokens = get_slack_tokens()
        
        if tokens.get('xoxp'):
            # OAuth mode: single xoxp- user token
            headers = {
                'Authorization': f'Bearer {tokens["xoxp"]}',
                'Content-Type': 'application/json; charset=utf-8',
            }
        elif tokens.get('xoxc'):
            # Legacy mode: xoxc + xoxd session tokens
            headers = {
                'Authorization': f'Bearer {tokens["xoxc"]}',
                'Content-Type': 'application/json; charset=utf-8',
                'Cookie': f'd={tokens["xoxd"]}'
            }
        else:
            return {'ok': False, 'error': 'No Slack token configured'}
    
    url = f'https://slack.com/api/{method}'
    
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


def is_using_oauth_token():
    """Check if we're using an OAuth (xoxp-) token vs legacy session tokens.
    
    Useful for gracefully degrading features that only work with session tokens.
    """
    tokens = get_slack_tokens()
    return bool(tokens.get('xoxp'))

# =============================================================================
# Users
# =============================================================================

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

# =============================================================================
# Unread Counts
# =============================================================================

def slack_get_unread_counts():
    """Get unread counts using client.counts API (internal Slack API).
    
    Note: client.counts is an undocumented internal API that only works with
    session tokens (xoxc/xoxd). When using OAuth (xoxp) tokens, this returns
    empty data and the UI gracefully degrades (no unread badges).
    
    Returns dict with:
        - ims: list of {id, has_unreads, mention_count}
        - channels: list of {id, has_unreads, mention_count}
        - mpims: list of group DMs
        - threads: {has_unreads, mention_count}
    """
    # client.counts only works with session tokens, not OAuth
    if is_using_oauth_token():
        logger.debug("[Slack] Skipping client.counts (not available with OAuth tokens)")
        return {'ims': [], 'channels': [], 'mpims': [], 'threads': {}}
    
    result = slack_api_call('client.counts', post_data={})
    
    if not result.get('ok'):
        return {'ims': [], 'channels': [], 'mpims': [], 'threads': {}}
    
    return {
        'ims': result.get('ims', []),
        'channels': result.get('channels', []),
        'mpims': result.get('mpims', []),
        'threads': result.get('threads', {})
    }

# =============================================================================
# Timestamp Conversion
# =============================================================================

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

# =============================================================================
# Conversations
# =============================================================================

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

# =============================================================================
# History & Messages
# =============================================================================

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

# =============================================================================
# Threads
# =============================================================================

def slack_get_threads(limit=20):
    """Get subscribed thread replies.
    
    Note: subscriptions.thread.getView is an undocumented internal API that
    only works with session tokens (xoxc/xoxd). When using OAuth (xoxp) tokens,
    this returns an empty list.
    
    Returns:
        List of thread items with replies
    """
    # subscriptions.thread.getView only works with session tokens
    if is_using_oauth_token():
        logger.debug("[Slack] Skipping subscriptions.thread.getView (not available with OAuth tokens)")
        return []
    
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

# =============================================================================
# Sending Messages
# =============================================================================

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

# =============================================================================
# User & DM Helpers
# =============================================================================

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
