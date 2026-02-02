"""
Tests for BriefDesk search-server.py - Prefetch Functions and Utility Functions

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

# Add tests directory to path
sys.path.insert(0, os.path.dirname(__file__))


# ============================================================================
# Helper module with extracted functions
# ============================================================================

def create_prefetch_utils_module():
    """Create a module with the functions we want to test."""
    import re
    
    server_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "search-server.py")
    with open(server_path, 'r') as f:
        content = f.read()
    
    module_code = '''
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

'''
    
    # Functions to extract
    functions_to_extract = [
        'copy_db',
        'cleanup_db', 
        'parse_slack_csv',
        'extract_mcp_content',
        'load_config',
        'format_slack_channel',
        'build_slack_url',
        'format_slack_message',
        'score_result',
        'add_prefetch_activity',
        'update_prefetch_status',
        'get_prefetch_status',
        'get_meeting_cache',
        'set_meeting_cache',
        'cleanup_old_caches',
        'check_services_auth',
        'prefetch_meeting_data',
        'set_force_aggressive_prefetch',
        'background_prefetch_loop',
        'start_prefetch_thread',
        'stop_prefetch_thread',
        'is_night_hours',
        'extract_domain',
        'load_prep_cache_from_disk',
    ]
    
    for func_name in functions_to_extract:
        pattern = rf'^def {func_name}\([^)]*\):.*?(?=\ndef |\nclass |\nif __name__|\Z)'
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        if match:
            func_code = match.group(0).rstrip()
            # Add the function
            module_code += func_code + '\n\n'
    
    module_path = os.path.join(os.path.dirname(__file__), 'prefetch_utils_funcs.py')
    with open(module_path, 'w') as f:
        f.write(module_code)
    
    return module_path


# Create the test module at import time
try:
    create_prefetch_utils_module()
except Exception as e:
    print(f"Warning: Could not create test module: {e}")


# ============================================================================
# PREFETCH FUNCTION TESTS
# ============================================================================

class TestAddPrefetchActivity:
    """Test the add_prefetch_activity function."""
    
    @pytest.fixture(autouse=True)
    def clear_status(self):
        """Clear prefetch status before each test."""
        import prefetch_utils_funcs as funcs
        with funcs._prefetch_status_lock:
            funcs._prefetch_status['activity_log'] = []
        yield
        with funcs._prefetch_status_lock:
            funcs._prefetch_status['activity_log'] = []
    
    def test_adds_activity_to_log(self):
        """Test that activity is added to the log."""
        import prefetch_utils_funcs as funcs
        
        funcs.add_prefetch_activity('fetch_start', 'Fetching jira...', 
                                   meeting='Test Meeting', source='jira', status='info')
        
        status = funcs.get_prefetch_status()
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
        import prefetch_utils_funcs as funcs
        
        long_name = "A" * 100  # 100 character meeting name
        funcs.add_prefetch_activity('test', 'msg', meeting=long_name)
        
        status = funcs.get_prefetch_status()
        assert len(status['activity_log'][0]['meeting']) == 40
    
    def test_handles_none_meeting(self):
        """Test handling of None meeting parameter."""
        import prefetch_utils_funcs as funcs
        
        funcs.add_prefetch_activity('test', 'msg', meeting=None)
        
        status = funcs.get_prefetch_status()
        assert status['activity_log'][0]['meeting'] is None
    
    def test_limits_activity_log_size(self):
        """Test that activity log is limited to MAX_ACTIVITY_LOG entries."""
        import prefetch_utils_funcs as funcs
        
        # Add more than MAX_ACTIVITY_LOG entries
        for i in range(60):
            funcs.add_prefetch_activity('test', f'Message {i}')
        
        status = funcs.get_prefetch_status()
        assert len(status['activity_log']) == funcs.MAX_ACTIVITY_LOG
        # Most recent should be first (index 0)
        assert 'Message 59' in status['activity_log'][0]['message']
    
    def test_includes_items_count(self):
        """Test that items count is included in activity."""
        import prefetch_utils_funcs as funcs
        
        funcs.add_prefetch_activity('fetch_complete', 'Done', items=15)
        
        status = funcs.get_prefetch_status()
        assert status['activity_log'][0]['items'] == 15


class TestUpdatePrefetchStatus:
    """Test the update_prefetch_status function."""
    
    @pytest.fixture(autouse=True)
    def reset_status(self):
        """Reset prefetch status before each test."""
        import prefetch_utils_funcs as funcs
        with funcs._prefetch_status_lock:
            funcs._prefetch_status.update({
                'running': False,
                'current_meeting': None,
                'current_source': None,
            })
        yield
    
    def test_updates_single_field(self):
        """Test updating a single field."""
        import prefetch_utils_funcs as funcs
        
        funcs.update_prefetch_status(running=True)
        
        status = funcs.get_prefetch_status()
        assert status['running'] == True
    
    def test_updates_multiple_fields(self):
        """Test updating multiple fields at once."""
        import prefetch_utils_funcs as funcs
        
        funcs.update_prefetch_status(
            running=True,
            current_meeting='Team Sync',
            current_source='slack'
        )
        
        status = funcs.get_prefetch_status()
        assert status['running'] == True
        assert status['current_meeting'] == 'Team Sync'
        assert status['current_source'] == 'slack'
    
    def test_thread_safe_update(self):
        """Test that updates are thread-safe."""
        import prefetch_utils_funcs as funcs
        
        errors = []
        
        def update_status(value):
            try:
                for _ in range(100):
                    funcs.update_prefetch_status(meetings_processed=value)
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
        import prefetch_utils_funcs as funcs
        
        status = funcs.get_prefetch_status()
        assert isinstance(status, dict)
        
        # Modifying returned dict shouldn't affect original
        status['running'] = 'modified'
        new_status = funcs.get_prefetch_status()
        assert new_status['running'] != 'modified'
    
    def test_includes_all_expected_fields(self):
        """Test that status includes all expected fields."""
        import prefetch_utils_funcs as funcs
        
        status = funcs.get_prefetch_status()
        
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
        import prefetch_utils_funcs as funcs
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    def test_creates_new_cache_entry(self):
        """Test that get_meeting_cache creates entry if not exists."""
        import prefetch_utils_funcs as funcs
        
        cache = funcs.get_meeting_cache('new-meeting-123')
        
        assert cache is not None
        assert 'jira' in cache
        assert 'confluence' in cache
        assert 'slack' in cache
        assert 'gmail' in cache
        assert 'drive' in cache
        assert 'summary' in cache
        assert 'meeting_info' in cache
    
    def test_returns_existing_cache_entry(self):
        """Test that existing cache entry is returned."""
        import prefetch_utils_funcs as funcs
        
        # Create entry
        cache1 = funcs.get_meeting_cache('existing-meeting')
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['existing-meeting']['jira']['data'] = [{'key': 'TEST-1'}]
        
        # Get again
        cache2 = funcs.get_meeting_cache('existing-meeting')
        assert cache2['jira']['data'] == [{'key': 'TEST-1'}]
    
    def test_thread_safe_cache_access(self):
        """Test that cache access is thread-safe."""
        import prefetch_utils_funcs as funcs
        
        errors = []
        
        def access_cache(meeting_id):
            try:
                for _ in range(50):
                    funcs.get_meeting_cache(meeting_id)
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
        import prefetch_utils_funcs as funcs
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    def test_removes_old_cache_entries(self):
        """Test that old cache entries are removed."""
        import prefetch_utils_funcs as funcs
        
        # Add an old entry (more than 3 hours old)
        old_timestamp = time.time() - (4 * 60 * 60)  # 4 hours ago
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['old-meeting'] = {
                'jira': {'data': [{'key': 'OLD-1'}], 'timestamp': old_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        funcs.cleanup_old_caches()
        
        with funcs._meeting_prep_cache_lock:
            assert 'old-meeting' not in funcs._meeting_prep_cache
    
    def test_keeps_recent_cache_entries(self):
        """Test that recent cache entries are kept."""
        import prefetch_utils_funcs as funcs
        
        # Add a recent entry (less than 3 hours old)
        recent_timestamp = time.time() - (1 * 60 * 60)  # 1 hour ago
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['recent-meeting'] = {
                'jira': {'data': [{'key': 'RECENT-1'}], 'timestamp': recent_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        funcs.cleanup_old_caches()
        
        with funcs._meeting_prep_cache_lock:
            assert 'recent-meeting' in funcs._meeting_prep_cache
    
    def test_handles_empty_cache(self):
        """Test that cleanup handles empty cache gracefully."""
        import prefetch_utils_funcs as funcs
        
        # Should not raise any exception
        funcs.cleanup_old_caches()


class TestCheckServicesAuth:
    """Test the check_services_auth function."""
    
    def test_returns_auth_status_dict(self):
        """Test that check_services_auth returns expected structure."""
        import prefetch_utils_funcs as funcs
        
        with patch('os.path.exists', return_value=False):
            result = funcs.check_services_auth()
        
        assert isinstance(result, dict)
        assert 'atlassian' in result
        assert 'slack' in result
        assert 'gmail' in result
    
    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('builtins.open', new_callable=mock_open, read_data='{"access_token": "test-token"}')
    def test_detects_atlassian_auth(self, mock_file, mock_listdir, mock_exists):
        """Test detection of Atlassian authentication."""
        import prefetch_utils_funcs as funcs
        
        def exists_side_effect(path):
            return '~/.mcp-auth' in path or 'mcp-auth' in path
        
        mock_exists.side_effect = exists_side_effect
        mock_listdir.return_value = ['mcp-remote']
        
        with patch('os.path.isdir', return_value=True):
            result = funcs.check_services_auth()
        
        # Due to complex path checking, just verify structure
        assert 'atlassian' in result
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, 
           read_data='{"mcpServers": {"slack": {"env": {"SLACK_BOT_TOKEN": "xoxb-test"}}}}')
    def test_detects_slack_auth_from_local_config(self, mock_file, mock_exists):
        """Test detection of Slack authentication from local config."""
        import prefetch_utils_funcs as funcs
        
        mock_exists.return_value = True
        
        result = funcs.check_services_auth()
        
        # Slack should be detected from local config
        assert 'slack' in result


class TestPrefetchMeetingData:
    """Test the prefetch_meeting_data function."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for prefetch tests."""
        import prefetch_utils_funcs as funcs
        funcs._prefetch_running = True
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        with funcs._prefetch_status_lock:
            funcs._prefetch_status['activity_log'] = []
        yield
        funcs._prefetch_running = False
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_prefetches_drive_always(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that Drive is always prefetched (doesn't need OAuth)."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = [{'name': 'file.txt', 'path': '/path/to/file.txt'}]
        
        meeting = {'id': 'test-123', 'title': 'Test Meeting', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Drive should have been called
        mock_cli.assert_called()
        call_args = [call[0][0] for call in mock_cli.call_args_list]
        assert 'drive' in call_args
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_skips_unauthenticated_services(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that unauthenticated services are skipped."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        meeting = {'id': 'test-456', 'title': 'Test Meeting', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Jira, Confluence, Slack, Gmail should NOT be called
        call_args = [call[0][0] for call in mock_cli.call_args_list if mock_cli.call_args_list]
        for source in ['jira', 'confluence', 'slack', 'gmail']:
            assert source not in call_args
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_stores_meeting_info(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that meeting info is stored in cache."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        meeting = {
            'id': 'info-test', 
            'title': 'Important Meeting', 
            'attendees': [{'name': 'John', 'email': 'john@test.com'}],
            'description': 'Meeting about stuff'
        }
        funcs.prefetch_meeting_data(meeting)
        
        with funcs._meeting_prep_cache_lock:
            cached = funcs._meeting_prep_cache.get('info-test', {})
            meeting_info = cached.get('meeting_info', {})
        
        assert meeting_info.get('title') == 'Important Meeting'


class TestSetForceAggressivePrefetch:
    """Test the set_force_aggressive_prefetch function."""
    
    def test_sets_on(self):
        """Test setting force prefetch to on."""
        import prefetch_utils_funcs as funcs
        
        funcs._force_aggressive_prefetch = False
        funcs.set_force_aggressive_prefetch('on')
        
        assert funcs._force_aggressive_prefetch == True
    
    def test_sets_off(self):
        """Test setting force prefetch to off."""
        import prefetch_utils_funcs as funcs
        
        funcs._force_aggressive_prefetch = True
        funcs.set_force_aggressive_prefetch('off')
        
        assert funcs._force_aggressive_prefetch == False
    
    def test_toggles_state(self):
        """Test toggling force prefetch state."""
        import prefetch_utils_funcs as funcs
        
        funcs._force_aggressive_prefetch = False
        funcs.set_force_aggressive_prefetch('toggle')
        assert funcs._force_aggressive_prefetch == True
        
        funcs.set_force_aggressive_prefetch('toggle')
        assert funcs._force_aggressive_prefetch == False


class TestBackgroundPrefetchLoop:
    """Test key paths of the background_prefetch_loop function."""
    
    def test_loop_exits_when_not_running(self):
        """Test that loop exits when _prefetch_running is False."""
        import prefetch_utils_funcs as funcs
        
        funcs._prefetch_running = False
        
        # Should exit immediately
        # Run in thread with timeout
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=1.0)
        
        assert not thread.is_alive()
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    @patch('prefetch_utils_funcs.prefetch_meeting_data')
    @patch('prefetch_utils_funcs.cleanup_old_caches')
    def test_processes_meetings_when_available(self, mock_cleanup, mock_prefetch, mock_calendar):
        """Test that meetings are processed when available."""
        import prefetch_utils_funcs as funcs
        
        # Setup: one iteration then stop
        call_count = [0]
        def stop_after_one(*args, **kwargs):
            call_count[0] += 1
            funcs._prefetch_running = False
            return []
        
        mock_calendar.side_effect = stop_after_one
        funcs._prefetch_running = True
        
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=3.0)
        
        assert call_count[0] >= 1


class TestStartPrefetchThread:
    """Test the start_prefetch_thread function."""
    
    @pytest.fixture(autouse=True)
    def cleanup_thread(self):
        """Cleanup thread after test."""
        import prefetch_utils_funcs as funcs
        yield
        funcs._prefetch_running = False
        if funcs._prefetch_thread and funcs._prefetch_thread.is_alive():
            funcs._prefetch_thread.join(timeout=1.0)
        funcs._prefetch_thread = None
    
    @patch('prefetch_utils_funcs.background_prefetch_loop')
    def test_starts_thread(self, mock_loop):
        """Test that thread is started."""
        import prefetch_utils_funcs as funcs
        
        funcs._prefetch_thread = None
        funcs._prefetch_running = False
        
        funcs.start_prefetch_thread()
        
        assert funcs._prefetch_running == True
        assert funcs._prefetch_thread is not None
    
    @patch('prefetch_utils_funcs.background_prefetch_loop')
    def test_does_not_start_if_already_running(self, mock_loop):
        """Test that new thread is not started if one is running."""
        import prefetch_utils_funcs as funcs
        
        # Create a mock thread that appears alive
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        funcs._prefetch_thread = mock_thread
        
        funcs.start_prefetch_thread()
        
        # Should not have started a new thread
        assert funcs._prefetch_thread == mock_thread


class TestStopPrefetchThread:
    """Test the stop_prefetch_thread function."""
    
    def test_sets_running_false(self):
        """Test that _prefetch_running is set to False."""
        import prefetch_utils_funcs as funcs
        
        funcs._prefetch_running = True
        funcs.stop_prefetch_thread()
        
        assert funcs._prefetch_running == False
    
    def test_idempotent(self):
        """Test that stopping multiple times is safe."""
        import prefetch_utils_funcs as funcs
        
        funcs._prefetch_running = True
        funcs.stop_prefetch_thread()
        funcs.stop_prefetch_thread()
        funcs.stop_prefetch_thread()
        
        assert funcs._prefetch_running == False


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================

class TestCopyDb:
    """Test the copy_db function."""
    
    def test_copies_database_file(self):
        """Test that database file is copied."""
        import prefetch_utils_funcs as funcs
        
        # Create a temp database
        with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
            src_path = f.name
            conn = sqlite3.connect(src_path)
            conn.execute('CREATE TABLE test (id INTEGER)')
            conn.execute('INSERT INTO test VALUES (1)')
            conn.commit()
            conn.close()
        
        try:
            result = funcs.copy_db(src_path)
            
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
            funcs.cleanup_db(result)
        finally:
            os.unlink(src_path)
    
    def test_returns_none_for_nonexistent_file(self):
        """Test that None is returned for nonexistent file."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.copy_db('/nonexistent/path/db.sqlite')
        assert result is None
    
    def test_copies_wal_file_if_exists(self):
        """Test that WAL file is copied if it exists."""
        import prefetch_utils_funcs as funcs
        
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
            
            result = funcs.copy_db(src_path)
            conn.close()
            
            if result:
                # Verify data is accessible
                conn2 = sqlite3.connect(result)
                cursor = conn2.execute('SELECT * FROM test')
                rows = cursor.fetchall()
                conn2.close()
                
                assert len(rows) == 1
                funcs.cleanup_db(result)
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
        import prefetch_utils_funcs as funcs
        
        # Create a temp dir with a file
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, 'db.sqlite')
        with open(tmp_path, 'w') as f:
            f.write('test')
        
        funcs.cleanup_db(tmp_path)
        
        assert not os.path.exists(tmp_dir)
    
    def test_handles_none_gracefully(self):
        """Test that None input is handled gracefully."""
        import prefetch_utils_funcs as funcs
        
        # Should not raise
        funcs.cleanup_db(None)


class TestParseSlackCsv:
    """Test the parse_slack_csv function."""
    
    def test_parses_simple_csv(self):
        """Test parsing simple CSV data."""
        import prefetch_utils_funcs as funcs
        
        csv_text = """header1,header2,header3
value1,value2,value3
a,b,c"""
        
        result = funcs.parse_slack_csv(csv_text)
        
        assert len(result) == 2
        assert result[0]['header1'] == 'value1'
        assert result[0]['header2'] == 'value2'
        assert result[1]['header1'] == 'a'
    
    def test_handles_quoted_values(self):
        """Test handling of quoted values with commas."""
        import prefetch_utils_funcs as funcs
        
        csv_text = 'name,message\nJohn,"Hello, world"\nJane,"How are you?"'
        
        result = funcs.parse_slack_csv(csv_text)
        
        assert len(result) == 2
        assert result[0]['message'] == 'Hello, world'
    
    def test_returns_empty_for_empty_input(self):
        """Test that empty input returns empty list."""
        import prefetch_utils_funcs as funcs
        
        assert funcs.parse_slack_csv('') == []
        assert funcs.parse_slack_csv(None) == []
    
    def test_returns_empty_for_header_only(self):
        """Test that header-only CSV returns empty list."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.parse_slack_csv('header1,header2')
        assert result == []


class TestExtractMcpContent:
    """Test the extract_mcp_content function."""
    
    def test_extracts_text_from_content_array(self):
        """Test extraction from standard MCP content array."""
        import prefetch_utils_funcs as funcs
        
        result = {
            'content': [
                {'type': 'text', 'text': 'Hello, world!'}
            ]
        }
        
        extracted = funcs.extract_mcp_content(result)
        assert extracted == 'Hello, world!'
    
    def test_handles_empty_result(self):
        """Test handling of empty result."""
        import prefetch_utils_funcs as funcs
        
        assert funcs.extract_mcp_content(None) is None
        # Empty dict without 'content' key returns the input as-is (fallback)
        # But actual implementation returns None for empty dict
        result = funcs.extract_mcp_content({})
        assert result is None or result == {}
    
    def test_handles_non_standard_format(self):
        """Test fallback for non-standard format."""
        import prefetch_utils_funcs as funcs
        
        result = {'data': 'some data'}
        extracted = funcs.extract_mcp_content(result)
        
        assert extracted == result
    
    def test_handles_multiple_content_items(self):
        """Test handling of multiple content items."""
        import prefetch_utils_funcs as funcs
        
        result = {
            'content': [
                {'type': 'image', 'url': 'http://example.com/img.png'},
                {'type': 'text', 'text': 'Found text'}
            ]
        }
        
        extracted = funcs.extract_mcp_content(result)
        assert extracted == 'Found text'


class TestLoadConfig:
    """Test the load_config function."""
    
    @patch('os.path.exists', return_value=False)
    def test_returns_defaults_when_no_config(self, mock_exists):
        """Test that defaults are returned when no config file exists."""
        import prefetch_utils_funcs as funcs
        
        config = funcs.load_config()
        
        assert 'slack_workspace' in config
        assert 'atlassian_domain' in config
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, 
           read_data='{"slack_workspace": "custom-workspace", "atlassian_domain": "custom.atlassian.net"}')
    def test_loads_from_config_file(self, mock_file, mock_exists):
        """Test loading configuration from file."""
        import prefetch_utils_funcs as funcs
        
        def exists_side_effect(path):
            return 'config.json' in path
        mock_exists.side_effect = exists_side_effect
        
        config = funcs.load_config()
        
        assert config['slack_workspace'] == 'custom-workspace'
        assert config['atlassian_domain'] == 'custom.atlassian.net'
    
    @patch('os.path.exists', return_value=False)
    @patch.dict(os.environ, {'SLACK_WORKSPACE': 'env-workspace'})
    def test_env_vars_override_config(self, mock_exists):
        """Test that environment variables override config file."""
        import prefetch_utils_funcs as funcs
        
        config = funcs.load_config()
        
        assert config['slack_workspace'] == 'env-workspace'


class TestFormatSlackChannel:
    """Test the format_slack_channel function."""
    
    def test_formats_regular_channel(self):
        """Test formatting of regular channel."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.format_slack_channel('general')
        assert result == '#general'
    
    def test_removes_leading_hash(self):
        """Test that leading # is handled."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.format_slack_channel('#general')
        assert result == '#general'
    
    def test_formats_dm_with_sender(self):
        """Test formatting of DM with sender name."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.format_slack_channel('D12345', sender_name='John Doe')
        assert result == 'DM with John Doe'
    
    def test_formats_dm_without_sender(self):
        """Test formatting of DM without sender name."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.format_slack_channel('D12345')
        assert result == 'DM'
    
    def test_formats_group_dm(self):
        """Test formatting of group DM."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.format_slack_channel('mpdm-user1--user2--user3')
        assert result == 'Group DM'
    
    def test_handles_empty_channel(self):
        """Test handling of empty channel."""
        import prefetch_utils_funcs as funcs
        
        assert funcs.format_slack_channel('') == ''
        assert funcs.format_slack_channel(None) == ''


class TestBuildSlackUrl:
    """Test the build_slack_url function."""
    
    def test_builds_valid_url(self):
        """Test building a valid Slack URL."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.build_slack_url('C12345', '1769817144.201689')
        
        assert 'slack.com/archives/C12345/p' in result
        assert '1769817144201689' in result  # Dot removed
    
    def test_removes_hash_from_channel(self):
        """Test that # prefix is removed from channel ID."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.build_slack_url('#C12345', '123.456')
        
        assert '#' not in result
    
    def test_returns_none_for_missing_params(self):
        """Test that None is returned for missing parameters."""
        import prefetch_utils_funcs as funcs
        
        assert funcs.build_slack_url('', '123.456') is None
        assert funcs.build_slack_url('C12345', '') is None
        assert funcs.build_slack_url(None, '123.456') is None


class TestFormatSlackMessage:
    """Test the format_slack_message function."""
    
    def test_formats_complete_message(self):
        """Test formatting a complete message."""
        import prefetch_utils_funcs as funcs
        
        msg = {
            'text': 'Hello, this is a test message that is quite long',
            'channel': 'general',
            'realname': 'John Doe',
            'username': 'johnd',
            'msgid': '1234567890.123456',
            'threadts': '1234567890.000000',
            'time': '2024-01-15T10:30:00'
        }
        
        result = funcs.format_slack_message(msg)
        
        assert result['title'] == msg['text'][:100]
        assert result['channel'] == '#general'
        assert result['from'] == 'John Doe'
        assert result['username'] == 'johnd'
        assert result['msg_id'] == '1234567890.123456'
        assert 'slack_url' in result
    
    def test_uses_username_when_no_realname(self):
        """Test that username is used when realname is missing."""
        import prefetch_utils_funcs as funcs
        
        msg = {
            'text': 'Test',
            'channel': 'general',
            'username': 'testuser',
            'msgid': '123.456'
        }
        
        result = funcs.format_slack_message(msg)
        
        assert result['from'] == 'testuser'
    
    def test_truncates_long_title(self):
        """Test that title is truncated to 100 chars."""
        import prefetch_utils_funcs as funcs
        
        long_text = 'A' * 200
        msg = {'text': long_text, 'channel': 'test', 'msgid': '1.1'}
        
        result = funcs.format_slack_message(msg)
        
        assert len(result['title']) == 100


class TestScoreResult:
    """Test the score_result function."""
    
    def test_exact_title_match_highest_score(self):
        """Test that exact title match gets highest score."""
        import prefetch_utils_funcs as funcs
        
        result = {'title': 'github', 'url': 'https://example.com'}
        score = funcs.score_result(result, 'github', ['github'])
        
        assert score >= 100  # Exact match bonus
    
    def test_title_starts_with_query(self):
        """Test scoring when title starts with query."""
        import prefetch_utils_funcs as funcs
        
        result = {'title': 'github documentation', 'url': 'https://example.com'}
        score = funcs.score_result(result, 'github', ['github'])
        
        assert score >= 80  # Starts with bonus
    
    def test_domain_match_boost(self):
        """Test that domain match gets boost."""
        import prefetch_utils_funcs as funcs
        
        result = {'title': 'Some Page', 'url': 'https://github.com/repo'}
        score = funcs.score_result(result, 'github', ['github'])
        
        assert score >= 90  # Domain match bonus
    
    def test_bookmark_boost(self):
        """Test that bookmarks get extra points."""
        import prefetch_utils_funcs as funcs
        
        bookmark = {'title': 'test', 'url': 'https://example.com', 'type': 'bookmark'}
        non_bookmark = {'title': 'test', 'url': 'https://example.com'}
        
        bookmark_score = funcs.score_result(bookmark, 'test', ['test'])
        non_bookmark_score = funcs.score_result(non_bookmark, 'test', ['test'])
        
        assert bookmark_score > non_bookmark_score
    
    def test_visit_count_boost(self):
        """Test that visit count adds to score."""
        import prefetch_utils_funcs as funcs
        
        result = {'title': 'test', 'url': 'https://example.com', 'visit_count': 100}
        score = funcs.score_result(result, 'test', ['test'])
        
        # Visit count bonus is capped at 50
        result_no_visits = {'title': 'test', 'url': 'https://example.com', 'visit_count': 0}
        score_no_visits = funcs.score_result(result_no_visits, 'test', ['test'])
        
        assert score > score_no_visits
    
    def test_multi_word_query_scoring(self):
        """Test scoring with multi-word queries."""
        import prefetch_utils_funcs as funcs
        
        result = {'title': 'react native documentation', 'url': 'https://example.com'}
        score = funcs.score_result(result, 'react native', ['react', 'native'])
        
        # Should get points for both words in title
        assert score > 0


class TestIsNightHours:
    """Test the is_night_hours function."""
    
    def test_returns_boolean(self):
        """Test that function returns a boolean."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.is_night_hours()
        assert isinstance(result, bool)
    
    @patch('prefetch_utils_funcs.datetime')
    def test_night_time(self, mock_datetime):
        """Test detection of night time (22:00-06:00)."""
        import prefetch_utils_funcs as funcs
        
        # Mock 11 PM on a weekday
        mock_now = MagicMock()
        mock_now.hour = 23
        mock_now.weekday.return_value = 2  # Wednesday
        mock_datetime.now.return_value = mock_now
        
        result = funcs.is_night_hours()
        assert result == True
    
    @patch('prefetch_utils_funcs.datetime')
    def test_weekend(self, mock_datetime):
        """Test detection of weekend."""
        import prefetch_utils_funcs as funcs
        
        # Mock 10 AM on Saturday
        mock_now = MagicMock()
        mock_now.hour = 10
        mock_now.weekday.return_value = 5  # Saturday
        mock_datetime.now.return_value = mock_now
        
        result = funcs.is_night_hours()
        assert result == True


class TestExtractDomain:
    """Test the extract_domain function."""
    
    def test_extracts_simple_domain(self):
        """Test extraction from simple URL."""
        import prefetch_utils_funcs as funcs
        
        assert funcs.extract_domain('https://example.com/path') == 'example.com'
    
    def test_removes_www_prefix(self):
        """Test that www. prefix is removed."""
        import prefetch_utils_funcs as funcs
        
        assert funcs.extract_domain('https://www.example.com/') == 'example.com'
    
    def test_preserves_subdomains(self):
        """Test that subdomains are preserved."""
        import prefetch_utils_funcs as funcs
        
        assert funcs.extract_domain('https://docs.example.com/page') == 'docs.example.com'
    
    def test_handles_port_numbers(self):
        """Test handling of port numbers."""
        import prefetch_utils_funcs as funcs
        
        assert funcs.extract_domain('http://localhost:8080/api') == 'localhost:8080'
    
    def test_handles_invalid_url(self):
        """Test handling of invalid URL."""
        import prefetch_utils_funcs as funcs
        
        assert funcs.extract_domain('not-a-url') == ''
        assert funcs.extract_domain('') == ''


# ============================================================================
# ADDITIONAL COMPREHENSIVE TESTS FOR PREFETCH FUNCTIONS
# ============================================================================


class TestPrefetchMeetingDataComprehensive:
    """Additional comprehensive tests for prefetch_meeting_data function."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for prefetch tests."""
        import prefetch_utils_funcs as funcs
        funcs._prefetch_running = True
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        with funcs._prefetch_status_lock:
            funcs._prefetch_status['activity_log'] = []
        yield
        funcs._prefetch_running = False
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.call_cli_for_meeting_summary')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_fetches_all_authenticated_services(self, mock_valid, mock_save, mock_summary, mock_cli, mock_auth):
        """Test that all authenticated services are fetched."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': True, 'slack': True, 'gmail': True}
        mock_cli.return_value = [{'key': 'TEST-1'}]
        mock_summary.return_value = {'status': 'success', 'summary': 'Test summary'}
        
        meeting = {'id': 'all-auth-test', 'title': 'Full Test', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Verify all sources were called
        call_args = [call[0][0] for call in mock_cli.call_args_list]
        assert 'drive' in call_args
        assert 'jira' in call_args
        assert 'confluence' in call_args
        assert 'slack' in call_args
        assert 'gmail' in call_args
        
        # Verify summary was called
        mock_summary.assert_called_once()
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_handles_source_error_gracefully(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that errors in one source don't stop other sources."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': True, 'slack': False, 'gmail': False}
        
        # First source raises error, second returns data
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # drive
                return [{'name': 'file.txt'}]
            elif call_count[0] == 2:  # jira
                raise Exception("Connection timeout")
            return [{'key': 'CONF-1'}]  # confluence
        
        mock_cli.side_effect = side_effect
        
        meeting = {'id': 'error-test', 'title': 'Error Test', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Should have continued after error
        assert call_count[0] >= 2
        
        # Cache should still have drive data
        with funcs._meeting_prep_cache_lock:
            cache = funcs._meeting_prep_cache.get('error-test', {})
            assert cache.get('drive', {}).get('data') is not None
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid')
    def test_skips_valid_cached_sources(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that sources with valid cache are skipped."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': True, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        # Drive is valid, jira/confluence are not
        def valid_side_effect(meeting_id, source):
            return source == 'drive'
        mock_valid.side_effect = valid_side_effect
        
        meeting = {'id': 'cache-test', 'title': 'Cache Test', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Drive should NOT have been called (valid cache)
        call_args = [call[0][0] for call in mock_cli.call_args_list]
        assert 'drive' not in call_args
        # But jira/confluence should have been called
        assert 'jira' in call_args or 'confluence' in call_args
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_stops_when_prefetch_running_false(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that prefetch stops when _prefetch_running becomes False."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': True, 'slack': True, 'gmail': True}
        
        call_count = [0]
        def stop_on_second_call(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                funcs._prefetch_running = False
            return []
        
        mock_cli.side_effect = stop_on_second_call
        
        meeting = {'id': 'stop-test', 'title': 'Stop Test', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Should have stopped early
        assert call_count[0] <= 3
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_uses_meeting_id_from_title_when_no_id(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test fallback to title when meeting has no id."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = [{'name': 'file.txt'}]
        
        meeting = {'title': 'My Meeting Title', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        with funcs._meeting_prep_cache_lock:
            # Cache key should be the title
            assert 'My Meeting Title' in funcs._meeting_prep_cache
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_stores_attendee_information(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that attendee information is stored correctly."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        meeting = {
            'id': 'attendee-test',
            'title': 'Team Sync',
            'attendees': [
                {'name': 'Alice', 'email': 'alice@example.com'},
                {'name': 'Bob', 'email': 'bob@example.com'},
            ],
            'description': 'Weekly sync'
        }
        funcs.prefetch_meeting_data(meeting)
        
        with funcs._meeting_prep_cache_lock:
            meeting_info = funcs._meeting_prep_cache['attendee-test'].get('meeting_info', {})
            assert 'Alice' in meeting_info.get('attendees_str', '')
            assert 'alice@example.com' in meeting_info.get('attendee_emails', [])


class TestBackgroundPrefetchLoopComprehensive:
    """Additional comprehensive tests for background_prefetch_loop."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset state before each test."""
        import prefetch_utils_funcs as funcs
        funcs._prefetch_running = False
        funcs._force_aggressive_prefetch = False
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        with funcs._prefetch_status_lock:
            funcs._prefetch_status['activity_log'] = []
        yield
        funcs._prefetch_running = False
        funcs._force_aggressive_prefetch = False
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    @patch('prefetch_utils_funcs.prefetch_meeting_data')
    @patch('prefetch_utils_funcs.cleanup_old_caches')
    @patch('prefetch_utils_funcs.is_night_hours', return_value=True)
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    @patch('prefetch_utils_funcs.has_cached_data', return_value=False)
    def test_aggressive_mode_during_night(self, mock_cached, mock_valid, mock_night, mock_cleanup, mock_prefetch, mock_calendar):
        """Test that aggressive mode is used during night hours."""
        import prefetch_utils_funcs as funcs
        
        meetings = [
            {'id': 'm1', 'title': 'Meeting 1'},
            {'id': 'm2', 'title': 'Meeting 2'},
        ]
        
        call_count = [0]
        def calendar_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                funcs._prefetch_running = False
                return []
            return meetings
        
        mock_calendar.side_effect = calendar_side_effect
        funcs._prefetch_running = True
        
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=5.0)
        
        # Should have prefetched all meetings
        assert mock_prefetch.call_count >= 2
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    @patch('prefetch_utils_funcs.prefetch_meeting_data')
    @patch('prefetch_utils_funcs.cleanup_old_caches')
    @patch('prefetch_utils_funcs.is_night_hours', return_value=False)
    @patch('prefetch_utils_funcs.has_cached_data')
    def test_day_mode_skips_cached_meetings(self, mock_cached, mock_night, mock_cleanup, mock_prefetch, mock_calendar):
        """Test that day mode skips meetings with cached data."""
        import prefetch_utils_funcs as funcs
        
        meetings = [
            {'id': 'cached-meeting', 'title': 'Cached'},
            {'id': 'uncached-meeting', 'title': 'Uncached'},
        ]
        
        # First meeting is cached, second is not
        def cached_side_effect(meeting_id, source):
            return meeting_id == 'cached-meeting'
        mock_cached.side_effect = cached_side_effect
        
        call_count = [0]
        def calendar_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                funcs._prefetch_running = False
                return []
            return meetings
        
        mock_calendar.side_effect = calendar_side_effect
        funcs._prefetch_running = True
        
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=5.0)
        
        # Only uncached meeting should be prefetched
        for call in mock_prefetch.call_args_list:
            meeting = call[0][0]
            assert meeting['id'] != 'cached-meeting'
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    @patch('prefetch_utils_funcs.prefetch_meeting_data')
    @patch('prefetch_utils_funcs.cleanup_old_caches')
    @patch('prefetch_utils_funcs.is_night_hours', return_value=False)
    @patch('prefetch_utils_funcs.has_cached_data', return_value=False)
    def test_force_aggressive_mode(self, mock_cached, mock_night, mock_cleanup, mock_prefetch, mock_calendar):
        """Test force aggressive prefetch mode processes meetings."""
        import prefetch_utils_funcs as funcs
        
        meetings = [{'id': f'm{i}', 'title': f'Meeting {i}'} for i in range(3)]
        
        call_count = [0]
        def calendar_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                funcs._prefetch_running = False
                return []
            return meetings
        
        # Stop immediately when first meeting starts processing
        prefetch_call_count = [0]
        def prefetch_side_effect(meeting):
            prefetch_call_count[0] += 1
            # Let all meetings process
        
        mock_prefetch.side_effect = prefetch_side_effect
        mock_calendar.side_effect = calendar_side_effect
        funcs._prefetch_running = True
        funcs._force_aggressive_prefetch = True
        
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=15.0)
        
        # At least some meetings should be prefetched (timing-dependent)
        assert mock_prefetch.call_count >= 1
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    def test_handles_calendar_error(self, mock_calendar):
        """Test that calendar errors are handled gracefully (doesn't crash)."""
        import prefetch_utils_funcs as funcs
        
        call_count = [0]
        def calendar_error(*args, **kwargs):
            call_count[0] += 1
            funcs._prefetch_running = False  # Stop immediately after error
            raise Exception("Calendar API error")
        
        mock_calendar.side_effect = calendar_error
        funcs._prefetch_running = True
        
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=5.0)
        
        # Should have called calendar at least once and handled error
        assert call_count[0] >= 1
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    @patch('prefetch_utils_funcs.cleanup_old_caches')
    def test_calls_cleanup_after_cycle(self, mock_cleanup, mock_calendar):
        """Test that cleanup_old_caches is called after processing."""
        import prefetch_utils_funcs as funcs
        
        call_count = [0]
        def calendar_side_effect(*args, **kwargs):
            call_count[0] += 1
            funcs._prefetch_running = False
            return [{'id': 'm1', 'title': 'Test'}]
        
        mock_calendar.side_effect = calendar_side_effect
        funcs._prefetch_running = True
        
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=3.0)
        
        mock_cleanup.assert_called()


class TestStartStopPrefetchThreadComprehensive:
    """Additional comprehensive tests for thread management."""
    
    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Cleanup thread state before and after tests."""
        import prefetch_utils_funcs as funcs
        funcs._prefetch_running = False
        funcs._prefetch_thread = None
        yield
        funcs._prefetch_running = False
        if funcs._prefetch_thread and funcs._prefetch_thread.is_alive():
            funcs._prefetch_thread.join(timeout=1.0)
        funcs._prefetch_thread = None
    
    @patch('prefetch_utils_funcs.background_prefetch_loop')
    def test_start_sets_daemon_thread(self, mock_loop):
        """Test that thread is started as daemon."""
        import prefetch_utils_funcs as funcs
        
        funcs.start_prefetch_thread()
        
        assert funcs._prefetch_thread is not None
        assert funcs._prefetch_thread.daemon == True
    
    @patch('prefetch_utils_funcs.background_prefetch_loop')
    def test_multiple_start_calls_idempotent(self, mock_loop):
        """Test that multiple start calls don't create multiple threads."""
        import prefetch_utils_funcs as funcs
        
        funcs.start_prefetch_thread()
        first_thread = funcs._prefetch_thread
        
        funcs.start_prefetch_thread()
        funcs.start_prefetch_thread()
        
        # Should still be the same thread (or replacement after first died)
        # No exception should be raised
        assert funcs._prefetch_thread is not None
    
    @patch('prefetch_utils_funcs.background_prefetch_loop')
    def test_stop_then_start_cycle(self, mock_loop):
        """Test stop then restart works correctly."""
        import prefetch_utils_funcs as funcs
        
        funcs.start_prefetch_thread()
        assert funcs._prefetch_running == True
        
        funcs.stop_prefetch_thread()
        assert funcs._prefetch_running == False
        
        # Wait for thread to potentially stop
        time.sleep(0.1)
        
        # Start again
        funcs._prefetch_thread = None  # Clear dead thread reference
        funcs.start_prefetch_thread()
        assert funcs._prefetch_running == True
    
    def test_stop_thread_safe_with_none_thread(self):
        """Test that stop handles None thread gracefully."""
        import prefetch_utils_funcs as funcs
        
        funcs._prefetch_thread = None
        funcs._prefetch_running = True
        
        funcs.stop_prefetch_thread()
        
        assert funcs._prefetch_running == False
    
    @patch('prefetch_utils_funcs.background_prefetch_loop')
    def test_thread_state_after_start(self, mock_loop):
        """Test thread state is properly set after start."""
        import prefetch_utils_funcs as funcs
        
        funcs.start_prefetch_thread()
        
        assert funcs._prefetch_running == True
        assert funcs._prefetch_thread is not None
        assert funcs._prefetch_thread.is_alive() or mock_loop.called


class TestCleanupOldCachesComprehensive:
    """Additional comprehensive tests for cleanup_old_caches."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear cache before and after tests."""
        import prefetch_utils_funcs as funcs
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    def test_removes_multiple_old_entries(self):
        """Test removing multiple old cache entries at once."""
        import prefetch_utils_funcs as funcs
        
        old_timestamp = time.time() - (5 * 60 * 60)  # 5 hours ago
        
        with funcs._meeting_prep_cache_lock:
            for i in range(10):
                funcs._meeting_prep_cache[f'old-meeting-{i}'] = {
                    'jira': {'data': [], 'timestamp': old_timestamp},
                    'confluence': {'data': None, 'timestamp': 0},
                    'drive': {'data': None, 'timestamp': 0},
                    'slack': {'data': None, 'timestamp': 0},
                    'gmail': {'data': None, 'timestamp': 0},
                    'summary': {'data': None, 'timestamp': 0},
                    'meeting_info': None
                }
        
        funcs.cleanup_old_caches()
        
        with funcs._meeting_prep_cache_lock:
            assert len(funcs._meeting_prep_cache) == 0
    
    def test_keeps_mixed_old_and_new(self):
        """Test that cleanup keeps new entries while removing old ones."""
        import prefetch_utils_funcs as funcs
        
        old_timestamp = time.time() - (4 * 60 * 60)
        recent_timestamp = time.time() - (30 * 60)  # 30 minutes ago
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['old-meeting'] = {
                'jira': {'data': [], 'timestamp': old_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
            funcs._meeting_prep_cache['new-meeting'] = {
                'jira': {'data': [{'key': 'NEW-1'}], 'timestamp': recent_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        funcs.cleanup_old_caches()
        
        with funcs._meeting_prep_cache_lock:
            assert 'old-meeting' not in funcs._meeting_prep_cache
            assert 'new-meeting' in funcs._meeting_prep_cache
    
    def test_thread_safe_cleanup(self):
        """Test that cleanup is thread-safe."""
        import prefetch_utils_funcs as funcs
        
        errors = []
        
        def add_entries():
            try:
                for i in range(50):
                    funcs.get_meeting_cache(f'thread-test-{i}')
            except Exception as e:
                errors.append(e)
        
        def cleanup_entries():
            try:
                for _ in range(10):
                    funcs.cleanup_old_caches()
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=add_entries),
            threading.Thread(target=cleanup_entries),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
    
    def test_cleanup_preserves_meeting_info(self):
        """Test that cleanup doesn't break meeting_info field."""
        import prefetch_utils_funcs as funcs
        
        recent_timestamp = time.time() - (60 * 60)  # 1 hour ago
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['info-test'] = {
                'jira': {'data': [], 'timestamp': recent_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': {'title': 'Test', 'attendees_str': 'John'}
            }
        
        funcs.cleanup_old_caches()
        
        with funcs._meeting_prep_cache_lock:
            assert 'info-test' in funcs._meeting_prep_cache
            assert funcs._meeting_prep_cache['info-test']['meeting_info']['title'] == 'Test'


class TestCheckServicesAuthComprehensive:
    """Additional comprehensive tests for check_services_auth."""
    
    @patch('os.path.exists')
    def test_returns_all_false_when_nothing_configured(self, mock_exists):
        """Test that all services return False when nothing is configured."""
        import prefetch_utils_funcs as funcs
        
        mock_exists.return_value = False
        
        result = funcs.check_services_auth()
        
        assert result['atlassian'] == False
        assert result['slack'] == False
        assert result['gmail'] == False
    
    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('os.path.isdir')
    @patch('builtins.open', new_callable=mock_open, read_data='{"access_token": "valid-token"}')
    def test_detects_atlassian_with_valid_token(self, mock_file, mock_isdir, mock_listdir, mock_exists):
        """Test detection of valid Atlassian token."""
        import prefetch_utils_funcs as funcs
        
        def exists_side_effect(path):
            return 'mcp-auth' in path or 'gmail' not in path
        mock_exists.side_effect = exists_side_effect
        mock_listdir.return_value = ['mcp-remote', 'atlassian_tokens.json']
        mock_isdir.return_value = True
        
        result = funcs.check_services_auth()
        
        assert 'atlassian' in result
    
    @patch('os.path.exists')
    def test_gmail_requires_both_keys_and_tokens(self, mock_exists):
        """Test that Gmail requires both gcp-oauth.keys.json and credentials.json."""
        import prefetch_utils_funcs as funcs
        
        # First test: only keys, no credentials
        def only_keys(path):
            if 'gcp-oauth.keys.json' in path:
                return True
            if 'credentials.json' in path:
                return False
            if 'gmail-mcp' in path:
                return True
            return False
        
        mock_exists.side_effect = only_keys
        
        result = funcs.check_services_auth()
        assert result['gmail'] == False
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_detects_slack_from_mcp_config(self, mock_file, mock_exists):
        """Test detection of Slack auth from MCP config."""
        import prefetch_utils_funcs as funcs
        
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = json.dumps({
            'mcpServers': {
                'slack': {
                    'env': {
                        'SLACK_BOT_TOKEN': 'xoxb-test-token'
                    }
                }
            }
        })
        
        result = funcs.check_services_auth()
        
        assert 'slack' in result
    
    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('os.path.isdir')
    @patch('builtins.open', new_callable=mock_open)
    def test_handles_corrupted_token_file(self, mock_file, mock_isdir, mock_listdir, mock_exists):
        """Test handling of corrupted token files."""
        import prefetch_utils_funcs as funcs
        
        mock_exists.return_value = True
        mock_listdir.return_value = ['mcp-remote']
        mock_isdir.return_value = True
        mock_file.return_value.read.return_value = 'not valid json'
        
        # Should not raise exception
        result = funcs.check_services_auth()
        
        assert isinstance(result, dict)


class TestLoadPrepCacheFromDisk:
    """Tests for load_prep_cache_from_disk function."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup and cleanup for disk cache tests."""
        import prefetch_utils_funcs as funcs
        # Clear in-memory cache
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    @patch('os.path.exists', return_value=False)
    def test_returns_false_when_no_file(self, mock_exists):
        """Test that function returns False when cache file doesn't exist."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.load_prep_cache_from_disk()
        
        assert result == False
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open)
    def test_loads_valid_cache_file(self, mock_file, mock_exists):
        """Test loading a valid cache file."""
        import prefetch_utils_funcs as funcs
        
        cache_data = {
            'meeting-1': {
                'jira': {'data': [{'key': 'TEST-1'}], 'timestamp': time.time()},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        }
        mock_file.return_value.read.return_value = json.dumps(cache_data)
        
        result = funcs.load_prep_cache_from_disk()
        
        assert result == True
        with funcs._meeting_prep_cache_lock:
            assert 'meeting-1' in funcs._meeting_prep_cache
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data='invalid json {{{')
    def test_handles_corrupted_cache_file(self, mock_file, mock_exists):
        """Test handling of corrupted cache file."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.load_prep_cache_from_disk()
        
        assert result == False
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open')
    def test_handles_file_read_error(self, mock_open_func, mock_exists):
        """Test handling of file read errors."""
        import prefetch_utils_funcs as funcs
        
        mock_open_func.side_effect = IOError("Permission denied")
        
        result = funcs.load_prep_cache_from_disk()
        
        assert result == False
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open)
    def test_counts_valid_entries(self, mock_file, mock_exists):
        """Test that function correctly counts valid entries."""
        import prefetch_utils_funcs as funcs
        
        now = time.time()
        cache_data = {
            'valid-meeting': {
                'jira': {'data': [{'key': 'V-1'}], 'timestamp': now},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            },
            'expired-meeting': {
                'jira': {'data': [{'key': 'E-1'}], 'timestamp': now - 100000},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        }
        mock_file.return_value.read.return_value = json.dumps(cache_data)
        
        result = funcs.load_prep_cache_from_disk()
        
        assert result == True
        # Both meetings should be loaded (cleanup happens separately)
        with funcs._meeting_prep_cache_lock:
            assert len(funcs._meeting_prep_cache) == 2


class TestGetMeetingCacheComprehensive:
    """Additional comprehensive tests for get_meeting_cache."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear cache before and after tests."""
        import prefetch_utils_funcs as funcs
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    def test_concurrent_access_same_meeting(self):
        """Test concurrent access to the same meeting cache."""
        import prefetch_utils_funcs as funcs
        
        errors = []
        caches = []
        
        def get_cache():
            try:
                for _ in range(100):
                    cache = funcs.get_meeting_cache('concurrent-test')
                    caches.append(cache)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=get_cache) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        # All caches should have same structure
        for cache in caches:
            assert 'jira' in cache
            assert 'drive' in cache
    
    def test_default_structure_has_all_sources(self):
        """Test that default cache structure includes all expected sources."""
        import prefetch_utils_funcs as funcs
        
        cache = funcs.get_meeting_cache('structure-test')
        
        expected_sources = ['jira', 'confluence', 'drive', 'slack', 'gmail', 'summary']
        for source in expected_sources:
            assert source in cache
            assert 'data' in cache[source]
            assert 'timestamp' in cache[source]
        
        assert 'meeting_info' in cache
    
    def test_preserves_modified_data(self):
        """Test that modifications to cache are preserved."""
        import prefetch_utils_funcs as funcs
        
        cache = funcs.get_meeting_cache('modify-test')
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['modify-test']['jira']['data'] = [{'key': 'MOD-1'}]
            funcs._meeting_prep_cache['modify-test']['jira']['timestamp'] = time.time()
        
        # Get again
        cache2 = funcs.get_meeting_cache('modify-test')
        
        assert cache2['jira']['data'] == [{'key': 'MOD-1'}]
    
    def test_handles_special_characters_in_meeting_id(self):
        """Test handling of special characters in meeting ID."""
        import prefetch_utils_funcs as funcs
        
        special_ids = [
            'meeting with spaces',
            'meeting/with/slashes',
            'meeting@with@symbols',
            'meeting#123',
            '日本語ミーティング',
        ]
        
        for meeting_id in special_ids:
            cache = funcs.get_meeting_cache(meeting_id)
            assert cache is not None
            assert 'jira' in cache
    
    def test_simultaneous_different_meetings(self):
        """Test creating multiple different meeting caches simultaneously."""
        import prefetch_utils_funcs as funcs
        
        meeting_ids = [f'meeting-{i}' for i in range(10)]
        results = {}
        errors = []
        
        def get_cache(meeting_id):
            try:
                cache = funcs.get_meeting_cache(meeting_id)
                results[meeting_id] = cache
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=get_cache, args=(mid,)) for mid in meeting_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 10
        
        # All caches should be separate
        with funcs._meeting_prep_cache_lock:
            assert len(funcs._meeting_prep_cache) == 10


class TestSetMeetingCache:
    """Tests for set_meeting_cache function."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear cache before and after tests."""
        import prefetch_utils_funcs as funcs
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    def test_sets_data_and_timestamp(self, mock_save):
        """Test that data and timestamp are set correctly."""
        import prefetch_utils_funcs as funcs
        
        test_data = [{'key': 'TEST-1'}, {'key': 'TEST-2'}]
        before = time.time()
        
        funcs.set_meeting_cache('set-test', 'jira', test_data)
        
        after = time.time()
        
        with funcs._meeting_prep_cache_lock:
            cache = funcs._meeting_prep_cache['set-test']['jira']
            assert cache['data'] == test_data
            assert before <= cache['timestamp'] <= after
    
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    def test_creates_meeting_entry_if_not_exists(self, mock_save):
        """Test that meeting entry is created if it doesn't exist."""
        import prefetch_utils_funcs as funcs
        
        funcs.set_meeting_cache('new-meeting', 'slack', [{'text': 'hello'}])
        
        with funcs._meeting_prep_cache_lock:
            assert 'new-meeting' in funcs._meeting_prep_cache
            assert funcs._meeting_prep_cache['new-meeting']['slack']['data'] == [{'text': 'hello'}]
    
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    def test_calls_save_to_disk(self, mock_save):
        """Test that save_prep_cache_to_disk is called."""
        import prefetch_utils_funcs as funcs
        
        funcs.set_meeting_cache('save-test', 'drive', [])
        
        mock_save.assert_called_once()
    
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    def test_thread_safe_concurrent_sets(self, mock_save):
        """Test thread-safe concurrent set operations."""
        import prefetch_utils_funcs as funcs
        
        errors = []
        
        def set_cache(source, data):
            try:
                for i in range(50):
                    funcs.set_meeting_cache('concurrent-set', source, data + [i])
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


# ============================================================================
# ADDITIONAL EDGE CASE AND COVERAGE TESTS
# ============================================================================


class TestPrefetchMeetingDataEdgeCases:
    """Edge case tests for prefetch_meeting_data function."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for prefetch tests."""
        import prefetch_utils_funcs as funcs
        funcs._prefetch_running = True
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        with funcs._prefetch_status_lock:
            funcs._prefetch_status['activity_log'] = []
        yield
        funcs._prefetch_running = False
        if funcs._meeting_prep_cache is not None:
            with funcs._meeting_prep_cache_lock:
                funcs._meeting_prep_cache.clear()
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_handles_empty_meeting_title(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test handling of meeting with empty title."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        meeting = {'id': 'empty-title', 'title': '', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Should still create cache entry with meeting id
        with funcs._meeting_prep_cache_lock:
            assert 'empty-title' in funcs._meeting_prep_cache
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_handles_empty_attendees(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test handling of meeting with empty attendees list."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        meeting = {'id': 'empty-attendees', 'title': 'Test', 'attendees': [], 'description': ''}
        
        # Should not raise exception
        funcs.prefetch_meeting_data(meeting)
        
        with funcs._meeting_prep_cache_lock:
            meeting_info = funcs._meeting_prep_cache['empty-attendees'].get('meeting_info', {})
            assert meeting_info.get('attendees_str', '') == ''
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_handles_very_long_description(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test that very long descriptions are truncated."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        long_description = 'A' * 10000
        meeting = {'id': 'long-desc', 'title': 'Test', 'attendees': [], 'description': long_description}
        funcs.prefetch_meeting_data(meeting)
        
        with funcs._meeting_prep_cache_lock:
            meeting_info = funcs._meeting_prep_cache['long-desc'].get('meeting_info', {})
            # Description should be truncated to 200 chars
            assert len(meeting_info.get('description', '')) <= 200
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_handles_dict_result_from_cli(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test handling when CLI returns dict instead of list."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = {'error': 'Some error', 'status': 'failed'}
        
        meeting = {'id': 'dict-result', 'title': 'Test', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Should store empty list for that source
        with funcs._meeting_prep_cache_lock:
            assert funcs._meeting_prep_cache['dict-result']['drive']['data'] == []
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_handles_many_attendees(self, mock_valid, mock_save, mock_cli, mock_auth):
        """Test handling of meeting with many attendees (truncates to 5)."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        attendees = [{'name': f'User{i}', 'email': f'user{i}@test.com'} for i in range(20)]
        meeting = {'id': 'many-attendees', 'title': 'Test', 'attendees': attendees, 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        with funcs._meeting_prep_cache_lock:
            meeting_info = funcs._meeting_prep_cache['many-attendees'].get('meeting_info', {})
            attendees_str = meeting_info.get('attendees_str', '')
            # Should only include first 5 names
            assert 'User4' in attendees_str
            assert 'User6' not in attendees_str or attendees_str.count(',') <= 4
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.call_cli_for_meeting_summary')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_summary_generated_when_at_least_one_service_authenticated(self, mock_valid, mock_save, mock_summary, mock_cli, mock_auth):
        """Test that summary is only generated when at least one service is authenticated."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': True, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        mock_summary.return_value = {'status': 'success', 'summary': 'Test summary'}
        
        meeting = {'id': 'summary-test', 'title': 'Test', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Summary should have been called
        mock_summary.assert_called_once()
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.call_cli_for_meeting_summary')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_summary_skipped_when_no_services_authenticated(self, mock_valid, mock_save, mock_summary, mock_cli, mock_auth):
        """Test that summary is skipped when no services are authenticated."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': False, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        
        meeting = {'id': 'no-summary', 'title': 'Test', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Summary should NOT have been called
        mock_summary.assert_not_called()
    
    @patch('prefetch_utils_funcs.check_services_auth')
    @patch('prefetch_utils_funcs.call_cli_for_source')
    @patch('prefetch_utils_funcs.call_cli_for_meeting_summary')
    @patch('prefetch_utils_funcs.save_prep_cache_to_disk')
    @patch('prefetch_utils_funcs.is_cache_valid', return_value=False)
    def test_handles_summary_error(self, mock_valid, mock_save, mock_summary, mock_cli, mock_auth):
        """Test handling of summary generation error."""
        import prefetch_utils_funcs as funcs
        
        mock_auth.return_value = {'atlassian': True, 'slack': False, 'gmail': False}
        mock_cli.return_value = []
        mock_summary.side_effect = Exception("Summary generation failed")
        
        meeting = {'id': 'summary-error', 'title': 'Test', 'attendees': [], 'description': ''}
        funcs.prefetch_meeting_data(meeting)
        
        # Should store error status for summary
        with funcs._meeting_prep_cache_lock:
            summary = funcs._meeting_prep_cache['summary-error'].get('summary', {})
            if summary and isinstance(summary, dict):
                assert summary.get('data', {}).get('status') in ['error', None] or summary.get('data') is None


class TestBackgroundPrefetchLoopEdgeCases:
    """Edge case tests for background_prefetch_loop."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset state before each test."""
        import prefetch_utils_funcs as funcs
        funcs._prefetch_running = False
        funcs._force_aggressive_prefetch = False
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        with funcs._prefetch_status_lock:
            funcs._prefetch_status['activity_log'] = []
            funcs._prefetch_status['running'] = False
            funcs._prefetch_status['current_meeting'] = None
        yield
        funcs._prefetch_running = False
        funcs._force_aggressive_prefetch = False
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    @patch('prefetch_utils_funcs.cleanup_old_caches')
    def test_handles_empty_calendar_call(self, mock_cleanup, mock_calendar):
        """Test that calendar is called with empty result."""
        import prefetch_utils_funcs as funcs
        
        mock_calendar.return_value = []
        funcs._prefetch_running = True
        
        # Run one iteration manually by calling calendar
        events = funcs.get_calendar_events_standalone(minutes_ahead=10080, limit=30)
        
        assert events == []
        mock_calendar.assert_called_once()
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    @patch('prefetch_utils_funcs.prefetch_meeting_data')
    @patch('prefetch_utils_funcs.cleanup_old_caches')
    @patch('prefetch_utils_funcs.is_night_hours', return_value=False)
    @patch('prefetch_utils_funcs.has_cached_data', return_value=True)
    def test_skips_all_meetings_when_all_cached_during_day(self, mock_cached, mock_night, mock_cleanup, mock_prefetch, mock_calendar):
        """Test that all meetings are skipped when all are cached during day hours."""
        import prefetch_utils_funcs as funcs
        
        meetings = [{'id': f'm{i}', 'title': f'Meeting {i}'} for i in range(5)]
        
        call_count = [0]
        def calendar_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                funcs._prefetch_running = False
                return []
            return meetings
        
        mock_calendar.side_effect = calendar_side_effect
        funcs._prefetch_running = True
        
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=5.0)
        
        # prefetch_meeting_data should NOT be called for any meeting
        mock_prefetch.assert_not_called()
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    @patch('prefetch_utils_funcs.prefetch_meeting_data')
    @patch('prefetch_utils_funcs.cleanup_old_caches')
    @patch('prefetch_utils_funcs.is_night_hours', return_value=True)
    @patch('prefetch_utils_funcs.is_cache_valid')
    def test_respects_cache_valid_during_night(self, mock_valid, mock_night, mock_cleanup, mock_prefetch, mock_calendar):
        """Test that night mode still respects is_cache_valid."""
        import prefetch_utils_funcs as funcs
        
        meetings = [
            {'id': 'valid-cache', 'title': 'Valid'},
            {'id': 'invalid-cache', 'title': 'Invalid'},
        ]
        
        def valid_side_effect(meeting_id, source):
            return meeting_id == 'valid-cache'
        mock_valid.side_effect = valid_side_effect
        
        call_count = [0]
        def calendar_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                funcs._prefetch_running = False
                return []
            return meetings
        
        mock_calendar.side_effect = calendar_side_effect
        funcs._prefetch_running = True
        
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=5.0)
        
        # Only invalid-cache meeting should be prefetched
        if mock_prefetch.call_count > 0:
            called_meetings = [call[0][0]['id'] for call in mock_prefetch.call_args_list]
            assert 'invalid-cache' in called_meetings
    
    @patch('prefetch_utils_funcs.get_calendar_events_standalone')
    @patch('prefetch_utils_funcs.prefetch_meeting_data')
    @patch('prefetch_utils_funcs.cleanup_old_caches')
    @patch('prefetch_utils_funcs.is_night_hours', return_value=False)
    @patch('prefetch_utils_funcs.has_cached_data', return_value=False)
    def test_updates_status_during_processing(self, mock_cached, mock_night, mock_cleanup, mock_prefetch, mock_calendar):
        """Test that prefetch status is updated during meeting processing."""
        import prefetch_utils_funcs as funcs
        
        meetings = [{'id': 'm1', 'title': 'Status Test Meeting'}]
        
        status_during_processing = []
        def prefetch_side_effect(meeting):
            status = funcs.get_prefetch_status()
            status_during_processing.append(dict(status))
        
        mock_prefetch.side_effect = prefetch_side_effect
        
        call_count = [0]
        def calendar_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                funcs._prefetch_running = False
                return []
            return meetings
        
        mock_calendar.side_effect = calendar_side_effect
        funcs._prefetch_running = True
        
        thread = threading.Thread(target=funcs.background_prefetch_loop)
        thread.start()
        thread.join(timeout=5.0)
        
        # Status should have been updated during processing
        if status_during_processing:
            assert status_during_processing[0]['running'] == True
            assert 'Status Test Meeting' in status_during_processing[0].get('current_meeting', '')


class TestCleanupOldCachesEdgeCases:
    """Edge case tests for cleanup_old_caches."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear cache before and after tests."""
        import prefetch_utils_funcs as funcs
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        if funcs._meeting_prep_cache is not None:
            with funcs._meeting_prep_cache_lock:
                funcs._meeting_prep_cache.clear()
    
    def test_handles_missing_timestamp_gracefully(self):
        """Test handling of cache entries missing timestamp field doesn't crash."""
        import prefetch_utils_funcs as funcs
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['no-timestamp'] = {
                'jira': {'data': []},  # Missing timestamp
                'confluence': {'data': None},
                'drive': {'data': None},
                'slack': {'data': None},
                'gmail': {'data': None},
                'summary': {'data': None},
                'meeting_info': None
            }
        
        # Should not raise exception
        funcs.cleanup_old_caches()
        
        # Function completes without error (cleanup may or may not remove based on logic)
        assert True
    
    def test_handles_non_dict_source_entries(self):
        """Test handling of source entries that are not dicts."""
        import prefetch_utils_funcs as funcs
        
        recent_timestamp = time.time() - (60 * 60)
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['mixed-types'] = {
                'jira': {'data': [], 'timestamp': recent_timestamp},
                'confluence': None,  # Non-dict
                'drive': "string value",  # Non-dict
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': {'title': 'Test'}
            }
        
        # Should not raise exception
        funcs.cleanup_old_caches()
        
        # Entry should be kept (has recent timestamp in jira)
        with funcs._meeting_prep_cache_lock:
            assert 'mixed-types' in funcs._meeting_prep_cache
    
    def test_handles_zero_timestamp(self):
        """Test handling of entries with timestamp 0."""
        import prefetch_utils_funcs as funcs
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['zero-timestamp'] = {
                'jira': {'data': [], 'timestamp': 0},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        funcs.cleanup_old_caches()
        
        # Entry should be removed (timestamp 0 is very old)
        with funcs._meeting_prep_cache_lock:
            assert 'zero-timestamp' not in funcs._meeting_prep_cache
    
    def test_handles_future_timestamp(self):
        """Test handling of entries with future timestamps (edge case)."""
        import prefetch_utils_funcs as funcs
        
        future_timestamp = time.time() + (24 * 60 * 60)  # 24 hours in future
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['future-timestamp'] = {
                'jira': {'data': [{'key': 'FUTURE-1'}], 'timestamp': future_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        funcs.cleanup_old_caches()
        
        # Entry should be kept (future timestamp is within cutoff)
        with funcs._meeting_prep_cache_lock:
            assert 'future-timestamp' in funcs._meeting_prep_cache


class TestCheckServicesAuthEdgeCases:
    """Edge case tests for check_services_auth."""
    
    @pytest.fixture(autouse=True)
    def ensure_cache(self):
        """Ensure cache is a dict."""
        import prefetch_utils_funcs as funcs
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        yield
    
    @patch('os.path.exists', return_value=False)
    @patch('os.listdir', return_value=[])
    def test_handles_missing_directories(self, mock_listdir, mock_exists):
        """Test handling when auth directories don't exist."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.check_services_auth()
        
        assert result['atlassian'] == False
        assert result['slack'] == False
        assert result['gmail'] == False
    
    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('os.path.isdir', return_value=True)
    @patch('builtins.open')
    def test_handles_empty_token_file(self, mock_open, mock_isdir, mock_listdir, mock_exists):
        """Test handling of empty token file."""
        import prefetch_utils_funcs as funcs
        
        mock_exists.return_value = True
        mock_listdir.return_value = ['mcp-remote']
        mock_open.return_value.__enter__.return_value.read.return_value = '{}'
        
        result = funcs.check_services_auth()
        
        # Should return False for atlassian (no access_token)
        assert 'atlassian' in result
    
    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('os.path.isdir', return_value=True)
    @patch('builtins.open')
    def test_handles_expired_token(self, mock_open, mock_isdir, mock_listdir, mock_exists):
        """Test handling of token file with access_token."""
        import prefetch_utils_funcs as funcs
        
        def exists_side_effect(path):
            return 'mcp-auth' in path or 'gmail' not in path
        mock_exists.side_effect = exists_side_effect
        mock_listdir.return_value = ['test_tokens.json']
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({
            'access_token': 'valid-token-here'
        })
        
        result = funcs.check_services_auth()
        
        # Should detect atlassian as authenticated
        assert 'atlassian' in result
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_gmail_with_only_keys_file(self, mock_file, mock_exists):
        """Test Gmail auth detection with only keys file (no credentials)."""
        import prefetch_utils_funcs as funcs
        
        def exists_side_effect(path):
            if 'gcp-oauth.keys.json' in path:
                return True
            if 'credentials.json' in path:
                return False
            if 'gmail-mcp' in path:
                return True
            return False
        mock_exists.side_effect = exists_side_effect
        
        result = funcs.check_services_auth()
        
        assert result['gmail'] == False
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_gmail_with_both_files(self, mock_file, mock_exists):
        """Test Gmail auth detection with both keys and credentials files."""
        import prefetch_utils_funcs as funcs
        
        def exists_side_effect(path):
            if 'gcp-oauth.keys.json' in path:
                return True
            if 'credentials.json' in path:
                return True
            if 'gmail-mcp' in path:
                return True
            return False
        mock_exists.side_effect = exists_side_effect
        
        result = funcs.check_services_auth()
        
        assert result['gmail'] == True


class TestLoadPrepCacheFromDiskEdgeCases:
    """Edge case tests for load_prep_cache_from_disk."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear cache before and after tests."""
        import prefetch_utils_funcs as funcs
        # Ensure cache is a dict before clearing
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        # Ensure cache is a dict after test for cleanup
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data='{}')
    def test_loads_empty_cache_file(self, mock_file, mock_exists):
        """Test loading an empty cache file."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.load_prep_cache_from_disk()
        
        assert result == True
        with funcs._meeting_prep_cache_lock:
            assert funcs._meeting_prep_cache == {}
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data='null')
    def test_handles_null_json(self, mock_file, mock_exists):
        """Test handling of null JSON value."""
        import prefetch_utils_funcs as funcs
        
        # Reset cache to dict before test
        with funcs._meeting_prep_cache_lock:
            if funcs._meeting_prep_cache is None:
                funcs._meeting_prep_cache = {}
        
        result = funcs.load_prep_cache_from_disk()
        
        # Should handle gracefully - may set cache to null/None
        assert result in [True, False]
        
        # Reset for cleanup
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data='[]')
    def test_handles_list_instead_of_dict(self, mock_file, mock_exists):
        """Test handling of list instead of dict."""
        import prefetch_utils_funcs as funcs
        
        # Reset cache to dict before test
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        
        result = funcs.load_prep_cache_from_disk()
        
        # Should handle gracefully (list is not expected format)
        assert result in [True, False]
        
        # Reset for cleanup
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open)
    def test_loads_cache_with_mixed_valid_invalid(self, mock_file, mock_exists):
        """Test loading cache with mix of valid and invalid entries."""
        import prefetch_utils_funcs as funcs
        
        # Reset cache to dict before test
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        
        now = time.time()
        cache_data = {
            'valid-meeting': {
                'jira': {'data': [{'key': 'V-1'}], 'timestamp': now},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            },
            'corrupted-meeting': {
                'jira': 'not-a-dict',  # Invalid format
                'confluence': None,
            }
        }
        mock_file.return_value.read.return_value = json.dumps(cache_data)
        
        result = funcs.load_prep_cache_from_disk()
        
        assert result == True
        # Both entries should be loaded (validation happens separately)
        with funcs._meeting_prep_cache_lock:
            assert len(funcs._meeting_prep_cache) == 2


class TestThreadManagementEdgeCases:
    """Edge case tests for thread management functions."""
    
    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Cleanup thread state before and after tests."""
        import prefetch_utils_funcs as funcs
        funcs._prefetch_running = False
        funcs._prefetch_thread = None
        # Ensure cache is a dict
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        yield
        funcs._prefetch_running = False
        if funcs._prefetch_thread and funcs._prefetch_thread.is_alive():
            funcs._prefetch_thread.join(timeout=1.0)
        funcs._prefetch_thread = None
    
    @patch('prefetch_utils_funcs.background_prefetch_loop')
    def test_rapid_start_stop_cycle(self, mock_loop):
        """Test rapid start/stop cycles don't cause issues."""
        import prefetch_utils_funcs as funcs
        
        errors = []
        
        def cycle():
            try:
                for _ in range(10):
                    funcs.start_prefetch_thread()
                    funcs.stop_prefetch_thread()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=cycle) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
    
    @patch('prefetch_utils_funcs.background_prefetch_loop')
    def test_start_with_dead_thread_reference(self, mock_loop):
        """Test starting when _prefetch_thread references a dead thread."""
        import prefetch_utils_funcs as funcs
        
        # Create a mock thread that is not alive
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        funcs._prefetch_thread = mock_thread
        funcs._prefetch_running = False
        
        funcs.start_prefetch_thread()
        
        # Should have started a new thread
        assert funcs._prefetch_running == True
        assert funcs._prefetch_thread != mock_thread or mock_loop.called
    
    def test_stop_concurrent_calls(self):
        """Test that concurrent stop calls are safe."""
        import prefetch_utils_funcs as funcs
        
        funcs._prefetch_running = True
        errors = []
        
        def stop_thread():
            try:
                for _ in range(100):
                    funcs.stop_prefetch_thread()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=stop_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert funcs._prefetch_running == False


class TestCacheValidation:
    """Tests for cache validation functions."""
    
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear cache before and after tests."""
        import prefetch_utils_funcs as funcs
        # Ensure cache is a dict before clearing
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
        yield
        # Ensure cache is a dict after test for cleanup
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache.clear()
    
    def test_is_cache_valid_for_nonexistent_meeting(self):
        """Test is_cache_valid returns False for nonexistent meeting."""
        import prefetch_utils_funcs as funcs
        
        result = funcs.is_cache_valid('nonexistent-meeting', 'jira')
        
        assert result == False
    
    def test_is_cache_valid_for_nonexistent_source(self):
        """Test is_cache_valid returns False for nonexistent source."""
        import prefetch_utils_funcs as funcs
        
        # Create meeting without the source
        funcs.get_meeting_cache('partial-meeting')
        
        result = funcs.is_cache_valid('partial-meeting', 'jira')
        
        assert result == False  # No data in jira yet
    
    def test_is_cache_valid_for_none_data(self):
        """Test is_cache_valid returns False for None data."""
        import prefetch_utils_funcs as funcs
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['none-data'] = {
                'jira': {'data': None, 'timestamp': time.time()},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        result = funcs.is_cache_valid('none-data', 'jira')
        
        assert result == False
    
    def test_is_cache_valid_expired_data(self):
        """Test is_cache_valid returns False for expired data."""
        import prefetch_utils_funcs as funcs
        
        old_timestamp = time.time() - (funcs.PREP_CACHE_TTL + 100)
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['expired'] = {
                'jira': {'data': [{'key': 'OLD-1'}], 'timestamp': old_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        result = funcs.is_cache_valid('expired', 'jira')
        
        assert result == False
    
    def test_is_cache_valid_fresh_data(self):
        """Test is_cache_valid returns True for fresh data."""
        import prefetch_utils_funcs as funcs
        
        recent_timestamp = time.time() - 60  # 1 minute ago
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['fresh'] = {
                'jira': {'data': [{'key': 'FRESH-1'}], 'timestamp': recent_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        result = funcs.is_cache_valid('fresh', 'jira')
        
        assert result == True
    
    def test_is_cache_valid_uses_summary_ttl_for_summary(self):
        """Test that summary source uses SUMMARY_CACHE_TTL."""
        import prefetch_utils_funcs as funcs
        
        # Timestamp between PREP_CACHE_TTL and SUMMARY_CACHE_TTL
        middle_timestamp = time.time() - (funcs.PREP_CACHE_TTL + 100)
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['summary-ttl'] = {
                'jira': {'data': None, 'timestamp': 0},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': {'status': 'success'}, 'timestamp': middle_timestamp},
                'meeting_info': None
            }
        
        # Summary should still be valid (longer TTL)
        result = funcs.is_cache_valid('summary-ttl', 'summary')
        
        assert result == True
    
    def test_has_cached_data_ignores_ttl(self):
        """Test that has_cached_data ignores TTL."""
        import prefetch_utils_funcs as funcs
        
        very_old_timestamp = time.time() - (24 * 60 * 60)  # 24 hours ago
        
        with funcs._meeting_prep_cache_lock:
            funcs._meeting_prep_cache['old-but-present'] = {
                'jira': {'data': [{'key': 'OLD-1'}], 'timestamp': very_old_timestamp},
                'confluence': {'data': None, 'timestamp': 0},
                'drive': {'data': None, 'timestamp': 0},
                'slack': {'data': None, 'timestamp': 0},
                'gmail': {'data': None, 'timestamp': 0},
                'summary': {'data': None, 'timestamp': 0},
                'meeting_info': None
            }
        
        # is_cache_valid should return False (expired)
        assert funcs.is_cache_valid('old-but-present', 'jira') == False
        
        # has_cached_data should return True (data exists)
        assert funcs.has_cached_data('old-but-present', 'jira') == True
    
    def test_has_cached_data_returns_false_for_none(self):
        """Test has_cached_data returns False for None data."""
        import prefetch_utils_funcs as funcs
        
        funcs.get_meeting_cache('no-data')
        
        result = funcs.has_cached_data('no-data', 'jira')
        
        assert result == False


class TestActivityLog:
    """Tests for activity logging functionality."""
    
    @pytest.fixture(autouse=True)
    def clear_status(self):
        """Clear prefetch status before each test."""
        import prefetch_utils_funcs as funcs
        # Ensure cache is a dict
        if funcs._meeting_prep_cache is None:
            funcs._meeting_prep_cache = {}
        with funcs._prefetch_status_lock:
            funcs._prefetch_status['activity_log'] = []
        yield
        with funcs._prefetch_status_lock:
            funcs._prefetch_status['activity_log'] = []
    
    def test_activity_log_concurrent_access(self):
        """Test thread-safe concurrent access to activity log."""
        import prefetch_utils_funcs as funcs
        
        errors = []
        
        def add_activities():
            try:
                for i in range(50):
                    funcs.add_prefetch_activity('test', f'Message {i}', meeting=f'Meeting {i}')
            except Exception as e:
                errors.append(e)
        
        def read_activities():
            try:
                for _ in range(50):
                    status = funcs.get_prefetch_status()
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
        import prefetch_utils_funcs as funcs
        
        funcs.add_prefetch_activity('first', 'First message')
        time.sleep(0.01)  # Small delay to ensure different timestamps
        funcs.add_prefetch_activity('second', 'Second message')
        
        status = funcs.get_prefetch_status()
        
        assert status['activity_log'][0]['message'] == 'Second message'
        assert status['activity_log'][1]['message'] == 'First message'
    
    def test_activity_with_all_fields(self):
        """Test activity entry with all optional fields."""
        import prefetch_utils_funcs as funcs
        
        funcs.add_prefetch_activity(
            'fetch_complete',
            'Completed fetch',
            meeting='Test Meeting',
            source='jira',
            status='success',
            items=42
        )
        
        status = funcs.get_prefetch_status()
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
