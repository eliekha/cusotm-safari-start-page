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

# Google Drive paths (auto-detect for any Google account)
GOOGLE_DRIVE_PATHS = [
    *[p for p in glob.glob(os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*/My Drive"))],
    *[p for p in glob.glob(os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*/Shared drives"))]
]

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

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

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

Find up to {limit} relevant Slack messages or threads. Return results as a JSON array with objects containing:
- title: message preview or thread topic
- url: Slack message permalink
- type: "slack"
- channel: channel name

Focus on messages that are:
1. From or mentioning attendees
2. Related to meeting topics
3. Recent discussions about the subject""",

    'gmail': """Search Gmail for emails related to this meeting. Meeting context:
Title: {title}
Attendees: {attendees}
Attendee emails: {emails}
Description: {description}

Find up to {limit} relevant email threads. Return results as a JSON array with objects containing:
- title: email subject
- url: Gmail URL (or empty string)
- type: "gmail"
- from: sender name/email

Focus on emails that are:
1. From/to meeting attendees
2. Related to meeting topics
3. Recent correspondence about the subject""",

    'drive': """Search Google Drive for files related to this meeting. Meeting context:
Title: {title}
Attendees: {attendees}
Description: {description}

Find up to {limit} relevant files. Return results as a JSON array with objects containing:
- title: file name
- url: file path or Drive URL
- type: "drive"

Focus on files that are:
1. Related to meeting topics
2. Recently modified
3. Shared with attendees""",

    'summary': """Generate a meeting prep brief based on the following context. Meeting:
Title: {title}
Attendees: {attendees}
Description: {description}

Available context from various sources:
{context}

Create a concise meeting prep summary with:
1. **Key Context** - What this meeting is about based on the gathered information
2. **Recent Activity** - Summary of recent discussions, tickets, or documents
3. **Talking Points** - 2-3 suggested topics based on the context

If a source returns nothing relevant, skip it. Focus on providing actionable insights.

Return ONLY the formatted summary text, nothing else."""
}
