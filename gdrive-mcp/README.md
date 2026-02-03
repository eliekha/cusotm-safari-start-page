# BriefDesk Google Drive MCP Server

A minimal, fully auditable MCP server for Google Drive integration.

## Security

- **No third-party code** - Only uses official Google (`googleapis`) and Anthropic (`@modelcontextprotocol/sdk`) packages
- **Read-only access** - Uses `drive.readonly` scope, cannot modify or delete files
- **Local credentials** - OAuth tokens stored locally in `credentials/` folder
- **Fully auditable** - ~300 lines of code you can review

## Setup

### If you already have BriefDesk Google credentials (Calendar/Gmail)

The MCP reuses your existing OAuth credentials from `~/.local/share/briefdesk/google_credentials.json`.

1. **Enable Drive API** in your Google Cloud project:
   - Go to [API Library](https://console.cloud.google.com/apis/library)
   - Search for "Google Drive API" and enable it
   - Also enable "Google Sheets API" and "Google Docs API" if needed

2. **Authenticate for Drive**:
   ```bash
   cd gdrive-mcp
   npm install
   npm run build
   npm run auth
   ```

This creates a separate Drive token (`google_drive_token.json`) without affecting your calendar auth.

### If you don't have existing credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/projectcreate) and create a project
2. Enable the Google Drive API
3. Configure OAuth consent screen (add `drive.readonly` scope)
4. Create OAuth client ID (Desktop app)
5. Save credentials as `~/.local/share/briefdesk/google_credentials.json`
6. Run `npm run auth`

## Usage

### With BriefDesk

The server is automatically used when Drive is selected as a source in AI search.

### Standalone

```bash
npm run start
```

### MCP Config

Add to your MCP config:

```json
{
  "mcpServers": {
    "gdrive": {
      "command": "node",
      "args": ["/path/to/briefdesk/gdrive-mcp/dist/index.js"]
    }
  }
}
```

## Tools

### gdrive_search

Search files by content and name.

```json
{
  "query": "quarterly report",
  "maxResults": 20
}
```

### gdrive_read

Read file content. Google Docs → Markdown, Sheets → CSV, Slides → Text.

```json
{
  "fileId": "1abc123..."
}
```

### gdrive_list

List files in a folder.

```json
{
  "folderId": "root",
  "maxResults": 50
}
```

## File Structure

```
gdrive-mcp/
├── src/
│   ├── index.ts        # MCP server (main entry)
│   ├── auth.ts         # OAuth authentication
│   └── drive-client.ts # Drive API wrapper
├── dist/               # Compiled JS
├── package.json
└── README.md

# Credentials stored in shared BriefDesk config:
~/.local/share/briefdesk/
├── google_credentials.json     # OAuth client keys (shared)
├── google_token.pickle         # Calendar token
└── google_drive_token.json     # Drive token (created by this MCP)
```

## Revoking Access

To revoke access:
1. Go to [Google Account Permissions](https://myaccount.google.com/permissions)
2. Find "BriefDesk Drive" and remove access
3. Delete `credentials/token.json`
