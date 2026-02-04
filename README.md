# BriefDesk

A beautiful, fast productivity hub with meeting prep, real-time history search, and Google Calendar integration.


## Features

### Core Features
- **Instant loading** - Static HTML served locally (~3ms load time)
- **Real-time history search** - Search Safari, Chrome, Helium, and Dia browser history as you type
- **Google Calendar** - Shows your next 3 meetings with join links (Google Meet, Zoom, Teams)
- **Smart search** - Multi-word queries, visit count ranking, URL detection
- **WAL support** - Reads browser write-ahead logs for truly real-time results
- **Customizable** - Edit name, quick links, background, and theme via settings gear
- **URL detection** - Type a URL and press Enter to navigate directly
- **Keyboard navigation** - Full keyboard support for search results
- **Dark/Light themes** - Choose UI style to match your background
- **Custom backgrounds** - Gradient presets, custom gradients, or upload an image
- **No external requests** - 100% local, privacy-focused

### Productivity Hub (Meeting Prep)
- **Week View** - Browse all meetings for the week with day tabs (Today, Mon, Tue, etc.)
- **Meeting Selector** - Click any meeting to load its prep data; navigate with arrows
- **AI Brief** - AI-generated meeting summary that reads and synthesizes content from all sources
- **Jira Integration** - Automatically finds related tickets based on meeting context
- **Confluence Integration** - Surfaces relevant wiki pages and documentation
- **Slack Integration** - Shows recent discussions related to meeting topics/attendees
- **Gmail Integration** - Finds relevant email threads with meeting participants
- **Google Drive** - Searches local Drive files for meeting-related documents
- **7-Day Prefetching** - Pre-caches data for up to 30 meetings across the entire week
- **Persistent Cache** - Prefetched data survives server restarts (stored in JSON)
- **Status Dashboard** - Monitor prefetch activity in Settings → Status tab
- **Collapsible Sections** - Each source can be collapsed; state persists across sessions
- **Model Selection** - Choose your preferred AI model (Settings → Hub → AI Model)

## Requirements

### Core (History Search + Calendar)
- macOS (tested on Sonoma/Sequoia)
- Safari
- Python 3 (included with Xcode Command Line Tools)

### Productivity Hub (Optional - for Meeting Prep features)
- Node.js 18+ (for MCP servers) - `brew install node`
- [devsai CLI](https://github.com/yourusername/devs-ai-cli) - AI-powered CLI for data source integrations
- MCP servers for each integration (Slack, Atlassian, Gmail)

## Installation

### Quick Install

```bash
git clone https://github.com/eliekha/BriefDesk.git
cd BriefDesk
./install.sh
```

Or with a one-liner:
```bash
curl -sL https://raw.githubusercontent.com/eliekha/BriefDesk/main/install.sh | bash
```

The install script will:
1. Copy files to `~/.local/share/briefdesk/`
2. Set up LaunchAgents to start servers on login
3. **Open an interactive setup wizard** in your browser

The setup wizard guides you through:
- Checking system requirements (Python, Node.js)
- Configuring integrations (Calendar, Slack, etc.)
- Verifying the installation

### Package Installer (.pkg)

For a clean installation without cloning the repo, use the macOS package installer:

1. Download the latest `.pkg` from the [Releases page](https://github.com/eliekha/BriefDesk/releases)
2. Double-click to run the installer
3. Follow the prompts
4. After installation, click "Open Setup Wizard" to complete configuration

The installer is **signed and notarized** by Apple, so it installs without Gatekeeper warnings (no "Open Anyway" required).

The installer automatically sets up LaunchAgents and copies all necessary files.

**DevsAI bundling (optional, for Meeting Prep / Productivity Hub):**
- Drop a devsai tarball into `./devsai/` (e.g., `devsai-latest.tgz`)
- The package build will pick the newest `devsai-*.tgz` and bundle it
- Postinstall installs it into `~/.local/share/devsai/` and exposes `~/.local/bin/devsai`

### After Installation

1. **Grant Full Disk Access** (required for Safari history and Google Drive):
   - System Settings → Privacy & Security → Full Disk Access
   - Add these binaries (use Cmd+Shift+G to paste paths):
   
   | Binary | Path | Purpose |
   |--------|------|---------|
   | Python | The path shown in the Setup Wizard (e.g., `/opt/homebrew/bin/python3`) | Safari history search |
   | Node | `~/.local/share/devsai/node` | Google Drive search (Hub) |
   
   **Note:** BriefDesk uses a Python wrapper script that calls your system Python. The Setup Wizard automatically detects and displays the correct Python path to add to Full Disk Access.

2. **Log in to DevsAI (for AI search / Meeting Prep)**:
   ```bash
   ~/.local/bin/devsai login
   ```
   This stores credentials in the DevsAI config file and enables the search service.

2. **Set your browser homepage:**
   - Safari → Settings → General → Homepage: `http://127.0.0.1:8765/start.html`
   - Or use the [New Tab Redirect](https://chrome.google.com/webstore/detail/new-tab-redirect/) extension for Chrome
   - The Setup Wizard (Step 6) can guide you through this for Chrome, Firefox, or Safari

### Reconfigure Later

You can always return to the setup wizard:
```
http://127.0.0.1:8765/installer.html
```

Or configure integrations from Settings → Status tab in the main app.

## Google Calendar Setup (Optional)

To show your upcoming meetings on the start page:

### 1. Create Google Cloud credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **Google Calendar API**: [Enable Calendar API →](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)
4. Go to **APIs & Services** → **OAuth consent screen**:
   - Choose **External** → Create
   - App name: "Calendar Widget", add your email
   - Save and Continue through all steps
5. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**:
   - Application type: **Desktop app**
   - Name: anything
   - Click **Create**
6. Click **Download JSON**

### 2. Install and authenticate

```bash
# Install Google API libraries
pip3 install google-auth-oauthlib google-api-python-client

# Save credentials file
cp ~/Downloads/client_secret_*.json ~/.local/share/briefdesk/google_credentials.json

# Authenticate (opens browser)
python3 ~/.local/share/briefdesk/search-server.py --auth
```

### 3. Rebuild the binary (if using standalone binary)

```bash
cd ~/.local/share/briefdesk
pip3 install pyinstaller
pyinstaller --onefile --name search-server --distpath . \
  --hidden-import=google.auth.transport.requests \
  --hidden-import=google.oauth2.credentials \
  --hidden-import=google_auth_oauthlib.flow \
  --hidden-import=googleapiclient.discovery \
  search-server.py
rm -rf build *.spec

# Restart server
launchctl kickstart -k gui/$(id -u)/com.briefdesk.search
```

### 4. Enable in settings

1. Open the start page
2. Click the gear icon (⚙️)
3. Check "Show next meeting"
4. Adjust the time window (default: 3 hours)
5. Save

Your calendar data is fetched directly from Google's API - no third-party servers involved.

## Using with Chromium Browsers (Chrome, Helium, Arc, etc.)

For Chromium-based browsers, use the **New Tab Redirect** extension:

1. Install [New Tab Redirect](https://chrome.google.com/webstore/detail/new-tab-redirect/) extension
2. Set the redirect URL to: `http://127.0.0.1:8765/start.html`
3. New tabs will now open your custom start page

This also gives you auto-focus on the search bar (which isn't possible without an extension).

## Productivity Hub (MCP Integrations)

The start page integrates with external services via **Model Context Protocol (MCP)** servers, turning it into a productivity hub for meeting preparation. When you have an upcoming meeting, it automatically searches all connected sources for relevant context.

### How It Works

1. **Search Service** (Node.js) keeps MCP connections warm for fast AI queries
2. **devsai library** is loaded once and reused - no cold start penalty
3. **MCP servers** provide access to each service (Slack, Atlassian, Gmail)
4. **Background prefetching** pre-loads data for meetings across the next 7 days
5. **AI Brief** uses the search service to read and summarize content from all sources
6. **Fallback** to CLI subprocess if search service is unavailable

### Configured MCP Servers

| Service | MCP Server | Capabilities |
|---------|------------|--------------|
| **Slack** | `slack-mcp-server` | Search messages, list channels, read history |
| **Atlassian** | `mcp-remote` → Atlassian | Jira issues, Confluence pages, search |
| **Gmail** | `@monsoft/mcp-gmail` | List/search/read emails |
| **Google Drive** | `briefdesk-gdrive-mcp` | Full-text search, read Google Docs/Sheets/Slides |

---

### Step 1: Install devsai CLI (Required)

The productivity hub uses `devsai` CLI to interact with MCP servers. Install it first:

```bash
# Install globally
npm install -g devsai

# Or use npx (no install needed)
npx devsai --help
```

Verify it works:
```bash
devsai -p "Hello, what can you do?" --output text
```

---

### Step 2: Configure MCP Servers

Create a `.devsai.json` file in the briefdesk directory:

```bash
cd ~/.local/share/briefdesk
touch .devsai.json
```

Add your MCP server configurations (see sections below for each service).

---

### Setting Up Slack MCP (Local, No App Required)

This uses browser tokens for "stealth mode" - no Slack app creation needed. **100% local** - data goes directly between your machine and Slack's API.

1. **Install the server:**
   ```bash
   npx -y slack-mcp-server
   ```

2. **Get your tokens from the browser:**
   - Open `https://app.slack.com` in Chrome
   - Open DevTools (`Cmd+Option+I`) → **Application** tab → **Cookies** → `https://app.slack.com`
   - Copy the `d` cookie value (starts with `xoxd-...`) → this is `SLACK_MCP_XOXD_TOKEN`
   - Go to **Console** tab and paste:
     ```javascript
     JSON.parse(localStorage.getItem('localConfig_v2'))?.['teams']?.[Object.keys(JSON.parse(localStorage.getItem('localConfig_v2'))?.['teams'] || {})[0]]?.['token']
     ```
   - Copy the output (starts with `xoxc-...`) → this is `SLACK_MCP_XOXC_TOKEN`

3. **Add to MCP config** (`~/.devsai/mcp.json`):
   ```json
   {
     "mcpServers": {
       "slack": {
         "command": "npx",
         "args": ["-y", "slack-mcp-server"],
         "env": {
           "SLACK_MCP_XOXC_TOKEN": "xoxc-...",
           "SLACK_MCP_XOXD_TOKEN": "xoxd-..."
         }
       }
     }
   }
   ```

4. **Test it:**
   ```bash
   SLACK_MCP_XOXC_TOKEN="xoxc-..." SLACK_MCP_XOXD_TOKEN="xoxd-..." \
     echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | npx -y slack-mcp-server
   ```

**Note:** Tokens are tied to your browser session. Re-extract if you sign out of Slack.

### Setting Up Atlassian MCP (Jira/Confluence)

Uses Atlassian's official MCP server with OAuth - opens browser for one-time authentication.

1. **First-time auth (opens browser):**
   ```bash
   npx -y mcp-remote https://mcp.atlassian.com/v1/sse
   ```
   
2. **Add to MCP config** (`~/.devsai/mcp.json`):
   ```json
   {
     "mcpServers": {
       "atlassian": {
         "command": "npx",
         "args": ["-y", "mcp-remote", "https://mcp.atlassian.com/v1/sse"]
       }
     }
   }
   ```

OAuth tokens are cached locally after first authentication.

### Setting Up Gmail MCP

Uses `@monsoft/mcp-gmail` server with OAuth authentication.

1. **Create Google Cloud OAuth credentials** (if you haven't already for Calendar):
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Select your project (or create one)
   - Enable the **Gmail API**: [Enable Gmail API →](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   - Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON file

2. **Set up the Gmail MCP directory:**
   ```bash
   mkdir -p ~/.gmail-mcp
   mv ~/Downloads/client_secret_*.json ~/.gmail-mcp/gcp-oauth.keys.json
   ```

3. **Authenticate (opens browser for OAuth):**
   ```bash
   npx @monsoft/mcp-gmail auth
   ```
   
   After authenticating, tokens are saved to `~/.gmail-mcp/`

4. **Add to your `.devsai.json`:**
   ```json
   {
     "mcpServers": {
       "gmail": {
         "command": "npx",
         "args": ["-y", "@monsoft/mcp-gmail"]
       }
     }
   }
   ```

5. **Test it:**
   ```bash
   devsai -p "List my 5 most recent emails" --output text
   ```

### Google Drive (Full-Text Search via API)

Google Drive search uses the built-in `briefdesk-gdrive-mcp` server to search file contents directly via Google Drive API.

**What it can do:**
- **Full-text search** - Find documents by content, not just filename
- **Read Google Docs/Sheets/Slides** - Exports content as text for AI analysis
- **Direct file links** - Click results to open in Google Drive

**Setup:**

1. **Enable the Google Drive API** (same project as Calendar):
   - [Enable Drive API →](https://console.cloud.google.com/apis/library/drive.googleapis.com)

2. **(Optional)** Enable these for better content export:
   - [Enable Sheets API →](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
   - [Enable Docs API →](https://console.cloud.google.com/apis/library/docs.googleapis.com)

3. **Authenticate** (opens browser):
   ```bash
   cd ~/.local/share/briefdesk/gdrive-mcp && npm run auth
   ```

4. Sign in and authorize **drive.readonly** access

**Note:** Uses read-only access. BriefDesk can search and read files but cannot modify them.

**Fallback:** If the Drive MCP is not configured, BriefDesk falls back to searching locally synced files via filesystem (requires Google Drive for Desktop).

### Complete MCP Config Example

Create `~/.local/share/briefdesk/.devsai.json` with all your services:

```json
{
  "mcpServers": {
    "slack": {
      "command": "npx",
      "args": ["-y", "slack-mcp-server"],
      "env": {
        "SLACK_MCP_XOXC_TOKEN": "xoxc-your-token-here",
        "SLACK_MCP_XOXD_TOKEN": "xoxd-your-token-here"
      }
    },
    "atlassian": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.atlassian.com/v1/sse"]
    },
    "gmail": {
      "command": "npx",
      "args": ["-y", "@monsoft/mcp-gmail"]
    }
  }
}
```

**Config locations** (checked in order):
1. `~/.local/share/briefdesk/.devsai.json` (project-specific, recommended)
2. `~/.devsai/mcp.json` (global)

---

### AI Brief & Background Prefetching

**AI Brief** generates a meeting summary by:
1. Searching all connected sources for relevant content
2. Reading the actual content (not just titles)
3. Synthesizing a concise brief with key context, recent activity, and talking points

**Week-Long Prefetching** keeps all your meetings ready:
- Fetches data for up to **30 meetings** across the next **7 days**
- Processes meetings continuously with short pauses between batches
- **5 seconds** between each meeting, **30 second** pause every 5 meetings
- Only waits **10 minutes** when all meetings are already cached
- Cache TTL: **30 minutes** (sources), **45 minutes** (AI summaries)

**Persistent Cache** survives restarts:
- Cache stored in `~/.local/share/briefdesk/prep_cache.json`
- Automatically loaded on server startup
- Typical size: **100-200KB** for 30 meetings
- No need to re-fetch after server restart or system reboot

**Status Dashboard** (Settings → Status tab):
- View current prefetch activity in real-time
- See which meeting/source is being fetched
- Activity log shows recent fetches with success/error status
- Click Refresh to update status

**"Try again" buttons** - If a source returns no results, click to retry with a fresh fetch (bypasses cache).

---

### Search Service (Fast AI Queries)

The search service is a Node.js process that keeps MCP connections alive, eliminating cold start delays:

**Architecture:**
- Runs on port **18766** as a LaunchAgent (`com.briefdesk.search-service`)
- Loads devsai library once at startup
- MCP servers stay connected between requests
- Python server calls search service via HTTP
- Falls back to CLI subprocess if service unavailable

**Performance comparison:**
| Method | First Query | Subsequent Queries |
|--------|-------------|-------------------|
| CLI subprocess | ~15-25s | ~10-15s (MCP restart each time) |
| Search service | ~8-12s | ~3-8s (MCP stays connected) |

**Managing the service:**
```bash
# Check if running
lsof -i:18766

# View logs
tail -f /tmp/briefdesk-search-service.log

# Restart
launchctl stop com.briefdesk.search-service && launchctl start com.briefdesk.search-service
```

---

### AI Model Selection

Choose your preferred AI model in **Settings → Hub → AI Model**. The selected model is used for:
- AI Brief generation (meeting summaries)
- Data source searches (Jira, Confluence, Slack, Gmail, Drive)

**Available models:**

| Category | Models |
|----------|--------|
| **Fast (Recommended)** | Claude 4.5 Haiku (default), Gemini 2.0 Flash, Gemini 2.5 Flash, Grok 4.1 Fast |
| **Balanced** | Claude 4.5 Sonnet, Claude 4 Sonnet, Claude 3.7 Sonnet, Gemini 2.5 Pro |
| **Best Quality** | Claude Opus 4.5, Gemini 3 Pro, Grok 4 |

Model selection is persisted in `~/.local/share/briefdesk/config.json` and used by both the search service and CLI fallback.

---

### Hub Features Status

| Feature | Status | Method |
|---------|--------|--------|
| Week view with day tabs | ✅ Working | Google Calendar API |
| Meeting selector | ✅ Working | Click/arrows to navigate |
| Jira ticket search | ✅ Working | CLI + Atlassian MCP |
| Confluence page search | ✅ Working | CLI + Atlassian MCP |
| Slack message search | ✅ Working | CLI + Slack MCP |
| Gmail email search | ✅ Working | CLI + Gmail MCP |
| Google Drive file search | ✅ Working | Drive MCP (full-text) or filesystem fallback |
| AI-generated meeting brief | ✅ Working | CLI + all sources |
| 7-day prefetching | ✅ Working | Continuous background |
| Persistent cache | ✅ Working | JSON file storage |
| Status dashboard | ✅ Working | Settings → Status tab |
| GitHub PR notifications | ⬜ Planned | - |

### Reliability & Error Handling

The Hub includes several reliability mechanisms:

| Mechanism | Description |
|-----------|-------------|
| **Retry logic** | Failed CLI calls retry up to 2 times |
| **Timeouts** | 60s for most sources, 90s for Drive |
| **Graceful degradation** | If a source fails, others still work |
| **7-day prefetch** | All meetings pre-loaded in background |
| **Persistent cache** | Data survives server restarts |
| **Cache TTL** | 30-min for sources, 45-min for summaries |
| **"Try again" buttons** | Manual retry bypasses cache |
| **Meeting ID fetch** | Fetches specific meetings by ID (not just "next") |

**Known limitations:**
- Slack tokens (xoxc/xoxd) expire when you sign out - re-extract from browser
- Atlassian OAuth may require re-auth after ~30 days
- Google Drive MCP tokens may expire - re-run `npm run auth` in gdrive-mcp folder
- CLI calls can timeout on slow networks (increase timeout in code if needed)

### Updating devsai CLI

The start page uses a **local copy** of devsai (with FDA-enabled Node binary). After updating devsai globally:

```bash
# Update global devsai
npm install -g devsai

# Re-copy to local folder
cp -r $(npm root -g)/devsai/dist ~/.local/share/devsai/

# Restart server to pick up changes
launchctl kickstart -k gui/$(id -u)/com.briefdesk.search
```

Or simply re-run `./install.sh` which handles this automatically

## Customization

Click the **gear icon** (⚙️) in the bottom-right corner to open settings where you can:
- Set your name (for personalized greetings)
- Add, edit, or remove quick links (with custom icons)
- Choose a background (gradient presets, custom gradient, or upload image)
- Switch between Dark UI and Light UI themes

Settings are stored in localStorage and persist across sessions.

## How It Works

Three lightweight servers run in the background:

1. **Static server** (port 8765) - Serves HTML/CSS
2. **Search server** (port 18765) - Queries browser history, calendar, and productivity hub
3. **Search service** (port 18766) - Node.js service that keeps MCP connections warm for fast AI queries

### History Search
- Searches multiple browsers: Safari, Chrome, Helium, and Dia
- Copies History.db + WAL files to a temp location (avoids locks)
- Runs a WAL checkpoint to include recent browsing
- Searches with smart ranking (visit count, title match, domain match)
- Cleans up temp files after each query

### Productivity Hub
- **Week view** shows meetings grouped by day with clickable tabs
- **Background prefetch thread** processes all meetings for the week continuously
- Calls `devsai` CLI with prompts to search each MCP source
- Caches results for 30 minutes (45 min for AI summaries)
- **Persistent cache** stored in JSON file - survives server restarts
- Fetches specific meetings by ID from Google Calendar API
- Skips sources that aren't authenticated (won't trigger OAuth prompts)

### Calendar
- Fetches Google Calendar events with caching (30s server-side, instant client-side)
- Shows meeting join links (Google Meet, Zoom, Teams)

## Search Features

- **Single word**: `github` → matches URLs and titles containing "github"
- **Multi-word**: `figma design` → matches entries containing both words
- **URL navigation**: `github.com` → navigates directly to the URL
- **Visit count**: Results ranked by how often you visit them
- **Real-time**: Reads Safari's WAL file for immediate results

## Troubleshooting

### Hub Features Not Working

**All sources returning empty:**
```bash
# Check if server is running
lsof -i:18765

# Check MCP server connections
~/.local/share/devsai/devsai.sh -p "List available tools" --max-iterations 1 2>&1 | head -10

# Check logs for errors
grep -E "error|timeout|failed" /tmp/safari-hub-server.log | tail -10
```

**Google Drive returning 0 items:**
1. Check if Drive MCP is authenticated:
   ```bash
   ls ~/.local/share/briefdesk/google_drive_token.json
   ```
2. If not authenticated, run:
   ```bash
   cd ~/.local/share/briefdesk/gdrive-mcp && npm run auth
   ```
3. Verify the Drive API is enabled: [Enable Drive API →](https://console.cloud.google.com/apis/library/drive.googleapis.com)
4. **Fallback mode** (if MCP not set up): Requires Google Drive for Desktop syncing files locally

**Slack/Gmail/Jira not working:**
- Check credentials in `~/.local/share/briefdesk/.devsai.json`
- Slack tokens expire when you sign out - re-extract from browser
- Atlassian may need re-auth: `npx mcp-remote https://mcp.atlassian.com/v1/sse`

### Search not finding recent pages
Safari buffers history writes. The search server reads the WAL file for real-time results, but if issues persist:
1. Quit Safari completely (Cmd+Q)
2. Reopen Safari
3. Search again

### Permission denied / History search stopped working
Full Disk Access is tied to specific Python binary paths, which can change after macOS or Xcode updates.

**How it works:** BriefDesk uses a Python wrapper script (`~/.local/share/briefdesk/python3`) that calls your system Python. This approach avoids issues with copying Python binaries (which breaks due to macOS dynamic library linking).

**Quick fix:** Check which Python is being used and grant FDA:
```bash
# Find the actual Python being used
python3 -c "import os, sys; print(os.path.realpath(sys.executable))"
```
Add that resolved path to Full Disk Access in System Settings.

**Alternative - Standalone binary** (path never changes):
```bash
pip3 install pyinstaller
cd ~/.local/share/briefdesk
pyinstaller --onefile --name search-server --distpath . search-server.py
rm -rf build *.spec
```
Then update your LaunchAgent plist to use the binary directly:
```xml
<string>/Users/YOURNAME/.local/share/briefdesk/search-server</string>
```
Grant FDA to the binary once - it will never change.

### Check server status
```bash
curl http://127.0.0.1:18765/debug
curl http://127.0.0.1:8765/start.html
```

### Restart servers
```bash
launchctl kickstart -k gui/$(id -u)/com.briefdesk.static
launchctl kickstart -k gui/$(id -u)/com.briefdesk.server
launchctl kickstart -k gui/$(id -u)/com.briefdesk.search-service
```

### Uninstall
```bash
launchctl bootout gui/$(id -u)/com.briefdesk.static
launchctl bootout gui/$(id -u)/com.briefdesk.server
launchctl bootout gui/$(id -u)/com.briefdesk.search-service
rm ~/Library/LaunchAgents/com.briefdesk.*.plist
rm -rf ~/.local/share/briefdesk
```

## Testing

The server has comprehensive unit test coverage (479 tests, 100% function coverage) to ensure reliability when making changes.

### Running Tests

```bash
# Install pytest (if not already installed)
pip3 install pytest

# Run all tests
cd ~/.local/share/briefdesk  # or your briefdesk directory
python3 -m pytest tests/ -v

# Run tests for a specific module
python3 -m pytest tests/test_slack.py -v
python3 -m pytest tests/test_atlassian.py -v
python3 -m pytest tests/test_google.py -v

# Run a specific test class
python3 -m pytest tests/test_server.py::TestExtractJsonArray -v

# Run with short output (just pass/fail)
python3 -m pytest tests/ --tb=no

# Run with coverage report (requires pytest-cov)
pip3 install pytest-cov
python3 -m pytest tests/ --cov=. --cov-report=term-missing
```

### Test Structure

```
tests/
├── conftest.py              # Pytest configuration (adds tests/ to path)
├── search_server_funcs.py   # Extracted functions for isolated testing
├── prefetch_utils_funcs.py  # Prefetch functions module
├── test_server.py           # Core utilities (23 tests)
│   └── JSON parsing, prompts, cache, domain extraction
├── test_slack.py            # Slack integration (57 tests)
│   └── Tokens, API calls, users, conversations, threads, DMs
├── test_atlassian.py        # Atlassian/MCP (93 tests)
│   └── MCP config, process management, Jira, Confluence
├── test_google.py           # Google Calendar/Drive (55 tests)
│   └── OAuth, calendar events, meeting lookup, Drive search
├── test_cli_calendar.py     # CLI and calendar utils (100 tests)
│   └── Keywords, CLI calls, JSON extraction, timestamps
└── test_prefetch_utils.py   # Prefetch & background tasks (151 tests)
    └── Caching, threading, cleanup, status tracking
```

### Test Coverage by Function Area

| Area | Functions Covered | Test Count |
|------|-------------------|------------|
| Core Utilities | `extract_json_array`, `extract_domain`, `slack_ts_to_iso`, `is_night_hours` | 23 |
| Prompt System | `get_prompt`, `set_custom_prompt`, `get_all_prompts`, `reset_prompt` | 12 |
| Cache System | `get_meeting_cache`, `set_meeting_cache`, `has_cached_data`, `is_cache_valid` | 45 |
| Slack | `slack_api_call`, `slack_get_users`, `slack_get_conversations_fast`, etc. | 57 |
| Atlassian | `load_mcp_config`, `call_atlassian_tool`, `search_atlassian`, etc. | 93 |
| Google | `authenticate_google`, `get_calendar_events_standalone`, `search_google_drive` | 55 |
| CLI | `call_cli_for_source`, `call_cli_for_meeting_summary`, `extract_meeting_keywords` | 48 |
| Prefetch | `prefetch_meeting_data`, `background_prefetch_loop`, `cleanup_old_caches` | 151 |

### Writing New Tests

Tests use `unittest.mock` to isolate functions from external dependencies:

```python
from unittest.mock import patch, MagicMock

class TestMyFunction:
    @patch('search_server_funcs.external_dependency')
    def test_something(self, mock_dep):
        from search_server_funcs import my_function
        
        mock_dep.return_value = {'expected': 'data'}
        result = my_function('input')
        
        assert result == expected_output
        mock_dep.assert_called_once_with('input')
```

Key patterns used:
- **Fixture for state reset**: `@pytest.fixture(autouse=True)` to reset globals between tests
- **Mock external calls**: `@patch` for subprocess, API calls, file I/O
- **Test isolation**: Each test imports fresh from `search_server_funcs`

### Verifying Test Integrity

The tests were validated with mutation testing:
1. Introduced intentional bugs (e.g., return `None` instead of data)
2. Verified tests caught the bugs with specific assertion failures
3. Reverted bugs and confirmed all tests pass

This ensures tests have "teeth" - they will catch real regressions.

## Files

```
briefdesk/
├── start.html           # Main start page (customizable)
├── search-server.py     # Main API server (imports from lib/)
├── search-service.mjs   # Node.js search service (keeps MCP warm)
├── lib/                 # Modular server components
│   ├── __init__.py
│   ├── config.py        # Constants, paths, logging, prompts, model config
│   ├── utils.py         # Utility functions
│   ├── cache.py         # Cache management
│   ├── slack.py         # Slack integration
│   ├── atlassian.py     # Jira/Confluence integration
│   ├── google_services.py # Calendar/Drive integration
│   ├── cli.py           # devsai CLI/search service integration
│   ├── prefetch.py      # Background prefetching
│   └── history.py       # Browser history/bookmarks
├── css/
│   └── styles.css       # Frontend styles
├── js/
│   ├── app.js           # Main frontend JavaScript
│   └── hub.js           # Hub/meeting prep JavaScript
├── install.sh           # Installation script
├── tests/               # Unit tests (479 tests, 100% coverage)
│   ├── test_server.py
│   ├── test_slack.py
│   ├── test_atlassian.py
│   ├── test_google.py
│   ├── test_cli_calendar.py
│   └── test_prefetch_utils.py
├── launchagents/
│   ├── com.briefdesk.static.plist      # Static file server
│   ├── com.briefdesk.server.plist      # Main API server
│   └── com.briefdesk.search-service.plist  # Node.js search service
└── README.md

# Runtime files (in ~/.local/share/briefdesk/)
├── lib/                 # Deployed server modules
├── css/                 # Deployed styles
├── js/                  # Deployed JavaScript
├── prep_cache.json      # Persistent prefetch cache (~100-200KB)
├── config.json          # User settings (model selection, etc.)
├── google_credentials.json  # Google OAuth credentials
└── token.pickle         # Google auth token
```

## Privacy

- **100% local** - No external API calls or tracking
- **No data collection** - History stays on your machine
- **Localhost only** - Servers bind to 127.0.0.1

## License

MIT License - feel free to customize and share!

## Building & Releases

### Building the Package Locally

**Contributors (unsigned build for testing):**
```bash
./build-pkg.sh --unsigned
```

**Maintainers (signed + notarized):**
```bash
APPLE_ID="your@email.com" APP_PASSWORD="app-specific-password" ./build-pkg.sh
```

Requires a Developer ID Installer certificate in Keychain.

### Creating a Release

Releases are automated via GitHub Actions. To create a new release:

```bash
git tag v1.0.3
git push origin v1.0.3
```

This triggers a workflow that:
1. Builds the `.pkg` installer
2. Signs it with the Developer ID certificate
3. Notarizes with Apple (Gatekeeper approval)
4. Attaches the signed package to a GitHub Release

### CI/CD

| Trigger | Build Type |
|---------|------------|
| Pull request | Unsigned (for testing) |
| Push tag `v*` | Signed + notarized → GitHub Release |
| Manual dispatch | Signed + notarized |

## Contributing

Pull requests welcome! Ideas for improvements:
- [ ] GitHub PR notifications (MCP server exists)
- [ ] Bookmark folder organization
- [ ] Keyboard shortcuts for quick links
- [ ] Weather widget
- [ ] Firefox history support
- [ ] Linear/Notion integrations
