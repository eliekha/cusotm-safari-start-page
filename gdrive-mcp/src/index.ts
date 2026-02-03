#!/usr/bin/env node
/**
 * BriefDesk Google Drive MCP Server
 * 
 * A minimal, auditable MCP server for Google Drive integration.
 * Uses only official Google and Anthropic SDKs - no third-party code.
 * 
 * Usage:
 *   npm run auth     # One-time OAuth authentication
 *   npm run start    # Start MCP server
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool,
} from '@modelcontextprotocol/sdk/types.js';

import { getAuthenticatedClient, runAuthFlow, isAuthenticated } from './auth.js';
import { DriveClient } from './drive-client.js';

// Tool definitions
const TOOLS: Tool[] = [
  {
    name: 'gdrive_search',
    description: 'Search for files in Google Drive using full-text search. Searches file names and content.',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search query - searches in file names and content',
        },
        maxResults: {
          type: 'number',
          description: 'Maximum number of results to return (default: 20, max: 100)',
          default: 20,
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'gdrive_read',
    description: 'Read the content of a file from Google Drive. Google Docs are exported as Markdown, Sheets as CSV, Slides as plain text.',
    inputSchema: {
      type: 'object',
      properties: {
        fileId: {
          type: 'string',
          description: 'The Google Drive file ID',
        },
      },
      required: ['fileId'],
    },
  },
  {
    name: 'gdrive_list',
    description: 'List files in a Google Drive folder',
    inputSchema: {
      type: 'object',
      properties: {
        folderId: {
          type: 'string',
          description: 'Folder ID to list (default: root folder)',
          default: 'root',
        },
        maxResults: {
          type: 'number',
          description: 'Maximum number of results (default: 50)',
          default: 50,
        },
      },
    },
  },
];

/**
 * Main MCP server
 */
async function main() {
  // Check for auth command
  if (process.argv[2] === 'auth') {
    await runAuthFlow();
    process.exit(0);
  }
  
  // Check authentication
  if (!isAuthenticated()) {
    console.error('Not authenticated. Run with "auth" argument first:');
    console.error('  npm run auth');
    process.exit(1);
  }
  
  // Get authenticated client
  const authClient = await getAuthenticatedClient();
  if (!authClient) {
    console.error('Failed to get authenticated client. Try running auth again.');
    process.exit(1);
  }
  
  const driveClient = new DriveClient(authClient);
  
  // Create MCP server
  const server = new Server(
    {
      name: 'briefdesk-gdrive-mcp',
      version: '1.0.0',
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );
  
  // Handle list tools
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return { tools: TOOLS };
  });
  
  // Handle tool calls
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    
    try {
      switch (name) {
        case 'gdrive_search': {
          const query = args?.query as string;
          const maxResults = Math.min((args?.maxResults as number) || 20, 100);
          
          const result = await driveClient.search(query, maxResults);
          
          const formattedFiles = result.files.map(file => ({
            id: file.id,
            name: file.name,
            type: formatMimeType(file.mimeType),
            url: driveClient.getWebViewUrl(file),
            modified: file.modifiedTime,
          }));
          
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  query,
                  resultCount: formattedFiles.length,
                  files: formattedFiles,
                }, null, 2),
              },
            ],
          };
        }
        
        case 'gdrive_read': {
          const fileId = args?.fileId as string;
          
          const result = await driveClient.readFile(fileId);
          
          return {
            content: [
              {
                type: 'text',
                text: `# ${result.name}\n\nType: ${result.mimeType}\n\n---\n\n${result.content}`,
              },
            ],
          };
        }
        
        case 'gdrive_list': {
          const folderId = (args?.folderId as string) || 'root';
          const maxResults = Math.min((args?.maxResults as number) || 50, 100);
          
          const result = await driveClient.listFolder(folderId, maxResults);
          
          const formattedFiles = result.files.map(file => ({
            id: file.id,
            name: file.name,
            type: formatMimeType(file.mimeType),
            url: driveClient.getWebViewUrl(file),
          }));
          
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  folderId,
                  fileCount: formattedFiles.length,
                  files: formattedFiles,
                }, null, 2),
              },
            ],
          };
        }
        
        default:
          throw new Error(`Unknown tool: ${name}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        content: [
          {
            type: 'text',
            text: `Error: ${message}`,
          },
        ],
        isError: true,
      };
    }
  });
  
  // Start server
  const transport = new StdioServerTransport();
  await server.connect(transport);
  
  console.error('BriefDesk Google Drive MCP server running');
}

/**
 * Format MIME type to human-readable string
 */
function formatMimeType(mimeType: string): string {
  const mapping: Record<string, string> = {
    'application/vnd.google-apps.document': 'Google Doc',
    'application/vnd.google-apps.spreadsheet': 'Google Sheet',
    'application/vnd.google-apps.presentation': 'Google Slides',
    'application/vnd.google-apps.folder': 'Folder',
    'application/vnd.google-apps.drawing': 'Google Drawing',
    'application/pdf': 'PDF',
    'text/plain': 'Text',
    'text/markdown': 'Markdown',
    'text/csv': 'CSV',
    'application/json': 'JSON',
  };
  
  return mapping[mimeType] || mimeType;
}

// Run
main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
