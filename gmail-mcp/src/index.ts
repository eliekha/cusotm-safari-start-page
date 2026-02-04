#!/usr/bin/env node
/**
 * BriefDesk Gmail MCP Server
 * 
 * A minimal, auditable MCP server for Gmail integration.
 * READ-ONLY: Cannot send, modify, or delete emails.
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
import { GmailClient } from './gmail-client.js';

// Tool definitions
const TOOLS: Tool[] = [
  {
    name: 'gmail_search',
    description: 'Search for emails in Gmail. Uses Gmail search syntax (same as web interface). Examples: "from:john@example.com", "subject:meeting", "is:unread", "after:2024/01/01"',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Gmail search query (supports Gmail search operators)',
        },
        maxResults: {
          type: 'number',
          description: 'Maximum number of results to return (default: 10, max: 50)',
          default: 10,
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'gmail_read',
    description: 'Read the full content of a specific email by its ID',
    inputSchema: {
      type: 'object',
      properties: {
        messageId: {
          type: 'string',
          description: 'The Gmail message ID',
        },
      },
      required: ['messageId'],
    },
  },
  {
    name: 'gmail_list',
    description: 'List recent emails from inbox or specific folder/label',
    inputSchema: {
      type: 'object',
      properties: {
        label: {
          type: 'string',
          description: 'Label/folder to list from (default: INBOX). Common labels: INBOX, SENT, DRAFT, SPAM, TRASH, STARRED, IMPORTANT',
          default: 'INBOX',
        },
        maxResults: {
          type: 'number',
          description: 'Maximum number of results (default: 10, max: 50)',
          default: 10,
        },
      },
    },
  },
  {
    name: 'gmail_thread',
    description: 'Get all messages in an email thread/conversation',
    inputSchema: {
      type: 'object',
      properties: {
        threadId: {
          type: 'string',
          description: 'The Gmail thread ID',
        },
      },
      required: ['threadId'],
    },
  },
  {
    name: 'gmail_labels',
    description: 'List all available Gmail labels/folders',
    inputSchema: {
      type: 'object',
      properties: {},
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
  
  const gmailClient = new GmailClient(authClient);
  
  // Create MCP server
  const server = new Server(
    {
      name: 'briefdesk-gmail-mcp',
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
        case 'gmail_search': {
          const query = args?.query as string;
          const maxResults = Math.min((args?.maxResults as number) || 10, 50);
          
          const result = await gmailClient.search(query, maxResults);
          
          const formattedEmails = result.emails.map(email => ({
            id: email.id,
            threadId: email.threadId,
            subject: email.subject,
            from: email.from,
            to: email.to,
            date: email.date,
            snippet: email.snippet,
            labels: email.labelIds,
          }));
          
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  query,
                  resultCount: formattedEmails.length,
                  estimatedTotal: result.resultSizeEstimate,
                  emails: formattedEmails,
                }, null, 2),
              },
            ],
          };
        }
        
        case 'gmail_read': {
          const messageId = args?.messageId as string;
          
          const email = await gmailClient.readEmail(messageId);
          
          return {
            content: [
              {
                type: 'text',
                text: `# ${email.subject}\n\n` +
                  `**From:** ${email.from}\n` +
                  `**To:** ${email.to}\n` +
                  (email.cc ? `**Cc:** ${email.cc}\n` : '') +
                  `**Date:** ${email.date}\n` +
                  (email.attachments.length > 0 
                    ? `**Attachments:** ${email.attachments.map(a => a.filename).join(', ')}\n`
                    : '') +
                  `\n---\n\n${email.body}`,
              },
            ],
          };
        }
        
        case 'gmail_list': {
          const label = (args?.label as string) || 'INBOX';
          const maxResults = Math.min((args?.maxResults as number) || 10, 50);
          
          const result = await gmailClient.list([label], maxResults);
          
          const formattedEmails = result.emails.map(email => ({
            id: email.id,
            threadId: email.threadId,
            subject: email.subject,
            from: email.from,
            date: email.date,
            snippet: email.snippet,
          }));
          
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  label,
                  emailCount: formattedEmails.length,
                  emails: formattedEmails,
                }, null, 2),
              },
            ],
          };
        }
        
        case 'gmail_thread': {
          const threadId = args?.threadId as string;
          
          const messages = await gmailClient.getThread(threadId);
          
          const formattedThread = messages.map(email => ({
            id: email.id,
            subject: email.subject,
            from: email.from,
            to: email.to,
            date: email.date,
            body: email.body,
          }));
          
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  threadId,
                  messageCount: formattedThread.length,
                  messages: formattedThread,
                }, null, 2),
              },
            ],
          };
        }
        
        case 'gmail_labels': {
          const labels = await gmailClient.getLabels();
          
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  labelCount: labels.length,
                  labels: labels.map(l => ({
                    id: l.id,
                    name: l.name,
                    type: l.type,
                  })),
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
  
  console.error('BriefDesk Gmail MCP server running (READ-ONLY)');
}

// Run
main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
