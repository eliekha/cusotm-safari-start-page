#!/usr/bin/env node
/**
 * BriefDesk AI Search Service
 * 
 * A lightweight Node.js service that keeps MCP connections warm
 * for fast AI-powered searches across Slack, Jira, Gmail, etc.
 * 
 * Usage:
 *   node search-service.js
 * 
 * Endpoints:
 *   GET /health - Health check
 *   GET /status - MCP server connection status
 *   POST /search - AI-powered search across sources
 *   POST /query - Raw AI query with MCP tools
 */

import http from 'http';
import { URL } from 'url';

// Import devsai library components from local installation
// Uses ~/.local/share/devsai/dist/ which has Full Disk Access
import os from 'os';
import path from 'path';

const HOME = os.homedir();
const LOCAL_DEVSAI_PATH = path.join(HOME, '.local/share/devsai/dist/lib');

let MCPManager, createApiClient, getMCPToolDefinitions, executeMCPTool, isMCPTool;
let isAuthenticated, getConfig;
let CLI_TOOLS, executeSearchFiles, executeFindFiles, executeReadFile, executeListDirectory;

const PORT = parseInt(process.env.SEARCH_SERVICE_PORT || '19765', 10);
const HOST = '127.0.0.1';

// State
let mcpManager = null;
let apiClient = null;
let initialized = false;
let initError = null;

// Retry configuration for MCP servers
const MCP_RETRY_CONFIG = {
  maxRetries: 3,
  retryDelayMs: 5000,  // 5 seconds between retries
  retryableErrors: ['empty cache', 'not found in empty cache', 'cache not ready'],
};

/**
 * Dynamic import of devsai modules from local installation
 */
async function loadDevsaiModules() {
  try {
    // Use the local devsai installation (has Full Disk Access)
    const mcpModule = await import(`file://${LOCAL_DEVSAI_PATH}/mcp/index.js`);
    MCPManager = mcpModule.MCPManager;
    getMCPToolDefinitions = mcpModule.getMCPToolDefinitions;
    executeMCPTool = mcpModule.executeMCPTool;
    isMCPTool = mcpModule.isMCPTool;
    
    const apiModule = await import(`file://${LOCAL_DEVSAI_PATH}/api-client.js`);
    createApiClient = apiModule.createApiClient;
    
    const configModule = await import(`file://${LOCAL_DEVSAI_PATH}/config.js`);
    isAuthenticated = configModule.isAuthenticated;
    getConfig = configModule.getConfig;
    
    // Load CLI tools for file operations
    const cliToolsModule = await import(`file://${LOCAL_DEVSAI_PATH}/cli-tools.js`);
    CLI_TOOLS = cliToolsModule.CLI_TOOLS;
    executeSearchFiles = cliToolsModule.executeSearchFiles;
    executeFindFiles = cliToolsModule.executeFindFiles;
    executeReadFile = cliToolsModule.executeReadFile;
    executeListDirectory = cliToolsModule.executeListDirectory;
    
    console.log('[SearchService] Loaded devsai modules from:', LOCAL_DEVSAI_PATH);
    return true;
  } catch (err) {
    console.error('[SearchService] Failed to load devsai modules:', err.message);
    initError = err.message;
    return false;
  }
}

/**
 * Check if an error is retryable (cache-related)
 */
function isRetryableError(error) {
  if (!error) return false;
  const errorLower = error.toLowerCase();
  return MCP_RETRY_CONFIG.retryableErrors.some(re => errorLower.includes(re));
}

/**
 * Sleep for a given number of milliseconds
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Retry failed MCP servers that have retryable errors
 */
async function retryFailedServers() {
  if (!mcpManager) return;
  
  const statuses = mcpManager.getServerStatuses();
  const failedServers = statuses.filter(s => 
    s.status === 'error' && isRetryableError(s.error)
  );
  
  if (failedServers.length === 0) return;
  
  console.log(`[SearchService] Retrying ${failedServers.length} failed server(s) with cache errors...`);
  
  for (const server of failedServers) {
    for (let attempt = 1; attempt <= MCP_RETRY_CONFIG.maxRetries; attempt++) {
      console.log(`[SearchService] Retry ${attempt}/${MCP_RETRY_CONFIG.maxRetries} for ${server.name}...`);
      
      try {
        // Disconnect and reconnect the server
        await mcpManager.disconnectServer(server.name);
        await sleep(MCP_RETRY_CONFIG.retryDelayMs);
        await mcpManager.connectServer(server.name);
        
        // Check if it succeeded
        const newStatuses = mcpManager.getServerStatuses();
        const newStatus = newStatuses.find(s => s.name === server.name);
        
        if (newStatus?.status === 'connected') {
          console.log(`[SearchService] ✓ ${server.name} reconnected successfully (${newStatus.toolCount} tools)`);
          break;
        } else if (newStatus?.status === 'error') {
          console.log(`[SearchService] ✗ ${server.name} retry ${attempt} failed: ${newStatus.error?.substring(0, 60)}`);
          if (!isRetryableError(newStatus.error)) {
            console.log(`[SearchService] Error not retryable, stopping retries for ${server.name}`);
            break;
          }
        }
      } catch (err) {
        console.log(`[SearchService] ✗ ${server.name} retry ${attempt} error: ${err.message}`);
      }
      
      // Wait before next retry (unless this was the last attempt)
      if (attempt < MCP_RETRY_CONFIG.maxRetries) {
        await sleep(MCP_RETRY_CONFIG.retryDelayMs);
      }
    }
  }
}

/**
 * Initialize MCP connections and API client
 */
async function initialize() {
  console.log('[SearchService] Initializing...');
  
  // Load modules
  const loaded = await loadDevsaiModules();
  if (!loaded) {
    initError = 'Failed to load devsai modules';
    return false;
  }
  
  // Check authentication
  if (!isAuthenticated()) {
    initError = 'Not authenticated. Run: devsai login';
    console.error('[SearchService]', initError);
    return false;
  }
  
  // Create API client
  apiClient = createApiClient();
  console.log('[SearchService] API client created');
  
  // Initialize MCP manager
  mcpManager = MCPManager.getInstance();
  mcpManager.setWorkingDir(process.cwd());
  
  // Connect to all enabled MCP servers
  console.log('[SearchService] Connecting to MCP servers...');
  try {
    await mcpManager.connectAllEnabled();
    let statuses = mcpManager.getServerStatuses();
    let connected = statuses.filter(s => s.status === 'connected');
    let errors = statuses.filter(s => s.status === 'error');
    
    console.log(`[SearchService] Initial connection: ${connected.length} servers`);
    for (const s of connected) {
      console.log(`  ✓ ${s.name} (${s.toolCount} tools)`);
    }
    for (const s of errors) {
      console.log(`  ✗ ${s.name}: ${s.error?.substring(0, 60)}`);
    }
    
    // Retry servers that failed with cache-related errors
    const retryableErrors = errors.filter(s => isRetryableError(s.error));
    if (retryableErrors.length > 0) {
      console.log(`[SearchService] ${retryableErrors.length} server(s) have retryable errors, scheduling retry...`);
      // Wait a bit for caches to load, then retry
      await sleep(MCP_RETRY_CONFIG.retryDelayMs);
      await retryFailedServers();
      
      // Log final status
      statuses = mcpManager.getServerStatuses();
      connected = statuses.filter(s => s.status === 'connected');
      errors = statuses.filter(s => s.status === 'error');
      console.log(`[SearchService] After retries: ${connected.length} connected, ${errors.length} errors`);
    }
  } catch (err) {
    console.error('[SearchService] MCP connection error:', err.message);
    // Continue anyway - some servers may have connected
  }
  
  initialized = true;
  console.log('[SearchService] Ready on port', PORT);
  return true;
}

/**
 * Execute an AI query with MCP tools
 */
async function executeQuery(prompt, options = {}) {
  if (!initialized || !apiClient) {
    throw new Error('Service not initialized');
  }
  
  const {
    model = 'gpt-4o',
    maxIterations = 10,
    systemPrompt = null,
    sources = null,  // Filter to specific sources: ['slack', 'jira', 'gmail', 'confluence']
  } = options;
  
  // Get available MCP tools
  let tools = [];
  try {
    tools = getMCPToolDefinitions();
    
    // Filter tools by source if specified
    if (sources && sources.length > 0) {
      const beforeCount = tools.length;
      tools = tools.filter(t => {
        const name = t.function.name.toLowerCase();
        
        // Include all atlassian tools when jira or confluence is selected
        if (sources.some(s => ['jira', 'confluence'].includes(s.toLowerCase()))) {
          if (name.includes('atlassian')) {
            return true;
          }
        }
        
        return sources.some(s => name.includes(s.toLowerCase()));
      });
      
      // Add CLI file tools when drive is in sources
      if (sources.some(s => s.toLowerCase() === 'drive')) {
        const fileTools = CLI_TOOLS.filter(t => 
          ['search_files', 'find_files', 'read_file', 'list_directory'].includes(t.function.name)
        );
        tools = [...tools, ...fileTools];
        console.log(`[SearchService] Added ${fileTools.length} CLI file tools for drive`);
      }
      
      console.log(`[SearchService] Filtered tools: ${beforeCount} -> ${tools.length} for sources: ${sources.join(', ')}`);
    }
  } catch (err) {
    console.error('[SearchService] Error getting MCP tools:', err.message);
  }
  
  // Build messages
  const messages = [];
  
  // System message
  // Build system prompt based on sources
  let defaultSystem = `You are a search assistant with access to various tools. You MUST use the available tools to search and retrieve information. Do not ask the user for configuration - use the tools to discover what you need.

Return your findings as a JSON array with objects containing:
- title: string (item title or subject)
- snippet: string (brief preview/excerpt)
- url: string (link to the item)
- source: string (slack, jira, confluence, gmail, drive)
- metadata: object (optional extra info like date, author, etc.)

Be concise. Focus on the most relevant results.`;

  // Add Atlassian-specific instructions if jira/confluence is in sources
  if (sources && sources.some(s => ['jira', 'confluence'].includes(s.toLowerCase()))) {
    defaultSystem += `

IMPORTANT FOR JIRA/CONFLUENCE:
1. FIRST call mcp_atlassian_getAccessibleAtlassianResources to get the cloudId
2. THEN use that cloudId with mcp_atlassian_searchJiraIssuesUsingJql or mcp_atlassian_searchConfluenceUsingCql
3. NEVER ask the user for cloudId - always discover it with step 1`;
  }
  
  // Add Drive-specific instructions
  if (sources && sources.some(s => s.toLowerCase() === 'drive')) {
    // Read config to get explicit Google Drive path
    let gdriveBase = path.join(HOME, 'Library/CloudStorage/GoogleDrive-*');
    try {
      const fs = await import('fs');
      const configPath = path.join(HOME, '.local/share/briefdesk/config.json');
      if (fs.existsSync(configPath)) {
        const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        if (config.google_drive_path) {
          gdriveBase = config.google_drive_path;
        }
      }
    } catch (e) {
      // Use default pattern
    }
    
    defaultSystem += `

IMPORTANT FOR GOOGLE DRIVE:
1. Use find_files or search_files to search for documents in the Google Drive folder
2. The Google Drive is synced locally at: ${gdriveBase}
3. Search for files using patterns like: ${gdriveBase}/My Drive/**/*keyword*
4. Use read_file to read file contents if needed
5. For links, convert filenames to Google Drive search URLs:
   - Extract just the filename (without path and extension)
   - URL encode spaces as +
   - Return as: https://drive.google.com/drive/search?q=FILENAME
   - Example: "My Document.gdoc" -> https://drive.google.com/drive/search?q=My+Document`;
  }

  messages.push({
    role: 'system',
    content: systemPrompt || defaultSystem,
  });
  
  messages.push({
    role: 'user',
    content: prompt,
  });
  
  // Execute with tool loop
  let iterations = 0;
  let finalResponse = '';
  
  while (iterations < maxIterations) {
    iterations++;
    
    try {
      const result = await apiClient.streamChatWithTools(
        {
          model,
          messages,
          tools,
          source: 'CLI',
        },
        // No streaming callback - we want the full result
        null
      );
      
      const responseText = result.content;
      const toolCalls = result.toolCalls || [];
      
      // No tool calls - we're done
      if (toolCalls.length === 0) {
        finalResponse = responseText;
        break;
      }
      
      // Add assistant message with tool calls
      messages.push({
        role: 'assistant',
        content: responseText || '',
        tool_calls: toolCalls.map(tc => ({
          id: tc.id,
          type: 'function',
          function: {
            name: tc.function.name,
            arguments: tc.function.arguments,
          },
        })),
      });
      
      // Execute tool calls
      for (const toolCall of toolCalls) {
        const toolName = toolCall.function.name;
        let toolResult = '';
        
        try {
          const args = JSON.parse(toolCall.function.arguments || '{}');
          
          if (isMCPTool(toolName)) {
            const result = await executeMCPTool(toolName, args);
            toolResult = result.message || JSON.stringify(result);
          } else if (toolName === 'search_files' && executeSearchFiles) {
            const result = executeSearchFiles(args);
            toolResult = typeof result === 'string' ? result : JSON.stringify(result);
          } else if (toolName === 'find_files' && executeFindFiles) {
            const result = executeFindFiles(args);
            toolResult = typeof result === 'string' ? result : JSON.stringify(result);
          } else if (toolName === 'read_file' && executeReadFile) {
            const result = executeReadFile(args);
            toolResult = typeof result === 'string' ? result : JSON.stringify(result);
          } else if (toolName === 'list_directory' && executeListDirectory) {
            const result = executeListDirectory(args);
            toolResult = typeof result === 'string' ? result : JSON.stringify(result);
          } else {
            toolResult = `Unknown tool: ${toolName}`;
          }
        } catch (err) {
          toolResult = `Tool error: ${err.message}`;
        }
        
        messages.push({
          role: 'tool',
          tool_call_id: toolCall.id,
          content: toolResult,
        });
      }
    } catch (err) {
      throw new Error(`API error: ${err.message}`);
    }
  }
  
  return {
    response: finalResponse,
    iterations,
  };
}

/**
 * Parse JSON body from request
 */
function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (e) {
        reject(new Error('Invalid JSON'));
      }
    });
    req.on('error', reject);
  });
}

/**
 * Send JSON response
 */
function sendJson(res, data, status = 200) {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(JSON.stringify(data));
}

/**
 * Handle HTTP requests
 */
async function handleRequest(req, res) {
  const url = new URL(req.url, `http://${HOST}:${PORT}`);
  const path = url.pathname;
  
  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    });
    res.end();
    return;
  }
  
  try {
    // Health check
    if (path === '/health') {
      sendJson(res, {
        status: initialized ? 'ok' : 'initializing',
        error: initError,
      });
      return;
    }
    
    // MCP status
    if (path === '/status') {
      const statuses = mcpManager ? mcpManager.getServerStatuses() : [];
      sendJson(res, {
        initialized,
        error: initError,
        servers: statuses,
      });
      return;
    }
    
    // Retry failed MCP servers
    if (path === '/retry' && req.method === 'POST') {
      if (!mcpManager) {
        sendJson(res, { error: 'MCP manager not initialized' }, 503);
        return;
      }
      
      console.log('[SearchService] Manual retry requested...');
      await retryFailedServers();
      
      const statuses = mcpManager.getServerStatuses();
      sendJson(res, {
        message: 'Retry completed',
        servers: statuses,
      });
      return;
    }
    
    // Search endpoint
    if (path === '/search' && req.method === 'POST') {
      if (!initialized) {
        sendJson(res, { error: 'Service not ready', initError }, 503);
        return;
      }
      
      const body = await parseBody(req);
      const { query, sources, model } = body;
      
      if (!query) {
        sendJson(res, { error: 'Missing query parameter' }, 400);
        return;
      }
      
      console.log(`[SearchService] Search: "${query.substring(0, 50)}..." sources=${sources?.join(',') || 'all'} model=${model || 'default'}`);
      
      const startTime = Date.now();
      const result = await executeQuery(query, { sources, model });
      const elapsed = Date.now() - startTime;
      
      console.log(`[SearchService] Completed in ${elapsed}ms (${result.iterations} iterations)`);
      
      sendJson(res, {
        ...result,
        elapsed_ms: elapsed,
      });
      return;
    }
    
    // Raw query endpoint (more control)
    if (path === '/query' && req.method === 'POST') {
      if (!initialized) {
        sendJson(res, { error: 'Service not ready', initError }, 503);
        return;
      }
      
      const body = await parseBody(req);
      const { prompt, systemPrompt, sources, model, maxIterations } = body;
      
      if (!prompt) {
        sendJson(res, { error: 'Missing prompt parameter' }, 400);
        return;
      }
      
      console.log(`[SearchService] Query: "${prompt.substring(0, 50)}..."`);
      
      const startTime = Date.now();
      const result = await executeQuery(prompt, {
        systemPrompt,
        sources,
        model,
        maxIterations,
      });
      const elapsed = Date.now() - startTime;
      
      console.log(`[SearchService] Completed in ${elapsed}ms (${result.iterations} iterations)`);
      
      sendJson(res, {
        ...result,
        elapsed_ms: elapsed,
      });
      return;
    }
    
    // 404
    sendJson(res, { error: 'Not found' }, 404);
    
  } catch (err) {
    console.error('[SearchService] Error:', err.message);
    sendJson(res, { error: err.message }, 500);
  }
}

/**
 * Start the server
 */
async function main() {
  // Start HTTP server
  const server = http.createServer(handleRequest);
  
  server.listen(PORT, HOST, async () => {
    console.log(`[SearchService] Starting on http://${HOST}:${PORT}`);
    
    // Initialize in background
    await initialize();
  });
  
  // Graceful shutdown
  process.on('SIGTERM', async () => {
    console.log('[SearchService] Shutting down...');
    if (mcpManager) {
      await mcpManager.disconnectAll();
    }
    server.close();
    process.exit(0);
  });
  
  process.on('SIGINT', async () => {
    console.log('[SearchService] Interrupted, shutting down...');
    if (mcpManager) {
      await mcpManager.disconnectAll();
    }
    server.close();
    process.exit(0);
  });
}

main().catch(err => {
  console.error('[SearchService] Fatal error:', err);
  process.exit(1);
});
