"""
Tests for Atlassian/MCP-related functions in search-server.py

Run with: pytest tests/test_atlassian.py -v
"""
import sys
import os
import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock, mock_open, call

# Add tests directory to path
sys.path.insert(0, os.path.dirname(__file__))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_mcp_config():
    """Standard MCP config for Atlassian."""
    return {
        "mcpServers": {
            "atlassian": {
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-server-atlassian"],
                "env": {"ATLASSIAN_API_TOKEN": "test-token"}
            },
            "slack": {
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-server-slack"],
                "env": {"SLACK_TOKEN": "xoxb-test"}
            }
        }
    }


@pytest.fixture
def mock_jira_search_response():
    """Mock Jira search response from MCP."""
    return {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "results": [
                    {
                        "id": "ari:cloud:jira:site:issue/12345",
                        "title": "PROJ-123: Fix login bug",
                        "url": "https://test.atlassian.net/browse/PROJ-123"
                    },
                    {
                        "id": "ari:cloud:jira:site:issue/12346",
                        "title": "PROJ-124: Add new feature",
                        "url": "https://test.atlassian.net/browse/PROJ-124"
                    }
                ]
            })
        }]
    }


@pytest.fixture
def mock_confluence_search_response():
    """Mock Confluence search response from MCP."""
    return {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "results": [
                    {
                        "id": "ari:cloud:confluence:site:page/98765",
                        "title": "Architecture Overview",
                        "url": "https://test.atlassian.net/wiki/spaces/TEAM/pages/98765",
                        "space": {"name": "Team Space"}
                    }
                ]
            })
        }]
    }


@pytest.fixture
def reset_atlassian_globals():
    """Reset global state before each test."""
    import search_server_funcs
    search_server_funcs._atlassian_process = None
    search_server_funcs._atlassian_initialized = False
    search_server_funcs._atlassian_msg_id = 0
    yield
    # Cleanup after test
    search_server_funcs._atlassian_process = None
    search_server_funcs._atlassian_initialized = False
    search_server_funcs._atlassian_msg_id = 0


# =============================================================================
# Tests for load_mcp_config()
# =============================================================================

class TestLoadMcpConfig:
    """Tests for load_mcp_config function."""

    def test_load_mcp_config_file_not_found(self):
        """Test returns empty dict when config file doesn't exist."""
        from search_server_funcs import load_mcp_config
        
        with patch('search_server_funcs.os.path.exists', return_value=False):
            result = load_mcp_config()
        
        assert result == {}

    def test_load_mcp_config_returns_dict(self):
        """Test always returns a dict type."""
        from search_server_funcs import load_mcp_config
        
        with patch('search_server_funcs.os.path.exists', return_value=False):
            result = load_mcp_config()
        
        assert isinstance(result, dict)

    def test_load_mcp_config_valid_json(self, mock_mcp_config):
        """Test successfully loads valid JSON config."""
        from search_server_funcs import load_mcp_config
        
        with patch('search_server_funcs.os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(mock_mcp_config))):
                result = load_mcp_config()
        
        assert 'atlassian' in result
        assert result['atlassian']['command'] == 'npx'

    def test_load_mcp_config_invalid_json(self):
        """Test returns empty dict on invalid JSON."""
        from search_server_funcs import load_mcp_config
        
        with patch('search_server_funcs.os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data="not valid json {{")):
                result = load_mcp_config()
        
        assert result == {}

    def test_load_mcp_config_missing_mcpservers_key(self):
        """Test returns empty dict when mcpServers key is missing."""
        from search_server_funcs import load_mcp_config
        
        config_without_servers = {"someOtherKey": "value"}
        with patch('search_server_funcs.os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(config_without_servers))):
                result = load_mcp_config()
        
        assert result == {}

    def test_load_mcp_config_file_read_error(self):
        """Test returns empty dict on file read error."""
        from search_server_funcs import load_mcp_config
        
        with patch('search_server_funcs.os.path.exists', return_value=True):
            with patch('builtins.open', side_effect=IOError("Permission denied")):
                result = load_mcp_config()
        
        assert result == {}

    def test_load_mcp_config_empty_file(self):
        """Test returns empty dict when file is empty."""
        from search_server_funcs import load_mcp_config
        
        with patch('search_server_funcs.os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data="")):
                result = load_mcp_config()
        
        assert result == {}

    def test_load_mcp_config_empty_mcpservers(self):
        """Test returns empty dict when mcpServers is empty."""
        from search_server_funcs import load_mcp_config
        
        config = {"mcpServers": {}}
        with patch('search_server_funcs.os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(config))):
                result = load_mcp_config()
        
        assert result == {}

    def test_load_mcp_config_multiple_servers(self, mock_mcp_config):
        """Test loads config with multiple MCP servers."""
        from search_server_funcs import load_mcp_config
        
        with patch('search_server_funcs.os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(mock_mcp_config))):
                result = load_mcp_config()
        
        assert 'atlassian' in result
        assert 'slack' in result
        assert len(result) == 2


# =============================================================================
# Tests for get_atlassian_process()
# =============================================================================

class TestGetAtlassianProcess:
    """Tests for get_atlassian_process function."""

    def test_returns_none_when_no_config(self, reset_atlassian_globals):
        """Test returns None when atlassian config is missing."""
        from search_server_funcs import get_atlassian_process
        
        with patch('search_server_funcs.load_mcp_config', return_value={}):
            result = get_atlassian_process()
        
        assert result is None

    def test_returns_none_when_no_command(self, reset_atlassian_globals):
        """Test returns None when command is not specified."""
        from search_server_funcs import get_atlassian_process
        
        config = {"atlassian": {"args": ["some-arg"]}}
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            result = get_atlassian_process()
        
        assert result is None

    def test_returns_existing_running_process(self, reset_atlassian_globals):
        """Test returns existing process if still running."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Process is running
        search_server_funcs._atlassian_process = mock_proc
        
        result = get_atlassian_process()
        
        assert result is mock_proc

    def test_starts_new_process_when_dead(self, reset_atlassian_globals, mock_mcp_config):
        """Test starts new process when existing one has died."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        # Existing dead process
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 1  # Process exited
        search_server_funcs._atlassian_process = dead_proc
        
        # New process mock
        new_proc = MagicMock()
        new_proc.poll.return_value = None
        new_proc.stdin = MagicMock()
        new_proc.stdout = MagicMock()
        new_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"capabilities": {}}
        }).encode()
        
        with patch('search_server_funcs.load_mcp_config', return_value=mock_mcp_config['mcpServers']):
            with patch('search_server_funcs.subprocess.Popen', return_value=new_proc):
                with patch('search_server_funcs.time.sleep'):
                    result = get_atlassian_process()
        
        assert result is new_proc
        assert search_server_funcs._atlassian_initialized is True

    def test_starts_process_and_initializes(self, reset_atlassian_globals, mock_mcp_config):
        """Test starts process and performs MCP initialization handshake."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"capabilities": {}, "serverInfo": {"name": "atlassian"}}
        }).encode()
        
        with patch('search_server_funcs.load_mcp_config', return_value=mock_mcp_config['mcpServers']):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                with patch('search_server_funcs.time.sleep'):
                    result = get_atlassian_process()
        
        assert result is mock_proc
        assert search_server_funcs._atlassian_initialized is True
        # Verify init request was sent
        assert mock_proc.stdin.write.called
        assert mock_proc.stdin.flush.called

    def test_initialization_fails_gracefully(self, reset_atlassian_globals, mock_mcp_config):
        """Test handles initialization failure gracefully."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        # Invalid JSON response
        mock_proc.stdout.readline.return_value = b"not json"
        
        with patch('search_server_funcs.load_mcp_config', return_value=mock_mcp_config['mcpServers']):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                with patch('search_server_funcs.time.sleep'):
                    result = get_atlassian_process()
        
        assert result is mock_proc
        assert search_server_funcs._atlassian_initialized is False

    def test_popen_exception_returns_none(self, reset_atlassian_globals, mock_mcp_config):
        """Test returns None when Popen raises exception."""
        from search_server_funcs import get_atlassian_process
        
        with patch('search_server_funcs.load_mcp_config', return_value=mock_mcp_config['mcpServers']):
            with patch('search_server_funcs.subprocess.Popen', side_effect=OSError("Command not found")):
                result = get_atlassian_process()
        
        assert result is None

    def test_empty_init_response(self, reset_atlassian_globals, mock_mcp_config):
        """Test handles empty initialization response."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b""  # Empty response
        
        with patch('search_server_funcs.load_mcp_config', return_value=mock_mcp_config['mcpServers']):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                with patch('search_server_funcs.time.sleep'):
                    result = get_atlassian_process()
        
        assert result is mock_proc
        assert search_server_funcs._atlassian_initialized is False

    def test_init_response_without_result(self, reset_atlassian_globals, mock_mcp_config):
        """Test handles initialization response without result key."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        # Response without 'result' key
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "Server error"}
        }).encode()
        
        with patch('search_server_funcs.load_mcp_config', return_value=mock_mcp_config['mcpServers']):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                with patch('search_server_funcs.time.sleep'):
                    result = get_atlassian_process()
        
        assert result is mock_proc
        assert search_server_funcs._atlassian_initialized is False

    def test_sends_initialized_notification(self, reset_atlassian_globals, mock_mcp_config):
        """Test sends notifications/initialized after successful init."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}
        }).encode()
        
        with patch('search_server_funcs.load_mcp_config', return_value=mock_mcp_config['mcpServers']):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                with patch('search_server_funcs.time.sleep'):
                    get_atlassian_process()
        
        # Check that the initialized notification was sent (second write call)
        write_calls = mock_proc.stdin.write.call_args_list
        assert len(write_calls) >= 2
        # Second call should be the initialized notification
        second_call_data = write_calls[1][0][0].decode()
        assert 'notifications/initialized' in second_call_data

    def test_resets_msg_id_on_new_process(self, reset_atlassian_globals, mock_mcp_config):
        """Test message ID is reset when starting new process."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        # Set a high msg_id as if there were previous calls
        search_server_funcs._atlassian_msg_id = 100
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        with patch('search_server_funcs.load_mcp_config', return_value=mock_mcp_config['mcpServers']):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                with patch('search_server_funcs.time.sleep'):
                    get_atlassian_process()
        
        # After starting, msg_id should be 1 (used for init)
        assert search_server_funcs._atlassian_msg_id == 1

    def test_config_without_env_vars(self, reset_atlassian_globals):
        """Test process starts even without env vars in config."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        config = {"atlassian": {"command": "npx", "args": ["-y", "mcp-server"]}}
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc) as mock_popen:
                with patch('search_server_funcs.time.sleep'):
                    result = get_atlassian_process()
        
        assert result is mock_proc
        mock_popen.assert_called_once()


# =============================================================================
# Tests for call_atlassian_tool()
# =============================================================================

class TestCallAtlassianTool:
    """Tests for call_atlassian_tool function."""

    def test_returns_error_when_no_process(self, reset_atlassian_globals):
        """Test returns error when process is not available."""
        from search_server_funcs import call_atlassian_tool
        
        with patch('search_server_funcs.get_atlassian_process', return_value=None):
            result = call_atlassian_tool('search', {'query': 'test'})
        
        assert 'error' in result
        assert 'not available' in result['error']

    def test_returns_error_when_process_dead(self, reset_atlassian_globals):
        """Test returns error when process has died."""
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Process exited
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            result = call_atlassian_tool('search', {'query': 'test'})
        
        assert 'error' in result
        assert 'not available' in result['error']

    def test_returns_error_when_not_initialized(self, reset_atlassian_globals):
        """Test returns error when MCP not initialized."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        search_server_funcs._atlassian_initialized = False
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            result = call_atlassian_tool('search', {'query': 'test'})
        
        assert 'error' in result
        assert 'not initialized' in result['error']

    def test_successful_tool_call(self, reset_atlassian_globals):
        """Test successful MCP tool call."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "Success"}]}
        }).encode()
        
        search_server_funcs._atlassian_initialized = True
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                result = call_atlassian_tool('search', {'query': 'test'})
        
        assert 'content' in result
        assert result['content'][0]['text'] == 'Success'

    def test_timeout_handling(self, reset_atlassian_globals):
        """Test timeout returns appropriate error."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        
        search_server_funcs._atlassian_initialized = True
        
        # select returns empty (timeout)
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([], [], [])):
                result = call_atlassian_tool('search', {'query': 'test'}, timeout=5)
        
        assert 'error' in result
        assert 'timeout' in result['error'].lower()

    def test_error_response_from_mcp(self, reset_atlassian_globals):
        """Test handles error response from MCP server."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid request"}
        }).encode()
        
        search_server_funcs._atlassian_initialized = True
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                result = call_atlassian_tool('search', {'query': 'test'})
        
        assert 'error' in result

    def test_json_decode_error(self, reset_atlassian_globals):
        """Test handles JSON decode error in response."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b"invalid json {{"
        
        search_server_funcs._atlassian_initialized = True
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                result = call_atlassian_tool('search', {'query': 'test'})
        
        assert 'error' in result

    def test_increments_message_id(self, reset_atlassian_globals):
        """Test message ID increments with each call."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        search_server_funcs._atlassian_initialized = True
        initial_id = search_server_funcs._atlassian_msg_id
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                call_atlassian_tool('search', {'query': 'test1'})
                call_atlassian_tool('search', {'query': 'test2'})
        
        assert search_server_funcs._atlassian_msg_id == initial_id + 2

    def test_exception_during_call(self, reset_atlassian_globals):
        """Test handles exceptions during tool call."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write.side_effect = IOError("Broken pipe")
        
        search_server_funcs._atlassian_initialized = True
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            result = call_atlassian_tool('search', {'query': 'test'})
        
        assert 'error' in result

    def test_empty_response_line(self, reset_atlassian_globals):
        """Test handles empty response line."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b""  # Empty line
        
        search_server_funcs._atlassian_initialized = True
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                result = call_atlassian_tool('search', {'query': 'test'})
        
        # Should return timeout error since no valid response
        assert 'error' in result

    def test_default_timeout_is_15_seconds(self, reset_atlassian_globals):
        """Test default timeout is 15 seconds."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        search_server_funcs._atlassian_initialized = True
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])) as mock_select:
                call_atlassian_tool('search', {'query': 'test'})
        
        # Check select was called with timeout=15
        mock_select.assert_called_with([mock_proc.stdout], [], [], 15)

    def test_custom_timeout(self, reset_atlassian_globals):
        """Test custom timeout is passed to select."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        search_server_funcs._atlassian_initialized = True
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])) as mock_select:
                call_atlassian_tool('search', {'query': 'test'}, timeout=30)
        
        mock_select.assert_called_with([mock_proc.stdout], [], [], 30)

    def test_sends_correct_request_format(self, reset_atlassian_globals):
        """Test sends correctly formatted JSON-RPC request."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        search_server_funcs._atlassian_initialized = True
        search_server_funcs._atlassian_msg_id = 5
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                call_atlassian_tool('my_tool', {'arg1': 'value1'})
        
        # Verify the request format
        write_call = mock_proc.stdin.write.call_args[0][0].decode()
        request = json.loads(write_call.strip())
        assert request['jsonrpc'] == '2.0'
        assert request['method'] == 'tools/call'
        assert request['id'] == 6  # 5 + 1
        assert request['params']['name'] == 'my_tool'
        assert request['params']['arguments'] == {'arg1': 'value1'}

    def test_flush_after_write(self, reset_atlassian_globals):
        """Test flushes stdin after writing request."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        search_server_funcs._atlassian_initialized = True
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                call_atlassian_tool('search', {'query': 'test'})
        
        mock_proc.stdin.flush.assert_called()


# =============================================================================
# Tests for call_mcp_tool()
# =============================================================================

class TestCallMcpTool:
    """Tests for call_mcp_tool function (generic MCP caller)."""

    def test_returns_error_when_server_not_configured(self):
        """Test returns error when server is not in config."""
        from search_server_funcs import call_mcp_tool
        
        with patch('search_server_funcs.load_mcp_config', return_value={}):
            result = call_mcp_tool('unknown_server', 'some_tool', {})
        
        assert 'error' in result
        assert 'not configured' in result['error']

    def test_returns_error_when_no_command(self):
        """Test returns error when command not specified."""
        from search_server_funcs import call_mcp_tool
        
        config = {"test_server": {"args": ["arg1"]}}
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            result = call_mcp_tool('test_server', 'some_tool', {})
        
        assert 'error' in result
        assert 'No command' in result['error']

    def test_successful_mcp_call(self):
        """Test successful MCP tool call via subprocess."""
        from search_server_funcs import call_mcp_tool
        
        config = {"slack": {"command": "npx", "args": ["-y", "mcp-slack"]}}
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"data": "success"}}).encode(),
            b""
        )
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                result = call_mcp_tool('slack', 'conversations_list', {})
        
        assert result == {"data": "success"}

    def test_timeout_expired(self):
        """Test handles subprocess timeout."""
        from search_server_funcs import call_mcp_tool
        
        config = {"slack": {"command": "npx", "args": []}}
        
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
        mock_proc.kill = MagicMock()
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                result = call_mcp_tool('slack', 'conversations_list', {})
        
        assert 'error' in result
        assert 'timed out' in result['error'].lower()
        mock_proc.kill.assert_called_once()

    def test_handles_multiline_json_response(self):
        """Test parses last valid JSON from multiline output."""
        from search_server_funcs import call_mcp_tool
        
        config = {"slack": {"command": "npx", "args": []}}
        
        # Multiple JSON lines, should use last one with result
        multiline_response = (
            '{"jsonrpc": "2.0", "method": "log"}\n'
            '{"jsonrpc": "2.0", "id": 1, "result": {"final": "data"}}\n'
        )
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (multiline_response.encode(), b"")
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                result = call_mcp_tool('slack', 'test_tool', {})
        
        assert result == {"final": "data"}

    def test_handles_error_in_response(self):
        """Test returns error from MCP error response."""
        from search_server_funcs import call_mcp_tool
        
        config = {"slack": {"command": "npx", "args": []}}
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": "Method not found"}
            }).encode(),
            b""
        )
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                result = call_mcp_tool('slack', 'unknown_tool', {})
        
        assert 'error' in result

    def test_no_valid_response(self):
        """Test handles invalid/non-JSON output."""
        from search_server_funcs import call_mcp_tool
        
        config = {"slack": {"command": "npx", "args": []}}
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"some random output", b"")
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                result = call_mcp_tool('slack', 'test_tool', {})
        
        assert 'error' in result
        assert 'No valid MCP response' in result['error']

    def test_uses_env_vars_from_config(self):
        """Test passes environment variables from config."""
        from search_server_funcs import call_mcp_tool
        
        config = {
            "slack": {
                "command": "npx",
                "args": [],
                "env": {"SLACK_TOKEN": "xoxb-test", "CUSTOM_VAR": "value"}
            }
        }
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode(),
            b""
        )
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc) as mock_popen:
                call_mcp_tool('slack', 'test', {})
        
        # Verify env was passed
        call_args = mock_popen.call_args
        assert 'env' in call_args.kwargs
        assert 'SLACK_TOKEN' in call_args.kwargs['env']

    def test_general_exception(self):
        """Test handles general exceptions."""
        from search_server_funcs import call_mcp_tool
        
        config = {"slack": {"command": "npx", "args": []}}
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', side_effect=Exception("Unexpected error")):
                result = call_mcp_tool('slack', 'test_tool', {})
        
        assert 'error' in result
        assert 'Unexpected error' in result['error']

    def test_empty_args_list(self):
        """Test handles config with empty args list."""
        from search_server_funcs import call_mcp_tool
        
        config = {"myserver": {"command": "mycommand", "args": []}}
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode(),
            b""
        )
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                result = call_mcp_tool('myserver', 'test', {})
        
        assert result == {"ok": True}

    def test_skips_non_json_lines(self):
        """Test skips lines that don't start with {."""
        from search_server_funcs import call_mcp_tool
        
        config = {"slack": {"command": "npx", "args": []}}
        
        multiline_response = (
            'Starting server...\n'
            'Listening on port 3000\n'
            '{"jsonrpc": "2.0", "id": 1, "result": {"data": "found"}}\n'
        )
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (multiline_response.encode(), b"")
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                result = call_mcp_tool('slack', 'test', {})
        
        assert result == {"data": "found"}

    def test_handles_invalid_json_line(self):
        """Test handles line that looks like JSON but isn't valid."""
        from search_server_funcs import call_mcp_tool
        
        config = {"slack": {"command": "npx", "args": []}}
        
        multiline_response = (
            '{broken json\n'
            '{"jsonrpc": "2.0", "id": 1, "result": {"valid": "data"}}\n'
        )
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (multiline_response.encode(), b"")
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc):
                result = call_mcp_tool('slack', 'test', {})
        
        assert result == {"valid": "data"}

    def test_uses_shell_true(self):
        """Test subprocess is run with shell=True."""
        from search_server_funcs import call_mcp_tool
        
        config = {"slack": {"command": "npx", "args": ["-y", "mcp-slack"]}}
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode(),
            b""
        )
        
        with patch('search_server_funcs.load_mcp_config', return_value=config):
            with patch('search_server_funcs.subprocess.Popen', return_value=mock_proc) as mock_popen:
                call_mcp_tool('slack', 'test', {})
        
        call_args = mock_popen.call_args
        assert call_args.kwargs.get('shell') is True


# =============================================================================
# Tests for search_atlassian()
# =============================================================================

class TestSearchAtlassian:
    """Tests for search_atlassian function."""

    def test_returns_both_jira_and_confluence(self, reset_atlassian_globals):
        """Test returns both Jira and Confluence results."""
        from search_server_funcs import search_atlassian
        
        # Combined response with both Jira and Confluence
        combined_response = {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [
                        {"id": "ari:cloud:jira:site:issue/1", "title": "PROJ-100: Bug fix", "url": ""},
                        {"id": "ari:cloud:confluence:site:page/2", "title": "Docs page", "url": ""}
                    ]
                })
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=combined_response):
            result = search_atlassian('test query', limit=5)
        
        assert 'jira' in result
        assert 'confluence' in result
        assert len(result['jira']) > 0
        assert len(result['confluence']) > 0

    def test_extracts_jira_key_from_title(self, reset_atlassian_globals):
        """Test extracts Jira issue key from title."""
        from search_server_funcs import search_atlassian
        
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [
                        {"id": "ari:cloud:jira:site:issue/1", "title": "ABC-123: Fix the thing", "url": ""}
                    ]
                })
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert result['jira'][0]['key'] == 'ABC-123'

    def test_respects_limit_parameter(self, reset_atlassian_globals):
        """Test respects the limit parameter."""
        from search_server_funcs import search_atlassian
        
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [
                        {"id": f"ari:cloud:jira:site:issue/{i}", "title": f"PROJ-{i}: Issue", "url": ""}
                        for i in range(20)
                    ]
                })
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=3)
        
        assert len(result['jira']) <= 3

    def test_handles_error_response(self, reset_atlassian_globals):
        """Test handles error from call_atlassian_tool."""
        from search_server_funcs import search_atlassian
        
        with patch('search_server_funcs.call_atlassian_tool', return_value={"error": "MCP not available"}):
            result = search_atlassian('test', limit=5)
        
        assert result['jira'] == []
        assert result['confluence'] == []
        assert 'error' in result

    def test_fallback_line_parsing(self, reset_atlassian_globals):
        """Test fallback to line-based parsing when JSON fails."""
        from search_server_funcs import search_atlassian
        
        response = {
            "content": [{
                "type": "text",
                "text": "PROJ-999: Some issue title\nAnother line without key"
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert len(result['jira']) > 0
        assert result['jira'][0]['key'] == 'PROJ-999'

    def test_handles_empty_content(self, reset_atlassian_globals):
        """Test handles empty content array."""
        from search_server_funcs import search_atlassian
        
        response = {"content": []}
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert result['jira'] == []
        assert result['confluence'] == []

    def test_handles_non_text_content_items(self, reset_atlassian_globals):
        """Test ignores non-text content items."""
        from search_server_funcs import search_atlassian
        
        response = {
            "content": [
                {"type": "image", "data": "base64..."},
                {"type": "text", "text": json.dumps({"results": [{"id": "ari:cloud:jira:site:issue/1", "title": "PROJ-1: Test", "url": ""}]})}
            ]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert len(result['jira']) == 1

    def test_handles_content_not_list(self, reset_atlassian_globals):
        """Test handles case where content is not a list."""
        from search_server_funcs import search_atlassian
        
        response = {"content": "not a list"}
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert result['jira'] == []
        assert result['confluence'] == []

    def test_truncates_long_titles(self, reset_atlassian_globals):
        """Test truncates titles longer than 150 characters."""
        from search_server_funcs import search_atlassian
        
        long_title = "PROJ-1: " + "x" * 200
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [{"id": "ari:cloud:jira:site:issue/1", "title": long_title, "url": ""}]
                })
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert len(result['jira'][0]['title']) == 150

    def test_extracts_confluence_space_name(self, reset_atlassian_globals):
        """Test extracts Confluence space name from response."""
        from search_server_funcs import search_atlassian
        
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [{
                        "id": "ari:cloud:confluence:site:page/1",
                        "title": "Docs",
                        "url": "",
                        "space": {"name": "Engineering"}
                    }]
                })
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert result['confluence'][0]['space'] == 'Engineering'

    def test_handles_missing_url(self, reset_atlassian_globals):
        """Test handles missing URL in results."""
        from search_server_funcs import search_atlassian
        
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [{"id": "ari:cloud:jira:site:issue/1", "title": "TEST-1: No URL"}]
                })
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            with patch('search_server_funcs.ATLASSIAN_DOMAIN', 'test.atlassian.net'):
                result = search_atlassian('test', limit=5)
        
        assert result['jira'][0]['url'] == 'https://test.atlassian.net/browse/TEST-1'

    def test_handles_non_dict_result(self, reset_atlassian_globals):
        """Test handles non-dict result from call_atlassian_tool."""
        from search_server_funcs import search_atlassian
        
        with patch('search_server_funcs.call_atlassian_tool', return_value="string result"):
            result = search_atlassian('test', limit=5)
        
        assert result['jira'] == []
        assert result['confluence'] == []
        assert 'error' in result

    def test_identifies_jira_by_issue_in_ari(self, reset_atlassian_globals):
        """Test identifies Jira issues by :issue/ in ARI."""
        from search_server_funcs import search_atlassian
        
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [{"id": "some:ari:with:issue/123", "title": "PROJ-1: Test", "url": ""}]
                })
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert len(result['jira']) == 1

    def test_identifies_confluence_by_page_in_ari(self, reset_atlassian_globals):
        """Test identifies Confluence pages by :page/ in ARI."""
        from search_server_funcs import search_atlassian
        
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [{"id": "some:ari:with:page/123", "title": "Wiki Page", "url": ""}]
                })
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert len(result['confluence']) == 1


# =============================================================================
# Tests for get_jira_context()
# =============================================================================

class TestGetJiraContext:
    """Tests for get_jira_context function."""

    def test_returns_only_jira_results(self, reset_atlassian_globals):
        """Test returns only Jira results from search."""
        from search_server_funcs import get_jira_context
        
        with patch('search_server_funcs.search_atlassian', return_value={
            'jira': [{'key': 'PROJ-1', 'title': 'Test'}],
            'confluence': [{'title': 'Doc page'}]
        }):
            result = get_jira_context('test query', limit=5)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['key'] == 'PROJ-1'

    def test_passes_limit_to_search(self, reset_atlassian_globals):
        """Test passes limit parameter to search_atlassian."""
        from search_server_funcs import get_jira_context
        
        with patch('search_server_funcs.search_atlassian', return_value={'jira': [], 'confluence': []}) as mock_search:
            get_jira_context('test', limit=10)
        
        mock_search.assert_called_once_with('test', 10)

    def test_returns_empty_list_on_error(self, reset_atlassian_globals):
        """Test returns empty list when search fails."""
        from search_server_funcs import get_jira_context
        
        with patch('search_server_funcs.search_atlassian', return_value={'error': 'Failed'}):
            result = get_jira_context('test', limit=5)
        
        assert result == []

    def test_handles_non_dict_response(self, reset_atlassian_globals):
        """Test handles non-dict response gracefully."""
        from search_server_funcs import get_jira_context
        
        with patch('search_server_funcs.search_atlassian', return_value=None):
            result = get_jira_context('test', limit=5)
        
        assert result == []

    def test_default_limit_is_5(self, reset_atlassian_globals):
        """Test default limit is 5."""
        from search_server_funcs import get_jira_context
        
        with patch('search_server_funcs.search_atlassian', return_value={'jira': [], 'confluence': []}) as mock_search:
            get_jira_context('test')
        
        mock_search.assert_called_once_with('test', 5)

    def test_returns_empty_when_jira_key_missing(self, reset_atlassian_globals):
        """Test returns empty list when jira key is missing from result."""
        from search_server_funcs import get_jira_context
        
        with patch('search_server_funcs.search_atlassian', return_value={'confluence': []}):
            result = get_jira_context('test', limit=5)
        
        assert result == []


# =============================================================================
# Tests for search_confluence()
# =============================================================================

class TestSearchConfluence:
    """Tests for search_confluence function."""

    def test_returns_only_confluence_results(self, reset_atlassian_globals):
        """Test returns only Confluence results from search."""
        from search_server_funcs import search_confluence
        
        with patch('search_server_funcs.search_atlassian', return_value={
            'jira': [{'key': 'PROJ-1', 'title': 'Test'}],
            'confluence': [{'title': 'Architecture Doc', 'space': 'TEAM'}]
        }):
            result = search_confluence('architecture', limit=5)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['title'] == 'Architecture Doc'

    def test_passes_limit_to_search(self, reset_atlassian_globals):
        """Test passes limit parameter to search_atlassian."""
        from search_server_funcs import search_confluence
        
        with patch('search_server_funcs.search_atlassian', return_value={'jira': [], 'confluence': []}) as mock_search:
            search_confluence('docs', limit=15)
        
        mock_search.assert_called_once_with('docs', 15)

    def test_returns_empty_list_on_error(self, reset_atlassian_globals):
        """Test returns empty list when search fails."""
        from search_server_funcs import search_confluence
        
        with patch('search_server_funcs.search_atlassian', return_value={'error': 'Connection failed'}):
            result = search_confluence('test', limit=5)
        
        assert result == []

    def test_handles_non_dict_response(self, reset_atlassian_globals):
        """Test handles non-dict response gracefully."""
        from search_server_funcs import search_confluence
        
        with patch('search_server_funcs.search_atlassian', return_value="unexpected"):
            result = search_confluence('test', limit=5)
        
        assert result == []

    def test_default_limit_is_5(self, reset_atlassian_globals):
        """Test default limit is 5."""
        from search_server_funcs import search_confluence
        
        with patch('search_server_funcs.search_atlassian', return_value={'jira': [], 'confluence': []}) as mock_search:
            search_confluence('docs')
        
        mock_search.assert_called_once_with('docs', 5)

    def test_returns_empty_when_confluence_key_missing(self, reset_atlassian_globals):
        """Test returns empty list when confluence key is missing from result."""
        from search_server_funcs import search_confluence
        
        with patch('search_server_funcs.search_atlassian', return_value={'jira': []}):
            result = search_confluence('test', limit=5)
        
        assert result == []


# =============================================================================
# Tests for list_atlassian_tools()
# =============================================================================

class TestListAtlassianTools:
    """Tests for list_atlassian_tools function."""

    def test_returns_error_when_no_process(self, reset_atlassian_globals):
        """Test returns error when process not available."""
        from search_server_funcs import list_atlassian_tools
        
        with patch('search_server_funcs.get_atlassian_process', return_value=None):
            result = list_atlassian_tools()
        
        assert 'error' in result
        assert 'not available' in result['error']

    def test_returns_error_when_process_dead(self, reset_atlassian_globals):
        """Test returns error when process has exited."""
        from search_server_funcs import list_atlassian_tools
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Exited
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            result = list_atlassian_tools()
        
        assert 'error' in result
        assert 'not available' in result['error']

    def test_successful_tools_list(self, reset_atlassian_globals):
        """Test successfully lists available tools."""
        from search_server_funcs import list_atlassian_tools
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {"name": "search", "description": "Search Jira and Confluence"},
                    {"name": "get_issue", "description": "Get Jira issue details"}
                ]
            }
        }).encode()
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                result = list_atlassian_tools()
        
        assert 'tools' in result
        assert len(result['tools']) == 2

    def test_timeout_listing_tools(self, reset_atlassian_globals):
        """Test handles timeout when listing tools."""
        from search_server_funcs import list_atlassian_tools
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([], [], [])):
                result = list_atlassian_tools()
        
        assert 'error' in result
        assert 'Timeout' in result['error']

    def test_exception_during_listing(self, reset_atlassian_globals):
        """Test handles exception during tools listing."""
        from search_server_funcs import list_atlassian_tools
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write.side_effect = IOError("Broken pipe")
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            result = list_atlassian_tools()
        
        assert 'error' in result

    def test_increments_message_id(self, reset_atlassian_globals):
        """Test message ID increments when listing tools."""
        import search_server_funcs
        from search_server_funcs import list_atlassian_tools
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {"tools": []}
        }).encode()
        
        initial_id = search_server_funcs._atlassian_msg_id
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                list_atlassian_tools()
        
        assert search_server_funcs._atlassian_msg_id == initial_id + 1

    def test_sends_correct_method(self, reset_atlassian_globals):
        """Test sends tools/list method."""
        import search_server_funcs
        from search_server_funcs import list_atlassian_tools
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {"tools": []}
        }).encode()
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                list_atlassian_tools()
        
        write_call = mock_proc.stdin.write.call_args[0][0].decode()
        request = json.loads(write_call.strip())
        assert request['method'] == 'tools/list'

    def test_uses_10_second_timeout(self, reset_atlassian_globals):
        """Test uses 10 second timeout for listing tools."""
        from search_server_funcs import list_atlassian_tools
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {"tools": []}
        }).encode()
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])) as mock_select:
                list_atlassian_tools()
        
        mock_select.assert_called_with([mock_proc.stdout], [], [], 10)

    def test_returns_empty_result_on_empty_response(self, reset_atlassian_globals):
        """Test returns empty dict when response is empty."""
        from search_server_funcs import list_atlassian_tools
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b""
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                result = list_atlassian_tools()
        
        # Should return timeout since empty response
        assert 'error' in result


# =============================================================================
# Integration-style tests (testing function interactions)
# =============================================================================

class TestAtlassianIntegration:
    """Integration tests for Atlassian MCP functions working together."""

    def test_process_restart_on_death(self, reset_atlassian_globals, mock_mcp_config):
        """Test process is restarted when it dies between calls."""
        import search_server_funcs
        from search_server_funcs import get_atlassian_process
        
        # First call - start process
        proc1 = MagicMock()
        proc1.poll.return_value = None
        proc1.stdin = MagicMock()
        proc1.stdout = MagicMock()
        proc1.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        # Second call - process died, need new one
        proc2 = MagicMock()
        proc2.poll.return_value = None
        proc2.stdin = MagicMock()
        proc2.stdout = MagicMock()
        proc2.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        popen_calls = [proc1, proc2]
        
        with patch('search_server_funcs.load_mcp_config', return_value=mock_mcp_config['mcpServers']):
            with patch('search_server_funcs.subprocess.Popen', side_effect=popen_calls):
                with patch('search_server_funcs.time.sleep'):
                    # First call starts process
                    result1 = get_atlassian_process()
                    assert result1 is proc1
                    
                    # Simulate process death
                    proc1.poll.return_value = 1
                    
                    # Second call should restart
                    result2 = get_atlassian_process()
                    assert result2 is proc2

    def test_full_search_flow(self, reset_atlassian_globals):
        """Test complete search flow from query to results."""
        import search_server_funcs
        from search_server_funcs import search_atlassian
        
        # Set up initialized state
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "results": [
                            {"id": "ari:cloud:jira:site:issue/1", "title": "SEARCH-123: Found issue", "url": "https://test.atlassian.net/browse/SEARCH-123"},
                            {"id": "ari:cloud:confluence:site:page/1", "title": "Found doc", "url": "https://test.atlassian.net/wiki/page/1"}
                        ]
                    })
                }]
            }
        }).encode()
        
        search_server_funcs._atlassian_initialized = True
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                result = search_atlassian('search query', limit=5)
        
        assert len(result['jira']) == 1
        assert result['jira'][0]['key'] == 'SEARCH-123'
        assert len(result['confluence']) == 1

    def test_jira_and_confluence_use_same_search(self, reset_atlassian_globals):
        """Test get_jira_context and search_confluence both use search_atlassian."""
        from search_server_funcs import get_jira_context, search_confluence
        
        mock_results = {
            'jira': [{'key': 'TEST-1'}],
            'confluence': [{'title': 'Test Doc'}]
        }
        
        with patch('search_server_funcs.search_atlassian', return_value=mock_results) as mock_search:
            jira_results = get_jira_context('query', limit=5)
            confluence_results = search_confluence('query', limit=5)
        
        assert mock_search.call_count == 2
        assert jira_results == [{'key': 'TEST-1'}]
        assert confluence_results == [{'title': 'Test Doc'}]

    def test_search_atlassian_calls_correct_tool(self, reset_atlassian_globals):
        """Test search_atlassian calls the 'search' tool with correct arguments."""
        from search_server_funcs import search_atlassian
        
        with patch('search_server_funcs.call_atlassian_tool', return_value={"content": []}) as mock_call:
            search_atlassian('my search query', limit=10)
        
        mock_call.assert_called_once_with('search', {'query': 'my search query'})

    def test_error_propagates_through_wrapper_functions(self, reset_atlassian_globals):
        """Test errors from search_atlassian propagate to wrapper functions."""
        from search_server_funcs import get_jira_context, search_confluence
        
        error_result = {'jira': [], 'confluence': [], 'error': 'Connection failed'}
        
        with patch('search_server_funcs.search_atlassian', return_value=error_result):
            jira = get_jira_context('test', limit=5)
            confluence = search_confluence('test', limit=5)
        
        # Both should return empty lists (error is absorbed)
        assert jira == []
        assert confluence == []


# =============================================================================
# Edge case tests
# =============================================================================

class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_call_atlassian_tool_with_complex_arguments(self, reset_atlassian_globals):
        """Test call_atlassian_tool with complex nested arguments."""
        import search_server_funcs
        from search_server_funcs import call_atlassian_tool
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {}
        }).encode()
        
        search_server_funcs._atlassian_initialized = True
        
        complex_args = {
            "query": "test",
            "filters": {"type": "issue", "project": ["PROJ1", "PROJ2"]},
            "options": {"limit": 10, "offset": 0}
        }
        
        with patch('search_server_funcs.get_atlassian_process', return_value=mock_proc):
            with patch('search_server_funcs.select.select', return_value=([mock_proc.stdout], [], [])):
                result = call_atlassian_tool('advanced_search', complex_args)
        
        # Verify the complex arguments were serialized correctly
        write_call = mock_proc.stdin.write.call_args[0][0].decode()
        request = json.loads(write_call.strip())
        assert request['params']['arguments'] == complex_args

    def test_search_atlassian_with_special_characters_in_query(self, reset_atlassian_globals):
        """Test search_atlassian handles special characters in query."""
        from search_server_funcs import search_atlassian
        
        with patch('search_server_funcs.call_atlassian_tool', return_value={"content": []}) as mock_call:
            search_atlassian('test "with quotes" & special <chars>', limit=5)
        
        mock_call.assert_called_once()
        called_args = mock_call.call_args[0][1]
        assert called_args['query'] == 'test "with quotes" & special <chars>'

    def test_handles_unicode_in_response(self, reset_atlassian_globals):
        """Test handles Unicode characters in MCP response."""
        from search_server_funcs import search_atlassian
        
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [{
                        "id": "ari:cloud:jira:site:issue/1",
                        "title": "PROJ-1: 日本語テスト émojis 🎉",
                        "url": ""
                    }]
                })
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        assert 'PROJ-1' in result['jira'][0]['key']
        assert '日本語' in result['jira'][0]['title']

    def test_very_large_response(self, reset_atlassian_globals):
        """Test handles very large response with many results."""
        from search_server_funcs import search_atlassian
        
        # Generate 100 results
        results = [
            {"id": f"ari:cloud:jira:site:issue/{i}", "title": f"PROJ-{i}: Issue number {i}", "url": ""}
            for i in range(100)
        ]
        
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({"results": results})
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=5)
        
        # Should be limited to 5
        assert len(result['jira']) == 5

    def test_mixed_jira_and_confluence_ordering(self, reset_atlassian_globals):
        """Test correctly separates Jira and Confluence when mixed."""
        from search_server_funcs import search_atlassian
        
        results = [
            {"id": "ari:cloud:jira:site:issue/1", "title": "PROJ-1: Jira 1", "url": ""},
            {"id": "ari:cloud:confluence:site:page/1", "title": "Confluence 1", "url": ""},
            {"id": "ari:cloud:jira:site:issue/2", "title": "PROJ-2: Jira 2", "url": ""},
            {"id": "ari:cloud:confluence:site:page/2", "title": "Confluence 2", "url": ""},
            {"id": "ari:cloud:jira:site:issue/3", "title": "PROJ-3: Jira 3", "url": ""},
        ]
        
        response = {
            "content": [{
                "type": "text",
                "text": json.dumps({"results": results})
            }]
        }
        
        with patch('search_server_funcs.call_atlassian_tool', return_value=response):
            result = search_atlassian('test', limit=10)
        
        assert len(result['jira']) == 3
        assert len(result['confluence']) == 2
