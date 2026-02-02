---
name: server-operations
description: Manage BriefDesk servers. Check status, view logs, restart servers, deploy changes, and troubleshoot issues. Use when the user needs help with server operations, debugging data issues, or deploying updates.
---

# BriefDesk Server Operations

Standardized workflows for managing the BriefDesk local servers.

## Server Architecture

BriefDesk runs three local servers:

| Server | Port | Purpose |
|--------|------|---------|
| Static File Server | 8765 | Serves `start.html` and static assets |
| Search/API Server | 18765 | Handles calendar, meeting prep, search, and AI features |
| Search Service | 18766 | Node.js service that keeps MCP connections warm for fast AI queries |

## File Locations

```
Production (deployed):
~/.local/share/briefdesk/
├── search-server.py      # Main API server (imports from lib/)
├── search-service.mjs    # Node.js search service (keeps MCP warm)
├── lib/                  # Modular server components
│   ├── __init__.py
│   ├── config.py         # Constants, paths, logging, model config
│   ├── utils.py          # Utility functions
│   ├── cache.py          # Cache management
│   ├── slack.py          # Slack integration
│   ├── atlassian.py      # Jira/Confluence integration
│   ├── google_services.py # Calendar/Drive integration
│   ├── cli.py            # devsai CLI/search service integration
│   ├── prefetch.py       # Background prefetching
│   └── history.py        # Browser history/bookmarks
├── start.html            # Frontend
├── js/app.js             # Main frontend JavaScript
├── js/hub.js             # Hub/meeting prep JavaScript
├── config.json           # User settings (model selection, etc.)
├── google_token.pickle   # Google Calendar/Drive auth token
└── .devsai.json          # MCP server configuration

~/.local/share/devsai/
├── node                  # Local Node binary (for FDA)
├── devsai.sh             # Wrapper script for CLI
├── dist/                 # devsai CLI code
└── node_modules/         # CLI dependencies

Source (development):
~/Documents/briefdesk/
├── search-server.py      # Edit here, then deploy
├── search-service.mjs    # Node.js search service
├── lib/                  # Modular components
├── tests/                # Unit tests (479 tests)
├── start.html
└── ...
```

## Full Disk Access Requirements

Both binaries need FDA for CloudStorage access:

| Binary | Path | Purpose |
|--------|------|---------|
| Python | System Python or `~/.local/share/briefdesk/python3` | Safari history, server |
| Node | `~/.local/share/devsai/node` | Google Drive search via CLI |

To grant FDA:
1. System Settings → Privacy & Security → Full Disk Access
2. Click + and use Cmd+Shift+G to paste each path
3. Restart servers after granting

## Quick Status Check

When user asks about server status, run these commands:

```bash
# Check if servers are running
lsof -i:8765   # Static file server
lsof -i:18765  # API server
lsof -i:18766  # Search service (Node.js)

# Check LaunchAgent status
launchctl list | grep -E "briefdesk"

# Quick health check
curl -s http://127.0.0.1:18765/hub/prep/meeting | python3 -c "import sys,json; d=json.load(sys.stdin); print('Meeting:', d.get('meeting',{}).get('title','None')[:50])"

# Check search service
curl -s http://127.0.0.1:18766/health 2>/dev/null && echo "Search service OK" || echo "Search service not running"
```

## Viewing Logs

Log files:
- `/tmp/briefdesk-server.log` - Main Python API server
- `/tmp/briefdesk-search-service.log` - Node.js search service

```bash
# View recent logs
tail -50 /tmp/briefdesk-server.log

# Follow logs in real-time
tail -f /tmp/briefdesk-server.log

# Filter by component
tail -f /tmp/briefdesk-server.log | grep -E "\[Prefetch\]"   # Background prefetch
tail -f /tmp/briefdesk-server.log | grep -E "\[CLI\]"        # CLI calls to devsai
tail -f /tmp/briefdesk-server.log | grep -E "\[API\]"        # API endpoint logs
tail -f /tmp/briefdesk-server.log | grep -E "\[Drive\]"      # Drive search logs

# Search service logs
tail -f /tmp/briefdesk-search-service.log | grep -E "SearchService"
```

## Checking Cache Status

To debug meeting prep data issues:

```bash
# View all cached meeting data
curl -s http://127.0.0.1:18765/hub/debug/cache | python3 -m json.tool

# Check what meeting the frontend expects
curl -s http://127.0.0.1:18765/hub/prep/meeting | python3 -m json.tool

# Test individual source endpoints
MEETING_ID="your-meeting-id"
curl -s "http://127.0.0.1:18765/hub/prep/jira?meeting_id=$MEETING_ID" | python3 -c "import sys,json; print('Jira:', len(json.load(sys.stdin)), 'items')"
curl -s "http://127.0.0.1:18765/hub/prep/confluence?meeting_id=$MEETING_ID" | python3 -c "import sys,json; print('Confluence:', len(json.load(sys.stdin)), 'items')"
curl -s "http://127.0.0.1:18765/hub/prep/slack?meeting_id=$MEETING_ID" | python3 -c "import sys,json; print('Slack:', len(json.load(sys.stdin)), 'items')"
curl -s "http://127.0.0.1:18765/hub/prep/gmail?meeting_id=$MEETING_ID" | python3 -c "import sys,json; print('Gmail:', len(json.load(sys.stdin)), 'items')"
curl -s "http://127.0.0.1:18765/hub/prep/drive?meeting_id=$MEETING_ID" | python3 -c "import sys,json; print('Drive:', len(json.load(sys.stdin)), 'items')"
```

## Restarting Servers

### Method 1: Using LaunchAgents (Recommended)

```bash
# Force restart both servers
launchctl unload ~/Library/LaunchAgents/com.startpage.search.plist && \
launchctl load ~/Library/LaunchAgents/com.startpage.search.plist

# Or use kickstart for quick restart
launchctl kickstart -k gui/$(id -u)/com.startpage.search
```

### Method 2: Manual Restart (For Debugging)

```bash
# 1. Kill existing server
lsof -ti:18765 | xargs kill -9

# 2. Start server with visible output
cd ~/.local/share/briefdesk
python3 -u search-server.py 2>&1 | tee /tmp/briefdesk-server.log
```

### Handling "Address Already in Use" Errors

```bash
# Kill all processes on the port
lsof -ti:18765 | xargs kill -9
pkill -9 -f "search-server"
sleep 2

# Verify port is free
lsof -i:18765 || echo "Port is free"

# Then restart using LaunchAgent
launchctl load ~/Library/LaunchAgents/com.startpage.search.plist
```

## Deploying Changes

After editing files in `~/Documents/briefdesk/`:

```bash
# 1. Deploy frontend, backend, lib modules, and search service
cp ~/Documents/briefdesk/search-server.py ~/.local/share/briefdesk/
cp ~/Documents/briefdesk/search-service.mjs ~/.local/share/briefdesk/
cp -r ~/Documents/briefdesk/lib ~/.local/share/briefdesk/
cp ~/Documents/briefdesk/start.html ~/.local/share/briefdesk/
cp -r ~/Documents/briefdesk/js ~/.local/share/briefdesk/
cp -r ~/Documents/briefdesk/css ~/.local/share/briefdesk/

# 2. Restart servers
launchctl stop com.briefdesk.server && sleep 1 && launchctl start com.briefdesk.server
launchctl stop com.briefdesk.search-service && sleep 1 && launchctl start com.briefdesk.search-service

# 3. Wait and verify
sleep 3
curl -s http://127.0.0.1:18765/hub/prep/meeting | python3 -c "import sys,json; print('Server OK')" && echo "API server deployed"
curl -s http://127.0.0.1:18766/health 2>/dev/null && echo "Search service deployed" || echo "Search service not running"
```

After deploying, remind user to hard refresh Safari with **Cmd+Shift+R**.

## Troubleshooting Workflows

### Meeting Prep Data Not Loading

1. **Check server is running:**
   ```bash
   lsof -i:18765 || echo "Server not running!"
   ```

2. **Check what meeting the frontend expects:**
   ```bash
   curl -s http://127.0.0.1:18765/hub/prep/meeting | python3 -m json.tool
   ```

3. **Check prefetch logs:**
   ```bash
   grep -E "Prefetch|CLI" /tmp/briefdesk-server.log | tail -30
   ```

4. **Common issues:**
   - Prefetch processing wrong meeting (check if ended meetings are being included)
   - Frontend not passing `meeting_id` parameter
   - Cache miss due to meeting ID mismatch
   - CLI timeouts (check for "timeout" in logs)

### Google Drive Search Not Working

1. **Check FDA for Node binary:**
   ```bash
   # This should list CloudStorage contents
   ~/.local/share/devsai/devsai.sh -p 'List /Users/$USER/Library/CloudStorage using list_directory' --max-iterations 1 2>&1 | grep -E "Drive|error" -i
   ```

2. **Check Drive path selection:**
   ```bash
   ls ~/Library/CloudStorage/ | grep GoogleDrive
   # Should prefer path WITHOUT timestamp in parentheses
   ```

3. **Test CLI Drive search manually:**
   ```bash
   cd ~/.local/share/briefdesk
   ~/.local/share/devsai/devsai.sh -p 'Run: find ~/Library/CloudStorage/GoogleDrive-*/Shared\ drives -iname "*keyword*" -type f | head -5' --max-iterations 2
   ```

### Calendar Not Working

```bash
# Check if token exists
ls -la ~/.local/share/briefdesk/google_token.pickle

# Test calendar endpoint
curl -s http://127.0.0.1:18765/calendar | python3 -m json.tool

# If authentication needed, run interactively
cd ~/.local/share/briefdesk
python3 search-server.py --auth
```

### CLI / MCP Not Working

```bash
# Check if devsai CLI works
~/.local/share/devsai/devsai.sh -p "Hello" --max-iterations 1

# Check MCP server connections
~/.local/share/devsai/devsai.sh -p "List available tools" --max-iterations 1 2>&1 | head -20

# Check CLI execution logs
grep -E "\[CLI\]" /tmp/briefdesk-server.log | tail -20
```

### Search Service Not Working

```bash
# Check if running
lsof -i:18766 || echo "Search service not running"

# View recent logs
tail -50 /tmp/briefdesk-search-service.log

# Restart search service
launchctl stop com.briefdesk.search-service && sleep 2 && launchctl start com.briefdesk.search-service

# Test directly
curl -s -X POST http://127.0.0.1:18766/search \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello", "maxIterations": 1}' | head -c 200

# Check if devsai library is loadable
cd ~/.local/share/briefdesk && node -e "import('./search-service.mjs').then(() => console.log('OK')).catch(e => console.log('Error:', e.message))"
```

**Common issues:**
- devsai not installed globally: `npm install -g devsai`
- Node not in PATH: Check LaunchAgent has correct PATH
- MCP config missing: Check `~/.local/share/briefdesk/.devsai.json` or `~/.devsai/mcp.json`

### Slack Token Expired

Symptoms: Slack search returns empty or errors

Fix:
1. Open `https://app.slack.com` in browser
2. Open DevTools → Application → Cookies
3. Copy new `d` cookie (xoxd-...) and token from localStorage (xoxc-...)
4. Update `~/.local/share/briefdesk/.devsai.json`
5. Restart server

## Search Service Operations

The search service is a Node.js process that keeps MCP connections warm:

```bash
# Check if running
lsof -i:18766

# View logs
tail -f /tmp/briefdesk-search-service.log

# Restart
launchctl stop com.briefdesk.search-service && sleep 1 && launchctl start com.briefdesk.search-service

# Test directly
curl -s -X POST http://127.0.0.1:18766/search \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello", "maxIterations": 1}'
```

**Fallback behavior:** If the search service is unavailable, the Python server automatically falls back to spawning a devsai CLI subprocess. This is slower but ensures functionality.

## Model Configuration

Model selection is stored in `~/.local/share/briefdesk/config.json`:

```bash
# View current model
cat ~/.local/share/briefdesk/config.json | python3 -c "import sys,json; print('Model:', json.load(sys.stdin).get('hubModel', 'anthropic-claude-4-5-haiku'))"

# Change model via API
curl -s -X POST http://127.0.0.1:18765/hub/settings \
  -H "Content-Type: application/json" \
  -d '{"model": "gemini-2.0-flash"}'
```

Available models (configured in Settings → Hub → AI Model):
- **Fast**: anthropic-claude-4-5-haiku (default), gemini-2.0-flash, gemini-2.5-flash-preview, grok-4-1-fast-non-reasoning
- **Balanced**: anthropic-claude-4-5-sonnet, anthropic-claude-4-sonnet, anthropic-claude-3-7-sonnet, gemini-2.5-preview
- **Best Quality**: claude-opus-4-5, gemini-3-pro, grok-4

## API Endpoints Reference

| Endpoint | Description |
|----------|-------------|
| `/hub/prep/meeting` | Get next meeting info |
| `/hub/prep/jira?meeting_id=X` | Get Jira tickets for meeting |
| `/hub/prep/confluence?meeting_id=X` | Get Confluence docs for meeting |
| `/hub/prep/slack?meeting_id=X` | Get Slack messages for meeting |
| `/hub/prep/gmail?meeting_id=X` | Get emails for meeting |
| `/hub/prep/drive?meeting_id=X` | Get Google Drive files for meeting |
| `/hub/prep/summary?meeting_id=X` | Get AI-generated meeting brief |
| `/hub/debug/cache` | View cache contents (debug) |
| `/hub/status` | Check auth status for integrations |
| `/hub/settings` | POST: Update model selection |
| `/calendar` | Get calendar events |

## Configuration Notes

| Setting | Value | Notes |
|---------|-------|-------|
| Prefetch interval | 10 minutes | Runs in background thread |
| Source cache TTL | 30 minutes | Per-meeting, per-source |
| Summary cache TTL | 45 minutes | AI briefs cached longer |
| Calendar lookback | 30 minutes | Includes recently started meetings |
| Calendar lookahead | 2 hours (prefetch), 3 hours (API) | - |
| CLI timeout | 60s (most), 90s (drive) | Configurable in code |
| Search service timeout | 60s | For HTTP calls to search service |
| Retry attempts | 2 | For failed CLI calls |
| Default AI model | anthropic-claude-4-5-haiku | Fast and capable |

## Source-Specific Behavior

| Source | Method | Timeout | Notes |
|--------|--------|---------|-------|
| Jira | Search service + Atlassian MCP | 60s | Uses `mcp_atlassian_search_issues` |
| Confluence | Search service + Atlassian MCP | 60s | Uses `mcp_atlassian_search_confluence` |
| Slack | Search service + Slack MCP | 60s | Uses `mcp_slack_search_messages` |
| Gmail | Search service + Gmail MCP | 60s | Uses `mcp_gmail_search_emails` |
| Drive | Search service + `find` command | 90s | Searches local CloudStorage folder |
| AI Brief | Search service (8 iterations) | 120s | Summarizes all sources |

**Note:** All sources automatically fall back to CLI subprocess if search service is unavailable.

## Best Practices

1. **Always check logs first** when debugging issues
2. **Use LaunchAgent restart** for production, manual for debugging
3. **Deploy all files** (search-server.py, search-service.mjs, lib/, js/, start.html) when making changes
4. **Hard refresh Safari** (Cmd+Shift+R) after frontend changes
5. **Check FDA** if Drive search or history search stops working
6. **Monitor prefetch logs** to understand what's being cached
7. **Test search service first** before testing CLI - it's the primary path
8. **Check search service logs** (`/tmp/briefdesk-search-service.log`) for AI query issues
9. **Restart both servers** (API and search service) after Python/Node code changes
10. **Use fast models** (Claude 4.5 Haiku) for quicker responses during testing
