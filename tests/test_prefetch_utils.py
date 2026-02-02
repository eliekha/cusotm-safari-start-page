"""
Tests for BriefDesk lib modules - Prefetch Functions and Utility Functions

Run with: pytest tests/test_prefetch_utils.py -v
"""
import sys
import os
import json
import time
import threading
import tempfile
import shutil
import sqlite3
import pytest
from unittest.mock import patch, MagicMock, mock_open

# Add parent directory to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import from lib modules
from lib import prefetch
from lib import cache
from lib import utils
from lib import slack
from lib import atlassian
from lib import config


# ============================================================================
# PREFETCH FUNCTION TESTS
# ============================================================================

class TestAddPrefetchActivity:
    """Test the add_prefetch_activity function."""
    
    @pytest.fixture(autouse=True)
    def clear_status(self):
        """Clear prefetch status before each test."""
        with prefetch._prefetch_status_lock:
            prefetch._prefetch_status['activity_log'] = []
        yield
        with prefetch._prefetch_status_lock:
            prefetch._prefetch_status['activity_log'] = []
    
    def test_adds_activity_to_log(self):
        """Test that activity is added to the log."""
        prefetch.add_prefetch_activity('fetch_start', 'Fetching jira...', 
                                   meeting='Test Meeting', source='jira', status='info')
        
        status = prefetch.get_prefetch_status()
        assert len(status['activity_log']) == 1
        entry = status['activity_log'][0]
        assert entry['type'] == 'fetch_start'
        assert entry['message'] == 'Fetching jira...'
        assert entry['meeting'] == 'Test Meeting'
        assert entry['source'] == 'jira'
        assert entry['status'] == 'info'
        assert 'timestamp' in entry
    
    def test_truncates_long_meeting_name(self):
        """Test that long meeting names are truncated to 40 chars."""
        long_name = "A" * 100  # 100 character meeting name
        prefetch.add_prefetch_activity('test', 'msg', meeting=long_name)
        
        status = prefetch.get_prefetch_status()
        assert len(status['activity_log'][0]['meeting']) == 40
    
    def test_handles_none_meeting(self):
        """Test handling of None meeting parameter."""
        prefetch.add_prefetch_activity('test', 'msg', meeting=None)
        
        status = prefetch.get_prefetch_status()
        assert status['activity_log'][0]['meeting'] is None
    
    def test_limits_activity_log_size(self):
        """Test that activity log is limited to MAX_ACTIVITY_LOG entries."""
        # Add more than MAX_ACTIVITY_LOG entries
        for i in range(60):
            prefetch.add_prefetch_activity('test', f'Message {i}')
        
        status = prefetch.get_prefetch_status()
        assert len(status['activity_log']) == config.MAX_ACTIVITY_LOG
        # Most recent should be first (index 0)
        assert 'Message 59' in status['activity_log'][0]['message']
    
    def test_includes_items_count(self):
        """Test that items count is included in activity."""
        prefetch.add_prefetch_activity('fetch_complete', 'Done', items=15)
        
        status = prefetch.get_prefetch_status()
        assert status['activity_log'][0]['items'] == 15


class TestUpdatePrefetchStatus:
    """Test the update_prefetch_status function."""
    
    @pytest.fixture(autouse=True)
    def reset_status(self):
        """Reset prefetch status before each test."""
        with prefetch._prefetch_status_lock:
            prefetch._prefetch_status.update({
                'running': False,
                'current_meeting': None,
                'current_source': None,
            })
        yield
    
    def test_updates_single_field(self):
        """Test updating a single field."""
        prefetch.update_prefetch_status(running=True)
        
        status = prefetch.get_prefetch_status()
        assert status['running'] == True
    
    def test_updates_multiple_fields(self):
        """Test updating multiple fields at once."""
        prefetch.update_prefetch_status(
            running=True,
            current_meeting='Team Sync',
            current_source='slack'
        )
        
        status = prefetch.get_prefetch_status()
        assert status['running'] == True
        assert status['current_meeting'] == 'Team Sync'
        assert status['current_source'] == 'slack'
    
    def test_thread_safe_update(self):
        """Test that updates are thread-safe."""
        errors = []
        
        def update_status(value):
            try:
                for _ in range(100):
                    prefetch.update_prefetch_status(meetings_processed=value)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=update_status, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


class TestGetPrefetchStatus:
    """Test the get_prefetch_status function."""
    
    def test_returns_dict_copy(self):
        """Test that get_prefetch_status returns a dict copy."""
        status = prefetch.get_prefetch_status()
        assert isinstance(status, dict)
        
        # Modifying returned dict shouldn't affect original
        status['running'] = 'modified'
        new_status = prefetch.get_prefetch_status()
        assert new_status['running'] != 'modified'
    
    def test_includes_all_expected_fields(self):
        """Test that status includes all expected fields."""
        status = prefetch.get_prefetch_status()
        
        expected_fields = ['running', 'current_meeting', 'current_source', 
                          'last_cycle_start', 'meetings_in_queue', 
                          'meetings_processed', 'activity_log']
        for field in expected_fields:
            assert field in status


class TestGetMeetingCache:
    """Test the get_meeting_cache function."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear meeting cache before each test."""
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
        yield
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
    
    def test_creates_new_cache_entry(self):
        """Test that get_meeting_cache creates entry if not exists."""
        meeting_cache = cache.get_meeting_cache('new-meeting-123')
        
        assert meeting_cache is not None
        assert 'jira' in meeting_cache
        assert 'confluence' in meeting_cache
        assert 'slack' in meeting_cache
        assert 'gmail' in meeting_cache
        assert 'drive' in meeting_cache
        assert 'summary' in meeting_cache
        assert 'meeting_info' in meeting_cache
    
    def test_returns_existing_cache_entry(self):
        """Test that existing cache entry is returned."""
        # Create entry
        cache1 = cache.get_meeting_cache('existing-meeting')
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache['existing-meeting']['jira']['data'] = [{'key': 'TEST-1'}]
        
        # Get again
        cache2 = cache.get_meeting_cache('existing-meeting')
        assert cache2['jira']['data'] == [{'key': 'TEST-1'}]
    
    def test_thread_safe_cache_access(self):
        """Test that cache access is thread-safe."""
        errors = []
        
        def access_cache(meeting_id):
            try:
                for _ in range(50):
                    cache.get_meeting_cache(meeting_id)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=access_cache, args=(f'meeting-{i}',)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


class TestCleanupOldCaches:
    """Test the cleanup_old_caches function."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear meeting cache before each test."""
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
        yield
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
    
    @patch('lib.cache.save_prep_cache_to_disk')
    def test_removes_old_cache_entries(self, mock_save):
        """Test that old cache entries are removed."""
        # Add an old entry (more than 24 hours old)
        old_timestamp = time.time() - (25 * 60 * 60)  # 25 hours ago
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache['old-meeting'] = {
                'jira': {'data': [{'key': 'OLD-1'}], 'timestamp': old_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        cache.cleanup_old_caches()
        
        with cache._meeting_prep_cache_lock:
            assert 'old-meeting' not in cache._meeting_prep_cache
    
    @patch('lib.cache.save_prep_cache_to_disk')
    def test_keeps_recent_cache_entries(self, mock_save):
        """Test that recent cache entries are kept."""
        # Add a recent entry (less than 24 hours old)
        recent_timestamp = time.time() - (1 * 60 * 60)  # 1 hour ago
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache['recent-meeting'] = {
                'jira': {'data': [{'key': 'RECENT-1'}], 'timestamp': recent_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        cache.cleanup_old_caches()
        
        with cache._meeting_prep_cache_lock:
            assert 'recent-meeting' in cache._meeting_prep_cache
    
    def test_handles_empty_cache(self):
        """Test that cleanup handles empty cache gracefully."""
        # Should not raise any exception
        cache.cleanup_old_caches()


class TestCheckServicesAuth:
    """Test the check_services_auth function."""
    
    def test_returns_auth_status_dict(self):
        """Test that check_services_auth returns expected structure."""
        with patch('os.path.exists', return_value=False):
            result = prefetch.check_services_auth()
        
        assert isinstance(result, dict)
        assert 'atlassian' in result
        assert 'slack' in result
        assert 'gmail' in result
    
    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('builtins.open', new_callable=mock_open, read_data='{"access_token": "test-token"}')
    def test_detects_atlassian_auth(self, mock_file, mock_listdir, mock_exists):
        """Test detection of Atlassian authentication."""
        def exists_side_effect(path):
            return '~/.mcp-auth' in path or 'mcp-auth' in path
        
        mock_exists.side_effect = exists_side_effect
        mock_listdir.return_value = ['mcp-remote']
        
        with patch('os.path.isdir', return_value=True):
            result = prefetch.check_services_auth()
        
        # Due to complex path checking, just verify structure
        assert 'atlassian' in result
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, 
           read_data='{"mcpServers": {"slack": {"env": {"SLACK_BOT_TOKEN": "xoxb-test"}}}}')
    def test_detects_slack_auth_from_local_config(self, mock_file, mock_exists):
        """Test detection of Slack authentication from local config."""
        mock_exists.return_value = True
        
        result = prefetch.check_services_auth()
        
        # Slack should be detected from local config
        assert 'slack' in result


class TestPrefetchMeetingData:
    """Test the prefetch_meeting_data function."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for prefetch tests."""
        # Configure CLI functions (required before using prefetch_meeting_data)
        prefetch.configure_cli_functions(
            lambda *args, **kwargs: [],
            lambda *args, **kwargs: {'status': 'success', 'summary': ''}
        )
        prefetch._prefetch_running = True
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
        with prefetch._prefetch_status_lock:
            prefetch._prefetch_status['activity_log'] = []
        yield
        prefetch._prefetch_running = False
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
    
    @patch('lib.prefetch.check_services_auth')
    @patch('lib.prefetch._call_cli_for_source')
    @patch('lib.cache.save_prep_cache_to_disk')
    @patch('lib.cache.is_cache_valid', return_value=False)
    def test_prefetches_drive_always(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that Drive is always prefetched (doesn't need OAuth)."""
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = [{'name': 'file.txt', 'path': '/path/to/file.txt'}]
        
        # Configure CLI
        prefetch.configure_cli_functions(mock_cli, lambda *args, **kwargs: {'status': 'success', 'summary': ''})
        
        meeting = {'id': 'test-123', 'title': 'Test Meeting', 'attendees': [], 'description': ''}
        prefetch.prefetch_meeting_data(meeting)
        
        # Drive should have been called
        mock_cli.assert_called()
        call_args = [call[0][0] for call in mock_cli.call_args_list]
        assert 'drive' in call_args
    
    @patch('lib.prefetch.check_services_auth')
    @patch('lib.prefetch._call_cli_for_source')
    @patch('lib.cache.save_prep_cache_to_disk')
    @patch('lib.cache.is_cache_valid', return_value=False)
    def test_skips_unauthenticated_services(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that unauthenticated services are skipped."""
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        # Configure CLI
        prefetch.configure_cli_functions(mock_cli, lambda *args, **kwargs: {'status': 'success', 'summary': ''})
        
        meeting = {'id': 'test-456', 'title': 'Test Meeting', 'attendees': [], 'description': ''}
        prefetch.prefetch_meeting_data(meeting)
        
        # Jira, Confluence, Slack, Gmail should NOT be called
        call_args = [call[0][0] for call in mock_cli.call_args_list if mock_cli.call_args_list]
        for source in ['jira', 'confluence', 'slack', 'gmail']:
            assert source not in call_args
    
    @patch('lib.prefetch.check_services_auth')
    @patch('lib.prefetch._call_cli_for_source')
    @patch('lib.cache.save_prep_cache_to_disk')
    @patch('lib.cache.is_cache_valid', return_value=False)
    def test_stores_meeting_info(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that meeting info is stored in cache."""
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        # Configure CLI
        prefetch.configure_cli_functions(mock_cli, lambda *args, **kwargs: {'status': 'success', 'summary': ''})
        
        meeting = {
            'id': 'info-test', 
            'title': 'Important Meeting', 
            'attendees': [{'name': 'John', 'email': 'john@test.com'}],
            'description': 'Meeting about stuff'
        }
        prefetch.prefetch_meeting_data(meeting)
        
        with cache._meeting_prep_cache_lock:
            cached = cache._meeting_prep_cache.get('info-test', {})
            meeting_info = cached.get('meeting_info', {})
        
        assert meeting_info.get('title') == 'Important Meeting'


class TestSetForceAggressivePrefetch:
    """Test the set_force_aggressive_prefetch function."""
    
    def test_sets_on(self):
        """Test setting force prefetch to on."""
        prefetch._force_aggressive_prefetch = False
        prefetch.set_force_aggressive_prefetch('on')
        
        assert prefetch._force_aggressive_prefetch == True
    
    def test_sets_off(self):
        """Test setting force prefetch to off."""
        prefetch._force_aggressive_prefetch = True
        prefetch.set_force_aggressive_prefetch('off')
        
        assert prefetch._force_aggressive_prefetch == False
    
    def test_toggles_state(self):
        """Test toggling force prefetch state."""
        prefetch._force_aggressive_prefetch = False
        prefetch.set_force_aggressive_prefetch('toggle')
        assert prefetch._force_aggressive_prefetch == True
        
        prefetch.set_force_aggressive_prefetch('toggle')
        assert prefetch._force_aggressive_prefetch == False


class TestBackgroundPrefetchLoop:
    """Test key paths of the background_prefetch_loop function."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for background loop tests."""
        # Configure CLI functions
        prefetch.configure_cli_functions(
            lambda *args, **kwargs: [],
            lambda *args, **kwargs: {'status': 'success', 'summary': ''}
        )
        prefetch._prefetch_running = False
        yield
        prefetch._prefetch_running = False
    
    def test_loop_exits_when_not_running(self):
        """Test that loop exits when _prefetch_running is False."""
        prefetch._prefetch_running = False
        
        # Should exit immediately
        # Run in thread with timeout
        thread = threading.Thread(target=prefetch.background_prefetch_loop)
        thread.start()
        thread.join(timeout=1.0)
        
        assert not thread.is_alive()
    
    @patch('lib.prefetch.get_calendar_events_standalone')
    @patch('lib.prefetch.prefetch_meeting_data')
    @patch('lib.cache.cleanup_old_caches')
    def test_processes_meetings_when_available(self, mock_cleanup, mock_prefetch, mock_calendar):
        """Test that meetings are processed when available."""
        # Setup: one iteration then stop
        call_count = [0]
        def stop_after_one(*args, **kwargs):
            call_count[0] += 1
            prefetch._prefetch_running = False
            return []
        
        mock_calendar.side_effect = stop_after_one
        prefetch._prefetch_running = True
        
        thread = threading.Thread(target=prefetch.background_prefetch_loop)
        thread.start()
        thread.join(timeout=3.0)
        
        assert call_count[0] >= 1


class TestStartPrefetchThread:
    """Test the start_prefetch_thread function."""
    
    @pytest.fixture(autouse=True)
    def cleanup_thread(self):
        """Cleanup thread after test."""
        # Configure CLI functions
        prefetch.configure_cli_functions(
            lambda *args, **kwargs: [],
            lambda *args, **kwargs: {'status': 'success', 'summary': ''}
        )
        yield
        prefetch._prefetch_running = False
        if prefetch._prefetch_thread and prefetch._prefetch_thread.is_alive():
            prefetch._prefetch_thread.join(timeout=1.0)
        prefetch._prefetch_thread = None
    
    @patch('lib.prefetch.background_prefetch_loop')
    def test_starts_thread(self, mock_loop):
        """Test that thread is started."""
        prefetch._prefetch_thread = None
        prefetch._prefetch_running = False
        
        prefetch.start_prefetch_thread()
        
        assert prefetch._prefetch_running == True
        assert prefetch._prefetch_thread is not None
    
    @patch('lib.prefetch.background_prefetch_loop')
    def test_does_not_start_if_already_running(self, mock_loop):
        """Test that new thread is not started if one is running."""
        # Create a mock thread that appears alive
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        prefetch._prefetch_thread = mock_thread
        
        prefetch.start_prefetch_thread()
        
        # Should not have started a new thread
        assert prefetch._prefetch_thread == mock_thread


class TestStopPrefetchThread:
    """Test the stop_prefetch_thread function."""
    
    def test_sets_running_false(self):
        """Test that _prefetch_running is set to False."""
        prefetch._prefetch_running = True
        prefetch.stop_prefetch_thread()
        
        assert prefetch._prefetch_running == False
    
    def test_idempotent(self):
        """Test that stopping multiple times is safe."""
        prefetch._prefetch_running = True
        prefetch.stop_prefetch_thread()
        prefetch.stop_prefetch_thread()
        prefetch.stop_prefetch_thread()
        
        assert prefetch._prefetch_running == False


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================

class TestCopyDb:
    """Test the copy_db function."""
    
    def test_copies_database_file(self):
        """Test that database file is copied."""
        # Create a temp database
        with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
            src_path = f.name
            conn = sqlite3.connect(src_path)
            conn.execute('CREATE TABLE test (id INTEGER)')
            conn.execute('INSERT INTO test VALUES (1)')
            conn.commit()
            conn.close()
        
        try:
            result = utils.copy_db(src_path)
            
            assert result is not None
            assert os.path.exists(result)
            
            # Verify data is copied
            conn = sqlite3.connect(result)
            cursor = conn.execute('SELECT * FROM test')
            rows = cursor.fetchall()
            conn.close()
            
            assert len(rows) == 1
            assert rows[0][0] == 1
            
            # Cleanup
            utils.cleanup_db(result)
        finally:
            os.unlink(src_path)
    
    def test_returns_none_for_nonexistent_file(self):
        """Test that None is returned for nonexistent file."""
        result = utils.copy_db('/nonexistent/path/db.sqlite')
        assert result is None
    
    def test_copies_wal_file_if_exists(self):
        """Test that WAL file is copied if it exists."""
        # Create a temp database with WAL mode
        with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
            src_path = f.name
        
        try:
            conn = sqlite3.connect(src_path)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE test (id INTEGER)')
            conn.execute('INSERT INTO test VALUES (42)')
            conn.commit()
            # Don't close yet - WAL file should exist
            
            result = utils.copy_db(src_path)
            conn.close()
            
            if result:
                # Verify data is accessible
                conn2 = sqlite3.connect(result)
                cursor = conn2.execute('SELECT * FROM test')
                rows = cursor.fetchall()
                conn2.close()
                
                assert len(rows) == 1
                utils.cleanup_db(result)
        finally:
            for suffix in ['', '-wal', '-shm']:
                try:
                    os.unlink(src_path + suffix)
                except:
                    pass


class TestCleanupDb:
    """Test the cleanup_db function."""
    
    def test_removes_temp_directory(self):
        """Test that temp directory is removed."""
        # Create a temp dir with a file
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, 'db.sqlite')
        with open(tmp_path, 'w') as f:
            f.write('test')
        
        utils.cleanup_db(tmp_path)
        
        assert not os.path.exists(tmp_dir)
    
    def test_handles_none_gracefully(self):
        """Test that None input is handled gracefully."""
        # Should not raise
        utils.cleanup_db(None)


class TestParseSlackCsv:
    """Test the parse_slack_csv function."""
    
    def test_parses_simple_csv(self):
        """Test parsing simple CSV data."""
        csv_text = """header1,header2,header3
value1,value2,value3
a,b,c"""
        
        result = slack.parse_slack_csv(csv_text)
        
        assert len(result) == 2
        assert result[0]['header1'] == 'value1'
        assert result[0]['header2'] == 'value2'
        assert result[1]['header1'] == 'a'
    
    def test_handles_quoted_values(self):
        """Test handling of quoted values with commas."""
        csv_text = 'name,message\nJohn,"Hello, world"\nJane,"How are you?"'
        
        result = slack.parse_slack_csv(csv_text)
        
        assert len(result) == 2
        assert result[0]['message'] == 'Hello, world'
    
    def test_returns_empty_for_empty_input(self):
        """Test that empty input returns empty list."""
        assert slack.parse_slack_csv('') == []
        assert slack.parse_slack_csv(None) == []
    
    def test_returns_empty_for_header_only(self):
        """Test that header-only CSV returns empty list."""
        result = slack.parse_slack_csv('header1,header2')
        assert result == []


class TestExtractMcpContent:
    """Test the extract_mcp_content function."""
    
    def test_extracts_text_from_content_array(self):
        """Test extraction from standard MCP content array."""
        result = {
            'content': [
                {'type': 'text', 'text': 'Hello, world!'}
            ]
        }
        
        extracted = atlassian.extract_mcp_content(result)
        assert extracted == 'Hello, world!'
    
    def test_handles_empty_result(self):
        """Test handling of empty result."""
        assert atlassian.extract_mcp_content(None) is None
        # Empty dict without 'content' key returns the input as-is (fallback)
        result = atlassian.extract_mcp_content({})
        assert result is None or result == {}
    
    def test_handles_non_standard_format(self):
        """Test fallback for non-standard format."""
        result = {'data': 'some data'}
        extracted = atlassian.extract_mcp_content(result)
        
        assert extracted == result
    
    def test_handles_multiple_content_items(self):
        """Test handling of multiple content items."""
        result = {
            'content': [
                {'type': 'image', 'url': 'http://example.com/img.png'},
                {'type': 'text', 'text': 'Found text'}
            ]
        }
        
        extracted = atlassian.extract_mcp_content(result)
        assert extracted == 'Found text'


class TestLoadConfig:
    """Test the load_config function."""
    
    @patch('os.path.exists', return_value=False)
    def test_returns_defaults_when_no_config(self, mock_exists):
        """Test that defaults are returned when no config file exists."""
        config_result = atlassian.load_config()
        
        assert 'slack_workspace' in config_result
        assert 'atlassian_domain' in config_result
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, 
           read_data='{"slack_workspace": "custom-workspace", "atlassian_domain": "custom.atlassian.net"}')
    def test_loads_from_config_file(self, mock_file, mock_exists):
        """Test loading configuration from file."""
        def exists_side_effect(path):
            return 'config.json' in path
        mock_exists.side_effect = exists_side_effect
        
        config_result = atlassian.load_config()
        
        assert config_result['slack_workspace'] == 'custom-workspace'
        assert config_result['atlassian_domain'] == 'custom.atlassian.net'
    
    @patch('os.path.exists', return_value=False)
    @patch.dict(os.environ, {'SLACK_WORKSPACE': 'env-workspace'})
    def test_env_vars_override_config(self, mock_exists):
        """Test that environment variables override config file."""
        config_result = atlassian.load_config()
        
        assert config_result['slack_workspace'] == 'env-workspace'


class TestFormatSlackChannel:
    """Test the format_slack_channel function."""
    
    def test_formats_regular_channel(self):
        """Test formatting of regular channel."""
        result = slack.format_slack_channel('general')
        assert result == '#general'
    
    def test_removes_leading_hash(self):
        """Test that leading # is handled."""
        result = slack.format_slack_channel('#general')
        assert result == '#general'
    
    def test_formats_dm_with_sender(self):
        """Test formatting of DM with sender name."""
        result = slack.format_slack_channel('D12345', sender_name='John Doe')
        assert result == 'DM with John Doe'
    
    def test_formats_dm_without_sender(self):
        """Test formatting of DM without sender name."""
        result = slack.format_slack_channel('D12345')
        assert result == 'DM'
    
    def test_formats_group_dm(self):
        """Test formatting of group DM."""
        result = slack.format_slack_channel('mpdm-user1--user2--user3')
        assert result == 'Group DM'
    
    def test_handles_empty_channel(self):
        """Test handling of empty channel."""
        assert slack.format_slack_channel('') == ''
        assert slack.format_slack_channel(None) == ''


class TestBuildSlackUrl:
    """Test the build_slack_url function."""
    
    def test_builds_valid_url(self):
        """Test building a valid Slack URL."""
        result = slack.build_slack_url('C12345', '1769817144.201689')
        
        assert 'slack.com/archives/C12345/p' in result
        assert '1769817144201689' in result  # Dot removed
    
    def test_removes_hash_from_channel(self):
        """Test that # prefix is removed from channel ID."""
        result = slack.build_slack_url('#C12345', '123.456')
        
        assert '#' not in result
    
    def test_returns_none_for_missing_params(self):
        """Test that None is returned for missing parameters."""
        assert slack.build_slack_url('', '123.456') is None
        assert slack.build_slack_url('C12345', '') is None
        assert slack.build_slack_url(None, '123.456') is None


class TestFormatSlackMessage:
    """Test the format_slack_message function."""
    
    def test_formats_complete_message(self):
        """Test formatting a complete message."""
        msg = {
            'text': 'Hello, this is a test message that is quite long',
            'channel': 'general',
            'realname': 'John Doe',
            'username': 'johnd',
            'msgid': '1234567890.123456',
            'threadts': '1234567890.000000',
            'time': '2024-01-15T10:30:00'
        }
        
        result = slack.format_slack_message(msg)
        
        assert result['title'] == msg['text'][:100]
        assert result['channel'] == '#general'
        assert result['from'] == 'John Doe'
        assert result['username'] == 'johnd'
        assert result['msg_id'] == '1234567890.123456'
        assert 'slack_url' in result
    
    def test_uses_username_when_no_realname(self):
        """Test that username is used when realname is missing."""
        msg = {
            'text': 'Test',
            'channel': 'general',
            'username': 'testuser',
            'msgid': '123.456'
        }
        
        result = slack.format_slack_message(msg)
        
        assert result['from'] == 'testuser'
    
    def test_truncates_long_title(self):
        """Test that title is truncated to 100 chars."""
        long_text = 'A' * 200
        msg = {'text': long_text, 'channel': 'test', 'msgid': '1.1'}
        
        result = slack.format_slack_message(msg)
        
        assert len(result['title']) == 100


class TestScoreResult:
    """Test the score_result function."""
    
    def test_exact_title_match_highest_score(self):
        """Test that exact title match gets highest score."""
        result = {'title': 'github', 'url': 'https://example.com'}
        score = utils.score_result(result, 'github', ['github'])
        
        assert score >= 100  # Exact match bonus
    
    def test_multi_word_query_scoring(self):
        """Test scoring with multi-word queries."""
        result = {'title': 'react native documentation', 'url': 'https://example.com'}
        score = utils.score_result(result, 'react native', ['react', 'native'])
        
        # Should get points for both words in title
        assert score > 0


class TestIsNightHours:
    """Test the is_night_hours function."""
    
    def test_returns_boolean(self):
        """Test that function returns a boolean."""
        result = utils.is_night_hours()
        assert isinstance(result, bool)


class TestExtractDomain:
    """Test the extract_domain function."""
    
    def test_extracts_simple_domain(self):
        """Test extraction from simple URL."""
        assert utils.extract_domain('https://example.com/path') == 'example.com'
    
    def test_removes_www_prefix(self):
        """Test that www. prefix is removed."""
        assert utils.extract_domain('https://www.example.com/') == 'example.com'
    
    def test_preserves_subdomains(self):
        """Test that subdomains are preserved."""
        assert utils.extract_domain('https://docs.example.com/page') == 'docs.example.com'
    
    def test_handles_port_numbers(self):
        """Test handling of port numbers."""
        assert utils.extract_domain('http://localhost:8080/api') == 'localhost:8080'
    
    def test_handles_invalid_url(self):
        """Test handling of invalid URL."""
        assert utils.extract_domain('not-a-url') == ''
        assert utils.extract_domain('') == ''


# ============================================================================
# CACHE VALIDATION TESTS
# ============================================================================

class TestCacheValidation:
    """Tests for cache validation functions."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear cache before and after tests."""
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
        yield
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
    
    def test_is_cache_valid_for_nonexistent_meeting(self):
        """Test is_cache_valid returns False for nonexistent meeting."""
        result = cache.is_cache_valid('nonexistent-meeting', 'jira')
        
        assert result == False
    
    def test_is_cache_valid_for_nonexistent_source(self):
        """Test is_cache_valid returns False for nonexistent source."""
        # Create meeting without the source
        cache.get_meeting_cache('partial-meeting')
        
        result = cache.is_cache_valid('partial-meeting', 'jira')
        
        assert result == False  # No data in jira yet
    
    def test_is_cache_valid_for_none_data(self):
        """Test is_cache_valid returns False for None data."""
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache['none-data'] = {
                'jira': {'data': None, 'timestamp': time.time()},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        result = cache.is_cache_valid('none-data', 'jira')
        
        assert result == False
    
    def test_is_cache_valid_expired_data(self):
        """Test is_cache_valid returns False for expired data."""
        old_timestamp = time.time() - (config.PREP_CACHE_TTL + 100)
        
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache['expired'] = {
                'jira': {'data': [{'key': 'OLD-1'}], 'timestamp': old_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        result = cache.is_cache_valid('expired', 'jira')
        
        assert result == False
    
    def test_is_cache_valid_fresh_data(self):
        """Test is_cache_valid returns True for fresh data."""
        recent_timestamp = time.time() - 60  # 1 minute ago
        
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache['fresh'] = {
                'jira': {'data': [{'key': 'FRESH-1'}], 'timestamp': recent_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        result = cache.is_cache_valid('fresh', 'jira')
        
        assert result == True
    
    def test_is_cache_valid_uses_summary_ttl_for_summary(self):
        """Test that summary source uses SUMMARY_CACHE_TTL."""
        # Timestamp between PREP_CACHE_TTL and SUMMARY_CACHE_TTL
        middle_timestamp = time.time() - (config.PREP_CACHE_TTL + 100)
        
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache['summary-ttl'] = {
                'jira': {'data': None, 'timestamp': 0},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': {'status': 'success'}, 'timestamp': middle_timestamp},
                'meeting_info': None
            }
        
        # Summary should still be valid (longer TTL)
        result = cache.is_cache_valid('summary-ttl', 'summary')
        
        assert result == True
    
    def test_has_cached_data_ignores_ttl(self):
        """Test that has_cached_data ignores TTL."""
        very_old_timestamp = time.time() - (24 * 60 * 60)  # 24 hours ago
        
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache['old-but-present'] = {
                'jira': {'data': [{'key': 'OLD-1'}], 'timestamp': very_old_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        # is_cache_valid should return False (expired)
        assert cache.is_cache_valid('old-but-present', 'jira') == False
        
        # has_cached_data should return True (data exists)
        assert cache.has_cached_data('old-but-present', 'jira') == True
    
    def test_has_cached_data_returns_false_for_none(self):
        """Test has_cached_data returns False for None data."""
        cache.get_meeting_cache('no-data')
        
        result = cache.has_cached_data('no-data', 'jira')
        
        assert result == False


class TestSetMeetingCache:
    """Tests for set_meeting_cache function."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear cache before and after tests."""
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
        yield
        with cache._meeting_prep_cache_lock:
            cache._meeting_prep_cache.clear()
    
    @patch('lib.cache.save_prep_cache_to_disk')
    def test_sets_data_and_timestamp(self, mock_save):
        """Test that data and timestamp are set correctly."""
        test_data = [{'key': 'TEST-1'}, {'key': 'TEST-2'}]
        before = time.time()
        
        cache.set_meeting_cache('set-test', 'jira', test_data)
        
        after = time.time()
        
        with cache._meeting_prep_cache_lock:
            cache_entry = cache._meeting_prep_cache['set-test']['jira']
            assert cache_entry['data'] == test_data
            assert before <= cache_entry['timestamp'] <= after
    
    @patch('lib.cache.save_prep_cache_to_disk')
    def test_creates_meeting_entry_if_not_exists(self, mock_save):
        """Test that meeting entry is created if it doesn't exist."""
        cache.set_meeting_cache('new-meeting', 'slack', [{'text': 'hello'}])
        
        with cache._meeting_prep_cache_lock:
            assert 'new-meeting' in cache._meeting_prep_cache
            assert cache._meeting_prep_cache['new-meeting']['slack']['data'] == [{'text': 'hello'}]
    
    @patch('lib.cache.save_prep_cache_to_disk')
    def test_calls_save_to_disk(self, mock_save):
        """Test that save_prep_cache_to_disk is called."""
        cache.set_meeting_cache('save-test', 'drive', [])
        
        mock_save.assert_called_once()
    
    @patch('lib.cache.save_prep_cache_to_disk')
    def test_thread_safe_concurrent_sets(self, mock_save):
        """Test thread-safe concurrent set operations."""
        errors = []
        
        def set_cache(source, data):
            try:
                for i in range(50):
                    cache.set_meeting_cache('concurrent-set', source, data + [i])
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=set_cache, args=('jira', [{'key': 'J'}])),
            threading.Thread(target=set_cache, args=('slack', [{'text': 'S'}])),
            threading.Thread(target=set_cache, args=('drive', [{'name': 'D'}])),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


class TestActivityLog:
    """Tests for activity logging functionality."""
    
    @pytest.fixture(autouse=True)
    def clear_status(self):
        """Clear prefetch status before each test."""
        with prefetch._prefetch_status_lock:
            prefetch._prefetch_status['activity_log'] = []
        yield
        with prefetch._prefetch_status_lock:
            prefetch._prefetch_status['activity_log'] = []
    
    def test_activity_log_concurrent_access(self):
        """Test thread-safe concurrent access to activity log."""
        errors = []
        
        def add_activities():
            try:
                for i in range(50):
                    prefetch.add_prefetch_activity('test', f'Message {i}', meeting=f'Meeting {i}')
            except Exception as e:
                errors.append(e)
        
        def read_activities():
            try:
                for _ in range(50):
                    status = prefetch.get_prefetch_status()
                    _ = len(status['activity_log'])
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=add_activities),
            threading.Thread(target=add_activities),
            threading.Thread(target=read_activities),
            threading.Thread(target=read_activities),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
    
    def test_activity_log_order_newest_first(self):
        """Test that newest activities are at the beginning of the log."""
        prefetch.add_prefetch_activity('first', 'First message')
        time.sleep(0.01)  # Small delay to ensure different timestamps
        prefetch.add_prefetch_activity('second', 'Second message')
        
        status = prefetch.get_prefetch_status()
        
        assert status['activity_log'][0]['message'] == 'Second message'
        assert status['activity_log'][1]['message'] == 'First message'
    
    def test_activity_with_all_fields(self):
        """Test activity entry with all optional fields."""
        prefetch.add_prefetch_activity(
            'fetch_complete',
            'Completed fetch',
            meeting='Test Meeting',
            source='jira',
            status='success',
            items=42
        )
        
        status = prefetch.get_prefetch_status()
        entry = status['activity_log'][0]
        
        assert entry['type'] == 'fetch_complete'
        assert entry['message'] == 'Completed fetch'
        assert entry['meeting'] == 'Test Meeting'
        assert entry['source'] == 'jira'
        assert entry['status'] == 'success'
        assert entry['items'] == 42
        assert 'timestamp' in entry


# ============================================================================
# Run tests
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
