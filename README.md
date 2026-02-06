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
- **Google Drive** - Full-text search via Drive API for meeting-related documents
- **GitHub** - Search code, issues, and PRs across your repositories
- **7-Day Prefetching** - Pre-caches data for up to 30 meetings across the entire week
- **Persistent Cache** - Prefetched data survives server restarts (stored in JSON)
- **Status Dashboard** - Monitor prefetch activity, MCP connections, and service health
- **Collapsible Sections** - Each source can be collapsed; state persists across sessions
- **Model Selection** - Choose your preferred AI model (Settings → Hub → AI Model)

## Requirements

- macOS (tested on Sonoma/Sequoia)
- Safari or any Chromium browser
- Python 3 (included with Xcode Command Line Tools)
- Node.js 18+ (for MCP servers) - `brew install node`

## Installation

### Package Installer (.pkg) — Recommended

The easiest way to install BriefDesk:

1. Download the latest `.pkg` from the [Releases page](https://github.com/eliekha/BriefDesk/releases)
2. Double-click to run the installer
3. After installation, the **Setup Wizard** opens automatically in your browser

The installer is **signed and notarized** by Apple — no Gatekeeper warnings.

**What the installer does automatically:**
- Copies all files to `~/.local/share/briefdesk/`
- Installs the **devsai CLI** from the bundled tarball (`~/.local/share/devsai/`)
- Builds **Gmail MCP** and **GDrive MCP** servers
- Downloads the **GitHub MCP Server** binary (architecture-aware)
- Sets up **LaunchAgents** for all three servers (static, API, search service)
- Creates a `devsai` wrapper script at `~/.local/bin/devsai`

### Setup Wizard

After installation, the setup wizard at `http://127.0.0.1:18765/installer` guides you through:

1. **System Check** — Verifies Python, Node.js, and devsai are installed
2. **Full Disk Access** — Shows which binaries need FDA for Safari history and Drive
3. **Google Calendar** — OAuth flow to connect your Google account (also enables Gmail and Drive)
4. **Slack** — OAuth flow or auto-detect from browser cookies
5. **Integrations** — Connect GitHub (OAuth Device Flow) and Atlassian (browser OAuth)
6. **Browser Setup** — Set BriefDesk as your homepage/new tab page

You can always return to the setup wizard later:
```
http://127.0.0.1:18765/installer
```

Or configure integrations from **Settings → Status** tab in the main app.

### Manual Install (Development)

```bash
git clone https://github.com/eliekha/BriefDesk.git
cd BriefDesk
./install.sh
```

### After Installation

1. **Grant Full Disk Access** (required for Safari history and Google Drive):
   - System Settings → Privacy & Security → Full Disk Access
   - Add these binaries (use Cmd+Shift+G to paste paths):
   
   | Binary | Path | Purpose |
   |--------|------|---------|
   | Python | Shown in Setup Wizard (e.g., `/opt/homebrew/bin/python3`) | Safari history search |
   | Node | `~/.local/share/devsai/node` | Google Drive search (Hub) |

2. **Set your browser homepage:**
   - Safari → Settings → General → Homepage: `http://127.0.0.1:8765/start.html`
   - Chrome/Arc: Use the [New Tab Redirect](https://chrome.google.com/webstore/detail/new-tab-redirect/) extension

## How Authentication Works

All integrations are authenticated through the setup wizard or settings page. No manual token management or config file editing required.

### Google (Calendar, Gmail, Drive)

A single Google OAuth flow connects all three Google services:

1. Click **"Connect Google"** in the setup wizard
2. Sign in and authorize Calendar, Gmail, and Drive scopes
3. BriefDesk stores the token locally in `~/.local/share/briefdesk/google_token.pickle`
4. Tokens auto-refresh; re-authenticate only if revoked

**Google Drive** uses the built-in `briefdesk-gdrive-mcp` server for full-text search via the Drive API. OAuth credentials are shared from the main Google auth flow.

### Slack

Two authentication methods:

1. **OAuth (Recommended)** — Click "Connect Slack" in the setup wizard. Uses a registered Slack OAuth App to get a `xoxp-` user token with read-only scopes.
2. **Auto-detect** — BriefDesk can extract tokens from your browser cookies/localStorage if you're signed into Slack web.

The Slack MCP server (`slack-mcp-server`) is configured automatically in `.devsai.json`.

**Note:** If you sign out of Slack in the browser, auto-detected tokens will expire. Use the OAuth method for more stable authentication.

### Atlassian (Jira / Confluence)

Uses Atlassian's official MCP server with OAuth:

1. Click **"Connect Atlassian"** in the setup wizard (or Settings → Status)
2. A Terminal window opens running `mcp-remote https://mcp.atlassian.com/v1/sse`
3. Complete the OAuth flow in your browser
4. Close Terminal when done, then click **"Reconnect"**

OAuth tokens are cached in `~/.mcp-auth/` and managed by `mcp-remote` internally (including token refresh).

**Automatic recovery:** If the Atlassian MCP fails to connect on startup (e.g., stale tokens, slow SSE handshake), the search service retries automatically after 10 seconds.

### GitHub

Uses the official [GitHub MCP Server](https://github.com/github/github-mcp-server) with OAuth Device Flow:

1. Click **"Connect with GitHub"** in the setup wizard
2. A browser tab opens — enter the device code shown in the modal
3. Authorize BriefDesk for your account (request org access if needed)
4. The installer auto-detects authorization and configures the MCP server

**What it searches:** Code, issues, pull requests, repositories, and file contents.

**PAT fallback:** If OAuth doesn't work, expand "Or use a Personal Access Token" in the GitHub setup modal and paste a fine-grained PAT with Contents, Issues, Pull Requests, and Metadata read access.

## Architecture

Three lightweight servers run in the background as LaunchAgents:

| Server | Port | Purpose |
|--------|------|---------|
| Static File Server | 8765 | Serves `start.html` and static assets |
| API Server | 18765 | Calendar, search, meeting prep, OAuth flows |
| Search Service | 19765 | Node.js — keeps MCP connections warm for fast AI queries |

### MCP Servers

| Service | MCP Server | Tools | Auth Method |
|---------|------------|-------|-------------|
| **Slack** | `slack-mcp-server` | 5 | OAuth (xoxp token) |
| **Atlassian** | `mcp-remote` → Atlassian SSE | 28 | Browser OAuth |
| **Gmail** | `@monsoft/mcp-gmail` (local build) | 5 | Shared Google OAuth |
| **Google Drive** | `briefdesk-gdrive-mcp` (local build) | 3 | Shared Google OAuth |
| **GitHub** | `github-mcp-server` (binary) | 40 | OAuth Device Flow |

All MCP server configurations are stored in `~/.local/share/briefdesk/.devsai.json` and managed automatically by the setup wizard.

### Search Service

The search service is a Node.js process that keeps MCP connections alive, eliminating cold start delays:

- Loads the `devsai` library once at startup
- MCP servers stay connected between requests
- Python API server calls the search service via HTTP
- Falls back to CLI subprocess if the service is unavailable

**Performance comparison:**

| Method | First Query | Subsequent Queries |
|--------|-------------|-------------------|
| CLI subprocess | ~15-25s | ~10-15s (MCP restart each time) |
| Search service | ~8-12s | ~3-8s (MCP stays connected) |

**Reliability features:**
- **Deferred retry** — If any MCP server fails to connect on startup (common with `mcp-remote` / Atlassian), the service automatically retries after 10 seconds
- **Reconnect endpoint** — `GET /reconnect?mcp=name` forces a reconnect (used after re-authentication)
- **Self-restart** — When a new MCP server is added to config, the service restarts automatically via LaunchAgent KeepAlive

### Background Prefetching

The prefetch system keeps meeting data ready before you need it:

- Fetches data for up to **30 meetings** across the next **7 days**
- Processes meetings continuously with short pauses between batches
- **Smart startup** — If Google auth isn't ready yet (fresh install), retries in 30 seconds instead of waiting 10 minutes
- **Night mode** — More aggressive refresh cycles during off-hours
- **Persistent cache** — Stored in `~/.local/share/briefdesk/prep_cache.json`, survives restarts
- Cache TTL: **30 minutes** (sources), **45 minutes** (AI summaries)

### Token Validation

The Atlassian status endpoint validates tokens by checking the search service's actual connection state (not just file existence):

1. Checks if `~/.mcp-auth/` token files exist
2. Queries the search service to see if Atlassian MCP is connected
3. If not connected, tries a direct API call to validate the token
4. If the token is expired, triggers a search service reconnect attempt
5. Reports accurate `authenticated: true/false` status to the UI

This prevents the false "connected" status that occurred with stale tokens after reinstalls.

## AI Model Selection

Choose your preferred AI model in **Settings → Hub → AI Model**:

| Category | Models |
|----------|--------|
| **Fast (Recommended)** | Claude 4.5 Haiku (default), Gemini 2.0 Flash, Gemini 2.5 Flash, Grok 4.1 Fast |
| **Balanced** | Claude 4.5 Sonnet, Claude 4 Sonnet, Claude 3.7 Sonnet, Gemini 2.5 Pro |
| **Best Quality** | Claude Opus 4.5, Gemini 3 Pro, Grok 4 |

## Status Dashboard

The **Settings → Status** tab shows:

- **Service health** — All 3 servers with connection status
- **MCP connections** — All 5 MCPs with tool counts (github, atlassian, slack, gmail, gdrive)
- **Integration auth** — Per-service authentication status with re-connect buttons
- **Prefetch activity** — Current cycle, meetings processed, activity log

## Customization

Click the **gear icon** (⚙️) in the bottom-right corner to:
- Set your name (for personalized greetings)
- Add, edit, or remove quick links (with custom icons)
- Choose a background (gradient presets, custom gradient, or upload image)
- Switch between Dark UI and Light UI themes
- Select AI model for meeting prep
- View service health and MCP status

Settings are stored in localStorage and persist across sessions.

## File Structure

```
briefdesk/
├── start.html              # Main start page
├── installer.html          # Setup wizard
├── search-server.py        # Main API server (imports from lib/)
├── search-service.mjs      # Node.js search service
├── lib/                    # Modular server components
│   ├── config.py           # Constants, paths, logging, model config
│   ├── utils.py            # Utility functions
│   ├── cache.py            # Cache management
│   ├── slack.py            # Slack integration
│   ├── atlassian.py        # Jira/Confluence MCP integration
│   ├── google_services.py  # Calendar/Drive/Gmail OAuth
│   ├── ai_search.py        # AI search via search service
│   ├── cli.py              # devsai CLI integration
│   ├── prefetch.py         # Background prefetching
│   └── history.py          # Browser history/bookmarks
├── js/
│   ├── app.js              # Main frontend JavaScript
│   └── hub.js              # Hub/meeting prep JavaScript
├── css/styles.css          # Frontend styles
├── gmail-mcp/              # Gmail MCP server (built during install)
├── gdrive-mcp/             # Google Drive MCP server (built during install)
├── install.sh              # Manual installation script
├── build-pkg.sh            # Package builder script
├── pkg-installer/
│   └── scripts/postinstall # Post-install script for .pkg
├── tests/                  # Unit tests (479 tests)
├── launchagents/           # LaunchAgent plist templates
└── README.md

# Runtime files (in ~/.local/share/briefdesk/)
├── search-server.py        # Deployed API server
├── search-service.mjs      # Deployed search service
├── lib/                    # Deployed server modules
├── .devsai.json            # MCP server configuration (auto-managed)
├── config.json             # User settings (model, domain, etc.)
├── google_token.pickle     # Google OAuth token
├── google_credentials.json # Google OAuth client keys (for Drive MCP)
├── google_drive_token.json # Drive MCP token (shared from main OAuth)
├── prep_cache.json         # Persistent prefetch cache (~100-200KB)
├── gmail-mcp/              # Built Gmail MCP server
├── gdrive-mcp/             # Built GDrive MCP server
└── github-mcp-server       # GitHub MCP binary

~/.local/share/devsai/
├── node                    # Local Node binary (for FDA)
├── devsai.sh               # Wrapper script for CLI
└── node_modules/devsai/    # Installed devsai CLI + dependencies
```

## Troubleshooting

### Services Not Running

```bash
# Check all services
lsof -i:8765    # Static file server
lsof -i:18765   # API server
lsof -i:19765   # Search service

# Restart all services
launchctl kickstart -k gui/$(id -u)/com.briefdesk.static
launchctl kickstart -k gui/$(id -u)/com.briefdesk.server
launchctl kickstart -k gui/$(id -u)/com.briefdesk.search-service

# View logs
tail -f /tmp/briefdesk-server.log              # API server
tail -f /tmp/briefdesk-search-service.log      # Search service
```

### MCP Connections Failing

Check the search service status:
```bash
curl -s http://127.0.0.1:19765/status | python3 -m json.tool
```

Force reconnect a specific MCP:
```bash
curl -s "http://127.0.0.1:19765/reconnect?mcp=atlassian"
```

Retry all failed MCPs:
```bash
curl -s -X POST http://127.0.0.1:19765/retry
```

### Atlassian Not Working

1. Check if tokens exist: `ls ~/.mcp-auth/`
2. Check search service: `curl -s http://127.0.0.1:19765/status | python3 -c "import sys,json; [print(s['name'],s['status']) for s in json.load(sys.stdin)['servers']]"`
3. If not connected, re-authenticate:
   - Go to Settings → Status → Atlassian → Re-authenticate
   - Or run: `npx -y mcp-remote https://mcp.atlassian.com/v1/sse`
4. After re-auth, the search service reconnects automatically

### Google Calendar Empty

If calendar shows no events but you have meetings:
- This usually happens on fresh install when prefetch runs before OAuth completes
- The prefetch now automatically retries in 30 seconds when auth isn't ready
- Force a manual check: `curl -s http://127.0.0.1:18765/calendar | python3 -m json.tool`

### Slack Token Expired

If Slack stops working:
1. Go to Settings → Status → Slack → Re-authenticate
2. Or re-run the Slack OAuth flow from the setup wizard
3. If using auto-detected tokens: sign into Slack web and restart the API server

### Google Drive Not Working

1. Check if Drive MCP is available: `curl -s http://127.0.0.1:19765/status | python3 -c "import sys,json; print(json.load(sys.stdin).get('gdriveMcp'))"`
2. If token missing, re-authenticate Google from the setup wizard
3. Verify the Drive API is enabled: [Enable Drive API →](https://console.cloud.google.com/apis/library/drive.googleapis.com)

### Permission Denied / History Search Stopped

Full Disk Access can break after macOS or Python updates:
```bash
# Find the actual Python binary
python3 -c "import os, sys; print(os.path.realpath(sys.executable))"
```
Add that resolved path to Full Disk Access in System Settings.

## Uninstall

```bash
launchctl bootout gui/$(id -u)/com.briefdesk.static
launchctl bootout gui/$(id -u)/com.briefdesk.server
launchctl bootout gui/$(id -u)/com.briefdesk.search-service
rm ~/Library/LaunchAgents/com.briefdesk.*.plist
rm -rf ~/.local/share/briefdesk
rm -rf ~/.local/share/devsai
rm -rf ~/.mcp-auth
```

## Testing

```bash
# Install pytest
pip3 install pytest

# Run all tests (479 tests)
python3 -m pytest tests/ -v

# Run specific modules
python3 -m pytest tests/test_slack.py -v
python3 -m pytest tests/test_atlassian.py -v
python3 -m pytest tests/test_google.py -v
```

## Building & Releases

### Building the Package Locally

```bash
# Unsigned (for testing)
./build-pkg.sh --unsigned

# Signed + notarized (maintainers)
APPLE_ID="your@email.com" APP_PASSWORD="app-specific-password" ./build-pkg.sh
```

### Creating a Release

```bash
git tag v1.1.28
git push origin v1.1.28
```

This triggers a GitHub Actions workflow that builds, signs, notarizes, and attaches the `.pkg` to a GitHub Release.

## Privacy

- **100% local** - No external API calls or tracking
- **No data collection** - History stays on your machine
- **Localhost only** - Servers bind to 127.0.0.1
- **Read-only access** - All integrations use read-only scopes

## License

MIT License - feel free to customize and share!
