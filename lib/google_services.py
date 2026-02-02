"""Google Calendar and Google Drive integration for BriefDesk."""

import os
import pickle
import glob
from datetime import datetime, timedelta

from .config import (
    logger, TOKEN_PATH, CREDENTIALS_PATH, SCOPES,
    GOOGLE_API_AVAILABLE, GOOGLE_DRIVE_PATHS,
    Request, Credentials, InstalledAppFlow, build
)

# =============================================================================
# Authentication
# =============================================================================

def authenticate_google():
    """Run OAuth flow for Google Calendar."""
    if not GOOGLE_API_AVAILABLE:
        print("Google API libraries not installed. Run: pip3 install google-auth-oauthlib google-api-python-client")
        return False
    
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"Credentials file not found at {CREDENTIALS_PATH}")
        print("Please download credentials.json from Google Cloud Console")
        return False
    
    print("Starting OAuth flow...")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open(TOKEN_PATH, 'wb') as token:
        pickle.dump(creds, token)
    
    print("Success! Token saved.")
    return True


def get_google_credentials():
    """Get valid Google credentials, refreshing if needed."""
    if not GOOGLE_API_AVAILABLE:
        return None
    
    if not os.path.exists(TOKEN_PATH):
        return None
    
    try:
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
        
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)
        
        return creds if creds and creds.valid else None
    except Exception as e:
        logger.error(f"Error loading Google credentials: {e}")
        return None

# =============================================================================
# Calendar
# =============================================================================

def get_calendar_events_standalone(minutes_ahead=120, limit=5):
    """Get upcoming calendar events."""
    if not GOOGLE_API_AVAILABLE:
        return []
    
    creds = get_google_credentials()
    if not creds:
        return []
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        
        now = datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        time_max = (now + timedelta(minutes=minutes_ahead)).isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=limit,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = []
        for event in events_result.get('items', []):
            # Skip all-day events (no dateTime)
            start = event.get('start', {})
            if 'dateTime' not in start:
                continue
            
            # Parse start time
            start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
            
            # Skip if already ended
            end = event.get('end', {})
            if 'dateTime' in end:
                end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
                if end_dt < datetime.now(end_dt.tzinfo):
                    continue
            
            # Get join link (prefer hangoutLink, fallback to htmlLink)
            join_link = event.get('hangoutLink', '')
            if not join_link:
                # Check for Zoom/Teams in description or location
                for field in ['description', 'location']:
                    text = event.get(field, '')
                    if 'zoom.us' in text.lower():
                        import re
                        match = re.search(r'https://[^\s]*zoom\.us/[^\s<>"\']+', text)
                        if match:
                            join_link = match.group(0)
                            break
                    elif 'teams.microsoft.com' in text.lower():
                        import re
                        match = re.search(r'https://teams\.microsoft\.com/[^\s<>"\']+', text)
                        if match:
                            join_link = match.group(0)
                            break
            
            if not join_link:
                join_link = event.get('htmlLink', '')
            
            events.append({
                'id': event.get('id', ''),
                'title': event.get('summary', 'No title'),
                'start': start['dateTime'],
                'end': end.get('dateTime', ''),
                'join_link': join_link,
                'location': event.get('location', ''),
                'description': event.get('description', '')[:500] if event.get('description') else '',
                'attendees': [
                    {'name': a.get('displayName', a.get('email', '')), 'email': a.get('email', '')}
                    for a in event.get('attendees', [])[:10]
                ]
            })
        
        return events
    
    except Exception as e:
        logger.error(f"Error fetching calendar events: {e}")
        return []


def get_meeting_by_id(event_id):
    """Get a specific calendar event by ID."""
    if not GOOGLE_API_AVAILABLE:
        return None
    
    creds = get_google_credentials()
    if not creds:
        return None
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        
        start = event.get('start', {})
        end = event.get('end', {})
        
        return {
            'id': event.get('id', ''),
            'title': event.get('summary', 'No title'),
            'start': start.get('dateTime', start.get('date', '')),
            'end': end.get('dateTime', end.get('date', '')),
            'join_link': event.get('hangoutLink', event.get('htmlLink', '')),
            'location': event.get('location', ''),
            'description': event.get('description', '')[:500] if event.get('description') else '',
            'attendees': [
                {'name': a.get('displayName', a.get('email', '')), 'email': a.get('email', '')}
                for a in event.get('attendees', [])[:10]
            ]
        }
    
    except Exception as e:
        logger.debug(f"Error fetching meeting {event_id}: {e}")
        return None


def get_meeting_info():
    """Get info about the next upcoming meeting."""
    events = get_calendar_events_standalone(minutes_ahead=180, limit=1)
    if not events:
        return None
    
    event = events[0]
    attendees = event.get('attendees', [])
    
    return {
        'title': event.get('title', ''),
        'start': event.get('start', ''),
        'end': event.get('end', ''),
        'attendees': ', '.join([a.get('name', a.get('email', '')) for a in attendees[:5]]),
        'attendee_count': len(attendees),
        'attendee_emails': [a.get('email', '') for a in attendees[:5]],
        'description': event.get('description', ''),
        'join_link': event.get('join_link', ''),
        'event': event
    }

# =============================================================================
# Google Drive
# =============================================================================

def search_google_drive(query, max_results=5):
    """Search Google Drive files using local filesystem (Drive for Desktop)."""
    if not GOOGLE_DRIVE_PATHS:
        return []
    
    # Extract meaningful search words
    words = [w.lower() for w in query.split() if len(w) > 2]
    if not words:
        return []
    
    results = []
    seen_paths = set()
    
    try:
        for drive_path in GOOGLE_DRIVE_PATHS:
            if not os.path.exists(drive_path):
                continue
            
            # Walk through the directory
            for root, dirs, files in os.walk(drive_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for filename in files:
                    # Skip hidden files
                    if filename.startswith('.'):
                        continue
                    
                    # Check if any word matches the filename
                    filename_lower = filename.lower()
                    if any(word in filename_lower for word in words):
                        full_path = os.path.join(root, filename)
                        
                        if full_path in seen_paths:
                            continue
                        seen_paths.add(full_path)
                        
                        try:
                            stat = os.stat(full_path)
                            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                        except:
                            modified = ''
                        
                        # Determine if it's from shared drives
                        is_shared = 'Shared drives' in full_path or 'SharedDrives' in full_path
                        
                        results.append({
                            'title': filename,
                            'path': full_path,
                            'url': f'file://{full_path}',
                            'modified': modified,
                            'type': 'drive',
                            'is_shared': is_shared
                        })
                        
                        if len(results) >= max_results:
                            return results
    
    except Exception as e:
        logger.error(f"Error searching Google Drive: {e}")
    
    return results
