"""Google Calendar and Google Drive integration for BriefDesk."""

import os
import pickle
import glob
from datetime import datetime, timedelta

from .config import (
    logger, CONFIG_DIR, TOKEN_PATH, CREDENTIALS_PATH, SCOPES, ALL_SCOPES,
    GOOGLE_API_AVAILABLE, GOOGLE_DRIVE_PATHS,
    Request, Credentials, InstalledAppFlow, build,
    get_oauth_credentials_config, GOOGLE_CLIENT_ID
)

# =============================================================================
# Authentication
# =============================================================================

def authenticate_google():
    """Run OAuth flow for Google Calendar (CLI mode)."""
    if not GOOGLE_API_AVAILABLE:
        print("Google API libraries not installed. Run: pip3 install google-auth-oauthlib google-api-python-client")
        return False

    oauth_config = get_oauth_credentials_config()
    if not oauth_config:
        print(f"No OAuth credentials available.")
        print(f"Either place google_credentials.json in {CREDENTIALS_PATH}")
        print("Or set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables")
        return False

    print("Starting OAuth flow...")

    # Create flow from config dict
    if os.path.exists(CREDENTIALS_PATH):
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, ALL_SCOPES)
    else:
        flow = InstalledAppFlow.from_client_config(
            {'installed': oauth_config},
            ALL_SCOPES
        )

    creds = flow.run_local_server(port=0)

    with open(TOKEN_PATH, 'wb') as token:
        pickle.dump(creds, token)

    print("Success! Token saved.")
    return True


def get_oauth_url(redirect_uri='http://localhost:18765/oauth/callback'):
    """Generate OAuth authorization URL for web-based flow."""
    if not GOOGLE_API_AVAILABLE:
        return None, "Google API libraries not installed"

    oauth_config = get_oauth_credentials_config()
    if not oauth_config:
        return None, "No OAuth credentials configured"

    try:
        from google_auth_oauthlib.flow import Flow

        # Create flow from config
        flow = Flow.from_client_config(
            {'installed': oauth_config},
            scopes=ALL_SCOPES,
            redirect_uri=redirect_uri
        )

        auth_url, state = flow.authorization_url(
            access_type='offline',
            prompt='consent'
        )

        return auth_url, state
    except Exception as e:
        logger.error(f"Error generating OAuth URL: {e}")
        return None, str(e)


def handle_oauth_callback(code, redirect_uri='http://localhost:18765/oauth/callback'):
    """Handle OAuth callback and save credentials."""
    if not GOOGLE_API_AVAILABLE:
        return False, "Google API libraries not installed"

    oauth_config = get_oauth_credentials_config()
    if not oauth_config:
        return False, "No OAuth credentials configured"

    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            {'installed': oauth_config},
            scopes=ALL_SCOPES,
            redirect_uri=redirect_uri
        )

        flow.fetch_token(code=code)
        creds = flow.credentials

        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

        # Export credentials for Gmail and GDrive MCPs to share authentication
        _export_credentials_for_gmail_mcp(creds)
        _export_credentials_for_gdrive_mcp(creds)

        logger.info("OAuth credentials saved successfully")
        return True, "Success"
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return False, str(e)


def _export_credentials_for_gmail_mcp(creds):
    """Export credentials to Gmail MCP format for shared authentication.
    
    This allows the Gmail MCP (used by devsai) to use the same OAuth tokens
    as BriefDesk, avoiding duplicate authentication prompts.
    """
    import json
    
    gmail_mcp_dir = os.path.expanduser("~/.gmail-mcp")
    gmail_mcp_creds_path = os.path.join(gmail_mcp_dir, "credentials.json")
    gmail_mcp_keys_path = os.path.join(gmail_mcp_dir, "gcp-oauth.keys.json")
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(gmail_mcp_dir, exist_ok=True)
        
        # 1. Export OAuth tokens (credentials.json)
        # Gmail MCP uses google-auth-library which expects this format
        creds_json = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "scope": " ".join(creds.scopes) if creds.scopes else "",
            "token_type": "Bearer",
        }
        
        # Add expiry if available (Gmail MCP expects expiry_date as Unix timestamp in ms)
        if creds.expiry:
            creds_json["expiry_date"] = int(creds.expiry.timestamp() * 1000)
        
        with open(gmail_mcp_creds_path, 'w') as f:
            json.dump(creds_json, f, indent=2)
        
        logger.info(f"Exported credentials for Gmail MCP to {gmail_mcp_creds_path}")
        
        # 2. Export OAuth client keys (gcp-oauth.keys.json)
        # Gmail MCP needs this to refresh tokens
        oauth_config = get_oauth_credentials_config()
        if oauth_config:
            keys_json = {
                "installed": {
                    "client_id": oauth_config.get('client_id'),
                    "client_secret": oauth_config.get('client_secret'),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost:3000/oauth2callback"]
                }
            }
            
            with open(gmail_mcp_keys_path, 'w') as f:
                json.dump(keys_json, f, indent=2)
            
            logger.info(f"Exported OAuth keys for Gmail MCP to {gmail_mcp_keys_path}")
            
    except Exception as e:
        # Don't fail the main OAuth flow if MCP export fails
        logger.warning(f"Failed to export credentials for Gmail MCP: {e}")


def _export_credentials_for_gdrive_mcp(creds):
    """Export credentials to GDrive MCP format for shared authentication.
    
    This allows the GDrive MCP (used by devsai) to use the same OAuth tokens
    as BriefDesk, avoiding a separate authentication step.
    The GDrive MCP reads its token from google_drive_token.json and its
    client keys from google_credentials.json (which already exists).
    """
    import json
    
    gdrive_token_path = os.path.join(CONFIG_DIR, "google_drive_token.json")
    
    try:
        # Export OAuth tokens in the format GDrive MCP expects
        creds_json = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "scope": " ".join(creds.scopes) if creds.scopes else "",
            "token_type": "Bearer",
        }
        
        # Add expiry if available (GDrive MCP expects expiry_date as Unix timestamp in ms)
        if creds.expiry:
            creds_json["expiry_date"] = int(creds.expiry.timestamp() * 1000)
        
        with open(gdrive_token_path, 'w') as f:
            json.dump(creds_json, f, indent=2)
        
        logger.info(f"Exported credentials for GDrive MCP to {gdrive_token_path}")
            
    except Exception as e:
        # Don't fail the main OAuth flow if MCP export fails
        logger.warning(f"Failed to export credentials for GDrive MCP: {e}")


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
            try:
                creds.refresh(Request())
                with open(TOKEN_PATH, 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                logger.error(f"Error refreshing credentials: {e}")
                return None

        return creds if creds and creds.valid else None
    except Exception as e:
        logger.error(f"Error loading Google credentials: {e}")
        return None


def has_oauth_credentials():
    """Check if OAuth credentials (embedded or file) are available."""
    return get_oauth_credentials_config() is not None


def is_google_authenticated():
    """Check if user has valid Google authentication."""
    return get_google_credentials() is not None


def get_granted_scopes():
    """Get the list of scopes granted by the user.

    Returns:
        dict: {'calendar': bool, 'drive': bool, 'gmail': bool} indicating which scopes are granted
    """
    creds = get_google_credentials()
    if not creds:
        return {'calendar': False, 'drive': False, 'gmail': False}

    # Get the scopes from the credentials
    granted = set(creds.scopes) if creds.scopes else set()

    return {
        'calendar': 'https://www.googleapis.com/auth/calendar.readonly' in granted,
        'drive': 'https://www.googleapis.com/auth/drive.readonly' in granted,
        'gmail': 'https://www.googleapis.com/auth/gmail.readonly' in granted,
    }


def disconnect_google():
    """Remove Google authentication (BriefDesk, Gmail MCP, and GDrive MCP credentials)."""
    success = False
    try:
        # Remove BriefDesk token
        if os.path.exists(TOKEN_PATH):
            os.remove(TOKEN_PATH)
            logger.info("BriefDesk Google credentials removed")
            success = True
        
        # Also remove Gmail MCP credentials (shared auth)
        gmail_mcp_creds = os.path.expanduser("~/.gmail-mcp/credentials.json")
        if os.path.exists(gmail_mcp_creds):
            os.remove(gmail_mcp_creds)
            logger.info("Gmail MCP credentials removed")
            success = True
        
        # Also remove GDrive MCP token (shared auth)
        gdrive_token_path = os.path.join(CONFIG_DIR, "google_drive_token.json")
        if os.path.exists(gdrive_token_path):
            os.remove(gdrive_token_path)
            logger.info("GDrive MCP credentials removed")
            success = True
            
        return success
    except Exception as e:
        logger.error(f"Error removing credentials: {e}")
    return False

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
