"""
Tests for Slack-related functions in BriefDesk search-server.py

Run with: pytest tests/test_slack.py -v
"""
import sys
import os
import time
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

# Add tests directory to path for importing the helper module
sys.path.insert(0, os.path.dirname(__file__))


# =============================================================================
# Test get_slack_tokens
# =============================================================================

class TestGetSlackTokens:
    """Test the get_slack_tokens function."""

    @pytest.fixture(autouse=True)
    def reset_tokens(self):
        """Reset the global _slack_tokens before each test."""
        import lib.slack as slack_module
        slack_module._slack_tokens = None
        yield
        slack_module._slack_tokens = None

    @patch('lib.atlassian.load_mcp_config')
    def test_returns_tokens_from_config(self, mock_load_config):
        """Test that tokens are correctly loaded from MCP config."""
        from search_server_funcs import get_slack_tokens
        
        mock_load_config.return_value = {
            'slack': {
                'env': {
                    'SLACK_MCP_XOXC_TOKEN': 'xoxc-test-token',
                    'SLACK_MCP_XOXD_TOKEN': 'xoxd-test-token'
                }
            }
        }
        
        result = get_slack_tokens()
        
        assert result['xoxc'] == 'xoxc-test-token'
        assert result['xoxd'] == 'xoxd-test-token'

    @patch('lib.atlassian.load_mcp_config')
    def test_returns_empty_strings_when_no_config(self, mock_load_config):
        """Test that empty strings are returned when config is missing."""
        from search_server_funcs import get_slack_tokens
        
        mock_load_config.return_value = {}
        
        result = get_slack_tokens()
        
        assert result['xoxc'] == ''
        assert result['xoxd'] == ''

    @patch('lib.atlassian.load_mcp_config')
    def test_caches_tokens_on_subsequent_calls(self, mock_load_config):
        """Test that tokens are cached and not reloaded."""
        import search_server_funcs as funcs
        
        mock_load_config.return_value = {
            'slack': {
                'env': {
                    'SLACK_MCP_XOXC_TOKEN': 'cached-token',
                    'SLACK_MCP_XOXD_TOKEN': 'cached-xoxd'
                }
            }
        }
        
        # First call
        result1 = funcs.get_slack_tokens()
        # Second call
        result2 = funcs.get_slack_tokens()
        
        # Should only load config once
        mock_load_config.assert_called_once()
        assert result1 is result2

    @patch('lib.atlassian.load_mcp_config')
    def test_handles_partial_config(self, mock_load_config):
        """Test handling config with only some tokens."""
        from search_server_funcs import get_slack_tokens
        
        mock_load_config.return_value = {
            'slack': {
                'env': {
                    'SLACK_MCP_XOXC_TOKEN': 'only-xoxc'
                    # xoxd is missing
                }
            }
        }
        
        result = get_slack_tokens()
        
        assert result['xoxc'] == 'only-xoxc'
        assert result['xoxd'] == ''


# =============================================================================
# Test slack_api_call
# =============================================================================

class TestSlackApiCall:
    """Test the slack_api_call function."""

    @pytest.fixture(autouse=True)
    def reset_tokens(self):
        """Reset tokens before each test."""
        import search_server_funcs as funcs
        funcs._slack_tokens = None
        yield
        funcs._slack_tokens = None

    @patch('lib.slack.slack_requests')
    @patch('lib.slack.get_slack_tokens')
    def test_successful_get_request(self, mock_get_tokens, mock_requests):
        """Test successful GET API call."""
        from search_server_funcs import slack_api_call
        
        mock_get_tokens.return_value = {'xoxc': 'test-token', 'xoxd': 'test-xoxd'}
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': True, 'data': 'test'}
        mock_requests.get.return_value = mock_response
        
        result = slack_api_call('users.list', {'limit': 10})
        
        assert result == {'ok': True, 'data': 'test'}
        mock_requests.get.assert_called_once()
        call_args = mock_requests.get.call_args
        assert 'https://slack.com/api/users.list' in call_args[0]

    @patch('lib.slack.slack_requests')
    @patch('lib.slack.get_slack_tokens')
    def test_successful_post_request(self, mock_get_tokens, mock_requests):
        """Test successful POST API call."""
        from search_server_funcs import slack_api_call
        
        mock_get_tokens.return_value = {'xoxc': 'test-token', 'xoxd': 'test-xoxd'}
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': True, 'ts': '123.456'}
        mock_requests.post.return_value = mock_response
        
        result = slack_api_call('chat.postMessage', post_data={'channel': 'C123', 'text': 'Hello'})
        
        assert result == {'ok': True, 'ts': '123.456'}
        mock_requests.post.assert_called_once()

    @patch('lib.slack.get_slack_tokens')
    def test_returns_error_when_no_token(self, mock_get_tokens):
        """Test that error is returned when no token is configured."""
        from search_server_funcs import slack_api_call
        
        mock_get_tokens.return_value = {'xoxc': '', 'xoxd': ''}
        
        result = slack_api_call('users.list')
        
        assert result['ok'] == False
        assert 'No Slack token configured' in result['error']

    @patch('lib.slack.slack_requests')
    @patch('lib.slack.get_slack_tokens')
    def test_handles_http_error(self, mock_get_tokens, mock_requests):
        """Test handling of HTTP errors."""
        from search_server_funcs import slack_api_call
        
        mock_get_tokens.return_value = {'xoxc': 'test-token', 'xoxd': 'test-xoxd'}
        
        # Create proper HTTP error simulation
        class MockHTTPError(Exception):
            def __init__(self, response):
                self.response = response
        
        class MockRequestException(Exception):
            pass
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.reason = 'Unauthorized'
        
        mock_requests.exceptions.HTTPError = MockHTTPError
        mock_requests.exceptions.RequestException = MockRequestException
        mock_requests.get.return_value.raise_for_status.side_effect = MockHTTPError(mock_response)
        
        result = slack_api_call('users.list')
        
        assert result['ok'] == False
        assert 'error' in result

    @patch('lib.slack.slack_requests')
    @patch('lib.slack.get_slack_tokens')
    def test_handles_request_exception(self, mock_get_tokens, mock_requests):
        """Test handling of request exceptions (network errors)."""
        from search_server_funcs import slack_api_call
        
        mock_get_tokens.return_value = {'xoxc': 'test-token', 'xoxd': 'test-xoxd'}
        mock_requests.get.side_effect = Exception('Connection failed')
        mock_requests.exceptions.HTTPError = type('HTTPError', (Exception,), {})
        mock_requests.exceptions.RequestException = type('RequestException', (Exception,), {})
        
        result = slack_api_call('users.list')
        
        assert result['ok'] == False
        assert 'error' in result

    @patch('lib.slack.slack_requests')
    @patch('lib.slack.get_slack_tokens')
    def test_includes_auth_headers(self, mock_get_tokens, mock_requests):
        """Test that authorization headers are included."""
        from search_server_funcs import slack_api_call
        
        mock_get_tokens.return_value = {'xoxc': 'xoxc-token-123', 'xoxd': 'xoxd-cookie-456'}
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': True}
        mock_requests.get.return_value = mock_response
        
        slack_api_call('users.list')
        
        call_kwargs = mock_requests.get.call_args[1]
        headers = call_kwargs['headers']
        assert 'Bearer xoxc-token-123' in headers['Authorization']
        assert 'd=xoxd-cookie-456' in headers['Cookie']


# =============================================================================
# Test slack_get_users
# =============================================================================

class TestSlackGetUsers:
    """Test the slack_get_users function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset the users cache before each test."""
        import lib.slack as slack_module
        slack_module._slack_users_cache = {"data": None, "timestamp": 0}
        yield
        slack_module._slack_users_cache = {"data": None, "timestamp": 0}

    @patch('lib.slack.slack_api_call')
    def test_returns_users_map(self, mock_api_call):
        """Test that users are returned as a map by ID."""
        from search_server_funcs import slack_get_users
        
        mock_api_call.return_value = {
            'ok': True,
            'members': [
                {'id': 'U123', 'name': 'john', 'real_name': 'John Doe', 'profile': {'display_name': 'johnd', 'image_48': 'http://img.jpg'}},
                {'id': 'U456', 'name': 'jane', 'real_name': 'Jane Smith', 'profile': {'display_name': '', 'image_48': ''}}
            ],
            'response_metadata': {}
        }
        
        result = slack_get_users()
        
        assert 'U123' in result
        assert result['U123']['name'] == 'John Doe'
        assert result['U123']['username'] == 'john'
        assert 'U456' in result

    @patch('lib.slack.slack_api_call')
    def test_handles_pagination(self, mock_api_call):
        """Test that pagination is handled correctly."""
        from search_server_funcs import slack_get_users
        
        # First call returns cursor for next page
        mock_api_call.side_effect = [
            {
                'ok': True,
                'members': [{'id': 'U1', 'name': 'user1', 'real_name': 'User 1', 'profile': {}}],
                'response_metadata': {'next_cursor': 'cursor123'}
            },
            {
                'ok': True,
                'members': [{'id': 'U2', 'name': 'user2', 'real_name': 'User 2', 'profile': {}}],
                'response_metadata': {}
            }
        ]
        
        result = slack_get_users()
        
        assert 'U1' in result
        assert 'U2' in result
        assert mock_api_call.call_count == 2

    @patch('lib.slack.slack_api_call')
    def test_returns_cached_data_within_ttl(self, mock_api_call):
        """Test that cached data is returned within TTL."""
        import lib.slack as slack_module
        from search_server_funcs import slack_get_users
        
        # Pre-populate cache in the actual module
        slack_module._slack_users_cache = {
            'data': {'U999': {'id': 'U999', 'name': 'Cached User'}},
            'timestamp': time.time()
        }
        
        result = slack_get_users()
        
        # Should not call API
        mock_api_call.assert_not_called()
        assert 'U999' in result

    @patch('lib.slack.slack_api_call')
    def test_refreshes_expired_cache(self, mock_api_call):
        """Test that expired cache is refreshed."""
        import lib.slack as slack_module
        from search_server_funcs import slack_get_users
        
        # Pre-populate with expired cache in the actual module
        slack_module._slack_users_cache = {
            'data': {'U999': {'id': 'U999', 'name': 'Old User'}},
            'timestamp': time.time() - 1000  # Expired
        }
        
        mock_api_call.return_value = {
            'ok': True,
            'members': [{'id': 'U1', 'name': 'new_user', 'real_name': 'New User', 'profile': {}}],
            'response_metadata': {}
        }
        
        result = slack_get_users()
        
        mock_api_call.assert_called()
        assert 'U1' in result

    @patch('lib.slack.slack_api_call')
    def test_handles_api_error(self, mock_api_call):
        """Test handling of API errors."""
        import lib.slack as slack_module
        from search_server_funcs import slack_get_users
        
        mock_api_call.return_value = {'ok': False, 'error': 'not_authed'}
        
        result = slack_get_users()
        
        assert result == {}


# =============================================================================
# Test slack_get_unread_counts
# =============================================================================

class TestSlackGetUnreadCounts:
    """Test the slack_get_unread_counts function."""

    @patch('lib.slack.slack_api_call')
    def test_returns_unread_counts(self, mock_api_call):
        """Test that unread counts are returned correctly."""
        from search_server_funcs import slack_get_unread_counts
        
        mock_api_call.return_value = {
            'ok': True,
            'ims': [{'id': 'D123', 'has_unreads': True, 'mention_count': 2}],
            'channels': [{'id': 'C456', 'has_unreads': False, 'mention_count': 0}],
            'mpims': [{'id': 'G789', 'has_unreads': True}],
            'threads': {'has_unreads': True, 'mention_count': 5}
        }
        
        result = slack_get_unread_counts()
        
        assert len(result['ims']) == 1
        assert result['ims'][0]['mention_count'] == 2
        assert len(result['channels']) == 1
        assert result['threads']['mention_count'] == 5

    @patch('lib.slack.slack_api_call')
    def test_returns_empty_on_api_failure(self, mock_api_call):
        """Test that empty structure is returned on API failure."""
        from search_server_funcs import slack_get_unread_counts
        
        mock_api_call.return_value = {'ok': False, 'error': 'not_authed'}
        
        result = slack_get_unread_counts()
        
        assert result == {'ims': [], 'channels': [], 'mpims': [], 'threads': {}}

    @patch('lib.slack.slack_api_call')
    def test_calls_correct_api_method(self, mock_api_call):
        """Test that the correct API method is called."""
        from search_server_funcs import slack_get_unread_counts
        
        mock_api_call.return_value = {'ok': True, 'ims': [], 'channels': [], 'mpims': [], 'threads': {}}
        
        slack_get_unread_counts()
        
        mock_api_call.assert_called_once_with('client.counts', post_data={})


# =============================================================================
# Test slack_ts_to_iso (edge cases)
# =============================================================================

class TestSlackTsToIso:
    """Test the slack_ts_to_iso function with edge cases."""

    def test_valid_timestamp(self):
        """Test conversion of valid Slack timestamp."""
        from search_server_funcs import slack_ts_to_iso
        
        # Slack timestamp: Unix epoch + microseconds
        ts = "1706745600.000000"  # 2024-02-01 00:00:00 UTC (approx, depends on timezone)
        result = slack_ts_to_iso(ts)
        
        assert result is not None
        assert len(result) > 0
        # Should be ISO format
        assert 'T' in result

    def test_empty_string(self):
        """Test handling of empty string."""
        from search_server_funcs import slack_ts_to_iso
        
        result = slack_ts_to_iso('')
        assert result == ''

    def test_none_value(self):
        """Test handling of None value."""
        from search_server_funcs import slack_ts_to_iso
        
        result = slack_ts_to_iso(None)
        assert result == ''

    def test_invalid_string(self):
        """Test handling of invalid string."""
        from search_server_funcs import slack_ts_to_iso
        
        result = slack_ts_to_iso('not-a-timestamp')
        assert result == ''

    def test_integer_timestamp(self):
        """Test handling of integer timestamp (should still work)."""
        from search_server_funcs import slack_ts_to_iso
        
        result = slack_ts_to_iso(1706745600)
        assert result != ''
        assert 'T' in result

    def test_float_timestamp(self):
        """Test handling of float timestamp."""
        from search_server_funcs import slack_ts_to_iso
        
        result = slack_ts_to_iso(1706745600.123456)
        assert result != ''
        assert 'T' in result

    def test_very_old_timestamp(self):
        """Test handling of very old timestamp."""
        from search_server_funcs import slack_ts_to_iso
        
        result = slack_ts_to_iso("0.000000")  # Unix epoch
        assert result != ''

    def test_string_with_only_integer_part(self):
        """Test timestamp without microseconds."""
        from search_server_funcs import slack_ts_to_iso
        
        result = slack_ts_to_iso("1706745600")
        assert result != ''


# =============================================================================
# Test slack_get_conversations_fast
# =============================================================================

class TestSlackGetConversationsFast:
    """Test the slack_get_conversations_fast function."""

    @pytest.fixture(autouse=True)
    def reset_caches(self):
        """Reset caches before each test."""
        import search_server_funcs as funcs
        funcs._slack_users_cache = {"data": None, "timestamp": 0}
        yield
        funcs._slack_users_cache = {"data": None, "timestamp": 0}

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    @patch('lib.slack.slack_get_unread_counts')
    def test_returns_conversations_list(self, mock_unread, mock_users, mock_api_call):
        """Test that conversations are returned as a list."""
        from search_server_funcs import slack_get_conversations_fast
        
        mock_users.return_value = {'U123': {'id': 'U123', 'name': 'John', 'username': 'john'}}
        mock_unread.return_value = {
            'ims': [],
            'channels': [],
            'mpims': [],
            'threads': {'has_unreads': False, 'mention_count': 0}
        }
        mock_api_call.return_value = {'ok': True, 'channels': []}
        
        result = slack_get_conversations_fast(limit=10)
        
        assert isinstance(result, list)

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    @patch('lib.slack.slack_get_unread_counts')
    def test_includes_threads_with_unreads(self, mock_unread, mock_users, mock_api_call):
        """Test that threads are included when they have unreads."""
        from search_server_funcs import slack_get_conversations_fast
        
        mock_users.return_value = {}
        mock_unread.return_value = {
            'ims': [],
            'channels': [],
            'mpims': [],
            'threads': {'has_unreads': True, 'mention_count': 3, 'latest': '1706745600.000'}
        }
        mock_api_call.return_value = {'ok': True, 'channels': []}
        
        result = slack_get_conversations_fast(limit=10, unread_only=True)
        
        threads_item = next((c for c in result if c.get('channel_id') == 'threads'), None)
        assert threads_item is not None
        assert threads_item['unread_count'] == 3
        assert threads_item['type'] == 'thread'

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    @patch('lib.slack.slack_get_unread_counts')
    def test_respects_limit_parameter(self, mock_unread, mock_users, mock_api_call):
        """Test that results are limited by the limit parameter."""
        from search_server_funcs import slack_get_conversations_fast
        
        mock_users.return_value = {}
        mock_unread.return_value = {
            'ims': [{'id': f'D{i}', 'has_unreads': True} for i in range(30)],
            'channels': [],
            'mpims': [],
            'threads': {}
        }
        # Mock conversations.info to return DM info
        mock_api_call.return_value = {'ok': True, 'channel': {'is_im': True, 'user': 'U1'}, 'channels': []}
        
        result = slack_get_conversations_fast(limit=5)
        
        assert len(result) <= 5

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    @patch('lib.slack.slack_get_unread_counts')
    def test_unread_only_filters_results(self, mock_unread, mock_users, mock_api_call):
        """Test that unread_only=True filters to only unread items."""
        from search_server_funcs import slack_get_conversations_fast
        
        mock_users.return_value = {}
        mock_unread.return_value = {
            'ims': [],
            'channels': [],
            'mpims': [],
            'threads': {'has_unreads': False, 'mention_count': 0}
        }
        mock_api_call.return_value = {'ok': True, 'channels': []}
        
        result = slack_get_conversations_fast(limit=10, unread_only=True)
        
        # With no unreads, should be empty or only have threads with activity
        for item in result:
            # Items should either have unreads or be threads marker
            assert item.get('unread_count', 0) >= 0


# =============================================================================
# Test slack_get_conversations_with_unread
# =============================================================================

class TestSlackGetConversationsWithUnread:
    """Test the slack_get_conversations_with_unread backwards-compatibility wrapper."""

    @patch('lib.slack.slack_get_conversations_fast')
    def test_calls_fast_function(self, mock_fast):
        """Test that it calls slack_get_conversations_fast."""
        from search_server_funcs import slack_get_conversations_with_unread
        
        mock_fast.return_value = []
        
        slack_get_conversations_with_unread(types='im', limit=25)
        
        mock_fast.assert_called_once_with(limit=25, unread_only=False)

    @patch('lib.slack.slack_get_conversations_fast')
    def test_returns_result_from_fast_function(self, mock_fast):
        """Test that it returns the result from slack_get_conversations_fast."""
        from search_server_funcs import slack_get_conversations_with_unread
        
        expected = [{'channel_id': 'C123', 'name': 'test'}]
        mock_fast.return_value = expected
        
        result = slack_get_conversations_with_unread()
        
        assert result == expected


# =============================================================================
# Test slack_get_conversation_history_direct
# =============================================================================

class TestSlackGetConversationHistoryDirect:
    """Test the slack_get_conversation_history_direct function."""

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_returns_messages_list(self, mock_users, mock_api_call):
        """Test that messages are returned as a list."""
        from search_server_funcs import slack_get_conversation_history_direct
        
        mock_users.return_value = {'U123': {'name': 'John', 'username': 'john'}}
        mock_api_call.side_effect = [
            {'ok': True, 'messages': [
                {'text': 'Hello', 'user': 'U123', 'ts': '1706745600.000'}
            ]},
            {'ok': True, 'user_id': 'U456'}  # auth.test response
        ]
        
        result = slack_get_conversation_history_direct('C123', limit=10)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['text'] == 'Hello'
        assert result[0]['user'] == 'John'

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_returns_error_on_failure(self, mock_users, mock_api_call):
        """Test that error dict is returned on API failure."""
        from search_server_funcs import slack_get_conversation_history_direct
        
        mock_users.return_value = {}
        mock_api_call.return_value = {'ok': False, 'error': 'channel_not_found'}
        
        result = slack_get_conversation_history_direct('C123')
        
        assert result['status'] == 'error'
        assert 'channel_not_found' in result['message']

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_handles_at_username_channel_error(self, mock_users, mock_api_call):
        """Test special handling of @username channel not found."""
        from search_server_funcs import slack_get_conversation_history_direct
        
        mock_users.return_value = {}
        mock_api_call.return_value = {'ok': False, 'error': 'channel_not_found'}
        
        result = slack_get_conversation_history_direct('@username')
        
        assert result['status'] == 'error'
        assert 'Cannot find channel' in result['message']

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_marks_own_messages(self, mock_users, mock_api_call):
        """Test that own messages are marked with is_me=True."""
        from search_server_funcs import slack_get_conversation_history_direct
        
        mock_users.return_value = {
            'U123': {'name': 'John'},
            'U456': {'name': 'Me'}
        }
        mock_api_call.side_effect = [
            {'ok': True, 'messages': [
                {'text': 'From other', 'user': 'U123', 'ts': '1.0'},
                {'text': 'From me', 'user': 'U456', 'ts': '2.0'}
            ]},
            {'ok': True, 'user_id': 'U456'}  # auth.test - I am U456
        ]
        
        result = slack_get_conversation_history_direct('C123')
        
        # Find the message from 'me'
        my_msg = next((m for m in result if m['user_id'] == 'U456'), None)
        other_msg = next((m for m in result if m['user_id'] == 'U123'), None)
        
        assert my_msg['is_me'] == True
        assert other_msg['is_me'] == False

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_reverses_message_order(self, mock_users, mock_api_call):
        """Test that messages are reversed to show oldest first."""
        from search_server_funcs import slack_get_conversation_history_direct
        
        mock_users.return_value = {'U1': {'name': 'User'}}
        mock_api_call.side_effect = [
            {'ok': True, 'messages': [
                {'text': 'Newer', 'user': 'U1', 'ts': '2.0'},
                {'text': 'Older', 'user': 'U1', 'ts': '1.0'}
            ]},
            {'ok': True, 'user_id': 'U999'}
        ]
        
        result = slack_get_conversation_history_direct('C123')
        
        # Should be oldest first
        assert result[0]['text'] == 'Older'
        assert result[1]['text'] == 'Newer'


# =============================================================================
# Test slack_get_threads
# =============================================================================

class TestSlackGetThreads:
    """Test the slack_get_threads function."""

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_returns_threads_list(self, mock_users, mock_api_call):
        """Test that threads are returned as a list."""
        from search_server_funcs import slack_get_threads
        
        mock_users.return_value = {'U123': {'name': 'John', 'username': 'john'}}
        mock_api_call.return_value = {
            'ok': True,
            'threads': [{
                'root_msg': {
                    'channel': 'C123',
                    'ts': '1.0',
                    'thread_ts': '1.0',
                    'text': 'Original message',
                    'user': 'U123',
                    'reply_count': 5
                },
                'unread_replies': [
                    {'user': 'U123', 'text': 'Reply text', 'ts': '2.0'}
                ]
            }]
        }
        
        result = slack_get_threads(limit=10)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['channel_id'] == 'C123'
        assert result[0]['root_text'] == 'Original message'

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_returns_empty_on_no_threads(self, mock_users, mock_api_call):
        """Test that empty list is returned when no threads."""
        from search_server_funcs import slack_get_threads
        
        mock_users.return_value = {}
        mock_api_call.return_value = {'ok': True, 'threads': []}
        
        result = slack_get_threads()
        
        assert result == []

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_includes_unread_count(self, mock_users, mock_api_call):
        """Test that unread reply count is included."""
        from search_server_funcs import slack_get_threads
        
        mock_users.return_value = {'U1': {'name': 'User'}}
        mock_api_call.return_value = {
            'ok': True,
            'threads': [{
                'root_msg': {'channel': 'C1', 'ts': '1.0', 'text': 'Root', 'user': 'U1'},
                'unread_replies': [
                    {'user': 'U1', 'text': 'Reply 1', 'ts': '2.0'},
                    {'user': 'U1', 'text': 'Reply 2', 'ts': '3.0'},
                    {'user': 'U1', 'text': 'Reply 3', 'ts': '4.0'}
                ]
            }]
        }
        
        result = slack_get_threads()
        
        assert result[0]['unread_count'] == 3


# =============================================================================
# Test slack_get_thread_replies
# =============================================================================

class TestSlackGetThreadReplies:
    """Test the slack_get_thread_replies function."""

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_returns_thread_messages(self, mock_users, mock_api_call):
        """Test that thread replies are returned."""
        from search_server_funcs import slack_get_thread_replies
        
        mock_users.return_value = {'U123': {'name': 'John', 'username': 'john'}}
        mock_api_call.side_effect = [
            {'ok': True, 'messages': [
                {'text': 'Root message', 'user': 'U123', 'ts': '1.0', 'reply_count': 2},
                {'text': 'Reply 1', 'user': 'U123', 'ts': '1.1'},
                {'text': 'Reply 2', 'user': 'U123', 'ts': '1.2'}
            ]},
            {'ok': True, 'user_id': 'U456'}  # auth.test
        ]
        
        result = slack_get_thread_replies('C123', '1.0', limit=50)
        
        assert isinstance(result, list)
        assert len(result) == 3

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_returns_error_on_failure(self, mock_users, mock_api_call):
        """Test that error dict is returned on API failure."""
        from search_server_funcs import slack_get_thread_replies
        
        mock_users.return_value = {}
        mock_api_call.return_value = {'ok': False, 'error': 'thread_not_found'}
        
        result = slack_get_thread_replies('C123', '1.0')
        
        assert result['status'] == 'error'

    @patch('lib.slack.slack_api_call')
    @patch('lib.slack.slack_get_users')
    def test_marks_root_message(self, mock_users, mock_api_call):
        """Test that root message is marked with is_root=True."""
        from search_server_funcs import slack_get_thread_replies
        
        mock_users.return_value = {'U1': {'name': 'User'}}
        mock_api_call.side_effect = [
            {'ok': True, 'messages': [
                {'text': 'Root', 'user': 'U1', 'ts': '1.0'},  # This is the thread_ts
                {'text': 'Reply', 'user': 'U1', 'ts': '1.1'}
            ]},
            {'ok': True, 'user_id': 'U999'}
        ]
        
        result = slack_get_thread_replies('C123', '1.0')
        
        root_msg = next((m for m in result if m['ts'] == '1.0'), None)
        reply_msg = next((m for m in result if m['ts'] == '1.1'), None)
        
        assert root_msg['is_root'] == True
        assert reply_msg['is_root'] == False


# =============================================================================
# Test slack_send_message_direct
# =============================================================================

class TestSlackSendMessageDirect:
    """Test the slack_send_message_direct function."""

    @patch('lib.slack.slack_api_call')
    def test_sends_message_successfully(self, mock_api_call):
        """Test successful message sending."""
        from search_server_funcs import slack_send_message_direct
        
        mock_api_call.return_value = {'ok': True, 'ts': '123.456', 'channel': 'C123'}
        
        result = slack_send_message_direct('C123', 'Hello world')
        
        assert result['success'] == True
        assert result['ts'] == '123.456'
        assert result['channel'] == 'C123'

    @patch('lib.slack.slack_api_call')
    def test_sends_thread_reply(self, mock_api_call):
        """Test sending a reply in a thread."""
        from search_server_funcs import slack_send_message_direct
        
        mock_api_call.return_value = {'ok': True, 'ts': '456.789', 'channel': 'C123'}
        
        result = slack_send_message_direct('C123', 'Thread reply', thread_ts='123.456')
        
        # Verify the call included thread_ts
        call_kwargs = mock_api_call.call_args[1]
        assert call_kwargs['post_data']['thread_ts'] == '123.456'

    @patch('lib.slack.slack_api_call')
    def test_returns_error_on_failure(self, mock_api_call):
        """Test error handling on send failure."""
        from search_server_funcs import slack_send_message_direct
        
        mock_api_call.return_value = {'ok': False, 'error': 'channel_not_found'}
        
        result = slack_send_message_direct('C123', 'Hello')
        
        assert result['success'] == False
        assert 'channel_not_found' in result['error']

    @patch('lib.slack.slack_api_call')
    def test_calls_correct_api_method(self, mock_api_call):
        """Test that chat.postMessage API is called."""
        from search_server_funcs import slack_send_message_direct
        
        mock_api_call.return_value = {'ok': True, 'ts': '1.0', 'channel': 'C1'}
        
        slack_send_message_direct('C123', 'Test')
        
        mock_api_call.assert_called_once()
        assert mock_api_call.call_args[0][0] == 'chat.postMessage'


# =============================================================================
# Test slack_get_dm_channel_for_user
# =============================================================================

class TestSlackGetDmChannelForUser:
    """Test the slack_get_dm_channel_for_user function."""

    @patch('lib.slack.slack_api_call')
    def test_returns_channel_id_on_success(self, mock_api_call):
        """Test that channel ID is returned on success."""
        from search_server_funcs import slack_get_dm_channel_for_user
        
        mock_api_call.return_value = {
            'ok': True,
            'channel': {'id': 'D123456'}
        }
        
        result = slack_get_dm_channel_for_user('U123')
        
        assert result['channel_id'] == 'D123456'

    @patch('lib.slack.slack_api_call')
    def test_returns_error_on_failure(self, mock_api_call):
        """Test that error is returned on API failure."""
        from search_server_funcs import slack_get_dm_channel_for_user
        
        mock_api_call.return_value = {'ok': False, 'error': 'user_not_found'}
        
        result = slack_get_dm_channel_for_user('U999')
        
        assert 'error' in result
        assert 'user_not_found' in result['error']

    @patch('lib.slack.slack_api_call')
    def test_calls_conversations_open(self, mock_api_call):
        """Test that conversations.open API is called."""
        from search_server_funcs import slack_get_dm_channel_for_user
        
        mock_api_call.return_value = {'ok': True, 'channel': {'id': 'D1'}}
        
        slack_get_dm_channel_for_user('U123')
        
        mock_api_call.assert_called_once_with('conversations.open', post_data={'users': 'U123'})


# =============================================================================
# Test slack_find_user_by_username
# =============================================================================

class TestSlackFindUserByUsername:
    """Test the slack_find_user_by_username function."""

    @patch('lib.slack.slack_get_users')
    def test_finds_user_by_exact_username(self, mock_get_users):
        """Test finding user by exact username match."""
        from search_server_funcs import slack_find_user_by_username
        
        mock_get_users.return_value = {
            'U123': {'id': 'U123', 'name': 'John Doe', 'username': 'johndoe'},
            'U456': {'id': 'U456', 'name': 'Jane Smith', 'username': 'janesmith'}
        }
        
        result = slack_find_user_by_username('johndoe')
        
        assert result is not None
        assert result['id'] == 'U123'
        assert result['username'] == 'johndoe'

    @patch('lib.slack.slack_get_users')
    def test_returns_none_when_not_found(self, mock_get_users):
        """Test that None is returned when user not found."""
        from search_server_funcs import slack_find_user_by_username
        
        mock_get_users.return_value = {
            'U123': {'id': 'U123', 'name': 'John Doe', 'username': 'johndoe'}
        }
        
        result = slack_find_user_by_username('nonexistent')
        
        assert result is None

    @patch('lib.slack.slack_get_users')
    def test_case_insensitive_search(self, mock_get_users):
        """Test that search is case-insensitive."""
        from search_server_funcs import slack_find_user_by_username
        
        mock_get_users.return_value = {
            'U123': {'id': 'U123', 'name': 'John', 'username': 'JohnDoe'}
        }
        
        result = slack_find_user_by_username('JOHNDOE')
        
        assert result is not None
        assert result['id'] == 'U123'

    @patch('lib.slack.slack_get_users')
    def test_strips_at_symbol(self, mock_get_users):
        """Test that @ prefix is stripped from username."""
        from search_server_funcs import slack_find_user_by_username
        
        mock_get_users.return_value = {
            'U123': {'id': 'U123', 'name': 'John', 'username': 'johndoe'}
        }
        
        result = slack_find_user_by_username('@johndoe')
        
        assert result is not None
        assert result['id'] == 'U123'


# =============================================================================
# Test slack_mark_conversation_read
# =============================================================================

class TestSlackMarkConversationRead:
    """Test the slack_mark_conversation_read function."""

    @patch('lib.slack.slack_api_call')
    def test_marks_conversation_read_successfully(self, mock_api_call):
        """Test successful marking of conversation as read."""
        from search_server_funcs import slack_mark_conversation_read
        
        mock_api_call.return_value = {'ok': True}
        
        result = slack_mark_conversation_read('C123', '1706745600.000')
        
        assert result['success'] == True

    @patch('lib.slack.slack_api_call')
    def test_returns_failure_on_error(self, mock_api_call):
        """Test that failure is returned on API error."""
        from search_server_funcs import slack_mark_conversation_read
        
        mock_api_call.return_value = {'ok': False, 'error': 'channel_not_found'}
        
        result = slack_mark_conversation_read('C999', '1.0')
        
        assert result['success'] == False

    @patch('lib.slack.slack_api_call')
    def test_calls_conversations_mark_api(self, mock_api_call):
        """Test that conversations.mark API is called with correct params."""
        from search_server_funcs import slack_mark_conversation_read
        
        mock_api_call.return_value = {'ok': True}
        
        slack_mark_conversation_read('C123', '456.789')
        
        mock_api_call.assert_called_once_with(
            'conversations.mark',
            post_data={'channel': 'C123', 'ts': '456.789'}
        )


# Module generation removed - handled by generate_test_module.py

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
