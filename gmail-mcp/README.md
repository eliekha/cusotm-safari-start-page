# BriefDesk Gmail MCP Server

A minimal, auditable MCP (Model Context Protocol) server for Gmail integration.

**READ-ONLY**: This server cannot send, modify, or delete emails. It only provides search and read access.

## Features

- **gmail_search** - Search emails using Gmail search syntax
- **gmail_read** - Read full email content by ID
- **gmail_list** - List recent emails from inbox or labels
- **gmail_thread** - Get all messages in a conversation
- **gmail_labels** - List available Gmail labels/folders

## Security

- Uses `gmail.readonly` scope only - no write access
- No third-party dependencies beyond Google and Anthropic official SDKs
- Credentials stored locally in `~/.gmail-mcp/`
- Fully auditable source code

## Setup

### Prerequisites

1. Node.js 18+
2. Google Cloud Project with Gmail API enabled
3. OAuth 2.0 credentials

### Installation

```bash
cd gmail-mcp
npm install
npm run build
```

### Authentication

1. Download OAuth credentials from Google Cloud Console
2. Save as `~/.gmail-mcp/gcp-oauth.keys.json`
3. Run authentication:

```bash
npm run auth
```

This opens a browser for Google sign-in. Tokens are saved to `~/.gmail-mcp/credentials.json`.

### Running

```bash
npm run start
```

## MCP Configuration

Add to your `~/.devsai/mcp.json`:

```json
{
  "mcpServers": {
    "gmail": {
      "command": "node",
      "args": ["/path/to/gmail-mcp/dist/index.js"]
    }
  }
}
```

## Search Syntax

The `gmail_search` tool supports Gmail's native search operators:

- `from:john@example.com` - Emails from specific sender
- `to:jane@example.com` - Emails to specific recipient
- `subject:meeting` - Emails with subject containing "meeting"
- `is:unread` - Unread emails
- `is:starred` - Starred emails
- `after:2024/01/01` - Emails after date
- `before:2024/12/31` - Emails before date
- `has:attachment` - Emails with attachments
- `filename:pdf` - Emails with PDF attachments
- Combine with AND/OR: `from:john AND subject:project`
