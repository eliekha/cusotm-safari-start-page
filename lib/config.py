"""Configuration constants, paths, and logging setup for BriefDesk."""

import os
import sys
import glob
import logging

# =============================================================================
# Logging Setup
# =============================================================================

LOG_FILE = "/tmp/briefdesk-server.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# Paths
# =============================================================================

CONFIG_DIR = os.path.expanduser("~/.local/share/briefdesk")
TOKEN_PATH = os.path.join(CONFIG_DIR, "google_token.pickle")
CREDENTIALS_PATH = os.path.join(CONFIG_DIR, "google_credentials.json")
MCP_CONFIG_PATH = os.path.expanduser("~/.devsai/mcp.json")
CACHE_DIR = CONFIG_DIR
PREP_CACHE_FILE = os.path.join(CACHE_DIR, "prep_cache.json")
PROMPTS_FILE = os.path.join(CACHE_DIR, "custom_prompts.json")
USER_CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# Load user configuration
def load_user_config():
    """Load user configuration from config.json."""
    import json
    if os.path.exists(USER_CONFIG_FILE):
        try:
            with open(USER_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

USER_CONFIG = load_user_config()

# =============================================================================
# Hub Model Configuration
# =============================================================================

_hub_model = USER_CONFIG.get('hubModel', 'anthropic-claude-4-5-haiku')

def get_hub_model():
    """Get the currently configured AI model for hub operations."""
    return _hub_model

def set_hub_model(model):
    """Set the AI model for hub operations and persist to config."""
    global _hub_model, USER_CONFIG
    import json
    
    _hub_model = model
    USER_CONFIG['hubModel'] = model
    
    try:
        with open(USER_CONFIG_FILE, 'w') as f:
            json.dump(USER_CONFIG, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save hub model config: {e}")

# Google Drive path from config or auto-detect
GOOGLE_DRIVE_BASE = USER_CONFIG.get('google_drive_path', '')
if not GOOGLE_DRIVE_BASE:
    # Auto-detect if not configured
    gdrive_folders = glob.glob(os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*"))
    if gdrive_folders:
        GOOGLE_DRIVE_BASE = gdrive_folders[0]

# Google Drive paths for searching
GOOGLE_DRIVE_PATHS = []
if GOOGLE_DRIVE_BASE:
    my_drive = os.path.join(GOOGLE_DRIVE_BASE, "My Drive")
    shared_drives = os.path.join(GOOGLE_DRIVE_BASE, "Shared drives")
    if os.path.exists(my_drive):
        GOOGLE_DRIVE_PATHS.append(my_drive)
    if os.path.exists(shared_drives):
        GOOGLE_DRIVE_PATHS.append(shared_drives)

# Browser database paths
SAFARI_HISTORY = os.path.expanduser("~/Library/Safari/History.db")
SAFARI_BOOKMARKS = os.path.expanduser("~/Library/Safari/Bookmarks.plist")
CHROME_HISTORY = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/History")
CHROME_BOOKMARKS = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Bookmarks")
HELIUM_HISTORY = os.path.expanduser("~/Library/Application Support/net.imput.helium/Default/History")
HELIUM_BOOKMARKS = os.path.expanduser("~/Library/Application Support/net.imput.helium/Default/Bookmarks")
DIA_HISTORY = os.path.expanduser("~/Library/Application Support/Dia/User Data/Default/History")
DIA_BOOKMARKS = os.path.expanduser("~/Library/Application Support/Dia/User Data/Default/Bookmarks")

# =============================================================================
# Google API
# =============================================================================

# OAuth scopes for Google services
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
ALL_SCOPES = SCOPES + DRIVE_SCOPES + GMAIL_SCOPES

# Embedded OAuth credentials (loaded from environment or defaults)
# These are safe to embed for installed/desktop apps - security comes from user consent
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

def get_oauth_credentials_config():
    """Get OAuth credentials config, preferring user's file over embedded."""
    # If user has their own credentials file, use that (advanced users)
    if os.path.exists(CREDENTIALS_PATH):
        try:
            import json
            with open(CREDENTIALS_PATH, 'r') as f:
                data = json.load(f)
                # Handle both formats: {"installed": {...}} and {"web": {...}}
                if 'installed' in data:
                    return data['installed']
                elif 'web' in data:
                    return data['web']
                return data
        except Exception as e:
            logger.error(f"Error reading credentials file: {e}")

    # Otherwise use embedded credentials (if available)
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        return {
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': ['http://127.0.0.1:8765/oauth/callback']
        }

    return None

# Try to import Google API libraries
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    Request = None
    Credentials = None
    InstalledAppFlow = None
    build = None

# =============================================================================
# Cache TTLs
# =============================================================================

CACHE_TTL = 30  # Calendar cache TTL in seconds
HUB_CACHE_TTL = 60  # Hub data cache TTL in seconds
PREP_CACHE_TTL = 1800  # Meeting prep cache TTL (30 minutes)
SUMMARY_CACHE_TTL = 2700  # AI summary cache TTL (45 minutes)
SLACK_USERS_CACHE_TTL = 300  # Slack users cache TTL (5 minutes)
PREFETCH_INTERVAL = 600  # Prefetch loop interval (10 minutes)
MAX_ACTIVITY_LOG = 50  # Max prefetch activity log entries

# =============================================================================
# Slack Configuration
# =============================================================================

# Get workspace from environment or use default
SLACK_WORKSPACE = os.environ.get('SLACK_WORKSPACE', 'appdirect')

# =============================================================================
# Default Prompts
# =============================================================================

DEFAULT_PROMPTS = {
    'jira': """Search Jira for tickets related to this meeting. Meeting context:
Title: {title}
Attendees: {attendees}
Description: {description}

IMPORTANT: 
1. FIRST call "Get Accessible Atlassian Resources" to get the cloudId
2. THEN use that cloudId with "Search Jira issues using JQL" 
3. NEVER ask the user for cloudId - discover it automatically

Find up to {limit} relevant Jira tickets. Return results as a JSON array with objects containing:
- title: ticket key and summary (e.g., "PROJ-123: Fix login bug")
- url: full Jira URL
- type: "jira"

Focus on tickets that are:
1. Mentioned in the meeting title/description
2. Recently updated by attendees
3. Related to topics being discussed""",

    'confluence': """Search Confluence for pages related to this meeting. Meeting context:
Title: {title}
Attendees: {attendees}
Description: {description}

IMPORTANT:
1. FIRST call "Get Accessible Atlassian Resources" to get the cloudId
2. THEN use that cloudId with "Search Confluence Using CQL"
3. NEVER ask the user for cloudId - discover it automatically

Find up to {limit} relevant Confluence pages. Return results as a JSON array with objects containing:
- title: page title
- url: full Confluence URL
- type: "confluence"
- space: space name (if available)

Focus on pages that are:
1. Related to meeting topics
2. Recently edited by attendees
3. Referenced in meeting description""",

    'slack': """Search Slack for messages related to this meeting. Meeting context:
Title: {title}
Attendees: {attendees}
Description: {description}

CRITICAL: This is a READ-ONLY operation. NEVER send, post, or create any Slack messages. Only search and read existing messages.

IMPORTANT - To find 1:1 DMs with attendees:
1. FIRST use channels_list with channel_types: "im" to find DM channels with attendees
2. THEN use conversations_history with that channel_id to get recent messages
3. ALSO use conversations_search_messages for broader channel searches

Search across ALL Slack conversations including:
- 1:1 Direct messages with attendees (use channels_list + conversations_history)
- Group DMs
- Public and private channels (use conversations_search_messages)

Find up to {limit} relevant Slack messages or threads. Return results as a JSON array with objects containing:
- title: message preview or thread topic
- url: Slack message permalink
- type: "slack"
- channel: channel name or "DM with [name]" for direct messages

Prioritize:
1. 1:1 DMs with meeting attendees (ALWAYS check these first)
2. Group DMs involving attendees
3. Channel messages from/to attendees
4. Recent discussions about the subject""",

    'gmail': """Search Gmail for emails related to this meeting. Meeting context:
Title: {title}
Attendees: {attendees}
Attendee emails: {emails}
Description: {description}

CRITICAL: This is a READ-ONLY operation. NEVER send, draft, compose, or create any emails. Only search and read existing emails.

Find up to {limit} relevant email threads. Return results as a JSON array with objects containing:
- title: email subject
- url: Gmail URL (or empty string)
- type: "gmail"
- from: sender name/email

Focus on emails that are:
1. From/to meeting attendees
2. Related to meeting topics
3. Recent correspondence about the subject""",

    'drive': """Search Google Drive for files related to this meeting using find_files.
Meeting context:
Title: {title}
Attendees: {attendees}
Description: {description}

Search in: {drive_path}

Find up to {limit} relevant files (documents, spreadsheets, presentations, etc).
Return results as a JSON array with objects containing:
- title: file name
- url: full file path
- type: "drive"

Focus on files that match meeting topics, attendee names, or project keywords.""",

    'summary': """Generate a brief meeting prep for: {title}
Attendees: {attendees}
{description}

Search Slack, Jira, Confluence, and Gmail for relevant context, then create a prep brief.

CRITICAL RESTRICTIONS:
- NEVER send, draft, compose, or create any emails, messages, or communications
- NEVER modify, update, or change any data in any system
- This is a READ-ONLY operation - only search and read existing data

RULES:
- Be specific: include ticket numbers, document names, dates. Prioritize slack/gmail exchanges.
- Provide context on the meeting first.
- Be opinionated: provide your opinion on what should be covered in the call based on the data retrieved, particularly the slack/gmail exchanges.
- Skip sections with no relevant info
- No filler or generic statements
- Total length: under 200 words"""
}
