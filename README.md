# Custom Start Page

A beautiful, fast, customizable start page with real-time history search and Google Calendar integration.

![Screenshot](screenshot.png)

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
- **AI Brief** - AI-generated meeting summary that reads and synthesizes content from all sources
- **Jira Integration** - Automatically finds related tickets based on meeting context
- **Confluence Integration** - Surfaces relevant wiki pages and documentation
- **Slack Integration** - Shows recent discussions related to meeting topics/attendees
- **Gmail Integration** - Finds relevant email threads with meeting participants
- **Google Drive** - Searches local Drive files for meeting-related documents
- **Background Prefetching** - Pre-caches data for upcoming meetings (30-min cache, 10-min refresh)
- **Collapsible Sections** - Each source can be collapsed; state persists across sessions

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
chmod +x install.sh
./install.sh
```

### Manual Install

1. **Copy files:**
   ```bash
   mkdir -p ~/.local/share/safari_start_page
   cp start.html search-server.py ~/.local/share/safari_start_page/
   ```

2. **Install LaunchAgents:**
   ```bash
   cp launchagents/*.plist ~/Library/LaunchAgents/
   # Edit plists to replace HOME_DIR with your home directory path
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.startpage.static.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.startpage.search.plist
   ```

3. **Grant Full Disk Access** (required for Safari history):
   - System Settings → Privacy & Security → Full Disk Access
   - Add: `/Applications/Xcode.app/Contents/Developer/usr/bin/python3`
   - (Or the Python that `/usr/bin/python3 -c "import sys; print(sys.executable)"` shows)

4. **Set Safari homepage:**
   - Safari → Settings → General
   - Homepage: `http://127.0.0.1:8765/start.html`
   - New windows/tabs open with: Homepage

## Google Calendar Setup (Optional)

To show your upcoming meetings on the start page:

### 1. Create Google Cloud credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Go to **APIs & Services** → **Library** → search "Google Calendar API" → **Enable**
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
cp ~/Downloads/client_secret_*.json ~/.local/share/safari_start_page/google_credentials.json

# Authenticate (opens browser)
python3 ~/.local/share/safari_start_page/search-server.py --auth
```

### 3. Rebuild the binary (if using standalone binary)

```bash
cd ~/.local/share/safari_start_page
pip3 install pyinstaller
pyinstaller --onefile --name search-server --distpath . \
  --hidden-import=google.auth.transport.requests \
  --hidden-import=google.oauth2.credentials \
  --hidden-import=google_auth_oauthlib.flow \
  --hidden-import=googleapiclient.discovery \
  search-server.py
rm -rf build *.spec

# Restart server
launchctl kickstart -k gui/$(id -u)/com.startpage.search
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

1. **devsai CLI** acts as the brain - it receives prompts and calls MCP tools
2. **MCP servers** provide access to each service (Slack, Atlassian, Gmail)
3. **Background prefetching** pre-loads data for meetings in the next 2 hours
4. **AI Brief** uses the CLI to read and summarize content from all sources

### Configured MCP Servers

| Service | MCP Server | Capabilities |
|---------|------------|--------------|
| **Slack** | `slack-mcp-server` | Search messages, list channels, read history |
| **Atlassian** | `mcp-remote` → Atlassian | Jira issues, Confluence pages, search |
| **Gmail** | `@anthropic/gmail-mcp-server` | List/search/read emails |
| **Google Drive** | Local filesystem | Read docs via Google Drive for Desktop |

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

Create a `.devsai.json` file in the safari_start_page directory:

```bash
cd ~/.local/share/safari_start_page
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
   npx -y mcp-remote https://mcp.atlassian.com/v1/mcp
   ```
   
2. **Add to MCP config** (`~/.devsai/mcp.json`):
   ```json
   {
     "mcpServers": {
       "atlassian": {
         "command": "npx",
         "args": ["-y", "mcp-remote", "https://mcp.atlassian.com/v1/mcp"]
       }
     }
   }
   ```

OAuth tokens are cached locally after first authentication.

### Setting Up Gmail MCP

Uses Anthropic's Gmail MCP server with OAuth authentication.

1. **Create Google Cloud OAuth credentials** (if you haven't already for Calendar):
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Select your project (or create one)
   - Go to **APIs & Services** → **Library** → search "Gmail API" → **Enable**
   - Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON file

2. **Set up the Gmail MCP directory:**
   ```bash
   mkdir -p ~/.gmail-mcp
   mv ~/Downloads/client_secret_*.json ~/.gmail-mcp/gcp-oauth.keys.json
   ```

3. **Install and authenticate:**
   ```bash
   # First run will open browser for OAuth
   npx @anthropic/gmail-mcp-server
   ```
   
   After authenticating, tokens are saved to `~/.gmail-mcp/credentials.json`

4. **Add to your `.devsai.json`:**
   ```json
   {
     "mcpServers": {
       "gmail": {
         "command": "npx",
         "args": ["-y", "@anthropic/gmail-mcp-server"]
       }
     }
   }
   ```

5. **Test it:**
   ```bash
   devsai -p "List my 5 most recent emails" --output text
   ```

### Google Drive (Local Access)

No MCP needed - Google Drive for Desktop syncs files locally. Access via standard file tools:

```
~/Library/CloudStorage/GoogleDrive-{email}/My Drive/
~/Library/CloudStorage/GoogleDrive-{email}/Shared drives/
```

This allows:
- Reading meeting agendas and docs directly
- Searching shared drive content
- No API setup required

### Complete MCP Config Example

Create `~/.local/share/safari_start_page/.devsai.json` with all your services:

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
      "args": ["-y", "mcp-remote", "https://mcp.atlassian.com/v1/mcp"]
    },
    "gmail": {
      "command": "npx",
      "args": ["-y", "@anthropic/gmail-mcp-server"]
    }
  }
}
```

**Config locations** (checked in order):
1. `~/.local/share/safari_start_page/.devsai.json` (project-specific, recommended)
2. `~/.devsai/mcp.json` (global)

---

### AI Brief & Background Prefetching

**AI Brief** generates a meeting summary by:
1. Searching all connected sources for relevant content
2. Reading the actual content (not just titles)
3. Synthesizing a concise brief with key context, recent activity, and talking points

**Background Prefetching** keeps data ready:
- Runs every **10 minutes** in the background
- Pre-loads data for meetings in the next **2 hours**
- Cache TTL: **30 minutes** (sources), **45 minutes** (AI summaries)
- Zero CPU usage between cycles

**"Try again" buttons** - If a source returns no results, click to retry with a fresh fetch.

---

### Hub Features Status

| Feature | Status |
|---------|--------|
| Jira ticket search | ✅ Working |
| Confluence page search | ✅ Working |
| Slack message search | ✅ Working |
| Gmail email search | ✅ Working |
| Google Drive file search | ✅ Working |
| AI-generated meeting brief | ✅ Working |
| Background prefetching | ✅ Working |
| GitHub PR notifications | ⬜ Planned |

## Customization

Click the **gear icon** (⚙️) in the bottom-right corner to open settings where you can:
- Set your name (for personalized greetings)
- Add, edit, or remove quick links (with custom icons)
- Choose a background (gradient presets, custom gradient, or upload image)
- Switch between Dark UI and Light UI themes

Settings are stored in localStorage and persist across sessions.

## How It Works

Two lightweight servers run in the background:

1. **Static server** (port 8765) - Serves HTML/CSS
2. **Search server** (port 18765) - Queries browser history, calendar, and productivity hub

### History Search
- Searches multiple browsers: Safari, Chrome, Helium, and Dia
- Copies History.db + WAL files to a temp location (avoids locks)
- Runs a WAL checkpoint to include recent browsing
- Searches with smart ranking (visit count, title match, domain match)
- Cleans up temp files after each query

### Productivity Hub
- **Background thread** runs every 10 minutes to prefetch meeting data
- Calls `devsai` CLI with prompts to search each MCP source
- Caches results for 30 minutes (45 min for AI summaries)
- Only fetches for meetings in the next 2 hours
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

### Search not finding recent pages
Safari buffers history writes. The search server reads the WAL file for real-time results, but if issues persist:
1. Quit Safari completely (Cmd+Q)
2. Reopen Safari
3. Search again

### Permission denied / History search stopped working
Full Disk Access is tied to specific Python binary paths, which can change after macOS or Xcode updates.

**Quick fix:** Re-grant FDA to the current Python:
```bash
/usr/bin/python3 -c "import sys; print(sys.executable)"
```
Add that path to Full Disk Access in System Settings.

**Most stable fix:** Build a standalone binary (path never changes):
```bash
pip3 install pyinstaller
cd ~/.local/share/safari_start_page
pyinstaller --onefile --name search-server --distpath . search-server.py
rm -rf build *.spec
```
Then update your LaunchAgent plist to use the binary directly (no Python path needed):
```xml
<string>/Users/YOURNAME/.local/share/safari_start_page/search-server</string>
```
Grant FDA to the binary once - it will never change.

### Check server status
```bash
curl http://127.0.0.1:18765/debug
curl http://127.0.0.1:8765/start.html
```

### Restart servers
```bash
launchctl kickstart -k gui/$(id -u)/com.startpage.static
launchctl kickstart -k gui/$(id -u)/com.startpage.search
```

### Uninstall
```bash
launchctl bootout gui/$(id -u)/com.startpage.static
launchctl bootout gui/$(id -u)/com.startpage.search
rm ~/Library/LaunchAgents/com.startpage.*.plist
rm -rf ~/.local/share/safari_start_page
```

## Files

```
safari_start_page/
├── start.html           # Main start page (customizable)
├── search-server.py     # History search server
├── install.sh           # Installation script
├── launchagents/
│   ├── com.startpage.static.plist
│   └── com.startpage.search.plist
└── README.md
```

## Privacy

- **100% local** - No external API calls or tracking
- **No data collection** - History stays on your machine
- **Localhost only** - Servers bind to 127.0.0.1

## License

MIT License - feel free to customize and share!

## Contributing

Pull requests welcome! Ideas for improvements:
- [ ] GitHub PR notifications (MCP server exists)
- [ ] Bookmark folder organization
- [ ] Keyboard shortcuts for quick links
- [ ] Weather widget
- [ ] Firefox history support
- [ ] Linear/Notion integrations
