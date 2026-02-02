"""
Tests for Google Calendar and Google Drive functions.

Run with: pytest tests/test_google.py -v
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open, PropertyMock
from datetime import datetime, timedelta
import pickle

# Add tests directory to path for importing the helper module
sys.path.insert(0, os.path.dirname(__file__))


# =============================================================================
# Tests for authenticate_google()
# =============================================================================
class TestAuthenticateGoogle:
    """Tests for the authenticate_google OAuth flow function."""
    
    def test_returns_false_when_google_api_unavailable(self, capsys):
        """Test that authenticate_google returns False when Google API is not available."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', False):
            from search_server_funcs import authenticate_google
            
            result = authenticate_google()
            
            assert result is False
            captured = capsys.readouterr()
            assert "Google API libraries not installed" in captured.out
    
    def test_returns_false_when_credentials_file_missing(self, capsys):
        """Test that authenticate_google returns False when credentials.json doesn't exist."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True), \
             patch('search_server_funcs.os.path.exists', return_value=False):
            from search_server_funcs import authenticate_google
            
            result = authenticate_google()
            
            assert result is False
            captured = capsys.readouterr()
            assert "Credentials file not found" in captured.out
    
    @patch('search_server_funcs.pickle.dump')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.InstalledAppFlow')
    @patch('search_server_funcs.os.path.exists')
    def test_successful_oauth_flow(self, mock_exists, mock_flow_class, mock_file, mock_pickle, capsys):
        """Test successful OAuth authentication flow."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            # Setup mocks
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = mock_creds
            mock_flow_class.from_client_secrets_file.return_value = mock_flow
            
            from search_server_funcs import authenticate_google
            
            result = authenticate_google()
            
            assert result is True
            mock_flow_class.from_client_secrets_file.assert_called_once()
            mock_flow.run_local_server.assert_called_once_with(port=0)
            mock_pickle.assert_called_once()
            captured = capsys.readouterr()
            assert "Success!" in captured.out
    
    @patch('search_server_funcs.pickle.dump')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.InstalledAppFlow')
    @patch('search_server_funcs.os.path.exists')
    def test_oauth_flow_saves_token(self, mock_exists, mock_flow_class, mock_file, mock_pickle):
        """Test that OAuth flow saves the token to the correct path."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = mock_creds
            mock_flow_class.from_client_secrets_file.return_value = mock_flow
            
            from search_server_funcs import authenticate_google, TOKEN_PATH
            
            authenticate_google()
            
            # Verify token was saved
            mock_file.assert_called_with(TOKEN_PATH, 'wb')
            mock_pickle.assert_called_once_with(mock_creds, mock_file())
    
    @patch('search_server_funcs.pickle.dump')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.InstalledAppFlow')
    @patch('search_server_funcs.os.path.exists')
    def test_oauth_uses_correct_scopes(self, mock_exists, mock_flow_class, mock_file, mock_pickle):
        """Test that OAuth flow uses the correct scopes for Calendar and Drive."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = mock_creds
            mock_flow_class.from_client_secrets_file.return_value = mock_flow
            
            from search_server_funcs import authenticate_google, SCOPES, CREDENTIALS_PATH
            
            authenticate_google()
            
            # Verify correct scopes were used
            mock_flow_class.from_client_secrets_file.assert_called_once_with(
                CREDENTIALS_PATH, SCOPES
            )
    
    def test_prints_setup_instructions_when_credentials_missing(self, capsys):
        """Test that setup instructions are printed when credentials file is missing."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True), \
             patch('search_server_funcs.os.path.exists', return_value=False):
            from search_server_funcs import authenticate_google
            
            authenticate_google()
            
            captured = capsys.readouterr()
            assert "console.cloud.google.com" in captured.out
            assert "Google Calendar API" in captured.out


# =============================================================================
# Tests for get_calendar_events_standalone()
# =============================================================================
class TestGetCalendarEventsStandalone:
    """Tests for the get_calendar_events_standalone function."""
    
    def test_returns_empty_list_when_google_api_unavailable(self):
        """Test that function returns empty list when Google API is not available."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', False):
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone()
            
            assert result == []
    
    def test_returns_empty_list_when_token_missing(self):
        """Test that function returns empty list when token file doesn't exist."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True), \
             patch('search_server_funcs.os.path.exists', return_value=False):
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone()
            
            assert result == []
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_successful_fetch_with_events(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test successful calendar events fetch with events returned."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            
            # Mock credentials that are not expired
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            # Mock calendar service with future events
            future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'
            end_time = (datetime.utcnow() + timedelta(hours=2)).isoformat() + 'Z'
            mock_events = {
                'items': [{
                    'id': 'event123',
                    'summary': 'Test Meeting',
                    'start': {'dateTime': future_time},
                    'end': {'dateTime': end_time},
                    'description': 'Test description',
                    'location': 'Conference Room A',
                    'hangoutLink': 'https://meet.google.com/test',
                    'attendees': [
                        {'email': 'user1@example.com', 'displayName': 'User One', 'self': True},
                        {'email': 'user2@example.com', 'displayName': 'User Two', 'self': False}
                    ]
                }]
            }
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = mock_events
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone(minutes_ahead=120, limit=5)
            
            assert len(result) == 1
            assert result[0]['id'] == 'event123'
            assert result[0]['title'] == 'Test Meeting'
            assert len(result[0]['attendees']) == 2
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_returns_empty_list_when_no_events(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that function returns empty list when no events are returned."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = {'items': []}
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone()
            
            assert result == []
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.dump')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.Request')
    def test_refreshes_expired_credentials(self, mock_request_class, mock_exists, mock_file, 
                                           mock_pickle_load, mock_pickle_dump, mock_build):
        """Test that expired credentials are refreshed."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            
            # Mock expired credentials with refresh token
            mock_creds = MagicMock()
            mock_creds.expired = True
            mock_creds.refresh_token = 'refresh_token_123'
            mock_pickle_load.return_value = mock_creds
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = {'items': []}
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            get_calendar_events_standalone()
            
            # Verify credentials were refreshed
            mock_creds.refresh.assert_called_once()
            # Verify token was saved after refresh
            mock_pickle_dump.assert_called()
    
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_returns_empty_list_on_exception(self, mock_exists, mock_file, mock_pickle):
        """Test that function returns empty list when an exception occurs."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_pickle.side_effect = Exception("Test error")
            
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone()
            
            assert result == []
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_skips_all_day_events(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that all-day events (without time) are skipped."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            # All-day event has date without 'T' (time component)
            mock_events = {
                'items': [{
                    'id': 'allday123',
                    'summary': 'All Day Event',
                    'start': {'date': '2025-02-01'},
                    'end': {'date': '2025-02-02'}
                }]
            }
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = mock_events
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone()
            
            # All-day event should be skipped
            assert result == []
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_respects_limit_parameter(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that the limit parameter is respected."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'
            end_time = (datetime.utcnow() + timedelta(hours=2)).isoformat() + 'Z'
            mock_events = {
                'items': [
                    {'id': f'event{i}', 'summary': f'Meeting {i}', 
                     'start': {'dateTime': future_time}, 'end': {'dateTime': end_time}}
                    for i in range(10)
                ]
            }
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = mock_events
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone(limit=3)
            
            assert len(result) <= 3
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_filters_ended_meetings(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that meetings that have already ended are filtered out."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            # Create a meeting that ended 2 hours ago
            past_start = (datetime.now() - timedelta(hours=3)).astimezone().isoformat()
            past_end = (datetime.now() - timedelta(hours=2)).astimezone().isoformat()
            
            # Create a meeting that's upcoming
            future_start = (datetime.now() + timedelta(hours=1)).astimezone().isoformat()
            future_end = (datetime.now() + timedelta(hours=2)).astimezone().isoformat()
            
            mock_events = {
                'items': [
                    {'id': 'past_event', 'summary': 'Past Meeting',
                     'start': {'dateTime': past_start}, 'end': {'dateTime': past_end}},
                    {'id': 'future_event', 'summary': 'Future Meeting',
                     'start': {'dateTime': future_start}, 'end': {'dateTime': future_end}}
                ]
            }
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = mock_events
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone()
            
            # Only future meeting should be returned
            assert len(result) == 1
            assert result[0]['id'] == 'future_event'
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_extracts_hangout_link(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that hangout/meet link is extracted correctly."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'
            end_time = (datetime.utcnow() + timedelta(hours=2)).isoformat() + 'Z'
            
            mock_events = {
                'items': [{
                    'id': 'event123',
                    'summary': 'Meeting with Link',
                    'start': {'dateTime': future_time},
                    'end': {'dateTime': end_time},
                    'hangoutLink': 'https://meet.google.com/abc-defg-hij'
                }]
            }
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = mock_events
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone()
            
            assert len(result) == 1
            assert result[0]['link'] == 'https://meet.google.com/abc-defg-hij'
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_falls_back_to_html_link(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that htmlLink is used when hangoutLink is not available."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'
            end_time = (datetime.utcnow() + timedelta(hours=2)).isoformat() + 'Z'
            
            mock_events = {
                'items': [{
                    'id': 'event123',
                    'summary': 'Meeting without Hangout',
                    'start': {'dateTime': future_time},
                    'end': {'dateTime': end_time},
                    'htmlLink': 'https://calendar.google.com/event?eid=xyz'
                }]
            }
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = mock_events
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone()
            
            assert len(result) == 1
            assert result[0]['link'] == 'https://calendar.google.com/event?eid=xyz'


# =============================================================================
# Tests for get_meeting_by_id()
# =============================================================================
class TestGetMeetingById:
    """Tests for the get_meeting_by_id function."""
    
    def test_returns_none_when_google_api_unavailable(self):
        """Test that function returns None when Google API is not available."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', False):
            from search_server_funcs import get_meeting_by_id
            
            result = get_meeting_by_id('event123')
            
            assert result is None
    
    def test_returns_none_when_token_missing(self):
        """Test that function returns None when token file doesn't exist."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True), \
             patch('search_server_funcs.os.path.exists', return_value=False):
            from search_server_funcs import get_meeting_by_id
            
            result = get_meeting_by_id('event123')
            
            assert result is None
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_successful_fetch_meeting(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test successful meeting fetch by ID."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            mock_event = {
                'id': 'event123',
                'summary': 'Important Meeting',
                'start': {'dateTime': '2025-02-01T14:00:00-05:00'},
                'end': {'dateTime': '2025-02-01T15:00:00-05:00'},
                'description': 'Meeting description',
                'location': 'Room 101',
                'htmlLink': 'https://calendar.google.com/event?eid=xxx',
                'attendees': [
                    {'displayName': 'Alice', 'email': 'alice@example.com', 'self': True},
                    {'displayName': 'Bob', 'email': 'bob@example.com', 'self': False}
                ]
            }
            
            mock_service = MagicMock()
            mock_service.events().get().execute.return_value = mock_event
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_meeting_by_id
            
            result = get_meeting_by_id('event123')
            
            assert result is not None
            assert result['id'] == 'event123'
            assert result['title'] == 'Important Meeting'
            assert result['location'] == 'Room 101'
            assert len(result['attendees']) == 2
            assert result['attendees'][0]['name'] == 'Alice'
            assert result['attendees'][0]['self'] is True
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_returns_none_when_event_not_found(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that function returns None when event is not found."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            mock_service = MagicMock()
            mock_service.events().get().execute.return_value = None
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_meeting_by_id
            
            result = get_meeting_by_id('nonexistent')
            
            assert result is None
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.dump')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.Request')
    def test_refreshes_expired_credentials(self, mock_request_class, mock_exists, mock_file,
                                           mock_pickle_load, mock_pickle_dump, mock_build):
        """Test that expired credentials are refreshed."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            
            mock_creds = MagicMock()
            mock_creds.expired = True
            mock_creds.refresh_token = 'refresh_token_123'
            mock_pickle_load.return_value = mock_creds
            
            mock_event = {
                'id': 'event123',
                'summary': 'Test Meeting',
                'start': {'dateTime': '2025-02-01T14:00:00Z'},
                'end': {'dateTime': '2025-02-01T15:00:00Z'}
            }
            
            mock_service = MagicMock()
            mock_service.events().get().execute.return_value = mock_event
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_meeting_by_id
            
            get_meeting_by_id('event123')
            
            mock_creds.refresh.assert_called_once()
            mock_pickle_dump.assert_called()
    
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_returns_none_on_exception(self, mock_exists, mock_file, mock_pickle):
        """Test that function returns None when an exception occurs."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_pickle.side_effect = Exception("Test error")
            
            from search_server_funcs import get_meeting_by_id
            
            result = get_meeting_by_id('event123')
            
            assert result is None
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_handles_event_without_optional_fields(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that function handles events with missing optional fields."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            # Minimal event without optional fields
            mock_event = {
                'id': 'minimal123',
                'start': {'date': '2025-02-01'},
                'end': {'date': '2025-02-01'}
            }
            
            mock_service = MagicMock()
            mock_service.events().get().execute.return_value = mock_event
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_meeting_by_id
            
            result = get_meeting_by_id('minimal123')
            
            assert result is not None
            assert result['id'] == 'minimal123'
            assert result['title'] == 'No title'  # Default value
            assert result['attendees'] == []
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_uses_correct_calendar_and_event_id(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that correct calendarId and eventId are used in API call."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            mock_service = MagicMock()
            mock_service.events().get().execute.return_value = {'id': 'test_event_id'}
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_meeting_by_id
            
            get_meeting_by_id('test_event_id')
            
            mock_service.events().get.assert_called_with(
                calendarId='primary',
                eventId='test_event_id'
            )
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_extracts_all_event_fields(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that all event fields are properly extracted."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            mock_event = {
                'id': 'full_event',
                'summary': 'Full Event',
                'start': {'dateTime': '2025-02-01T10:00:00-05:00'},
                'end': {'dateTime': '2025-02-01T11:00:00-05:00'},
                'description': 'Full description',
                'location': 'Virtual',
                'htmlLink': 'https://calendar.google.com/event/123',
                'attendees': [
                    {'displayName': 'Test User', 'email': 'test@example.com', 'self': False}
                ]
            }
            
            mock_service = MagicMock()
            mock_service.events().get().execute.return_value = mock_event
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_meeting_by_id
            
            result = get_meeting_by_id('full_event')
            
            assert result['id'] == 'full_event'
            assert result['title'] == 'Full Event'
            assert result['start'] == '2025-02-01T10:00:00-05:00'
            assert result['end'] == '2025-02-01T11:00:00-05:00'
            assert result['description'] == 'Full description'
            assert result['location'] == 'Virtual'
            assert result['htmlLink'] == 'https://calendar.google.com/event/123'


# =============================================================================
# Tests for get_meeting_info()
# =============================================================================
class TestGetMeetingInfo:
    """Tests for the get_meeting_info function."""
    
    @patch('search_server_funcs.SearchHandler')
    def test_returns_none_when_no_events(self, mock_handler_class):
        """Test that function returns None when no events are found."""
        mock_handler = MagicMock()
        mock_handler.get_upcoming_events_google.return_value = {'events': []}
        mock_handler_class.return_value = mock_handler
        
        from search_server_funcs import get_meeting_info
        
        result = get_meeting_info()
        
        assert result is None
    
    @patch('search_server_funcs.SearchHandler')
    def test_returns_meeting_info_when_event_exists(self, mock_handler_class):
        """Test that function returns formatted meeting info when event exists."""
        mock_handler = MagicMock()
        mock_handler.get_upcoming_events_google.return_value = {
            'events': [{
                'id': 'meeting123',
                'title': 'Team Standup',
                'description': 'Daily standup meeting',
                'attendees': [
                    {'name': 'Alice', 'email': 'alice@example.com'},
                    {'name': 'Bob', 'email': 'bob@example.com'}
                ]
            }]
        }
        mock_handler_class.return_value = mock_handler
        
        from search_server_funcs import get_meeting_info
        
        result = get_meeting_info()
        
        assert result is not None
        assert result['title'] == 'Team Standup'
        assert 'Alice' in result['attendees_str']
        assert 'Bob' in result['attendees_str']
        assert result['description'] == 'Daily standup meeting'
    
    @patch('search_server_funcs.SearchHandler')
    def test_returns_none_on_exception(self, mock_handler_class):
        """Test that function returns None when an exception occurs."""
        mock_handler_class.side_effect = Exception("Test error")
        
        from search_server_funcs import get_meeting_info
        
        result = get_meeting_info()
        
        assert result is None
    
    @patch('search_server_funcs.SearchHandler')
    def test_truncates_long_description(self, mock_handler_class):
        """Test that long descriptions are truncated to 200 characters."""
        mock_handler = MagicMock()
        long_description = 'A' * 500  # 500 character description
        mock_handler.get_upcoming_events_google.return_value = {
            'events': [{
                'id': 'meeting123',
                'title': 'Meeting',
                'description': long_description,
                'attendees': []
            }]
        }
        mock_handler_class.return_value = mock_handler
        
        from search_server_funcs import get_meeting_info
        
        result = get_meeting_info()
        
        assert result is not None
        assert len(result['description']) <= 200
    
    @patch('search_server_funcs.SearchHandler')
    def test_limits_attendees_to_five(self, mock_handler_class):
        """Test that attendees list is limited to 5 names."""
        mock_handler = MagicMock()
        attendees = [{'name': f'Person {i}', 'email': f'person{i}@example.com'} for i in range(10)]
        mock_handler.get_upcoming_events_google.return_value = {
            'events': [{
                'id': 'meeting123',
                'title': 'Big Meeting',
                'description': '',
                'attendees': attendees
            }]
        }
        mock_handler_class.return_value = mock_handler
        
        from search_server_funcs import get_meeting_info
        
        result = get_meeting_info()
        
        assert result is not None
        # Should only have first 5 attendees in the string
        attendee_count = result['attendees_str'].count(',') + 1 if result['attendees_str'] else 0
        assert attendee_count <= 5
    
    @patch('search_server_funcs.SearchHandler')
    def test_handles_empty_attendees(self, mock_handler_class):
        """Test that function handles events with no attendees."""
        mock_handler = MagicMock()
        mock_handler.get_upcoming_events_google.return_value = {
            'events': [{
                'id': 'meeting123',
                'title': 'Solo Meeting',
                'description': 'Meeting with myself',
                'attendees': []
            }]
        }
        mock_handler_class.return_value = mock_handler
        
        from search_server_funcs import get_meeting_info
        
        result = get_meeting_info()
        
        assert result is not None
        assert result['attendees_str'] == ''
    
    @patch('search_server_funcs.SearchHandler')
    def test_uses_email_when_name_missing(self, mock_handler_class):
        """Test that email is used when attendee name is missing."""
        mock_handler = MagicMock()
        mock_handler.get_upcoming_events_google.return_value = {
            'events': [{
                'id': 'meeting123',
                'title': 'Meeting',
                'description': '',
                'attendees': [
                    {'email': 'noname@example.com'},  # No name field
                    {'name': 'Has Name', 'email': 'hasname@example.com'}
                ]
            }]
        }
        mock_handler_class.return_value = mock_handler
        
        from search_server_funcs import get_meeting_info
        
        result = get_meeting_info()
        
        assert result is not None
        assert 'noname@example.com' in result['attendees_str']
        assert 'Has Name' in result['attendees_str']
    
    @patch('search_server_funcs.SearchHandler')
    def test_includes_event_object_in_result(self, mock_handler_class):
        """Test that the full event object is included in result."""
        mock_handler = MagicMock()
        event = {
            'id': 'meeting123',
            'title': 'Full Meeting',
            'description': 'Description',
            'attendees': [],
            'extra_field': 'extra_value'
        }
        mock_handler.get_upcoming_events_google.return_value = {'events': [event]}
        mock_handler_class.return_value = mock_handler
        
        from search_server_funcs import get_meeting_info
        
        result = get_meeting_info()
        
        assert result is not None
        assert 'event' in result
        assert result['event']['id'] == 'meeting123'
    
    @patch('search_server_funcs.SearchHandler')
    def test_calls_handler_with_correct_params(self, mock_handler_class):
        """Test that SearchHandler is called with correct parameters."""
        mock_handler = MagicMock()
        mock_handler.get_upcoming_events_google.return_value = {'events': []}
        mock_handler_class.return_value = mock_handler
        
        from search_server_funcs import get_meeting_info
        
        get_meeting_info()
        
        mock_handler.get_upcoming_events_google.assert_called_once_with(
            minutes_ahead=180, limit=1
        )


# =============================================================================
# Tests for search_google_drive()
# =============================================================================
class TestSearchGoogleDrive:
    """Tests for the search_google_drive function."""
    
    def test_returns_empty_when_query_words_too_short(self):
        """Test that function returns empty list when all query words are <= 3 characters."""
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('a bc de')  # All words <= 3 chars
        
        assert result == []
    
    @patch('search_server_funcs.glob.glob')
    def test_returns_empty_when_no_drive_paths(self, mock_glob):
        """Test that function returns empty list when no Google Drive paths exist."""
        mock_glob.return_value = []
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('important document')
        
        assert result == []
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.stat')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_finds_matching_files(self, mock_glob, mock_path_exists, mock_stat, mock_walk):
        """Test that function finds files matching the query."""
        # Setup mocks
        drive_path = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/My Drive'
        mock_glob.return_value = [drive_path]
        mock_path_exists.return_value = True
        
        # Mock directory walk
        mock_walk.return_value = [
            (drive_path, ['Documents'], ['project_notes.pdf', 'project_plan.docx', 'other.txt']),
            (f'{drive_path}/Documents', [], ['project_summary.pdf'])
        ]
        
        # Mock file stats
        mock_stat_result = MagicMock()
        mock_stat_result.st_mtime = datetime.now().timestamp()
        mock_stat.return_value = mock_stat_result
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('project')
        
        # Should find files with 'project' in name
        assert len(result) >= 1
        assert any('project' in r['name'].lower() for r in result)
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.stat')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_respects_max_results(self, mock_glob, mock_path_exists, mock_stat, mock_walk):
        """Test that function respects the max_results parameter."""
        drive_path = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/My Drive'
        mock_glob.return_value = [drive_path]
        mock_path_exists.return_value = True
        
        # Create many matching files
        files = [f'document_{i}.pdf' for i in range(20)]
        mock_walk.return_value = [(drive_path, [], files)]
        
        mock_stat_result = MagicMock()
        mock_stat_result.st_mtime = datetime.now().timestamp()
        mock_stat.return_value = mock_stat_result
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('document', max_results=3)
        
        assert len(result) == 3
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_skips_hidden_files_and_directories(self, mock_glob, mock_path_exists, mock_walk):
        """Test that hidden files and directories are skipped."""
        drive_path = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/My Drive'
        mock_glob.return_value = [drive_path]
        mock_path_exists.return_value = True
        
        # Include hidden files/directories
        mock_walk.return_value = [
            (drive_path, ['.hidden_dir', 'visible_dir'], ['.hidden_file.txt', 'visible_file.txt'])
        ]
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('visible')
        
        # Should only find visible file
        assert all(not r['name'].startswith('.') for r in result)
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_handles_exception_gracefully(self, mock_glob, mock_path_exists, mock_walk):
        """Test that function handles exceptions gracefully."""
        drive_path = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/My Drive'
        mock_glob.return_value = [drive_path]
        mock_path_exists.return_value = True
        mock_walk.side_effect = PermissionError("Access denied")
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('important')
        
        # Should return empty list, not raise exception
        assert result == []
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.stat')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_returns_correct_file_metadata(self, mock_glob, mock_path_exists, mock_stat, mock_walk):
        """Test that function returns correct file metadata."""
        drive_path = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/My Drive'
        # glob.glob is called twice: once for "My Drive" and once for "Shared drives"
        mock_glob.side_effect = [[drive_path], []]  # Only return My Drive path
        mock_path_exists.return_value = True
        
        # Use side_effect to return results only for specific paths
        def walk_side_effect(path):
            if path == drive_path:
                return [(f'{drive_path}/Documents', [], ['report_final.pdf'])]
            return []
        mock_walk.side_effect = walk_side_effect
        
        test_time = datetime(2025, 1, 15, 10, 30, 0)
        mock_stat_result = MagicMock()
        mock_stat_result.st_mtime = test_time.timestamp()
        mock_stat.return_value = mock_stat_result
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('report')
        
        assert len(result) == 1
        assert result[0]['name'] == 'report_final.pdf'
        assert 'Documents' in result[0]['path']
        assert result[0]['drive'] == 'My Drive'
        assert result[0]['modified'] is not None
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.stat')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_identifies_shared_drives(self, mock_glob, mock_path_exists, mock_stat, mock_walk):
        """Test that function correctly identifies Shared drives."""
        shared_drive_path = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/Shared drives'
        # glob.glob is called twice: once for "My Drive" and once for "Shared drives"
        mock_glob.side_effect = [[], [shared_drive_path]]  # Only return Shared drives path
        mock_path_exists.return_value = True
        
        def walk_side_effect(path):
            if path == shared_drive_path:
                return [(shared_drive_path, [], ['shared_doc.pdf'])]
            return []
        mock_walk.side_effect = walk_side_effect
        
        mock_stat_result = MagicMock()
        mock_stat_result.st_mtime = datetime.now().timestamp()
        mock_stat.return_value = mock_stat_result
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('shared')
        
        assert len(result) == 1
        assert result[0]['drive'] == 'Shared drives'
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.stat')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_handles_stat_error_gracefully(self, mock_glob, mock_path_exists, mock_stat, mock_walk):
        """Test that function handles os.stat errors gracefully."""
        drive_path = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/My Drive'
        # glob.glob is called twice: once for "My Drive" and once for "Shared drives"
        mock_glob.side_effect = [[drive_path], []]  # Only return My Drive path
        mock_path_exists.return_value = True
        
        def walk_side_effect(path):
            if path == drive_path:
                return [(drive_path, [], ['document.pdf'])]
            return []
        mock_walk.side_effect = walk_side_effect
        
        # os.stat raises an exception
        mock_stat.side_effect = OSError("Cannot stat file")
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('document')
        
        # Should still return the file but with modified=None
        assert len(result) == 1
        assert result[0]['modified'] is None
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.stat')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_includes_full_path_in_result(self, mock_glob, mock_path_exists, mock_stat, mock_walk):
        """Test that full_path is included in the result."""
        drive_path = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/My Drive'
        # glob.glob is called twice: once for "My Drive" and once for "Shared drives"
        mock_glob.side_effect = [[drive_path], []]  # Only return My Drive path
        mock_path_exists.return_value = True
        
        def walk_side_effect(path):
            if path == drive_path:
                return [(f'{drive_path}/Projects', [], ['project_file.docx'])]
            return []
        mock_walk.side_effect = walk_side_effect
        
        mock_stat_result = MagicMock()
        mock_stat_result.st_mtime = datetime.now().timestamp()
        mock_stat.return_value = mock_stat_result
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('project')
        
        assert len(result) == 1
        assert 'full_path' in result[0]
        assert result[0]['full_path'] == f'{drive_path}/Projects/project_file.docx'
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.stat')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_searches_multiple_drive_paths(self, mock_glob, mock_path_exists, mock_stat, mock_walk):
        """Test that function searches both My Drive and Shared drives."""
        my_drive = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/My Drive'
        shared_drive = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/Shared drives'
        # glob.glob is called twice: once for "My Drive" and once for "Shared drives"
        mock_glob.side_effect = [[my_drive], [shared_drive]]
        mock_path_exists.return_value = True
        
        def walk_side_effect(path):
            if path == my_drive:
                return [(my_drive, [], ['document_one.pdf'])]
            elif path == shared_drive:
                return [(shared_drive, [], ['document_two.pdf'])]
            return []
        mock_walk.side_effect = walk_side_effect
        
        mock_stat_result = MagicMock()
        mock_stat_result.st_mtime = datetime.now().timestamp()
        mock_stat.return_value = mock_stat_result
        
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('document', max_results=10)
        
        assert len(result) == 2
    
    def test_filters_short_query_words(self):
        """Test that short words in query are filtered out."""
        from search_server_funcs import search_google_drive
        
        # Query with mix of short and long words
        result = search_google_drive('a to the')  # All <= 3 chars
        
        assert result == []


# =============================================================================
# Integration-like Tests
# =============================================================================
class TestGoogleIntegration:
    """Integration-like tests that verify multiple functions work together."""
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_credentials_not_refreshed_when_valid(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that valid credentials are not unnecessarily refreshed."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            
            # Valid, non-expired credentials
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_creds.refresh_token = 'token123'
            mock_pickle.return_value = mock_creds
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = {'items': []}
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            get_calendar_events_standalone()
            
            # refresh should NOT be called
            mock_creds.refresh.assert_not_called()
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_credentials_not_refreshed_when_no_refresh_token(self, mock_exists, mock_file, 
                                                              mock_pickle, mock_build):
        """Test that credentials without refresh token are not refreshed even if expired."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            
            # Expired credentials but no refresh token
            mock_creds = MagicMock()
            mock_creds.expired = True
            mock_creds.refresh_token = None  # No refresh token
            mock_pickle.return_value = mock_creds
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = {'items': []}
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            get_calendar_events_standalone()
            
            # refresh should NOT be called (no refresh token)
            mock_creds.refresh.assert_not_called()
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_calendar_service_built_with_correct_api(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that calendar service is built with correct API name and version."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = {'items': []}
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            get_calendar_events_standalone()
            
            mock_build.assert_called_with('calendar', 'v3', credentials=mock_creds)


# =============================================================================
# Edge Case Tests
# =============================================================================
class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_handles_api_error_gracefully(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that API errors are handled gracefully."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            mock_service = MagicMock()
            mock_service.events().list().execute.side_effect = Exception("API Error")
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            result = get_calendar_events_standalone()
            
            assert result == []
    
    @patch('search_server_funcs.build')
    @patch('search_server_funcs.pickle.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('search_server_funcs.os.path.exists')
    def test_handles_malformed_event_data(self, mock_exists, mock_file, mock_pickle, mock_build):
        """Test that malformed event data doesn't crash the function."""
        with patch('search_server_funcs.GOOGLE_API_AVAILABLE', True):
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_pickle.return_value = mock_creds
            
            # Malformed event missing required fields
            mock_events = {
                'items': [{
                    'id': 'malformed'
                    # Missing start/end
                }]
            }
            
            mock_service = MagicMock()
            mock_service.events().list().execute.return_value = mock_events
            mock_build.return_value = mock_service
            
            from search_server_funcs import get_calendar_events_standalone
            
            # Should not raise an exception
            result = get_calendar_events_standalone()
            assert isinstance(result, list)
    
    @patch('search_server_funcs.os.walk')
    @patch('search_server_funcs.os.path.exists')
    @patch('search_server_funcs.glob.glob')
    def test_drive_search_with_special_characters(self, mock_glob, mock_path_exists, mock_walk):
        """Test that search handles special characters in filenames."""
        drive_path = '/Users/test/Library/CloudStorage/GoogleDrive-test@gmail.com/My Drive'
        mock_glob.return_value = [drive_path]
        mock_path_exists.return_value = True
        
        mock_walk.return_value = [
            (drive_path, [], ['report_(2025).pdf', 'report_[final].docx'])
        ]
        
        from search_server_funcs import search_google_drive
        
        # Should not raise exception with special chars in filenames
        result = search_google_drive('report')
        assert isinstance(result, list)
    
    def test_empty_query_returns_empty_list(self):
        """Test that empty query returns empty list."""
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('')
        
        assert result == []
    
    def test_whitespace_only_query_returns_empty_list(self):
        """Test that whitespace-only query returns empty list."""
        from search_server_funcs import search_google_drive
        
        result = search_google_drive('   ')
        
        assert result == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
