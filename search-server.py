#!/usr/bin/env python3
"""BriefDesk Search Server - Local browser history, calendar, and productivity hub.

This is the refactored version using modular lib/ components.
"""

import json
import os
import re
import sys
import time
import pickle
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from socketserver import ThreadingMixIn

# Add lib to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import from lib modules
from lib.config import (
    logger, LOG_FILE, CONFIG_DIR, TOKEN_PATH, CREDENTIALS_PATH,
    SAFARI_HISTORY, SAFARI_BOOKMARKS, CHROME_HISTORY, CHROME_BOOKMARKS,
    HELIUM_HISTORY, HELIUM_BOOKMARKS, DIA_HISTORY, DIA_BOOKMARKS,
    SCOPES, GOOGLE_API_AVAILABLE, CACHE_TTL, PREP_CACHE_TTL,
    Request, Credentials, InstalledAppFlow, build,
)

from lib.utils import (
    copy_db, cleanup_db, extract_domain, score_result, is_night_hours,
)

from lib.cache import (
    _calendar_cache,
    load_custom_prompts, save_custom_prompts,
    get_prompt, set_custom_prompt, reset_prompt, get_all_prompts,
    load_prep_cache_from_disk, save_prep_cache_to_disk,
    get_meeting_cache, set_meeting_cache,
    is_cache_valid, has_cached_data, get_cached_data,
    set_meeting_info, get_meeting_info,
)

from lib.slack import (
    slack_get_conversations_fast, slack_get_conversation_history_direct,
    slack_get_threads, slack_get_thread_replies,
    slack_send_message_direct, slack_mark_conversation_read,
)

from lib.atlassian import (
    search_atlassian, get_jira_context, search_confluence,
    list_atlassian_tools, load_mcp_config,
)

from lib.google_services import (
    authenticate_google, get_meeting_by_id, search_google_drive,
    get_oauth_url, handle_oauth_callback,
    has_oauth_credentials, is_google_authenticated, disconnect_google,
)

from lib.cli import (
    extract_meeting_keywords, call_cli_for_source, call_cli_for_meeting_summary,
)

from lib.prefetch import (
    configure_cli_functions, start_prefetch_thread, stop_prefetch_thread,
    get_prefetch_status, set_force_aggressive_prefetch,
    add_prefetch_activity, update_prefetch_status,
    prefetch_meeting_data, check_services_auth,
)

from lib.history import (
    search_history, search_bookmarks, search_browser_history,
    search_chrome_bookmarks, search_helium_bookmarks,
    search_dia_bookmarks, search_safari_bookmarks,
    search_chrome_history, search_helium_history,
    search_dia_history, search_safari_history,
)


class SearchHandler(BaseHTTPRequestHandler):
    """HTTP request handler for all BriefDesk endpoints."""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def send_json(self, data):
        """Send JSON response with CORS headers."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        # Route to appropriate handler
        if path == "/search":
            self.handle_search(params)
        elif path == "/calendar":
            self.handle_calendar(params)
        elif path == "/calendar/status":
            self.handle_calendar_status()
        elif path == "/debug":
            self.handle_debug()
        # Hub endpoints
        elif path == "/hub/prep/week":
            self.handle_prep_week()
        elif path in ("/hub/meeting-prep", "/hub/prep/meeting"):
            self.handle_prep_meeting(params)
        elif path == "/hub/prep/all":
            self.handle_prep_all(params)
        elif path.startswith("/hub/prep/"):
            self.handle_prep_source(path, params)
        elif path == "/hub/meeting/summary":
            self.handle_meeting_summary(params)
        elif path == "/hub/status":
            self.handle_hub_status()
        elif path == "/hub/prefetch-status":
            self.handle_prefetch_status()
        elif path == "/hub/service-health":
            self.handle_service_health()
        elif path == "/hub/prefetch/control":
            self.handle_prefetch_control(params)
        elif path == "/hub/mcp-reauth":
            self.handle_mcp_reauth(params)
        elif path == "/hub/restart-search-service":
            self.handle_restart_search_service()
        elif path == "/hub/prompts":
            self.handle_get_prompts()
        elif path == "/hub/batch":
            self.handle_batch(params)
        # Slack endpoints
        elif path == "/slack/conversations":
            self.handle_slack_conversations(params)
        elif path == "/slack/history":
            self.handle_slack_history(params)
        elif path == "/slack/threads":
            self.handle_slack_threads(params)
        elif path == "/slack/thread":
            self.handle_slack_thread(params)
        elif path == "/slack/mark-read":
            self.handle_slack_mark_read(params)
        # Setup page
        elif path == "/setup":
            self.handle_setup_page()
        # OAuth endpoints
        elif path == "/oauth/google/start":
            self.handle_oauth_google_start()
        elif path == "/oauth/callback":
            self.handle_oauth_callback(params)
        elif path == "/oauth/google/status":
            self.handle_oauth_google_status()
        elif path == "/oauth/google/disconnect":
            self.handle_oauth_google_disconnect()
        # Installer endpoints
        elif path == "/installer":
            self.handle_installer_page()
        elif path == "/installer/check":
            self.handle_installer_check(params)
        elif path == "/installer/check-fda":
            self.handle_installer_check_fda()
        else:
            self.send_json({"error": "Not found"})
    
    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # Read POST body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length else '{}'
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        
        if path == "/slack/send":
            self.handle_slack_send(data)
        elif path == "/hub/prompts":
            self.handle_set_prompt(data)
        elif path == "/hub/settings":
            self.handle_hub_settings(data)
        elif path == "/hub/ai-search":
            self.handle_ai_search(data)
        elif path == "/hub/ai-search-stream":
            self.handle_ai_search_stream(data)
        # Setup endpoints
        elif path == "/setup/slack":
            self.handle_setup_slack(data)
        # Installer endpoints
        elif path == "/installer/install":
            self.handle_installer_install(data)
        else:
            self.send_json({"error": "Not found"})
    
    def handle_hub_settings(self, data):
        """Handle hub settings update (model selection, etc)."""
        from lib.config import set_hub_model, get_hub_model
        
        model = data.get('model')
        if model:
            set_hub_model(model)
            logger.info(f"[Settings] Model updated to: {model}")
        
        self.send_json({"success": True, "model": get_hub_model()})
    
    def handle_ai_search(self, data):
        """Handle AI-powered search across multiple sources."""
        from lib.ai_search import ai_search
        from lib.config import get_hub_model
        
        query = data.get('query', '').strip()
        sources = data.get('sources', ['slack', 'jira', 'confluence', 'gmail', 'drive'])
        
        if not query:
            self.send_json({"error": "Query is required"})
            return
        
        logger.info(f"[AI Search] Query: '{query}' | Sources: {sources}")
        
        # Build the search prompt
        source_names = ', '.join([s.title() for s in sources])
        
        # Add source-specific instructions
        source_instructions = ""
        
        if 'slack' in sources:
            source_instructions += """
SLACK SEARCH INSTRUCTIONS:
When searching for conversations with a specific person:
1. FIRST use channels_list with channel_types: "im" to find their 1:1 DM channel
2. THEN use conversations_history with that channel_id to get recent messages
3. ALSO use conversations_search_messages for broader searches in channels
ALWAYS check 1:1 DMs when searching for discussions with specific people.
"""
        
        if 'jira' in sources:
            source_instructions += """
JIRA SEARCH INSTRUCTIONS:
1. FIRST call "Get Accessible Atlassian Resources" to get the cloudId - do NOT ask the user for it
2. THEN use that cloudId for all Jira searches (e.g., "Search Jira issues using JQL")
3. Use JQL queries like: text ~ "keyword" OR summary ~ "keyword" ORDER BY updated DESC
4. NEVER ask the user for cloudId or site URL - discover it automatically with step 1
"""
        
        if 'confluence' in sources:
            source_instructions += """
CONFLUENCE SEARCH INSTRUCTIONS:
1. FIRST call "Get Accessible Atlassian Resources" to get the cloudId - do NOT ask the user for it
2. THEN use that cloudId for all Confluence searches (e.g., "Search Confluence Using CQL")
3. Use CQL queries like: text ~ "keyword" OR title ~ "keyword" ORDER BY lastmodified DESC
4. NEVER ask the user for cloudId or site URL - discover it automatically with step 1
"""
        
        if 'drive' in sources:
            from lib.config import GOOGLE_DRIVE_BASE
            drive_path = GOOGLE_DRIVE_BASE or "~/Library/CloudStorage/GoogleDrive-*"
            source_instructions += f"""
GOOGLE DRIVE SEARCH INSTRUCTIONS:
1. Use find_files or search_files to search for documents in the local Google Drive folder
2. Search path: {drive_path}/My Drive/
3. Use patterns like: {drive_path}/My Drive/**/*keyword* to find files matching keywords
4. For links, convert filenames to Google Drive search URLs:
   - Extract just the filename (without path and extension)
   - URL encode spaces as +
   - Return as: https://drive.google.com/drive/search?q=FILENAME
   - Example: "My Document.gdoc" -> https://drive.google.com/drive/search?q=My+Document
"""
        
        prompt = f"""Search {source_names} to answer this question: {query}
{source_instructions}
Provide a comprehensive but concise answer based on the information found.

RULES:
- Be specific: include ticket numbers, document names, channel names, dates
- ALWAYS include clickable markdown links to sources:
  - Slack: [#channel-name](slack_permalink) or [DM with Name](slack_permalink)
  - Jira: [PROJ-123](jira_url)
  - Confluence: [Page Title](confluence_url)
  - Gmail: [Email Subject](gmail_url) (if available)
  - Drive: [Document Name](drive_url)
- At the end, add a "Sources" section with all referenced links
- If you find conflicting information, mention it
- If no relevant information is found, say so clearly
- Keep the response under 300 words unless more detail is needed

FORMAT EXAMPLE:
Based on discussions in [DM with John](https://slack.com/...) and [#project-alpha](https://slack.com/...), ...

**Sources:**
- [DM with John](url) - Direct message
- [#project-alpha](url) - Slack channel"""
        
        try:
            model = get_hub_model()
            result = ai_search(prompt, sources=sources, model=model, timeout=90)
            
            if result and result.get('response'):
                self.send_json({"response": result['response'], "sources": sources})
            elif result and result.get('error'):
                self.send_json({"error": result['error']})
            else:
                self.send_json({"error": "No response received. Please try again."})
        except Exception as e:
            logger.error(f"[AI Search] Error: {e}")
            self.send_json({"error": f"Search failed: {str(e)}"})
    
    def handle_ai_search_stream(self, data):
        """Handle AI-powered search with streaming progress updates via SSE."""
        from lib.ai_search import ai_search_stream
        from lib.config import get_hub_model
        
        query = data.get('query', '').strip()
        sources = data.get('sources', ['slack', 'jira', 'confluence', 'gmail', 'drive'])
        
        if not query:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Query is required"}).encode())
            return
        
        logger.info(f"[AI Search Stream] Query: '{query}' | Sources: {sources}")
        
        # Build the search prompt (same as non-streaming)
        source_names = ', '.join([s.title() for s in sources])
        source_instructions = ""
        
        if 'slack' in sources:
            source_instructions += "\nSLACK: Use channels_list with channel_types: 'im' to find DMs, then conversations_history for messages."
        if 'jira' in sources:
            source_instructions += "\nJIRA: FIRST call 'Get Accessible Atlassian Resources' for cloudId, THEN search."
        if 'confluence' in sources:
            source_instructions += "\nCONFLUENCE: FIRST call 'Get Accessible Atlassian Resources' for cloudId, THEN search."
        if 'drive' in sources:
            from lib.config import GOOGLE_DRIVE_BASE
            drive_path = GOOGLE_DRIVE_BASE or "~/Library/CloudStorage/GoogleDrive-*"
            source_instructions += f"\nDRIVE: Search files in {drive_path}/My Drive/"
        
        prompt = f"Search {source_names} for: {query}\n{source_instructions}\nInclude links to sources. Keep response concise."
        
        # Set up SSE response
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        def send_event(event_type, data):
            try:
                event_str = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                self.wfile.write(event_str.encode())
                self.wfile.flush()
            except Exception as e:
                logger.error(f"[AI Search Stream] Failed to send event: {e}")
        
        try:
            model = get_hub_model()
            
            for event_type, event_data in ai_search_stream(prompt, sources=sources, model=model, timeout=120):
                send_event(event_type, event_data)
                
        except Exception as e:
            logger.error(f"[AI Search Stream] Error: {e}")
            send_event("error", {"error": str(e)})
    
    # =========================================================================
    # Search Handlers
    # =========================================================================
    
    def handle_search(self, params):
        """Handle browser history/bookmarks search."""
        query = params.get("q", [""])[0].lower().strip()
        if not query:
            self.send_json([])
            return
        
        limit = int(params.get("limit", ["10"])[0])
        results = search_history(query, limit=limit)
        self.send_json(results)
    
    # =========================================================================
    # Calendar Handlers
    # =========================================================================
    
    def handle_calendar(self, params):
        """Handle calendar events request."""
        minutes = int(params.get("minutes", ["180"])[0])
        limit = int(params.get("limit", ["3"])[0])
        force_refresh = params.get("refresh", ["0"])[0] == "1"
        
        now = time.time()
        # Return cached data if fresh enough (unless force refresh)
        if not force_refresh and _calendar_cache["data"] and (now - _calendar_cache["timestamp"]) < CACHE_TTL:
            self.send_json(_calendar_cache["data"])
            return
        
        try:
            events = self.get_upcoming_events_google(minutes, limit)
            # Check if the response contains an auth error
            if events.get("error"):
                error = events["error"]
                if error in ("not_authenticated", "invalid_token", "auth_failed") or "401" in str(events.get("detail", "")).lower():
                    self.send_json({"events": [], "in_meeting": False, "current_meeting": None, "auth_error": True, "error": "Calendar authentication expired. Please re-authenticate."})
                    return
            _calendar_cache["data"] = events
            _calendar_cache["timestamp"] = now
            self.send_json(events)
        except Exception as e:
            error_str = str(e).lower()
            # Detect auth-related errors
            if "401" in error_str or "invalid_grant" in error_str or "token" in error_str or "credentials" in error_str or "auth" in error_str:
                self.send_json({"events": [], "in_meeting": False, "current_meeting": None, "auth_error": True, "error": "Calendar authentication expired. Please re-authenticate."})
            elif _calendar_cache["data"]:
                self.send_json(_calendar_cache["data"])
            else:
                self.send_json({"events": [], "in_meeting": False, "current_meeting": None, "error": str(e)})
    
    def handle_calendar_status(self):
        """Check calendar configuration status."""
        if not GOOGLE_API_AVAILABLE:
            self.send_json({"status": "missing_libraries"})
        elif not os.path.exists(CREDENTIALS_PATH):
            self.send_json({"status": "not_configured", "message": f"Place google_credentials.json in {CONFIG_DIR}"})
        elif not os.path.exists(TOKEN_PATH):
            self.send_json({"status": "not_authenticated", "message": "Run: python3 ~/.local/share/briefdesk/search-server.py --auth"})
        else:
            self.send_json({"status": "ready"})
    
    def get_google_calendar_service(self):
        """Get authenticated Google Calendar service."""
        if not GOOGLE_API_AVAILABLE:
            return None, "missing_libraries"
        
        if not os.path.exists(TOKEN_PATH):
            return None, "not_authenticated"
        
        try:
            with open(TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)
        except Exception:
            return None, "invalid_token"
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(TOKEN_PATH, 'wb') as token:
                    pickle.dump(creds, token)
            else:
                return None, "not_authenticated"
        
        service = build('calendar', 'v3', credentials=creds)
        return service, None
    
    def get_upcoming_events_google(self, minutes_ahead=180, limit=3):
        """Get upcoming events from Google Calendar API."""
        service, error = self.get_google_calendar_service()
        if error:
            return {"error": error}
        
        try:
            now = datetime.utcnow()
            local_now = datetime.now()
            
            time_min = (now - timedelta(hours=2)).isoformat() + 'Z'
            time_max = (now + timedelta(minutes=minutes_ahead)).isoformat() + 'Z'
            
            # Request more events than needed since we filter out ended ones
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max(20, limit * 3),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            raw_events = events_result.get('items', [])
            
            if not raw_events:
                return {"events": [], "in_meeting": False}
            
            processed = []
            in_meeting = False
            current_meetings = []
            
            for event in raw_events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                if 'T' not in start:
                    continue  # Skip all-day events
                
                # Parse times - Google returns ISO format with timezone
                # Convert to UTC naive datetime for consistent comparison
                if start.endswith('Z'):
                    start_utc = datetime.fromisoformat(start.replace('Z', ''))
                elif '+' in start or (start.count('-') > 2):
                    # Has timezone offset like +00:00 or -05:00
                    start_parsed = datetime.fromisoformat(start)
                    # Convert to UTC by subtracting offset
                    start_utc = start_parsed.replace(tzinfo=None) - start_parsed.utcoffset()
                else:
                    start_utc = datetime.fromisoformat(start)
                
                end = event['end'].get('dateTime', event['end'].get('date'))
                end_utc = None
                if end and 'T' in end:
                    if end.endswith('Z'):
                        end_utc = datetime.fromisoformat(end.replace('Z', ''))
                    elif '+' in end or (end.count('-') > 2):
                        end_parsed = datetime.fromisoformat(end)
                        end_utc = end_parsed.replace(tzinfo=None) - end_parsed.utcoffset()
                    else:
                        end_utc = datetime.fromisoformat(end)
                
                # Compare in UTC
                minutes_until = int((start_utc - now).total_seconds() / 60)
                
                is_current = False
                if end_utc:
                    minutes_until_end = int((end_utc - now).total_seconds() / 60)
                    if minutes_until <= 0 and minutes_until_end > 0:
                        is_current = True
                        in_meeting = True
                
                if end_utc and (end_utc - now).total_seconds() < 0:
                    continue
                
                # Extract meeting link
                meet_link = None
                if 'conferenceData' in event:
                    for entry in event['conferenceData'].get('entryPoints', []):
                        if entry.get('entryPointType') == 'video':
                            meet_link = entry.get('uri')
                            break
                
                if not meet_link:
                    search_text = ' '.join(filter(None, [
                        event.get('description', ''),
                        event.get('location', ''),
                        event.get('hangoutLink', '')
                    ]))
                    patterns = [
                        r'https://meet\.google\.com/[a-z-]+',
                        r'https://zoom\.us/j/\d+[^\s]*',
                        r'https://[a-z0-9]+\.zoom\.us/j/\d+[^\s]*',
                        r'https://teams\.microsoft\.com/l/meetup-join/[^\s<>]+',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, search_text, re.IGNORECASE)
                        if match:
                            meet_link = match.group(0)
                            break
                
                attendees = []
                for a in event.get('attendees', []):
                    attendees.append({
                        'email': a.get('email', ''),
                        'name': a.get('displayName', a.get('email', '')),
                        'self': a.get('self', False)
                    })
                
                # Convert UTC to local time for display
                start_local = start_utc + (local_now - now)
                end_local = end_utc + (local_now - now) if end_utc else None
                
                evt_data = {
                    'id': event.get('id', ''),
                    'title': event.get('summary', 'Untitled'),
                    'start': start_local.strftime('%Y-%m-%dT%H:%M:%S'),
                    'end': end_local.strftime('%Y-%m-%dT%H:%M:%S') if end_local else None,
                    'start_formatted': start_local.strftime('%I:%M %p').lstrip('0'),
                    'location': event.get('location'),
                    'description': event.get('description', ''),
                    'attendees': attendees,
                    'meet_link': meet_link,
                    'minutes_until': minutes_until,
                    'is_current': is_current
                }
                
                if is_current:
                    current_meetings.append(evt_data)
                else:
                    processed.append(evt_data)
            
            future_events = [e for e in processed if e['minutes_until'] >= -5][:limit]
            
            return {
                "events": future_events,
                "in_meeting": in_meeting,
                "current_meetings": current_meetings,
                # Keep current_meeting for backward compatibility (first one)
                "current_meeting": current_meetings[0] if current_meetings else None
            }
            
        except Exception as e:
            error_str = str(e).lower()
            # Check for auth-related errors
            if "401" in error_str or "invalid_grant" in error_str or "token" in error_str or "refresh" in error_str:
                logger.error(f"[Calendar] Auth error: {e}")
                return {"error": "not_authenticated", "detail": str(e)}
            logger.error(f"[Calendar] Error: {e}")
            return {"error": str(e)}
    
    # =========================================================================
    # Hub/Prep Handlers
    # =========================================================================
    
    def handle_prep_week(self):
        """Get meetings for the next 7 days."""
        try:
            calendar_data = self.get_upcoming_events_google(minutes_ahead=10080, limit=200)
            events = calendar_data.get('events', [])
            
            by_date = {}
            for evt in events:
                start = evt.get('start', '')
                date_str = start.split('T')[0] if 'T' in start else start[:10]
                if date_str:
                    if date_str not in by_date:
                        by_date[date_str] = []
                    by_date[date_str].append(evt)
            
            from datetime import date
            today = date.today()
            days = []
            for i in range(7):
                d = today + timedelta(days=i)
                date_str = d.isoformat()
                day_meetings = by_date.get(date_str, [])
                days.append({
                    'date': date_str,
                    'day_name': 'Today' if i == 0 else d.strftime('%a'),
                    'day_short': d.strftime('%d'),
                    'meeting_count': len(day_meetings),
                    'meetings': day_meetings
                })
            
            self.send_json({'days': days, 'total_meetings': len(events)})
        except Exception as e:
            self.send_json({"error": str(e)})
    
    def handle_prep_meeting(self, params):
        """Get meeting info with support for multiple meetings."""
        try:
            index = int(params.get("index", ["0"])[0])
            date_filter = params.get("date", [None])[0]
            
            calendar_data = self.get_upcoming_events_google(minutes_ahead=10080, limit=200)
            events = calendar_data.get('events', [])
            
            if date_filter:
                events = [e for e in events if e.get('start', '').startswith(date_filter)]
            
            if not events:
                self.send_json({
                    "meeting": None, "all_meetings": [], "total": 0, "index": 0,
                    "date": date_filter, "message": "No meetings" + (f" on {date_filter}" if date_filter else "")
                })
                return
            
            index = max(0, min(index, len(events) - 1))
            selected_meeting = events[index]
            attendees = selected_meeting.get('attendees', [])
            attendee_names = [a.get('name', a.get('email', '')) for a in attendees]
            
            self.send_json({
                "meeting": selected_meeting,
                "attendees_str": ', '.join(attendee_names[:5]),
                "all_meetings": events,
                "total": len(events),
                "index": index,
                "date": date_filter
            })
        except Exception as e:
            self.send_json({"error": str(e)})
    
    def handle_prep_all(self, params):
        """Return all cached prep data for a meeting (batch endpoint)."""
        meeting_id = params.get("meeting_id", [None])[0]
        
        if not meeting_id:
            self.send_json({"error": "meeting_id required"})
            return
        
        sources = ['jira', 'confluence', 'drive', 'slack', 'gmail', 'summary']
        result = {'all_cached': True}
        
        for source in sources:
            if has_cached_data(meeting_id, source):
                cached = get_cached_data(meeting_id, source)
                # Summary might be stored as dict with 'summary' key - extract string
                if source == 'summary' and isinstance(cached, dict):
                    result[source] = cached.get('summary', '') or None
                else:
                    result[source] = cached or []
            else:
                result[source] = None
                result['all_cached'] = False
        
        self.send_json(result)
    
    def handle_prep_source(self, path, params):
        """Handle prep data requests for specific sources."""
        # Extract source from path: /hub/prep/jira -> jira
        source = path.split('/')[-1]
        valid_sources = ['jira', 'confluence', 'slack', 'gmail', 'drive', 'summary']
        
        if source not in valid_sources:
            self.send_json({"error": f"Unknown source: {source}"})
            return
        
        meeting_id = params.get("meeting_id", [None])[0]
        refresh = params.get("refresh", ["0"])[0] == "1"
        
        if not meeting_id:
            self.send_json({"error": "meeting_id required"})
            return
        
        # Check cache first (unless refresh requested)
        if not refresh and has_cached_data(meeting_id, source):
            cached = get_cached_data(meeting_id, source)
            # Return array directly for sources, or string for summary
            if source == 'summary':
                self.send_json(cached or '')
            else:
                self.send_json(cached or [])
            return
        
        # Get meeting info for context
        meeting = get_meeting_by_id(meeting_id)
        
        if meeting:
            # Extract and store meeting info for future refreshes
            title = meeting.get('title', '')
            attendees = meeting.get('attendees', [])
            attendees_str = ', '.join([a.get('name', a.get('email', '')) for a in attendees[:5]])
            attendee_emails = [a.get('email', '') for a in attendees[:5]]
            description = meeting.get('description', '')[:500]
            # Store for future use (when meeting is no longer in calendar view)
            set_meeting_info(meeting_id, title, attendees_str, attendee_emails, description)
        else:
            # Try to get from cached meeting info
            cached_info = get_meeting_info(meeting_id)
            if cached_info:
                title = cached_info.get('title', '')
                # Handle both old format (attendees_str) and new format (attendees)
                attendees_str = cached_info.get('attendees') or cached_info.get('attendees_str', '')
                attendee_emails = cached_info.get('attendee_emails', [])
                description = cached_info.get('description', '')
            else:
                self.send_json({"error": "Meeting not found", "items": []})
                return
        
        if source == 'summary':
            result = call_cli_for_meeting_summary(title, attendees_str, attendee_emails, description)
            summary_text = result.get('summary', '') if isinstance(result, dict) else result
            status = result.get('status', 'success') if isinstance(result, dict) else 'success'
            # Cache and return in expected format: {"summary": "...", "status": "..."}
            response = {"summary": summary_text or '', "status": status if summary_text else 'empty'}
            set_meeting_cache(meeting_id, source, response)
            self.send_json(response)
        else:
            items = call_cli_for_source(source, title, attendees_str, description, attendee_emails=attendee_emails)
            # Cache the result
            set_meeting_cache(meeting_id, source, items if items else [])
            # Return array directly (frontend expects array, not {items: []})
            self.send_json(items or [])
    
    def handle_meeting_summary(self, params):
        """Generate AI meeting summary."""
        meeting_id = params.get("meeting_id", [None])[0]
        
        if not meeting_id:
            self.send_json({"error": "meeting_id required"})
            return
        
        # Check cache
        if has_cached_data(meeting_id, 'summary'):
            cached = get_cached_data(meeting_id, 'summary')
            self.send_json({"summary": cached, "cached": True})
            return
        
        meeting = get_meeting_by_id(meeting_id)
        if not meeting:
            self.send_json({"error": "Meeting not found"})
            return
        
        title = meeting.get('title', '')
        attendees = meeting.get('attendees', [])
        attendees_str = ', '.join([a.get('name', a.get('email', '')) for a in attendees[:5]])
        attendee_emails = [a.get('email', '') for a in attendees[:5]]
        description = meeting.get('description', '')[:500]
        
        result = call_cli_for_meeting_summary(title, attendees_str, attendee_emails, description)
        summary = result.get('summary', '') if isinstance(result, dict) else str(result)
        status = result.get('status', 'success') if isinstance(result, dict) else 'success'
        
        # Cache in consistent format
        response = {"summary": summary or '', "status": status if summary else 'empty'}
        set_meeting_cache(meeting_id, 'summary', response)
        
        self.send_json({"summary": summary, "status": status, "cached": False})
    
    def handle_hub_status(self):
        """Get hub/prefetch status."""
        status = get_prefetch_status()
        auth_status = check_services_auth()
        
        # Actually test calendar credentials by trying to get the service
        calendar_configured = os.path.exists(CREDENTIALS_PATH)
        calendar_authenticated = False
        calendar_error = None
        
        if os.path.exists(TOKEN_PATH):
            try:
                service, error = self.get_google_calendar_service()
                if service:
                    calendar_authenticated = True
                else:
                    calendar_error = error or "auth_failed"
            except Exception as e:
                calendar_error = str(e)
        
        # Check Drive MCP token
        drive_token_path = os.path.join(CONFIG_DIR, "google_drive_token.json")
        drive_configured = os.path.exists(CREDENTIALS_PATH)  # Uses same OAuth client as calendar
        drive_authenticated = os.path.exists(drive_token_path)
        
        # Format auth status for frontend (expects objects with .configured/.authenticated properties)
        self.send_json({
            **status,
            "auth": auth_status,
            # Frontend expects these at top level with {configured: bool, authenticated: bool} format
            "slack": {"configured": auth_status.get("slack", False), "authenticated": auth_status.get("slack", False)},
            "atlassian": {"configured": auth_status.get("atlassian", False), "authenticated": auth_status.get("atlassian", False)},
            "gmail": {"configured": auth_status.get("gmail", False), "authenticated": auth_status.get("gmail", False)},
            "calendar": {"configured": calendar_configured, 
                        "authenticated": calendar_authenticated,
                        "error": calendar_error},
            "drive": {"configured": drive_configured, "authenticated": drive_authenticated},
        })
    
    def handle_setup_page(self):
        """Serve the setup page."""
        setup_path = os.path.join(CONFIG_DIR, 'setup.html')
        if os.path.exists(setup_path):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            with open(setup_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_json({"error": "Setup page not found"})
    
    def handle_setup_slack(self, data):
        """Save Slack tokens to MCP config."""
        xoxc = data.get('xoxc', '').strip()
        xoxd = data.get('xoxd', '').strip()
        
        if not xoxc or not xoxd:
            self.send_json({"success": False, "error": "Both tokens required"})
            return
        
        if not xoxc.startswith('xoxc-') or not xoxd.startswith('xoxd-'):
            self.send_json({"success": False, "error": "Invalid token format"})
            return
        
        try:
            # Load existing MCP config
            mcp_config_path = os.path.join(CONFIG_DIR, '.devsai.json')
            config = {}
            if os.path.exists(mcp_config_path):
                with open(mcp_config_path, 'r') as f:
                    config = json.load(f)
            
            # Ensure mcpServers exists
            if 'mcpServers' not in config:
                config['mcpServers'] = {}
            
            # Add/update Slack config
            config['mcpServers']['slack'] = {
                "command": "npx",
                "args": ["-y", "slack-mcp-server"],
                "env": {
                    "SLACK_MCP_XOXC_TOKEN": xoxc,
                    "SLACK_MCP_XOXD_TOKEN": xoxd
                }
            }
            
            # Save config
            with open(mcp_config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info("[Setup] Slack tokens saved to MCP config")
            
            # Test the connection by trying to load the tokens
            from lib.slack import slack_api_call
            result = slack_api_call('auth.test', xoxc_token=xoxc, xoxd_token=xoxd)
            
            if result and result.get('ok'):
                self.send_json({"success": True, "team": result.get('team', 'Unknown')})
            else:
                self.send_json({"success": True, "warning": "Tokens saved but could not verify"})
                
        except Exception as e:
            logger.error(f"[Setup] Slack setup error: {e}")
            self.send_json({"success": False, "error": str(e)})
    
    def handle_installer_page(self):
        """Serve the installer page."""
        installer_path = os.path.join(CONFIG_DIR, 'installer.html')
        # Also check in the script directory for development
        if not os.path.exists(installer_path):
            installer_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'installer.html')
        
        if os.path.exists(installer_path):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            with open(installer_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_json({"error": "Installer page not found"})
    
    def handle_installer_check(self, params):
        """Check if a command/dependency is available."""
        import subprocess
        
        cmd = params.get('cmd', [''])[0]
        if not cmd:
            self.send_json({"ok": False, "error": "No command specified"})
            return
        
        # Add common Homebrew and system paths that may not be in LaunchAgent environment
        env = os.environ.copy()
        extra_paths = [
            '/opt/homebrew/bin',
            '/opt/homebrew/opt/node/bin',
            '/usr/local/bin',
            '/usr/bin',
            '/bin'
        ]
        current_path = env.get('PATH', '')
        env['PATH'] = ':'.join(extra_paths) + ':' + current_path
        
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            if result.returncode == 0:
                version = result.stdout.strip() or result.stderr.strip()
                self.send_json({"ok": True, "version": version})
            else:
                self.send_json({"ok": False, "error": "Command failed"})
        except FileNotFoundError:
            self.send_json({"ok": False, "error": "Not installed"})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)})
    
    def handle_installer_install(self, data):
        """Run the installation process."""
        import subprocess
        
        try:
            # Installation is already done if this endpoint is reachable
            # Just return success since the server is running
            self.send_json({
                "success": True,
                "message": "BriefDesk is already installed and running"
            })
        except Exception as e:
            logger.error(f"[Installer] Install error: {e}")
            self.send_json({"success": False, "error": str(e)})
    
    def handle_installer_check_fda(self):
        """Check if Full Disk Access is granted for Python and Node."""
        import sqlite3
        import sys
        
        python_fda = False
        node_fda = 'not_installed'
        # Resolve symlinks to get the actual binary path for FDA
        python_path = os.path.realpath(sys.executable)
        
        # Test Python FDA by trying to read Safari history
        try:
            safari_history = os.path.expanduser("~/Library/Safari/History.db")
            if os.path.exists(safari_history):
                conn = sqlite3.connect(f"file:{safari_history}?mode=ro", uri=True)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM history_items LIMIT 1")
                cursor.fetchone()
                conn.close()
                python_fda = True
        except (sqlite3.OperationalError, PermissionError) as e:
            logger.info(f"[FDA Check] Python FDA not granted: {e}")
            python_fda = False
        except Exception as e:
            logger.info(f"[FDA Check] Python FDA check error: {e}")
            python_fda = False
        
        # Test Node FDA by checking if the devsai node binary exists
        # (actual FDA testing would require running node to read a protected file)
        devsai_node = os.path.expanduser("~/.local/share/devsai/node")
        if os.path.exists(devsai_node):
            # For now, just check if it exists - actual FDA would need to run it
            # We'll assume if Python has FDA and node exists, user will grant it
            node_fda = True  # Optimistic - they'll need to add it manually
        
        self.send_json({
            "python_fda": python_fda,
            "node_fda": node_fda,
            "python_path": python_path
        })

    # ==========================================================================
    # OAuth Endpoints
    # ==========================================================================

    def handle_oauth_google_start(self):
        """Start Google OAuth flow - returns URL to redirect user to."""
        if not has_oauth_credentials():
            self.send_json({
                "success": False,
                "error": "No OAuth credentials configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables."
            })
            return

        auth_url, state = get_oauth_url()
        if auth_url:
            self.send_json({
                "success": True,
                "auth_url": auth_url,
                "state": state
            })
        else:
            self.send_json({
                "success": False,
                "error": state  # state contains error message on failure
            })

    def handle_oauth_callback(self, params):
        """Handle OAuth callback from Google."""
        code = params.get('code', [None])[0]
        error = params.get('error', [None])[0]

        if error:
            # Redirect to installer with error
            self.send_response(302)
            self.send_header('Location', f'/installer.html?oauth_error={error}')
            self.end_headers()
            return

        if not code:
            self.send_response(302)
            self.send_header('Location', '/installer.html?oauth_error=no_code')
            self.end_headers()
            return

        success, message = handle_oauth_callback(code)

        if success:
            # Redirect to installer with success
            self.send_response(302)
            self.send_header('Location', '/installer.html?oauth_success=google')
            self.end_headers()
        else:
            self.send_response(302)
            self.send_header('Location', f'/installer.html?oauth_error={message}')
            self.end_headers()

    def handle_oauth_google_status(self):
        """Check Google OAuth status."""
        self.send_json({
            "has_credentials": has_oauth_credentials(),
            "is_authenticated": is_google_authenticated(),
            "token_exists": os.path.exists(TOKEN_PATH)
        })

    def handle_oauth_google_disconnect(self):
        """Disconnect Google account."""
        success = disconnect_google()
        self.send_json({
            "success": success,
            "message": "Disconnected from Google" if success else "Failed to disconnect"
        })

    def handle_service_health(self):
        """Check health of all BriefDesk services."""
        import socket
        import urllib.request
        
        services = []
        
        # Static server (port 8765)
        static_ok = False
        static_error = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', 8765))
            static_ok = result == 0
            sock.close()
        except Exception as e:
            static_error = str(e)
        services.append({
            'name': 'Static Server',
            'port': 8765,
            'status': 'ok' if static_ok else 'error',
            'error': static_error,
            'description': 'Serves HTML/CSS/JS'
        })
        
        # API server (port 18765) - this is us, always OK
        services.append({
            'name': 'API Server',
            'port': 18765,
            'status': 'ok',
            'error': None,
            'description': 'Calendar, search, meeting prep'
        })
        
        # Search service (port 19765)
        search_ok = False
        search_error = None
        search_details = {}
        try:
            req = urllib.request.Request('http://127.0.0.1:19765/health', method='GET')
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                search_ok = data.get('status') == 'ok'
                search_details = data
                if not search_ok:
                    search_error = data.get('error', 'Unknown error')
        except urllib.error.URLError as e:
            search_error = 'Not running'
        except Exception as e:
            search_error = str(e)
        
        # Get MCP server count and GDrive MCP status if available
        mcp_servers = None
        gdrive_mcp = None
        if search_ok:
            try:
                req = urllib.request.Request('http://127.0.0.1:19765/status', method='GET')
                with urllib.request.urlopen(req, timeout=3) as resp:
                    status_data = json.loads(resp.read().decode())
                    servers = status_data.get('servers', [])
                    connected = [s for s in servers if s.get('status') == 'connected']
                    failed = [s for s in servers if s.get('status') != 'connected']
                    # Include ALL servers (connected and failed) with their status and error
                    all_servers = []
                    for s in servers:
                        server_info = {
                            'name': s.get('name'),
                            'tools': s.get('toolCount', 0),
                            'status': s.get('status', 'unknown'),
                            'error': s.get('error')
                        }
                        all_servers.append(server_info)
                    mcp_servers = {
                        'connected': len(connected),
                        'total': len(servers),
                        'servers': all_servers
                    }
                    # Get GDrive MCP status
                    gdrive_mcp = status_data.get('gdriveMcp', {})
            except:
                pass
        
        services.append({
            'name': 'Search Service',
            'port': 19765,
            'status': 'ok' if search_ok else 'error',
            'error': search_error,
            'description': 'AI queries, MCP connections',
            'mcp': mcp_servers,
            'gdriveMcp': gdrive_mcp
        })
        
        self.send_json({
            'services': services,
            'timestamp': datetime.now().isoformat()
        })
    
    def handle_prefetch_status(self):
        """Get detailed prefetch status for the status tab."""
        status = get_prefetch_status()
        
        # Add mode information that frontend expects
        is_night = is_night_hours()
        force_aggressive = status.get('force_aggressive', False)
        
        if force_aggressive:
            mode = 'aggressive'
            mode_reason = 'User forced'
        elif is_night:
            mode = 'aggressive'
            mode_reason = 'Night hours (10pm-6am)'
        else:
            mode = 'normal'
            mode_reason = 'Day hours'
        
        day_mode_note = None
        if not is_night and not force_aggressive:
            day_mode_note = 'Prefetch is slower during day hours to save resources. Click Force Refresh to override.'
        
        self.send_json({
            **status,
            "mode": mode,
            "mode_reason": mode_reason,
            "force_aggressive": force_aggressive,
            "day_mode_note": day_mode_note,
        })
    
    def handle_prefetch_control(self, params):
        """Control prefetch behavior."""
        action = params.get("action", [None])[0]
        
        if action in ('force', 'aggressive', 'normal'):
            result = set_force_aggressive_prefetch(action)
            self.send_json({"success": True, "action": action, "result": result})
        else:
            self.send_json({"error": "Invalid action. Use 'force', 'aggressive', or 'normal'"})
    
    def handle_mcp_reauth(self, params):
        """Spawn re-authentication process for an MCP server via Terminal."""
        import subprocess
        
        mcp = params.get("mcp", [None])[0]
        
        # Use osascript to open Terminal with the auth command
        # This allows the OAuth callback to work properly
        def run_in_terminal(cmd, title="MCP Authentication"):
            applescript = f'''
            tell application "Terminal"
                activate
                do script "{cmd}"
            end tell
            '''
            subprocess.Popen(["osascript", "-e", applescript])
        
        if mcp == "atlassian":
            cmd = "npx -y mcp-remote https://mcp.atlassian.com/v1/sse"
            try:
                run_in_terminal(cmd)
                self.send_json({
                    "success": True, 
                    "mcp": mcp,
                    "message": "Terminal opened - sign in with Atlassian in your browser, then close Terminal when done"
                })
            except Exception as e:
                self.send_json({"error": f"Failed to open Terminal: {str(e)}"})
        
        elif mcp == "gmail":
            cmd = "npx -y @monsoft/mcp-gmail auth"
            try:
                run_in_terminal(cmd)
                self.send_json({
                    "success": True,
                    "mcp": mcp,
                    "message": "Terminal opened - sign in with Google in your browser, then close Terminal when done"
                })
            except Exception as e:
                self.send_json({"error": f"Failed to open Terminal: {str(e)}"})
        
        elif mcp == "drive":
            gdrive_mcp_path = os.path.join(CONFIG_DIR, "gdrive-mcp")
            cmd = f"cd {gdrive_mcp_path} && npm run auth"
            try:
                run_in_terminal(cmd)
                self.send_json({
                    "success": True,
                    "mcp": mcp,
                    "message": "Terminal opened - sign in with Google in your browser, then close Terminal when done"
                })
            except Exception as e:
                self.send_json({"error": f"Failed to open Terminal: {str(e)}"})
        
        else:
            self.send_json({"error": f"Unknown MCP: {mcp}. Supported: atlassian, gmail, drive"})
    
    def handle_restart_search_service(self):
        """Restart the search-service to pick up new credentials."""
        import subprocess
        import os
        
        try:
            # Use launchctl to restart the search-service
            user_id = os.getuid()
            cmd = ["launchctl", "kickstart", "-k", f"gui/{user_id}/com.briefdesk.search-service"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                self.send_json({
                    "success": True,
                    "message": "Search service restarting..."
                })
            else:
                self.send_json({
                    "error": f"Failed to restart: {result.stderr or result.stdout}"
                })
        except subprocess.TimeoutExpired:
            self.send_json({"success": True, "message": "Restart initiated"})
        except Exception as e:
            self.send_json({"error": f"Failed to restart: {str(e)}"})
    
    def handle_get_prompts(self):
        """Get all prompts with current values and defaults."""
        self.send_json({"prompts": get_all_prompts()})
    
    def handle_set_prompt(self, data):
        """Set a custom prompt for a source."""
        source = data.get('source')
        prompt = data.get('prompt')
        reset = data.get('reset', False)
        
        if not source:
            self.send_json({"error": "source required"})
            return
        
        if reset:
            reset_prompt(source)
            self.send_json({"success": True, "action": "reset"})
        else:
            set_custom_prompt(source, prompt)
            self.send_json({"success": True, "action": "set"})
    
    def handle_batch(self, params):
        """Handle batch data request for multiple sources."""
        meeting_id = params.get("meeting_id", [None])[0]
        sources = params.get("sources", ["jira,confluence,slack,drive,gmail"])[0].split(',')
        
        if not meeting_id:
            self.send_json({"error": "meeting_id required"})
            return
        
        result = {}
        for source in sources:
            source = source.strip()
            if has_cached_data(meeting_id, source):
                result[source] = {"items": get_cached_data(meeting_id, source) or [], "cached": True}
            else:
                result[source] = {"items": [], "cached": False, "status": "not_cached"}
        
        self.send_json(result)
    
    # =========================================================================
    # Slack Handlers
    # =========================================================================
    
    def handle_slack_conversations(self, params):
        """Get Slack conversations."""
        limit = int(params.get("limit", ["20"])[0])
        unread_only = params.get("unread_only", ["0"])[0] == "1"
        
        conversations = slack_get_conversations_fast(limit=limit, unread_only=unread_only)
        self.send_json(conversations)
    
    def handle_slack_history(self, params):
        """Get Slack conversation history."""
        channel_id = params.get("channel_id", [None])[0]
        limit = int(params.get("limit", ["30"])[0])
        
        if not channel_id:
            self.send_json({"error": "channel_id required"})
            return
        
        messages = slack_get_conversation_history_direct(channel_id, limit=limit)
        self.send_json(messages)
    
    def handle_slack_threads(self, params):
        """Get Slack threads."""
        limit = int(params.get("limit", ["20"])[0])
        threads = slack_get_threads(limit=limit)
        self.send_json(threads)
    
    def handle_slack_thread(self, params):
        """Get Slack thread replies."""
        channel_id = params.get("channel_id", [None])[0]
        thread_ts = params.get("thread_ts", [None])[0]
        limit = int(params.get("limit", ["50"])[0])
        
        if not channel_id or not thread_ts:
            self.send_json({"error": "channel_id and thread_ts required"})
            return
        
        replies = slack_get_thread_replies(channel_id, thread_ts, limit=limit)
        self.send_json(replies)
    
    def handle_slack_send(self, data):
        """Send Slack message."""
        channel_id = data.get('channel_id')
        text = data.get('text')
        thread_ts = data.get('thread_ts')
        
        if not channel_id or not text:
            self.send_json({"error": "channel_id and text required"})
            return
        
        result = slack_send_message_direct(channel_id, text, thread_ts)
        self.send_json(result)
    
    def handle_slack_mark_read(self, params):
        """Mark Slack conversation as read."""
        channel_id = params.get("channel_id", [None])[0]
        ts = params.get("ts", [None])[0]
        
        if not channel_id or not ts:
            self.send_json({"error": "channel_id and ts required"})
            return
        
        result = slack_mark_conversation_read(channel_id, ts)
        self.send_json(result)
    
    # =========================================================================
    # Debug Handler
    # =========================================================================
    
    def handle_debug(self):
        """Return debug information."""
        info = {
            "safari_history_exists": os.path.exists(SAFARI_HISTORY),
            "safari_bookmarks_exists": os.path.exists(SAFARI_BOOKMARKS),
            "chrome_history_exists": os.path.exists(CHROME_HISTORY),
            "chrome_bookmarks_exists": os.path.exists(CHROME_BOOKMARKS),
            "helium_history_exists": os.path.exists(HELIUM_HISTORY),
            "helium_bookmarks_exists": os.path.exists(HELIUM_BOOKMARKS),
            "dia_history_exists": os.path.exists(DIA_HISTORY),
            "dia_bookmarks_exists": os.path.exists(DIA_BOOKMARKS),
            "google_api_available": GOOGLE_API_AVAILABLE,
            "token_exists": os.path.exists(TOKEN_PATH),
            "credentials_exist": os.path.exists(CREDENTIALS_PATH),
        }
        
        for name, path in [
            ("safari_history", SAFARI_HISTORY),
            ("chrome_history", CHROME_HISTORY),
            ("helium_history", HELIUM_HISTORY),
            ("dia_history", DIA_HISTORY)
        ]:
            try:
                tmp = copy_db(path)
                if tmp:
                    info[f"{name}_readable"] = True
                    cleanup_db(tmp)
                else:
                    info[f"{name}_readable"] = False
            except Exception as e:
                info[f"{name}_readable"] = str(e)
        
        self.send_json(info)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads for parallel processing."""
    daemon_threads = True


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--auth":
        authenticate_google()
        return
    
    logger.info(f"Starting BriefDesk server, logging to {LOG_FILE}")
    
    # Configure prefetch module with CLI functions
    configure_cli_functions(call_cli_for_source, call_cli_for_meeting_summary)
    
    # Start server
    server = ThreadedHTTPServer(("127.0.0.1", 18765), SearchHandler)
    logger.info("BriefDesk server running on http://127.0.0.1:18765 (multi-threaded)")
    
    # Start background prefetch thread
    start_prefetch_thread()
    print("Background meeting prep prefetch enabled (7-day lookahead)")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop_prefetch_thread()
        server.shutdown()
if __name__ == "__main__":
    main()