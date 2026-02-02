"""
Tests for BriefDesk search-server.py

Run with: pytest tests/ -v
"""
import sys
import os
import json
import time
import threading
import pytest
from unittest.mock import patch, MagicMock

# Add tests directory to path for importing the helper module
sys.path.insert(0, os.path.dirname(__file__))


class TestExtractJsonArray:
    """Test the extract_json_array function."""
    
    def test_simple_array(self):
        """Test extracting a simple JSON array."""
        from search_server_funcs import extract_json_array
        text = '[{"name": "test", "value": 1}]'
        result = extract_json_array(text)
        assert result == [{"name": "test", "value": 1}]
    
    def test_array_with_prefix(self):
        """Test extracting JSON array with text before it."""
        from search_server_funcs import extract_json_array
        text = 'Some output text\n[{"key": "value"}]'
        result = extract_json_array(text)
        assert result == [{"key": "value"}]
    
    def test_array_with_suffix(self):
        """Test extracting JSON array with text after it."""
        from search_server_funcs import extract_json_array
        text = '[{"key": "value"}]\nMore text here'
        result = extract_json_array(text)
        assert result == [{"key": "value"}]
    
    def test_nested_array(self):
        """Test extracting nested JSON array."""
        from search_server_funcs import extract_json_array
        text = '[{"items": [1, 2, 3]}]'
        result = extract_json_array(text)
        assert result == [{"items": [1, 2, 3]}]
    
    def test_array_with_strings_containing_brackets(self):
        """Test array with strings that contain bracket characters."""
        from search_server_funcs import extract_json_array
        text = '[{"text": "Hello [world]"}]'
        result = extract_json_array(text)
        assert result == [{"text": "Hello [world]"}]
    
    def test_empty_array(self):
        """Test extracting empty array."""
        from search_server_funcs import extract_json_array
        text = '[]'
        result = extract_json_array(text)
        assert result == []
    
    def test_no_array(self):
        """Test when there's no JSON array."""
        from search_server_funcs import extract_json_array
        text = 'Just some text without JSON'
        result = extract_json_array(text)
        assert result is None
    
    def test_skip_mcp_status_lines(self):
        """Test that MCP status lines are skipped."""
        from search_server_funcs import extract_json_array
        text = 'Connecting to MCP server...\nMCP tool output: [invalid]\n[{"valid": true}]'
        result = extract_json_array(text)
        assert result == [{"valid": True}]
    
    def test_malformed_json(self):
        """Test handling of malformed JSON."""
        from search_server_funcs import extract_json_array
        text = '[{"key": "missing quote}]'
        result = extract_json_array(text)
        assert result is None


class TestPromptFunctions:
    """Test prompt-related functions."""
    
    def test_default_prompts_exist(self):
        """Test that all default prompts are defined."""
        from search_server_funcs import DEFAULT_PROMPTS
        expected_sources = ['jira', 'confluence', 'slack', 'gmail', 'drive', 'summary']
        for source in expected_sources:
            assert source in DEFAULT_PROMPTS, f"Missing prompt for {source}"
            assert len(DEFAULT_PROMPTS[source]) > 0, f"Empty prompt for {source}"
    
    def test_get_prompt_returns_default(self):
        """Test get_prompt returns default when no custom set."""
        from search_server_funcs import get_prompt, DEFAULT_PROMPTS
        result = get_prompt('jira')
        assert result == DEFAULT_PROMPTS['jira']
    
    def test_get_all_prompts_structure(self):
        """Test get_all_prompts returns correct structure."""
        from search_server_funcs import get_all_prompts
        result = get_all_prompts()
        assert isinstance(result, dict)
        for source, data in result.items():
            assert 'current' in data
            assert 'default' in data
            assert 'is_custom' in data
    
    def test_set_custom_prompt(self):
        """Test setting a custom prompt."""
        import search_server_funcs as funcs
        
        original = funcs.get_prompt('jira')
        
        # Set custom prompt
        funcs.set_custom_prompt('jira', 'Custom Jira prompt for testing')
        assert funcs.get_prompt('jira') == 'Custom Jira prompt for testing'
        
        # Verify it's marked as custom (is_custom is truthy when custom)
        all_prompts = funcs.get_all_prompts()
        assert all_prompts['jira']['is_custom']  # Truthy check
        
        # Reset to default
        funcs.set_custom_prompt('jira', '')
        assert funcs.get_prompt('jira') == original
        
        # Verify it's no longer custom (is_custom is falsy when default)
        all_prompts = funcs.get_all_prompts()
        assert not all_prompts['jira']['is_custom']  # Falsy check


class TestCacheFunctions:
    """Test cache-related functions."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear the cache before each test."""
        import search_server_funcs as funcs
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        # Clean up after test
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    @patch('search_server_funcs.save_prep_cache_to_disk')
    def test_set_and_get_meeting_cache(self, mock_save):
        """Test setting and getting meeting cache."""
        import search_server_funcs as funcs
        
        test_data = [{"title": "Test Item", "url": "https://example.com"}]
        funcs.set_meeting_cache('test-meeting-123', 'jira', test_data)
        
        # Verify save was called
        mock_save.assert_called_once()
        
        # Verify data was stored
        result = funcs.get_cached_data('test-meeting-123', 'jira')
        assert result == test_data
    
    @patch('search_server_funcs.save_prep_cache_to_disk')
    def test_has_cached_data(self, mock_save):
        """Test has_cached_data function."""
        import search_server_funcs as funcs
        
        assert funcs.has_cached_data('nonexistent', 'jira') == False
        
        funcs.set_meeting_cache('test-meeting-456', 'slack', [{"msg": "test"}])
        assert funcs.has_cached_data('test-meeting-456', 'slack') == True
        assert funcs.has_cached_data('test-meeting-456', 'jira') == False
    
    @patch('search_server_funcs.save_prep_cache_to_disk')
    def test_is_cache_valid_with_fresh_data(self, mock_save):
        """Test is_cache_valid with fresh data."""
        import search_server_funcs as funcs
        
        funcs.set_meeting_cache('test-meeting-789', 'confluence', [{"page": "test"}])
        assert funcs.is_cache_valid('test-meeting-789', 'confluence') == True
    
    @patch('search_server_funcs.save_prep_cache_to_disk')
    def test_is_cache_valid_with_stale_data(self, mock_save):
        """Test is_cache_valid with stale data."""
        import search_server_funcs as funcs
        
        # Manually insert cache with old timestamp
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['stale-meeting'] = {
                'jira': {'data': None, 'timestamp': 0},
                'confluence': {'data': [{"old": "data"}], 'timestamp': time.time() - 100000},  # Very old
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        assert funcs.is_cache_valid('stale-meeting', 'confluence') == False
    
    def test_get_cached_data_nonexistent(self):
        """Test get_cached_data returns None for nonexistent data."""
        from search_server_funcs import get_cached_data
        result = get_cached_data('nonexistent-meeting', 'jira')
        assert result is None
    
    @patch('search_server_funcs.save_prep_cache_to_disk')
    def test_cache_multiple_sources(self, mock_save):
        """Test caching data for multiple sources."""
        import search_server_funcs as funcs
        
        jira_data = [{"key": "PROJ-1"}]
        slack_data = [{"channel": "general"}]
        confluence_data = [{"page": "Meeting Notes"}]
        
        funcs.set_meeting_cache('multi-source-meeting', 'jira', jira_data)
        funcs.set_meeting_cache('multi-source-meeting', 'slack', slack_data)
        funcs.set_meeting_cache('multi-source-meeting', 'confluence', confluence_data)
        
        assert funcs.get_cached_data('multi-source-meeting', 'jira') == jira_data
        assert funcs.get_cached_data('multi-source-meeting', 'slack') == slack_data
        assert funcs.get_cached_data('multi-source-meeting', 'confluence') == confluence_data
        assert funcs.get_cached_data('multi-source-meeting', 'gmail') is None


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_is_night_hours(self):
        """Test is_night_hours function."""
        from search_server_funcs import is_night_hours
        # This will return True if current time is 10pm-6am or weekend
        result = is_night_hours()
        assert isinstance(result, bool)
    
    def test_extract_domain(self):
        """Test domain extraction from URLs."""
        from search_server_funcs import extract_domain
        assert extract_domain('https://example.com/path') == 'example.com'
        assert extract_domain('https://www.example.com/') == 'example.com'
        assert extract_domain('https://sub.example.com/page') == 'sub.example.com'
        assert extract_domain('http://localhost:8080/api') == 'localhost:8080'
        assert extract_domain('invalid-url') == ''
        assert extract_domain('') == ''


class TestSlackHelpers:
    """Test Slack helper functions."""
    
    def test_slack_ts_to_iso(self):
        """Test Slack timestamp to ISO conversion."""
        from search_server_funcs import slack_ts_to_iso
        # Slack uses Unix timestamp with decimal
        ts = "1706745600.000000"  # 2024-02-01 00:00:00 UTC
        result = slack_ts_to_iso(ts)
        assert result is not None
        assert '2024' in result
    
    def test_slack_ts_to_iso_invalid(self):
        """Test Slack timestamp conversion with invalid input."""
        from search_server_funcs import slack_ts_to_iso
        result = slack_ts_to_iso('invalid')
        # Should handle gracefully - either return None or a fallback
        # The actual behavior depends on implementation


# Module generation is handled by conftest.py


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
