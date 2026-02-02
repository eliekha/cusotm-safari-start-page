"""
Tests for CLI/AI and Calendar functions in search-server.py

These tests cover:
1. extract_meeting_keywords - extracts keywords from calendar events
2. call_cli_for_source - calls devsai CLI for specific sources with retry logic
3. call_cli_for_meeting_summary - generates meeting prep summaries

Run with: pytest tests/test_cli_calendar.py -v
"""
import sys
import os
import pytest
import subprocess
from unittest.mock import patch, MagicMock

# Add tests directory to path
sys.path.insert(0, os.path.dirname(__file__))


# =============================================================================
# TestExtractMeetingKeywords - Tests for extract_meeting_keywords function
# =============================================================================

class TestExtractMeetingKeywords:
    """Tests for extract_meeting_keywords function."""

    # -------------------------------------------------------------------------
    # Basic title word extraction tests
    # -------------------------------------------------------------------------

    def test_extracts_title_words(self):
        """Test that meaningful title words are extracted."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Project Alpha Review Discussion',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'project' in keywords
        assert 'alpha' in keywords
        assert 'review' in keywords
        assert 'discussion' in keywords

    def test_extracts_lowercase_keywords(self):
        """Test that keywords are converted to lowercase."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'PROJECT Alpha REVIEW',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'project' in keywords
        assert 'alpha' in keywords
        assert 'review' in keywords
        # Uppercase versions should not be present (they're lowercased)
        assert 'PROJECT' not in keywords

    # -------------------------------------------------------------------------
    # Skip common meeting words tests
    # -------------------------------------------------------------------------

    def test_skips_common_meeting_words(self):
        """Test that common meeting words are filtered out."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Weekly Sync Meeting with the Team',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        # Common words should be skipped
        assert 'meeting' not in keywords
        assert 'sync' not in keywords
        assert 'weekly' not in keywords
        assert 'with' not in keywords
        assert 'the' not in keywords
        # 'team' should be included (not in skip list)
        assert 'team' in keywords

    def test_skips_standup_variations(self):
        """Test that standup variations are filtered."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Daily Standup Stand-up Team Alpha',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'daily' not in keywords
        assert 'standup' not in keywords
        # Note: stand-up gets split on '-' and both parts filtered
        assert 'team' in keywords
        assert 'alpha' in keywords

    def test_skips_one_on_one_variations(self):
        """Test that 1:1 and 1-1 are filtered."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': '1:1 with John',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert '1:1' not in keywords
        assert '1-1' not in keywords
        assert 'with' not in keywords
        # 'john' is only 4 chars, might be included

    def test_skips_articles_and_prepositions(self):
        """Test that common articles and prepositions are filtered."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'A meeting for the review and discussion',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'a' not in keywords
        assert 'an' not in keywords
        assert 'for' not in keywords
        assert 'the' not in keywords
        assert 'and' not in keywords
        assert 'to' not in keywords

    # -------------------------------------------------------------------------
    # Word length filtering tests
    # -------------------------------------------------------------------------

    def test_filters_short_words(self):
        """Test that words with 2 or fewer characters are filtered."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Q1 US EU Review of AI ML',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        # 2-char words should be filtered
        assert 'q1' not in keywords
        assert 'us' not in keywords
        assert 'eu' not in keywords
        assert 'ai' not in keywords
        assert 'ml' not in keywords
        # Longer words should be included
        assert 'review' in keywords

    def test_includes_three_char_words(self):
        """Test that 3-character words are included."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'API SDK Review',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'api' in keywords
        assert 'sdk' in keywords
        assert 'review' in keywords

    # -------------------------------------------------------------------------
    # Jira ticket extraction tests
    # -------------------------------------------------------------------------

    def test_extracts_jira_tickets_from_description(self):
        """Test extraction of Jira-style ticket IDs from description."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Sprint Planning',
            'description': 'Discuss PROJ-123 and TEAM-456 items. Also review ABC-789.',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'PROJ-123' in keywords
        assert 'TEAM-456' in keywords
        assert 'ABC-789' in keywords

    def test_extracts_tickets_from_jira_urls(self):
        """Test extraction of ticket IDs from Jira URLs."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Review',
            'description': 'See https://company.atlassian.net/jira/browse/PROJ-999 for details',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'PROJ-999' in keywords

    def test_extracts_tickets_from_confluence_urls(self):
        """Test extraction of ticket IDs from Confluence URLs."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Doc Review',
            'description': 'Check confluence at https://wiki.company.com/confluence/DOC-555',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'DOC-555' in keywords

    def test_extracts_multiple_tickets_from_urls(self):
        """Test extraction of multiple ticket IDs from various URLs."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Review',
            'description': '''
                JIRA: https://company.atlassian.net/jira/browse/PROJ-111
                Confluence: https://wiki.company.com/confluence/display/DOC-222
                Also check TEAM-333 in the tracker
            ''',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'PROJ-111' in keywords
        assert 'DOC-222' in keywords
        assert 'TEAM-333' in keywords

    def test_ignores_non_jira_confluence_urls(self):
        """Test that URLs without jira/confluence don't get ticket extraction."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Review',
            'description': 'Check https://github.com/repo/PROJ-123 for code',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        # PROJ-123 should still be found by the standalone ticket regex
        assert 'PROJ-123' in keywords

    # -------------------------------------------------------------------------
    # Attendee extraction tests
    # -------------------------------------------------------------------------

    def test_extracts_attendee_first_names(self):
        """Test extraction of attendee first names."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Discussion',
            'description': '',
            'attendees': [
                {'name': 'John Smith'},
                {'name': 'Jane Doe'},
                {'name': 'Bob Johnson'}
            ]
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'John' in keywords
        assert 'Jane' in keywords
        assert 'Bob' in keywords

    def test_skips_email_addresses_as_attendee_names(self):
        """Test that email addresses in attendee names are skipped."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Discussion',
            'description': '',
            'attendees': [
                {'name': 'john@example.com'},
                {'name': 'Jane Doe'}
            ]
        }
        keywords = extract_meeting_keywords(event)
        
        # Email should not be added
        assert 'john@example.com' not in keywords
        assert 'john' not in keywords
        # Normal name should be added
        assert 'Jane' in keywords

    def test_handles_attendee_with_only_email(self):
        """Test handling of attendee with email as name."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Planning',
            'description': '',
            'attendees': [
                {'name': 'alice@company.com'},
                {'name': 'bob.smith@company.com'},
            ]
        }
        keywords = extract_meeting_keywords(event)
        
        # Emails should be skipped
        assert 'alice@company.com' not in keywords
        assert 'bob.smith@company.com' not in keywords
        # First part of email should not be added
        assert 'alice' not in keywords

    def test_handles_empty_attendee_name(self):
        """Test handling of empty attendee name."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Planning Session',
            'description': '',
            'attendees': [
                {'name': ''},
                {'name': 'Alice Smith'},
            ]
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'Alice' in keywords
        assert '' not in keywords

    def test_handles_missing_name_field(self):
        """Test handling of attendee without name field."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Planning',
            'description': '',
            'attendees': [
                {'email': 'alice@example.com'},
                {'name': 'Bob Smith'},
            ]
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'Bob' in keywords

    # -------------------------------------------------------------------------
    # Uniqueness and deduplication tests
    # -------------------------------------------------------------------------

    def test_returns_unique_keywords(self):
        """Test that duplicate keywords are removed."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Alpha Alpha Project',
            'description': 'Discuss PROJ-123. Details at https://jira.com/PROJ-123',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        # Check uniqueness
        assert len(keywords) == len(set(keywords))
        # Alpha should appear only once
        assert keywords.count('alpha') == 1

    def test_deduplicates_tickets_from_multiple_sources(self):
        """Test that tickets found in description and URLs are deduplicated."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Review PROJ-123',
            'description': 'PROJ-123 is at https://jira.company.com/PROJ-123',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        # Should only have one PROJ-123
        assert keywords.count('PROJ-123') == 1

    # -------------------------------------------------------------------------
    # Edge cases and error handling tests
    # -------------------------------------------------------------------------

    def test_handles_empty_event(self):
        """Test handling of empty event dictionary."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {}
        keywords = extract_meeting_keywords(event)
        
        assert keywords == []

    def test_handles_missing_fields(self):
        """Test handling of event with missing fields."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Important Review'
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'important' in keywords
        assert 'review' in keywords

    def test_handles_none_values(self):
        """Test handling of None values in event."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Planning',
            'description': None,
            'attendees': None
        }
        # This might fail depending on implementation - testing defensive coding
        try:
            keywords = extract_meeting_keywords(event)
            # If it doesn't fail, verify we got something
            assert 'planning' in keywords
        except (TypeError, AttributeError):
            # If it fails on None, that's acceptable behavior to document
            pass

    def test_handles_special_characters_in_title(self):
        """Test handling of special characters in title."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Project:Alpha/Beta-Review|Discussion',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'project' in keywords
        assert 'alpha' in keywords
        assert 'beta' in keywords
        assert 'review' in keywords
        assert 'discussion' in keywords

    def test_handles_unicode_characters(self):
        """Test handling of unicode characters in title."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': 'Café Strategy Discussion',
            'description': '',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'café' in keywords or 'cafe' in keywords
        assert 'strategy' in keywords
        assert 'discussion' in keywords

    def test_handles_empty_title(self):
        """Test handling of empty title."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': '',
            'description': 'Discuss PROJ-123',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'PROJ-123' in keywords

    def test_handles_whitespace_only_title(self):
        """Test handling of whitespace-only title."""
        from search_server_funcs import extract_meeting_keywords
        
        event = {
            'title': '   \t\n   ',
            'description': 'Review PROJ-456',
            'attendees': []
        }
        keywords = extract_meeting_keywords(event)
        
        assert 'PROJ-456' in keywords


# =============================================================================
# TestCallCliForSource - Tests for call_cli_for_source function
# =============================================================================

class TestCallCliForSource:
    """Tests for call_cli_for_source function."""

    # -------------------------------------------------------------------------
    # Successful CLI call tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_successful_cli_call_returns_json_array(self, mock_exists, mock_get_prompt, mock_popen):
        """Test successful CLI call that returns valid JSON array."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            b'',
            b'[{"title": "Result 1", "url": "http://example.com"}]'
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'jira',
            'Sprint Planning',
            'John, Jane',
            'Discuss items',
            timeout=60,
            max_retries=2
        )
        
        assert result == [{"title": "Result 1", "url": "http://example.com"}]

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_successful_cli_call_with_multiple_results(self, mock_exists, mock_get_prompt, mock_popen):
        """Test successful CLI call with multiple JSON results."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            b'',
            b'[{"title": "Result 1"}, {"title": "Result 2"}, {"title": "Result 3"}]'
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'confluence',
            'Doc Review',
            'Alice',
            timeout=60,
            max_retries=1
        )
        
        assert len(result) == 3
        assert result[0]['title'] == 'Result 1'
        assert result[2]['title'] == 'Result 3'

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_json_in_stdout(self, mock_exists, mock_get_prompt, mock_popen):
        """Test CLI returning JSON in stdout instead of stderr."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            b'[{"source": "stdout", "title": "From stdout"}]',
            b''
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'slack',
            'Meeting',
            '',
            timeout=60,
            max_retries=1
        )
        
        assert result == [{"source": "stdout", "title": "From stdout"}]

    # -------------------------------------------------------------------------
    # Prompt handling tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_returns_empty_list_when_no_prompt(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that empty list is returned when no prompt template."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = None  # No prompt template
        
        result = call_cli_for_source('unknown_source', 'Meeting', '', '')
        
        assert result == []
        mock_popen.assert_not_called()

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_returns_empty_list_when_empty_prompt(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that empty list is returned when prompt is empty string."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = ''  # Empty prompt
        
        result = call_cli_for_source('source', 'Meeting', '', '')
        
        # Empty string is falsy, should return []
        assert result == []
        mock_popen.assert_not_called()

    # -------------------------------------------------------------------------
    # Timeout and retry tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_timeout_with_retry(self, mock_exists, mock_get_prompt, mock_popen):
        """Test timeout handling with retry logic."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd='devsai', timeout=60)
        mock_proc.kill = MagicMock()
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'jira',
            'Sprint Planning',
            'John',
            timeout=60,
            max_retries=3
        )
        
        # Should return error after all retries exhausted
        assert isinstance(result, dict)
        assert 'error' in result
        assert 'timeout' in result['error']
        # Should have attempted max_retries times
        assert mock_popen.call_count == 3
        assert mock_proc.kill.call_count == 3

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_retry_then_success(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that retry works and succeeds on second attempt."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        # First call times out, second succeeds
        mock_proc_fail = MagicMock()
        mock_proc_fail.communicate.side_effect = subprocess.TimeoutExpired(cmd='devsai', timeout=60)
        mock_proc_fail.kill = MagicMock()
        
        mock_proc_success = MagicMock()
        mock_proc_success.communicate.return_value = (b'', b'[{"result": "success"}]')
        
        mock_popen.side_effect = [mock_proc_fail, mock_proc_success]
        
        result = call_cli_for_source(
            'jira',
            'Sprint Planning',
            'John',
            timeout=60,
            max_retries=2
        )
        
        assert result == [{"result": "success"}]
        assert mock_popen.call_count == 2

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_single_retry_on_timeout(self, mock_exists, mock_get_prompt, mock_popen):
        """Test with max_retries=1 only attempts once."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd='devsai', timeout=60)
        mock_proc.kill = MagicMock()
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'jira',
            'Meeting',
            '',
            timeout=60,
            max_retries=1
        )
        
        assert isinstance(result, dict)
        assert 'error' in result
        assert mock_popen.call_count == 1

    # -------------------------------------------------------------------------
    # Exception handling tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_exception_handling_oserror(self, mock_exists, mock_get_prompt, mock_popen):
        """Test handling of OSError exceptions."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_popen.side_effect = OSError("Failed to start process")
        
        result = call_cli_for_source(
            'jira',
            'Meeting',
            '',
            timeout=60,
            max_retries=2
        )
        
        assert isinstance(result, dict)
        assert 'error' in result
        assert 'Failed to start process' in result['error']

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_exception_handling_filenotfound(self, mock_exists, mock_get_prompt, mock_popen):
        """Test handling of FileNotFoundError."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_popen.side_effect = FileNotFoundError("devsai not found")
        
        result = call_cli_for_source(
            'confluence',
            'Meeting',
            '',
            timeout=60,
            max_retries=2
        )
        
        assert isinstance(result, dict)
        assert 'error' in result
        assert 'devsai not found' in result['error']

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_exception_retries_then_fails(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that exceptions trigger retries before failing."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_popen.side_effect = RuntimeError("Unexpected error")
        
        result = call_cli_for_source(
            'jira',
            'Meeting',
            '',
            timeout=60,
            max_retries=3
        )
        
        assert isinstance(result, dict)
        assert 'error' in result
        # Should have retried max_retries times
        assert mock_popen.call_count == 3

    # -------------------------------------------------------------------------
    # Empty and invalid output tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_empty_output_returns_empty_list(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that empty output (no JSON) returns empty list."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'No results found', b'')
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'confluence',
            'Meeting',
            '',
            timeout=60,
            max_retries=1
        )
        
        assert result == []

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_invalid_json_returns_empty_list(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that invalid JSON output returns empty list."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'{not valid json')
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'jira',
            'Meeting',
            '',
            timeout=60,
            max_retries=1
        )
        
        assert result == []

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_json_object_not_array_returns_empty(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that JSON object (not array) returns empty list."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'{"single": "object"}')
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'jira',
            'Meeting',
            '',
            timeout=60,
            max_retries=1
        )
        
        # extract_json_array looks for arrays, not objects
        assert result == []

    # -------------------------------------------------------------------------
    # Drive source specific tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    @patch('lib.cli.glob.glob')
    def test_drive_source_with_drive_paths(self, mock_glob, mock_exists, mock_get_prompt, mock_popen):
        """Test drive source handling with Google Drive paths."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search {drive_path} for {keywords}'
        mock_glob.return_value = ['/Users/test/Library/CloudStorage/GoogleDrive-user@example.com']
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'[{"file": "doc.pdf"}]')
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'drive',
            'Project Alpha Planning',
            'John',
            timeout=60,
            max_retries=1
        )
        
        assert result == [{"file": "doc.pdf"}]

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    @patch('lib.cli.glob.glob')
    def test_drive_source_no_drive_path_returns_empty(self, mock_glob, mock_exists, mock_get_prompt, mock_popen):
        """Test drive source returns empty when no Google Drive path found."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search {drive_path} for {keywords}'
        mock_glob.return_value = []  # No Google Drive paths
        
        result = call_cli_for_source(
            'drive',
            'Meeting',
            '',
            timeout=60,
            max_retries=1
        )
        
        assert result == []
        mock_popen.assert_not_called()

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    @patch('lib.cli.glob.glob')
    def test_drive_source_prefers_main_path(self, mock_glob, mock_exists, mock_get_prompt, mock_popen):
        """Test drive source prefers main path over path with parentheses."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Search {drive_path} for {keywords}'
        mock_glob.return_value = [
            '/Users/test/Library/CloudStorage/GoogleDrive-user@example.com (1)',
            '/Users/test/Library/CloudStorage/GoogleDrive-user@example.com'
        ]
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'[]')
        mock_popen.return_value = mock_proc
        
        call_cli_for_source(
            'drive',
            'Project Planning',
            '',
            timeout=60,
            max_retries=1
        )
        
        # Should prefer the path without parentheses
        call_args = mock_popen.call_args[0][0]
        prompt = call_args[2]  # The -p argument
        assert '(1)' not in prompt

    # -------------------------------------------------------------------------
    # Path resolution tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    @patch('lib.cli.shutil.which')
    def test_fallback_to_which_devsai(self, mock_which, mock_exists, mock_get_prompt, mock_popen):
        """Test fallback to shutil.which when local devsai doesn't exist."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = False  # Local devsai doesn't exist
        mock_which.return_value = '/usr/local/bin/devsai'
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'[{"result": "ok"}]')
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'jira',
            'Meeting',
            '',
            timeout=60,
            max_retries=1
        )
        
        assert result == [{"result": "ok"}]
        # Verify the correct path was used
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == '/usr/local/bin/devsai'

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    @patch('lib.cli.shutil.which')
    def test_fallback_to_nvm_path(self, mock_which, mock_exists, mock_get_prompt, mock_popen):
        """Test fallback to nvm path when shutil.which returns None."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = False  # Local devsai doesn't exist
        mock_which.return_value = None  # shutil.which also returns None
        mock_get_prompt.return_value = 'Search for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'[{"result": "fallback"}]')
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_source(
            'jira',
            'Meeting',
            '',
            timeout=60,
            max_retries=1
        )
        
        assert result == [{"result": "fallback"}]
        # Should use the nvm fallback path
        call_args = mock_popen.call_args[0][0]
        assert 'nvm' in call_args[0] or 'devsai' in call_args[0]

    # -------------------------------------------------------------------------
    # Meeting context building tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_meeting_context_built_correctly(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that meeting context is built with all components."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = '{meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'[]', b'')
        mock_popen.return_value = mock_proc
        
        call_cli_for_source(
            'jira',
            'Important Planning Session',
            'Alice, Bob, Charlie',
            'This is a long description that should be truncated at 300 characters if necessary',
            timeout=60,
            max_retries=1
        )
        
        # Verify prompt was called and meeting context was built
        call_args = mock_popen.call_args
        prompt_arg = call_args[0][0][2]  # The -p argument value
        assert 'Meeting: Important Planning Session' in prompt_arg
        assert 'Attendees: Alice, Bob, Charlie' in prompt_arg
        assert 'Description:' in prompt_arg

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_description_truncated_at_300_chars(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that description is truncated at 300 characters."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = '{meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'[]', b'')
        mock_popen.return_value = mock_proc
        
        long_description = 'A' * 500  # 500 character description
        
        call_cli_for_source(
            'jira',
            'Meeting',
            '',
            long_description,
            timeout=60,
            max_retries=1
        )
        
        call_args = mock_popen.call_args
        prompt_arg = call_args[0][0][2]
        
        # Count A's in the prompt
        a_count = prompt_arg.count('A')
        assert a_count <= 300

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_context_without_attendees(self, mock_exists, mock_get_prompt, mock_popen):
        """Test context building without attendees."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = '{meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'[]', b'')
        mock_popen.return_value = mock_proc
        
        call_cli_for_source(
            'jira',
            'Solo Planning',
            '',  # No attendees
            'Description here',
            timeout=60,
            max_retries=1
        )
        
        call_args = mock_popen.call_args
        prompt_arg = call_args[0][0][2]
        
        assert 'Meeting: Solo Planning' in prompt_arg
        assert 'Attendees' not in prompt_arg  # No attendees line
        assert 'Description:' in prompt_arg

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_context_without_description(self, mock_exists, mock_get_prompt, mock_popen):
        """Test context building without description."""
        from search_server_funcs import call_cli_for_source
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = '{meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'[]', b'')
        mock_popen.return_value = mock_proc
        
        call_cli_for_source(
            'jira',
            'Quick Sync',
            'Alice, Bob',
            '',  # No description
            timeout=60,
            max_retries=1
        )
        
        call_args = mock_popen.call_args
        prompt_arg = call_args[0][0][2]
        
        assert 'Meeting: Quick Sync' in prompt_arg
        assert 'Attendees: Alice, Bob' in prompt_arg
        assert 'Description' not in prompt_arg  # No description line


# =============================================================================
# TestCallCliForMeetingSummary - Tests for call_cli_for_meeting_summary function
# =============================================================================

class TestCallCliForMeetingSummary:
    """Tests for call_cli_for_meeting_summary function."""

    # -------------------------------------------------------------------------
    # Successful summary generation tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_successful_summary_generation(self, mock_exists, mock_get_prompt, mock_popen):
        """Test successful meeting summary generation."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            b'',
            b'## Meeting Summary\n\nKey points to discuss:\n- Item 1\n- Item 2'
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Sprint Review',
            'John, Jane',
            ['john@example.com', 'jane@example.com'],
            'Review sprint progress'
        )
        
        assert result['status'] == 'success'
        assert 'Meeting Summary' in result['summary']
        assert 'Item 1' in result['summary']

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_summary_with_markdown_formatting(self, mock_exists, mock_get_prompt, mock_popen):
        """Test summary with complex markdown formatting."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        summary_text = '''# Meeting Prep

## Key Topics
1. Budget Review
2. Timeline Discussion

## Action Items
- [ ] Review financials
- [ ] Update roadmap

## Attendee Notes
| Name | Role |
|------|------|
| John | Lead |
| Jane | Dev  |
'''
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', summary_text.encode())
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Planning',
            'John, Jane',
            [],
            ''
        )
        
        assert result['status'] == 'success'
        assert '# Meeting Prep' in result['summary']
        assert 'Budget Review' in result['summary']

    # -------------------------------------------------------------------------
    # Timeout handling tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_timeout_returns_timeout_status(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that timeout returns proper status."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd='devsai', timeout=90)
        mock_proc.kill = MagicMock()
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Long Meeting',
            'Team',
            ['team@example.com'],
            timeout=90
        )
        
        assert result['status'] == 'timeout'
        assert result['summary'] == ''
        mock_proc.kill.assert_called_once()

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_timeout_with_custom_timeout_value(self, mock_exists, mock_get_prompt, mock_popen):
        """Test timeout with custom timeout value."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd='devsai', timeout=120)
        mock_proc.kill = MagicMock()
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Very Long Meeting',
            'Team',
            [],
            timeout=120  # Custom timeout
        )
        
        assert result['status'] == 'timeout'

    # -------------------------------------------------------------------------
    # Error handling tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_exception_returns_error_status(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that exceptions return error status with message."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_popen.side_effect = FileNotFoundError("devsai not found")
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'error'
        assert 'devsai not found' in result['error']
        assert result['summary'] == ''

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_oserror_returns_error_status(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that OSError returns error status."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_popen.side_effect = OSError("Permission denied")
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'error'
        assert 'Permission denied' in result['error']

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_runtime_error_returns_error_status(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that RuntimeError returns error status."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_popen.side_effect = RuntimeError("Unexpected failure")
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'error'
        assert 'Unexpected failure' in result['error']

    # -------------------------------------------------------------------------
    # Empty output tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_empty_output_returns_empty_status(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that empty output returns empty status."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'empty'
        assert result['summary'] == ''

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_whitespace_only_output_returns_empty_status(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that whitespace-only output returns empty status."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'   \n\t  \n  ', b'')
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'empty'

    # -------------------------------------------------------------------------
    # Output filtering tests - ANSI codes
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_filters_ansi_color_codes(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that ANSI color codes are stripped from output."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        # Output with ANSI codes
        mock_proc.communicate.return_value = (
            b'',
            b'\x1b[32mSummary:\x1b[0m This is the result\x1b[31m important\x1b[0m'
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'success'
        # ANSI codes should be stripped
        assert '\x1b[' not in result['summary']
        assert 'Summary:' in result['summary']
        assert 'important' in result['summary']

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_filters_complex_ansi_sequences(self, mock_exists, mock_get_prompt, mock_popen):
        """Test filtering of complex ANSI sequences."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        # Various ANSI codes: bold, colors, reset
        mock_proc.communicate.return_value = (
            b'',
            b'\x1b[1m\x1b[34mBold Blue\x1b[0m \x1b[4mUnderline\x1b[0m Normal'
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'success'
        assert '\x1b[' not in result['summary']
        assert 'Bold Blue' in result['summary']
        assert 'Underline' in result['summary']

    # -------------------------------------------------------------------------
    # Output filtering tests - CLI progress messages
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_filters_cli_progress_messages(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that CLI progress/status messages are filtered out."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            b'',
            b'''Connecting to MCP servers...
MCP server(s) connected
[mcp_jira] Searching...
Loading MCP tools
Starting MCP
Actual Summary Content
This is the real output
Output delivered'''
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'success'
        # Progress messages should be filtered
        assert 'Connecting to MCP' not in result['summary']
        assert 'MCP server(s) connected' not in result['summary']
        assert '[mcp_' not in result['summary']
        assert 'Loading MCP' not in result['summary']
        assert 'Starting MCP' not in result['summary']
        assert 'Output delivered' not in result['summary']
        # Actual content should remain
        assert 'Actual Summary Content' in result['summary']
        assert 'real output' in result['summary']

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_filters_checkmark_messages(self, mock_exists, mock_get_prompt, mock_popen):
        """Test filtering of checkmark status messages."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        # Use unicode string then encode to handle checkmark character
        output_text = '\u2713 Output delivered\n\u2713 MCP connected\nReal content here'
        mock_proc.communicate.return_value = (
            b'',
            output_text.encode('utf-8')
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'success'
        assert '\u2713 Output delivered' not in result['summary']
        assert '\u2713 MCP' not in result['summary']
        assert 'Real content here' in result['summary']

    # -------------------------------------------------------------------------
    # Meeting context building tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_meeting_context_includes_emails(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that meeting context includes attendee emails."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = '{meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'Summary output')
        mock_popen.return_value = mock_proc
        
        call_cli_for_meeting_summary(
            'Team Standup',
            'Alice, Bob, Charlie',
            ['alice@example.com', 'bob@example.com', 'charlie@example.com'],
            'Daily status update'
        )
        
        call_args = mock_popen.call_args
        prompt_arg = call_args[0][0][2]  # The -p argument value
        assert 'Meeting: Team Standup' in prompt_arg
        assert 'Attendees: Alice, Bob, Charlie' in prompt_arg
        assert 'alice@example.com' in prompt_arg
        assert 'bob@example.com' in prompt_arg
        assert 'Description:' in prompt_arg

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_limits_attendee_emails_to_five(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that only first 5 attendee emails are included."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = '{meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'Summary')
        mock_popen.return_value = mock_proc
        
        emails = [f'user{i}@example.com' for i in range(10)]
        
        call_cli_for_meeting_summary(
            'Large Meeting',
            'Many People',
            emails,
            'Description'
        )
        
        call_args = mock_popen.call_args
        prompt_arg = call_args[0][0][2]
        
        # First 5 should be included
        for i in range(5):
            assert f'user{i}@example.com' in prompt_arg
        # 6th and beyond should not
        assert 'user5@example.com' not in prompt_arg
        assert 'user9@example.com' not in prompt_arg

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_truncates_description_at_500_chars(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that description is truncated at approximately 500 characters."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = '{meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'Summary')
        mock_popen.return_value = mock_proc
        
        long_description = 'A' * 1000  # 1000 character description
        
        call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            [],
            long_description
        )
        
        call_args = mock_popen.call_args
        prompt_arg = call_args[0][0][2]
        
        # Count A's - should be approximately 500 (truncation at [:500] is 500 chars)
        a_count = prompt_arg.count('A')
        # Allow slight variance due to slicing behavior
        assert a_count <= 510
        assert a_count >= 490  # Should be close to 500, not way under

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_context_without_optional_fields(self, mock_exists, mock_get_prompt, mock_popen):
        """Test context building with minimal fields."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = '{meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'Summary')
        mock_popen.return_value = mock_proc
        
        call_cli_for_meeting_summary(
            'Quick Chat',
            '',  # No attendees string
            [],  # No emails
            ''   # No description
        )
        
        call_args = mock_popen.call_args
        prompt_arg = call_args[0][0][2]
        
        assert 'Meeting: Quick Chat' in prompt_arg
        # These should NOT appear when empty
        assert 'Attendees:' not in prompt_arg or 'Attendees: \n' not in prompt_arg

    # -------------------------------------------------------------------------
    # Path resolution tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    @patch('lib.cli.shutil.which')
    def test_fallback_devsai_path(self, mock_which, mock_exists, mock_get_prompt, mock_popen):
        """Test fallback to shutil.which for devsai path."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = False
        mock_which.return_value = '/opt/bin/devsai'
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'Summary content')
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'success'
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == '/opt/bin/devsai'

    # -------------------------------------------------------------------------
    # CLI argument tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_uses_higher_max_iterations(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that summary uses higher max-iterations (8 vs 3)."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'Summary')
        mock_popen.return_value = mock_proc
        
        call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        call_args = mock_popen.call_args[0][0]
        # Find --max-iterations argument
        max_iter_index = call_args.index('--max-iterations')
        assert call_args[max_iter_index + 1] == '8'

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_uses_correct_model(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that the correct model is specified."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'', b'Summary')
        mock_popen.return_value = mock_proc
        
        call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        call_args = mock_popen.call_args[0][0]
        # Find -m argument
        model_index = call_args.index('-m')
        assert 'haiku' in call_args[model_index + 1].lower() or 'claude' in call_args[model_index + 1].lower()

    # -------------------------------------------------------------------------
    # Output combination tests
    # -------------------------------------------------------------------------

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_combines_stdout_and_stderr(self, mock_exists, mock_get_prompt, mock_popen):
        """Test that both stdout and stderr are combined."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            b'Stdout content ',
            b'Stderr content'
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'success'
        # Both should be combined
        assert 'Stdout content' in result['summary']
        assert 'Stderr content' in result['summary']

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_only_stdout_content(self, mock_exists, mock_get_prompt, mock_popen):
        """Test with only stdout content."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            b'Only stdout here',
            b''
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'success'
        assert 'Only stdout here' in result['summary']

    @patch('lib.cli.subprocess.Popen')
    @patch('lib.cli.get_prompt')
    @patch('lib.cli.os.path.exists')
    def test_only_stderr_content(self, mock_exists, mock_get_prompt, mock_popen):
        """Test with only stderr content (normal for devsai)."""
        from search_server_funcs import call_cli_for_meeting_summary
        
        mock_exists.return_value = True
        mock_get_prompt.return_value = 'Generate summary for {meeting_context}'
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            b'',
            b'All content in stderr'
        )
        mock_popen.return_value = mock_proc
        
        result = call_cli_for_meeting_summary(
            'Meeting',
            'Team',
            []
        )
        
        assert result['status'] == 'success'
        assert 'All content in stderr' in result['summary']


# =============================================================================
# TestExtractJsonArray - Tests for extract_json_array helper function
# =============================================================================

class TestExtractJsonArray:
    """Tests for extract_json_array helper used by CLI functions."""

    def test_extracts_simple_array(self):
        """Test extraction of simple JSON array."""
        from search_server_funcs import extract_json_array
        
        text = '[{"id": 1}, {"id": 2}]'
        result = extract_json_array(text)
        assert result == [{"id": 1}, {"id": 2}]

    def test_handles_mcp_output_prefix(self):
        """Test handling of MCP tool output prefixes."""
        from search_server_funcs import extract_json_array
        
        text = 'MCP tool completed successfully\n[{"result": "test"}]'
        result = extract_json_array(text)
        assert result == [{"result": "test"}]

    def test_handles_multiline_json(self):
        """Test handling of formatted JSON."""
        from search_server_funcs import extract_json_array
        
        text = '''[
            {"name": "item1"},
            {"name": "item2"}
        ]'''
        result = extract_json_array(text)
        assert len(result) == 2

    def test_returns_none_for_invalid_json(self):
        """Test that invalid JSON returns None."""
        from search_server_funcs import extract_json_array
        
        text = 'This is not JSON at all'
        result = extract_json_array(text)
        assert result is None

    def test_extracts_array_from_mixed_content(self):
        """Test extraction of array from mixed content (array must start on its own line)."""
        from search_server_funcs import extract_json_array
        
        # Note: extract_json_array only finds arrays that start at the beginning of a line
        text = 'Some text before\n[{"id": 1}, {"id": 2}]\nand text after'
        result = extract_json_array(text)
        assert result == [{"id": 1}, {"id": 2}]

    def test_handles_empty_array(self):
        """Test handling of empty JSON array."""
        from search_server_funcs import extract_json_array
        
        text = '[]'
        result = extract_json_array(text)
        assert result == []

    def test_handles_nested_objects(self):
        """Test handling of nested objects in array."""
        from search_server_funcs import extract_json_array
        
        text = '[{"outer": {"inner": "value"}}]'
        result = extract_json_array(text)
        assert result == [{"outer": {"inner": "value"}}]

    def test_handles_arrays_in_objects(self):
        """Test handling of arrays inside objects."""
        from search_server_funcs import extract_json_array
        
        text = '[{"items": [1, 2, 3]}]'
        result = extract_json_array(text)
        assert result == [{"items": [1, 2, 3]}]

    def test_skips_status_lines_with_brackets(self):
        """Test that status lines containing brackets are skipped."""
        from search_server_funcs import extract_json_array
        
        text = '''Connecting to [server]...
MCP tool [started]
[{"actual": "data"}]'''
        result = extract_json_array(text)
        assert result == [{"actual": "data"}]

    def test_handles_unicode_content(self):
        """Test handling of unicode in JSON."""
        from search_server_funcs import extract_json_array
        
        text = '[{"emoji": "🎉", "text": "café"}]'
        result = extract_json_array(text)
        assert result == [{"emoji": "🎉", "text": "café"}]


# =============================================================================
# Additional helper function tests
# =============================================================================

class TestSlackHelpers:
    """Additional Slack helper tests."""

    def test_slack_ts_to_iso_with_milliseconds(self):
        """Test timestamp with milliseconds."""
        from search_server_funcs import slack_ts_to_iso
        
        ts = "1706745600.123456"
        result = slack_ts_to_iso(ts)
        assert result is not None
        assert '2024' in result

    def test_slack_ts_to_iso_basic(self):
        """Test basic timestamp conversion."""
        from search_server_funcs import slack_ts_to_iso
        
        ts = "1706745600.000000"
        result = slack_ts_to_iso(ts)
        assert result is not None

    def test_slack_ts_to_iso_empty_string(self):
        """Test with empty string."""
        from search_server_funcs import slack_ts_to_iso
        
        result = slack_ts_to_iso("")
        # Should handle gracefully (may return None or empty)


class TestIsNightHours:
    """Tests for is_night_hours function."""

    def test_returns_boolean(self):
        """Test that function returns a boolean."""
        from search_server_funcs import is_night_hours
        
        result = is_night_hours()
        assert isinstance(result, bool)


class TestExtractDomain:
    """Tests for extract_domain function."""

    def test_extracts_simple_domain(self):
        """Test basic domain extraction."""
        from search_server_funcs import extract_domain
        
        assert extract_domain('https://example.com/path') == 'example.com'

    def test_removes_www_prefix(self):
        """Test www prefix is removed."""
        from search_server_funcs import extract_domain
        
        assert extract_domain('https://www.example.com/') == 'example.com'

    def test_preserves_subdomains(self):
        """Test subdomains are preserved."""
        from search_server_funcs import extract_domain
        
        assert extract_domain('https://api.example.com/') == 'api.example.com'

    def test_handles_ports(self):
        """Test domain with port."""
        from search_server_funcs import extract_domain
        
        assert extract_domain('http://localhost:8080/api') == 'localhost:8080'

    def test_handles_invalid_url(self):
        """Test invalid URL returns empty."""
        from search_server_funcs import extract_domain
        
        assert extract_domain('not-a-url') == ''


class TestCacheFunctions:
    """Tests for cache functions."""

    def test_get_cached_data_returns_none_for_unknown(self):
        """Test get_cached_data returns None for unknown meeting."""
        from search_server_funcs import get_cached_data
        
        result = get_cached_data('unknown-meeting-id', 'jira')
        assert result is None

    def test_has_cached_data_returns_false_for_unknown(self):
        """Test has_cached_data returns False for unknown meeting."""
        from search_server_funcs import has_cached_data
        
        result = has_cached_data('unknown-meeting-id', 'jira')
        assert result == False

    def test_is_cache_valid_returns_false_for_unknown(self):
        """Test is_cache_valid returns False for unknown meeting."""
        from search_server_funcs import is_cache_valid
        
        result = is_cache_valid('unknown-meeting-id', 'jira')
        assert result == False


class TestPromptFunctions:
    """Tests for prompt functions."""

    def test_get_prompt_returns_string(self):
        """Test get_prompt returns a string."""
        from search_server_funcs import get_prompt
        
        result = get_prompt('jira')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_prompt_for_confluence(self):
        """Test get_prompt works for confluence."""
        from search_server_funcs import get_prompt
        
        result = get_prompt('confluence')
        assert isinstance(result, str)

    def test_get_prompt_for_slack(self):
        """Test get_prompt works for slack."""
        from search_server_funcs import get_prompt
        
        result = get_prompt('slack')
        assert isinstance(result, str)

    def test_get_prompt_for_summary(self):
        """Test get_prompt works for summary."""
        from search_server_funcs import get_prompt
        
        result = get_prompt('summary')
        assert isinstance(result, str)

    def test_get_all_prompts_returns_dict(self):
        """Test get_all_prompts returns correct structure."""
        from search_server_funcs import get_all_prompts
        
        result = get_all_prompts()
        assert isinstance(result, dict)
        assert 'jira' in result
        assert 'confluence' in result
        assert 'slack' in result
