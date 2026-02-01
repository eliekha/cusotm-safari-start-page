---
name: server-operations
description: Manage Safari Start Page servers. Check status, view logs, restart servers, deploy changes, and troubleshoot issues. Use when the user needs help with server operations, debugging data issues, or deploying updates.
---

# Safari Start Page Server Operations

Standardized workflows for managing the Safari Start Page local servers.

## Server Architecture

The Safari Start Page runs two local servers:

| Server | Port | Purpose |
|--------|------|---------|
| Static File Server | 8765 | Serves `start.html` and static assets |
| Search/API Server | 18765 | Handles calendar, meeting prep, search, and AI features |

## File Locations

```
Production (deployed):
~/.local/share/safari_start_page/
├── search-server.py      # Main API server
├── start.html            # Frontend
├── python3               # Local Python binary (for FDA)
├── google_token.pickle   # Google Calendar/Drive auth token
└── .devsai.json          # MCP server configuration

~/.local/share/devsai/
├── node                  # Local Node binary (for FDA)
├── devsai.sh             # Wrapper script for CLI
├── dist/                 # devsai CLI code
└── node_modules/         # CLI dependencies

Source (development):
~/Documents/safari_start_page/
├── search-server.py      # Edit here, then deploy
├── start.html
├── install.sh
└── ...
```

## Full Disk Access Requirements

Both binaries need FDA for CloudStorage access:

| Binary | Path | Purpose |
|--------|------|---------|
| Python | `~/.local/share/safari_start_page/python3` | Safari history, server |
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

# Check LaunchAgent status
launchctl list | grep -E "startpage|safari"

# Quick health check
curl -s http://127.0.0.1:18765/hub/prep/meeting | python3 -c "import sys,json; d=json.load(sys.stdin); print('Meeting:', d.get('meeting',{}).get('title','None')[:50])"
```

## Viewing Logs

The main log file is `/tmp/safari-hub-server.log`.

```bash
# View recent logs
tail -50 /tmp/safari-hub-server.log

# Follow logs in real-time
tail -f /tmp/safari-hub-server.log

# Filter by component
tail -f /tmp/safari-hub-server.log | grep -E "\[Prefetch\]"   # Background prefetch
tail -f /tmp/safari-hub-server.log | grep -E "\[CLI\]"        # CLI calls to devsai
tail -f /tmp/safari-hub-server.log | grep -E "\[API\]"        # API endpoint logs
tail -f /tmp/safari-hub-server.log | grep -E "\[Drive\]"      # Drive search logs
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
cd ~/.local/share/safari_start_page
./python3 -u search-server.py 2>&1 | tee /tmp/safari-hub-server.log
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

After editing files in `~/Documents/safari_start_page/`:

```bash
# 1. Deploy both frontend and backend
cp ~/Documents/safari_start_page/search-server.py ~/.local/share/safari_start_page/
cp ~/Documents/safari_start_page/start.html ~/.local/share/safari_start_page/

# 2. Restart server
lsof -ti:18765 | xargs kill -9 2>/dev/null
launchctl unload ~/Library/LaunchAgents/com.startpage.search.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.startpage.search.plist

# 3. Wait and verify
sleep 3
curl -s http://127.0.0.1:18765/hub/prep/meeting | python3 -c "import sys,json; print('Server OK')" && echo "Deployed successfully"
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
   grep -E "Prefetch|CLI" /tmp/safari-hub-server.log | tail -30
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
   cd ~/.local/share/safari_start_page
   ~/.local/share/devsai/devsai.sh -p 'Run: find ~/Library/CloudStorage/GoogleDrive-*/Shared\ drives -iname "*keyword*" -type f | head -5' --max-iterations 2
   ```

### Calendar Not Working

```bash
# Check if token exists
ls -la ~/.local/share/safari_start_page/google_token.pickle

# Test calendar endpoint
curl -s http://127.0.0.1:18765/calendar | python3 -m json.tool

# If authentication needed, run interactively
cd ~/.local/share/safari_start_page
./python3 search-server.py --auth
```

### CLI / MCP Not Working

```bash
# Check if devsai CLI works
~/.local/share/devsai/devsai.sh -p "Hello" --max-iterations 1

# Check MCP server connections
~/.local/share/devsai/devsai.sh -p "List available tools" --max-iterations 1 2>&1 | head -20

# Check CLI execution logs
grep -E "\[CLI\]" /tmp/safari-hub-server.log | tail -20
```

### Slack Token Expired

Symptoms: Slack search returns empty or errors

Fix:
1. Open `https://app.slack.com` in browser
2. Open DevTools → Application → Cookies
3. Copy new `d` cookie (xoxd-...) and token from localStorage (xoxc-...)
4. Update `~/.local/share/safari_start_page/.devsai.json`
5. Restart server

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
| Retry attempts | 2 | For failed CLI calls |

## Source-Specific Behavior

| Source | Method | Timeout | Notes |
|--------|--------|---------|-------|
| Jira | CLI + Atlassian MCP | 60s | Uses `mcp_atlassian_search_issues` |
| Confluence | CLI + Atlassian MCP | 60s | Uses `mcp_atlassian_search_confluence` |
| Slack | CLI + Slack MCP | 60s | Uses `mcp_slack_search_messages` |
| Gmail | CLI + Gmail MCP | 60s | Uses `mcp_gmail_search_emails` |
| Drive | CLI + `find` command | 90s | Searches local CloudStorage folder |

## Best Practices

1. **Always check logs first** when debugging issues
2. **Use LaunchAgent restart** for production, manual for debugging
3. **Deploy both files** (search-server.py and start.html) when making changes
4. **Hard refresh Safari** (Cmd+Shift+R) after frontend changes
5. **Check FDA** if Drive search or history search stops working
6. **Monitor prefetch logs** to understand what's being cached
7. **Test CLI manually** before assuming server issues
