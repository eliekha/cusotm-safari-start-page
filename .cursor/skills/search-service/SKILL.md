---
name: search-service
description: Node.js search service that keeps MCP connections warm for fast AI queries. Use when debugging AI query performance, search service issues, or model configuration.
---

# BriefDesk Search Service

The search service (`search-service.mjs`) is a Node.js HTTP server that keeps MCP connections alive, eliminating cold start delays for AI queries.

## Architecture

```
┌─────────────────┐     HTTP      ┌──────────────────┐
│  Python Server  │ ───────────▶ │  Search Service  │
│  (port 18765)   │              │  (port 18766)    │
└─────────────────┘              └──────────────────┘
                                          │
                                          ▼
                               ┌──────────────────────┐
                               │   devsai Library     │
                               │  (loaded once)       │
                               └──────────────────────┘
                                          │
                         ┌────────────────┼────────────────┐
                         ▼                ▼                ▼
                   ┌──────────┐    ┌──────────┐    ┌──────────┐
                   │  Slack   │    │ Atlassian│    │  Gmail   │
                   │   MCP    │    │   MCP    │    │   MCP    │
                   └──────────┘    └──────────┘    └──────────┘
```

## Key Files

| File | Location | Purpose |
|------|----------|---------|
| `search-service.mjs` | `~/Documents/briefdesk/` | Source file |
| `search-service.mjs` | `~/.local/share/briefdesk/` | Deployed file |
| `com.briefdesk.search-service.plist` | `~/Library/LaunchAgents/` | LaunchAgent |
| `/tmp/briefdesk-search-service.log` | - | Log file |

## API Endpoints

### POST /search

Execute an AI query with MCP tools.

**Request:**
```json
{
  "prompt": "Search Slack for messages about project X",
  "sources": ["slack", "atlassian"],  // optional: filter available tools
  "systemPrompt": "You are a helpful assistant",  // optional
  "maxIterations": 5,  // optional, default 5
  "model": "anthropic-claude-4-5-haiku"  // optional, uses config default
}
```

**Response:**
```json
{
  "result": "Found 3 messages about project X...",
  "iterations": 3
}
```

### GET /health

Check service status.

**Response:**
```json
{
  "status": "ok",
  "devsaiLoaded": true
}
```

## Source Filtering

The `sources` parameter filters which MCP tools are available:

| Source | Tool Prefixes Enabled |
|--------|----------------------|
| `slack` | `mcp_slack_` |
| `atlassian` | `mcp_atlassian_` |
| `gmail` | `mcp_gmail_` |
| `drive` | `mcp_filesystem_`, `execute_shell` |

Example: `sources: ['slack']` only allows Slack MCP tools.

## Model Configuration

The service uses the model specified in the request, or falls back to the configured default:

1. Request `model` parameter (if provided)
2. `config.json` → `hubModel` setting
3. Default: `anthropic-claude-4-5-haiku`

**Available models:**
- **Fast**: `anthropic-claude-4-5-haiku`, `gemini-2.0-flash`, `gemini-2.5-flash-preview`, `grok-4-1-fast-non-reasoning`
- **Balanced**: `anthropic-claude-4-5-sonnet`, `anthropic-claude-4-sonnet`, `anthropic-claude-3-7-sonnet`, `gemini-2.5-preview`
- **Best Quality**: `claude-opus-4-5`, `gemini-3-pro`, `grok-4`

## Quick Commands

```bash
# Check if running
lsof -i:18766

# View logs (live)
tail -f /tmp/briefdesk-search-service.log

# Restart
launchctl stop com.briefdesk.search-service && sleep 1 && launchctl start com.briefdesk.search-service

# Test health
curl -s http://127.0.0.1:18766/health

# Test search
curl -s -X POST http://127.0.0.1:18766/search \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, list your available tools", "maxIterations": 1}'

# Test with specific model
curl -s -X POST http://127.0.0.1:18766/search \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello", "maxIterations": 1, "model": "gemini-2.0-flash"}'
```

## Performance Comparison

| Method | First Query | Subsequent Queries | MCP State |
|--------|-------------|-------------------|-----------|
| CLI subprocess | ~15-25s | ~10-15s | Restarts each time |
| Search service | ~8-12s | ~3-8s | Stays connected |

## Fallback Behavior

If the search service is unavailable (port 18766 not responding), the Python server automatically falls back to spawning a `devsai` CLI subprocess:

```python
# In lib/cli.py
try:
    result = _call_search_service(prompt, sources, ...)
    if result is not None:
        return result
except Exception as e:
    logger.warning(f"Search service failed: {e}")

# Fallback to subprocess
return _call_cli_subprocess(source, prompt, timeout, max_retries)
```

## Troubleshooting

### Service not starting

```bash
# Check LaunchAgent
launchctl list | grep search-service

# Check for port conflicts
lsof -i:18766

# Check Node is available
which node
~/.local/share/devsai/node --version

# Start manually to see errors
cd ~/.local/share/briefdesk
~/.local/share/devsai/node search-service.mjs
```

### devsai library not loading

```bash
# Check if devsai is installed
npm list -g devsai

# Check library paths in service
grep -E "import|require" ~/.local/share/briefdesk/search-service.mjs

# Test import manually
cd ~/.local/share/briefdesk
~/.local/share/devsai/node -e "
import('./search-service.mjs')
  .then(() => console.log('Service loads OK'))
  .catch(e => console.error('Load failed:', e))
"
```

### MCP tools not available

```bash
# Check MCP config exists
ls -la ~/.local/share/briefdesk/.devsai.json
ls -la ~/.devsai/mcp.json

# Test MCP tools via CLI
~/.local/share/devsai/devsai.sh -p "List available tools" --max-iterations 1 2>&1 | head -30
```

### Slow queries

1. Check iteration count in logs - high counts mean complex tool chains
2. Try a faster model: `gemini-2.0-flash` or `anthropic-claude-4-5-haiku`
3. Check MCP server response times in logs
4. Verify network connectivity to external services (Slack, Atlassian, Gmail APIs)

## Logs Analysis

Key log patterns:

```bash
# Successful query
[SearchService] Query received: "Search Slack..."
[SearchService] Using model: anthropic-claude-4-5-haiku
[SearchService] Completed in 3241ms (2 iterations)

# Tool filtering
[SearchService] Filtering tools for sources: slack,atlassian
[SearchService] Available tools: 12 -> 6 after filtering

# Errors
[SearchService] Error executing query: Connection refused
[SearchService] devsai library not loaded, returning error
```

## Deploying Changes

After editing `search-service.mjs`:

```bash
# Copy to deployed location
cp ~/Documents/briefdesk/search-service.mjs ~/.local/share/briefdesk/

# Restart service
launchctl stop com.briefdesk.search-service && sleep 1 && launchctl start com.briefdesk.search-service

# Verify
sleep 2 && curl -s http://127.0.0.1:18766/health
```
