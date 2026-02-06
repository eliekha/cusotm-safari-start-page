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
 *   GET /devsai/status - DevsAI auth + config status
 *   POST /devsai/login - Start DevsAI browser login
 *   GET /gmail/status - Gmail MCP auth status
 *   POST /gmail/auth - Start Gmail OAuth flow (read-only)
 *   GET /reconnect?mcp=name - Force reconnect a specific MCP (after re-auth)
 *   POST /search - AI-powered search across sources
 *   POST /query - Raw AI query with MCP tools
 *   POST /retry - Retry failed MCP server connections
 */

import http from 'http';
import { URL } from 'url';
import { fileURLToPath } from 'url';
import fs from 'fs';
import { spawn } from 'child_process';

// Import devsai library components from local installation
// Uses ~/.local/share/devsai/dist/ which has Full Disk Access
import os from 'os';
import path from 'path';
import { execSync } from 'child_process';

const HOME = os.homedir();

/**
 * Find the devsai library path by checking multiple locations.
 * The dist files use bare imports (@modelcontextprotocol/sdk etc.)
 * so we need a location where node_modules is resolvable.
 */
function findDevsaiLibPath() {
  const candidates = [
    // 1. Tarball install via npm (pkg installer: npm install --prefix ~/.local/share/devsai devsai.tgz)
    path.join(HOME, '.local/share/devsai/node_modules/devsai/dist/lib'),
    // 2. Direct dist copy (set up by install.sh with node_modules symlink)
    path.join(HOME, '.local/share/devsai/dist/lib'),
    // 3. Dev repo (has its own node_modules with all deps)
    path.join(HOME, 'Documents/GitHub/devs-ai-cli/dist/lib'),
  ];
  
  // 3. Try global npm install location
  try {
    const npmRoot = execSync('npm root -g 2>/dev/null', { encoding: 'utf8', timeout: 5000 }).trim();
    if (npmRoot) {
      candidates.push(path.join(npmRoot, 'devsai/dist/lib'));
    }
  } catch {
    // npm not available or timed out, skip
  }
  
  // Return first candidate that has the expected entry point
  for (const dir of candidates) {
    if (fs.existsSync(path.join(dir, 'mcp', 'index.js'))) {
      return dir;
    }
  }
  
  // Default fallback (will fail gracefully in loadDevsaiModules)
  return path.join(HOME, '.local/share/devsai/dist/lib');
}

// Resolve DEVSAI_BASE_PATH: use env var if it points to a valid location,
// otherwise auto-detect from multiple candidate locations
function resolveDevsaiBasePath() {
  if (process.env.DEVSAI_LIB_PATH) {
    const envPath = path.join(process.env.DEVSAI_LIB_PATH, 'dist', 'lib');
    if (fs.existsSync(path.join(envPath, 'mcp', 'index.js'))) {
      return envPath;
    }
    console.log(`[SearchService] DEVSAI_LIB_PATH env points to invalid location: ${envPath}`);
  }
  return findDevsaiLibPath();
}

const DEVSAI_BASE_PATH = resolveDevsaiBasePath();

function resolveDevsaiCliPath() {
  const candidates = [
    path.join(HOME, '.local/share/devsai/devsai.sh'),
    path.join(HOME, '.local/bin/devsai'),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

let MCPManager, createApiClient, getMCPToolDefinitions, executeMCPTool, isMCPTool;
let isAuthenticated, getConfig, getConfigPath, getApiKey;
let devsaiLoaded = false;
let CLI_TOOLS, executeSearchFiles, executeFindFiles, executeReadFile, executeListDirectory;

const PORT = parseInt(process.env.SEARCH_SERVICE_PORT || '19765', 10);
const HOST = '127.0.0.1';

// State (exported for testing)
export let mcpManager = null;
export let apiClient = null;
export let initialized = false;
export let initError = null;
export let gdriveMcpAvailable = false;
let apiKeyCache = null;

// BriefDesk install directory
const BRIEFDESK_DIR = `${HOME}/.local/share/briefdesk`;

// GDrive MCP paths
const GDRIVE_MCP_PATH = path.join(HOME, '.local/share/briefdesk/gdrive-mcp');
const GDRIVE_TOKEN_PATH = path.join(HOME, '.local/share/briefdesk/google_drive_token.json');

/**
 * Check if gdrive MCP is available (token exists and MCP is built)
 */
export function checkGdriveMcpAvailability() {
  const tokenExists = fs.existsSync(GDRIVE_TOKEN_PATH);
  const mcpExists = fs.existsSync(path.join(GDRIVE_MCP_PATH, 'dist/index.js'));
  gdriveMcpAvailable = tokenExists && mcpExists;
  console.log(`[SearchService] GDrive MCP: ${gdriveMcpAvailable ? 'available' : 'not available'} (token: ${tokenExists}, mcp: ${mcpExists})`);
  return gdriveMcpAvailable;
}

/**
 * Execute a gdrive MCP tool call
 */
export async function executeGdriveMcpTool(toolName, args) {
  return new Promise((resolve, reject) => {
    const mcpPath = path.join(GDRIVE_MCP_PATH, 'dist/index.js');
    
    // Build JSON-RPC request
    const request = {
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/call',
      params: {
        name: toolName,
        arguments: args,
      },
    };
    
    const proc = spawn('node', [mcpPath], {
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: GDRIVE_MCP_PATH,
    });
    
    let stdout = '';
    let stderr = '';
    
    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });
    
    proc.stderr.on('data', (data) => {
      stderr += data.toString();
    });
    
    proc.on('close', (code) => {
      // Parse JSON-RPC response from stdout
      try {
        // Skip the "BriefDesk Google Drive MCP server running" line
        const lines = stdout.split('\n');
        const jsonLine = lines.find(l => l.startsWith('{'));
        if (jsonLine) {
          const response = JSON.parse(jsonLine);
          if (response.result?.content?.[0]?.text) {
            resolve({ message: response.result.content[0].text });
          } else if (response.error) {
            reject(new Error(response.error.message || 'MCP error'));
          } else {
            resolve({ message: JSON.stringify(response.result) });
          }
        } else {
          reject(new Error(`GDrive MCP returned no JSON: ${stdout.substring(0, 200)}`));
        }
      } catch (err) {
        reject(new Error(`GDrive MCP parse error: ${err.message}`));
      }
    });
    
    proc.on('error', (err) => {
      reject(new Error(`GDrive MCP spawn error: ${err.message}`));
    });
    
    // Send the request and close stdin
    proc.stdin.write(JSON.stringify(request) + '\n');
    proc.stdin.end();
    
    // Timeout after 30 seconds
    setTimeout(() => {
      proc.kill();
      reject(new Error('GDrive MCP timeout'));
    }, 30000);
  });
}

/**
 * Get gdrive MCP tool definitions
 */
export function getGdriveMcpToolDefinitions() {
  return [
    {
      type: 'function',
      function: {
        name: 'gdrive_search',
        description: 'Search Google Drive for files by name or content. Returns file IDs, names, types, and direct URLs. Use the file ID with gdrive_read to get content.',
        parameters: {
          type: 'object',
          properties: {
            query: {
              type: 'string',
              description: 'Search query (searches file names and content)',
            },
            maxResults: {
              type: 'number',
              description: 'Maximum number of results to return (default: 20)',
            },
          },
          required: ['query'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: 'gdrive_read',
        description: 'Read the content of a Google Drive file. For Google Docs/Sheets/Slides, exports as text/markdown.',
        parameters: {
          type: 'object',
          properties: {
            fileId: {
              type: 'string',
              description: 'The Google Drive file ID (from search results)',
            },
          },
          required: ['fileId'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: 'gdrive_list',
        description: 'List files in a Google Drive folder.',
        parameters: {
          type: 'object',
          properties: {
            folderId: {
              type: 'string',
              description: 'Folder ID (optional, defaults to root)',
            },
            maxResults: {
              type: 'number',
              description: 'Maximum number of results (default: 50)',
            },
          },
          required: [],
        },
      },
    },
  ];
}

// Retry configuration for MCP servers
export const MCP_RETRY_CONFIG = {
  maxRetries: 3,
  retryDelayMs: 5000,  // 5 seconds between retries
  retryableErrors: ['empty cache', 'not found in empty cache', 'cache not ready'],
  // Deferred retry: re-attempt servers that failed or never connected on startup
  deferredRetryDelayMs: 10000,  // 10 seconds after startup
  deferredMaxRetries: 2,
};

// Functions to set state (for testing)
export function _setMcpManager(manager) { mcpManager = manager; }
export function _setApiClient(client) { apiClient = client; }
export function _setInitialized(value) { initialized = value; }
export function _setInitError(error) { initError = error; }
export function _setGdriveMcpAvailable(value) { gdriveMcpAvailable = value; }
export function _resetState() {
  mcpManager = null;
  apiClient = null;
  initialized = false;
  initError = null;
  gdriveMcpAvailable = false;
  apiKeyCache = null;
}

function refreshApiClient() {
  const apiKey = getApiKey ? getApiKey() : null;
  if (!apiKey) {
    apiClient = null;
    apiKeyCache = null;
    return false;
  }
  if (!apiClient || apiKeyCache !== apiKey) {
    apiClient = createApiClient();
    apiKeyCache = apiKey;
  }
  return true;
}

/**
 * Load all devsai modules from a given base path.
 * Returns true on success, throws on failure.
 */
async function _loadModulesFrom(basePath) {
  const mcpModule = await import(`file://${basePath}/mcp/index.js`);
  MCPManager = mcpModule.MCPManager;
  getMCPToolDefinitions = mcpModule.getMCPToolDefinitions;
  executeMCPTool = mcpModule.executeMCPTool;
  isMCPTool = mcpModule.isMCPTool;
  
  const apiModule = await import(`file://${basePath}/api-client.js`);
  createApiClient = apiModule.createApiClient;
  
  const configModule = await import(`file://${basePath}/config.js`);
  isAuthenticated = configModule.isAuthenticated;
  getConfig = configModule.getConfig;
  getConfigPath = configModule.getConfigPath;
  getApiKey = configModule.getApiKey;
  
  const cliToolsModule = await import(`file://${basePath}/cli-tools.js`);
  CLI_TOOLS = cliToolsModule.CLI_TOOLS;
  executeSearchFiles = cliToolsModule.executeSearchFiles;
  executeFindFiles = cliToolsModule.executeFindFiles;
  executeReadFile = cliToolsModule.executeReadFile;
  executeListDirectory = cliToolsModule.executeListDirectory;
  
  return true;
}

/**
 * Dynamic import of devsai modules with multi-path fallback.
 * Tries the primary path first, then falls back to dev repo and global npm.
 */
export async function loadDevsaiModules() {
  // Build list of candidate paths (primary first, then fallbacks)
  const candidatePaths = [DEVSAI_BASE_PATH];
  
  // Add fallback paths that aren't already the primary
  const devRepoPath = path.join(HOME, 'Documents/GitHub/devs-ai-cli/dist/lib');
  if (devRepoPath !== DEVSAI_BASE_PATH && fs.existsSync(path.join(devRepoPath, 'mcp', 'index.js'))) {
    candidatePaths.push(devRepoPath);
  }
  
  // Try global npm location as last resort
  try {
    const npmRoot = execSync('npm root -g 2>/dev/null', { encoding: 'utf8', timeout: 5000 }).trim();
    const npmPath = path.join(npmRoot, 'devsai/dist/lib');
    if (npmPath !== DEVSAI_BASE_PATH && fs.existsSync(path.join(npmPath, 'mcp', 'index.js'))) {
      candidatePaths.push(npmPath);
    }
  } catch {}
  
  // Try each candidate path
  for (const basePath of candidatePaths) {
    try {
      await _loadModulesFrom(basePath);
      console.log('[SearchService] Loaded devsai modules from:', basePath);
      devsaiLoaded = true;
      return true;
    } catch (err) {
      const shortErr = err.message.substring(0, 100);
      console.log(`[SearchService] Failed to load from ${basePath}: ${shortErr}`);
    }
  }
  
  console.error('[SearchService] Failed to load devsai modules from any location');
  console.error('[SearchService] Tried:', candidatePaths.join(', '));
  initError = 'Failed to load devsai modules - ensure devsai CLI is installed';
  return false;
}

/**
 * Check if an error is retryable (cache-related)
 */
export function isRetryableError(error) {
  if (!error) return false;
  const errorLower = error.toLowerCase();
  return MCP_RETRY_CONFIG.retryableErrors.some(re => errorLower.includes(re));
}

/**
 * Sleep for a given number of milliseconds
 */
export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Force reconnect a specific MCP server (used after re-authentication)
 * Works even if the server never connected initially (e.g., timed out on startup)
 */
export async function reconnectServer(serverName) {
  if (!mcpManager) {
    throw new Error('MCP manager not initialized');
  }
  
  console.log(`[SearchService] Force reconnecting ${serverName}...`);
  
  const statuses = mcpManager.getServerStatuses();
  const existingServer = statuses.find(s => s.name === serverName);
  
  // If server was never loaded (not in original config), we need to
  // restart the entire process to pick up the new config.
  // Signal the caller that a restart is needed.
  if (!existingServer) {
    console.log(`[SearchService] ${serverName} not in current config, process restart required`);
    console.log(`[SearchService] Scheduling self-restart to pick up new MCP config...`);
    
    // Schedule a graceful restart after responding
    setTimeout(() => {
      console.log(`[SearchService] Restarting process to load new MCP server: ${serverName}`);
      process.exit(0); // LaunchAgent KeepAlive will restart us
    }, 1000);
    
    return { success: false, restarting: true, error: 'New server detected, restarting service to load config' };
  }
  
  try {
    // If server exists, try to disconnect first (ignore errors)
    try {
      await mcpManager.disconnectServer(serverName);
      console.log(`[SearchService] Disconnected ${serverName}`);
    } catch (e) {
      console.log(`[SearchService] Disconnect: ${e.message}`);
    }
    
    // Wait a moment for cleanup
    await sleep(500);
    
    // Try to connect (this works for both reconnect and first-time connect)
    await mcpManager.connectServer(serverName);
    
    // Check result
    const newStatuses = mcpManager.getServerStatuses();
    const newStatus = newStatuses.find(s => s.name === serverName);
    
    if (newStatus?.status === 'connected') {
      console.log(`[SearchService] ✓ ${serverName} reconnected successfully (${newStatus.toolCount} tools)`);
      return { success: true, status: newStatus };
    } else {
      const error = newStatus?.error || 'Unknown error';
      console.log(`[SearchService] ✗ ${serverName} reconnect failed: ${error}`);
      return { success: false, error, status: newStatus };
    }
  } catch (err) {
    console.log(`[SearchService] ✗ ${serverName} reconnect error: ${err.message}`);
    return { success: false, error: err.message };
  }
}

/**
 * Retry failed MCP servers that have retryable errors
 */
export async function retryFailedServers() {
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
 * Schedule a deferred retry for MCP servers that failed or never connected.
 *
 * On initial startup, mcp-remote (Atlassian) can fail silently — e.g. stale
 * OAuth tokens, slow SSE handshake, or the process exiting before the MCP SDK
 * registers an error.  This function reads the expected server list from
 * .devsai.json, compares it with actually-connected servers, and retries any
 * that are missing or in error state.  Runs in the background so it doesn't
 * block startup.
 */
function scheduleDeferredRetry() {
  setTimeout(async () => {
    try {
      if (!mcpManager) return;

      // Read expected servers from .devsai.json
      const devsaiConfigPath = path.join(process.cwd(), '.devsai.json');
      let expectedServers = [];
      try {
        if (fs.existsSync(devsaiConfigPath)) {
          const cfg = JSON.parse(fs.readFileSync(devsaiConfigPath, 'utf8'));
          expectedServers = Object.keys(cfg.mcpServers || {});
        }
      } catch {}

      if (expectedServers.length === 0) return;

      const statuses = mcpManager.getServerStatuses();
      const connectedNames = new Set(
        statuses.filter(s => s.status === 'connected').map(s => s.name)
      );

      // Find servers that should be connected but aren't
      const missing = expectedServers.filter(name => !connectedNames.has(name));
      if (missing.length === 0) return;

      console.log(`[SearchService] Deferred retry: ${missing.length} server(s) not connected: ${missing.join(', ')}`);

      for (const serverName of missing) {
        for (let attempt = 1; attempt <= MCP_RETRY_CONFIG.deferredMaxRetries; attempt++) {
          console.log(`[SearchService] Deferred retry ${attempt}/${MCP_RETRY_CONFIG.deferredMaxRetries} for ${serverName}...`);

          try {
            // Disconnect first (ignore errors — server may never have registered)
            try { await mcpManager.disconnectServer(serverName); } catch {}

            // Re-read config to get server config (may have been added after startup)
            let serverConfig = null;
            try {
              const cfg = JSON.parse(fs.readFileSync(devsaiConfigPath, 'utf8'));
              serverConfig = (cfg.mcpServers || {})[serverName];
            } catch {}

            if (serverConfig) {
              await mcpManager.connectServer(serverName, serverConfig);
            } else {
              await mcpManager.connectServer(serverName);
            }

            const newStatuses = mcpManager.getServerStatuses();
            const newStatus = newStatuses.find(s => s.name === serverName);

            if (newStatus?.status === 'connected') {
              console.log(`[SearchService] ✓ ${serverName} connected via deferred retry (${newStatus.toolCount} tools)`);
              break;
            } else {
              console.log(`[SearchService] ✗ ${serverName} deferred retry ${attempt} failed: ${newStatus?.error?.substring(0, 80) || 'unknown'}`);
            }
          } catch (err) {
            console.log(`[SearchService] ✗ ${serverName} deferred retry ${attempt} error: ${err.message?.substring(0, 80)}`);
          }

          // Wait before next attempt
          if (attempt < MCP_RETRY_CONFIG.deferredMaxRetries) {
            await sleep(MCP_RETRY_CONFIG.retryDelayMs);
          }
        }
      }

      // Log final status after deferred retries
      const finalStatuses = mcpManager.getServerStatuses();
      const finalConnected = finalStatuses.filter(s => s.status === 'connected');
      console.log(`[SearchService] After deferred retries: ${finalConnected.length} servers connected`);
      for (const s of finalConnected) {
        console.log(`  ✓ ${s.name} (${s.toolCount} tools)`);
      }
    } catch (err) {
      console.error('[SearchService] Deferred retry error:', err.message);
    }
  }, MCP_RETRY_CONFIG.deferredRetryDelayMs);
}

/**
 * Initialize MCP connections and API client
 */
export async function initialize() {
  console.log('[SearchService] Initializing...');
  
  // Check for GDrive MCP availability
  checkGdriveMcpAvailability();
  
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
  
  // Create API client (refreshable for token changes)
  if (refreshApiClient()) {
    console.log('[SearchService] API client created');
  } else {
    initError = 'Not authenticated. Run: devsai login';
    console.error('[SearchService]', initError);
    return false;
  }
  
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
    // Schedule deferred retry for any servers that failed or never connected.
    // mcp-remote (Atlassian) can fail silently on first startup if tokens are
    // stale or the SSE handshake takes too long.  We compare the expected
    // server list from .devsai.json with what actually connected.
    scheduleDeferredRetry();
  } catch (err) {
    console.error('[SearchService] MCP connection error:', err.message);
    // Continue anyway - some servers may have connected
    scheduleDeferredRetry();
  }
  
  initialized = true;
  console.log('[SearchService] Ready on port', PORT);
  return true;
}

/**
 * Execute an AI query with MCP tools
 */
export async function executeQuery(prompt, options = {}) {
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
      
      // Add Drive tools when drive is in sources
      if (sources.some(s => s.toLowerCase() === 'drive')) {
        if (gdriveMcpAvailable) {
          // Use GDrive MCP tools (API-based, can search content)
          const gdriveTools = getGdriveMcpToolDefinitions();
          tools = [...tools, ...gdriveTools];
          console.log(`[SearchService] Added ${gdriveTools.length} GDrive MCP tools (API mode)`);
        } else if (CLI_TOOLS) {
          // Fallback to filesystem CLI tools (local sync folder)
          const fileTools = CLI_TOOLS.filter(t => 
            ['search_files', 'find_files', 'read_file', 'list_directory'].includes(t.function.name)
          );
          tools = [...tools, ...fileTools];
          console.log(`[SearchService] Added ${fileTools.length} CLI file tools for drive (fallback mode)`);
        }
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
  let defaultSystem = `You are a helpful search assistant with access to various tools. You MUST use the available tools to search and retrieve information. Do not ask the user for configuration - use the tools to discover what you need.

RESPONSE FORMAT:
Write a clear, helpful narrative answer that synthesizes information from all sources. Use inline citations like [1], [2], etc. to reference your sources.

After your answer, include a SOURCES section in this exact format:
---SOURCES---
[1] Title | source_type | url
[2] Title | source_type | url
---END_SOURCES---

Where source_type is one of: slack, jira, confluence, gmail, drive

Example:
Based on the recent discussion in Slack [1], the project deadline has been moved to next Friday. The updated timeline is documented in the project plan [2], and Sarah mentioned she'll update the Jira tickets accordingly [3].

---SOURCES---
[1] #engineering-updates | slack | https://slack.com/archives/C123/p456
[2] Q1 Project Timeline | confluence | https://company.atlassian.net/wiki/spaces/ENG/pages/123
[3] PROJ-456: Update timeline | jira | https://company.atlassian.net/browse/PROJ-456
---END_SOURCES---

Be concise but thorough. Prioritize the most relevant information.`;

  // Add Atlassian-specific instructions if jira/confluence is in sources
  if (sources && sources.some(s => ['jira', 'confluence'].includes(s.toLowerCase()))) {
    defaultSystem += `

IMPORTANT FOR JIRA/CONFLUENCE:
1. FIRST call mcp_atlassian_getAccessibleAtlassianResources to get the cloudId
2. THEN use that cloudId with mcp_atlassian_searchJiraIssuesUsingJql or mcp_atlassian_searchConfluenceUsingCql
3. NEVER ask the user for cloudId - always discover it with step 1`;
  }
  
  // Add GitHub-specific instructions
  if (sources && sources.some(s => s.toLowerCase() === 'github')) {
    defaultSystem += `

IMPORTANT FOR GITHUB SEARCH - USE PARALLEL TOOL CALLS FOR SPEED:
You have access to the GitHub MCP server tools. Follow this optimized strategy:

STEP 1 - BROAD SEARCH (use ALL of these in PARALLEL in a single turn):
  - search_code: with keywords from the query (e.g., "auth middleware language:typescript")
  - search_issues: with keywords (finds open issues/discussions)
  - search_pull_requests: with keywords (finds PRs)
  - search_repositories: ONLY if the query is about finding repos or you need to narrow scope
Call ALL relevant search tools simultaneously in one turn for maximum speed.

STEP 2 - DEEP DIVE (if Step 1 results point to specific repos):
  - search_code with repo: qualifier for targeted search (e.g., "query repo:owner/name")
  - get_file_contents to read README.md or key source files from the most relevant matches

SEARCH QUALIFIERS (use these to improve results):
  - Code: language:typescript, path:src/, filename:auth, extension:ts
  - Issues/PRs: is:open, is:closed, label:bug, author:username
  - Repos: language:typescript, stars:>10, pushed:>2024-01-01
  - Scope: user:USERNAME, org:ORGNAME to limit to specific owners

IMPORTANT RULES:
  - ALWAYS make multiple tool calls in the SAME turn when possible (parallel execution)
  - Use specific search qualifiers to reduce noise
  - Prefer search_code over get_file_contents for discovery
  - For source links use full GitHub URLs: https://github.com/owner/repo/...
  - Prioritize: recent PRs > open issues > code matches > old closed items`;
  }

  // Add Drive-specific instructions
  if (sources && sources.some(s => s.toLowerCase() === 'drive')) {
    if (gdriveMcpAvailable) {
      // Using GDrive MCP (API-based)
      defaultSystem += `

CRITICAL FOR GOOGLE DRIVE - YOU MUST READ FILE CONTENTS:
1. First use gdrive_search to find relevant documents
2. From search results, get the "id" field of the top 2-3 most relevant files
3. ALWAYS call gdrive_read with fileId for each relevant file to get its content
   Example: gdrive_search returns {"files":[{"id":"abc123","name":"Meeting Notes",...}]}
   Then call: gdrive_read({"fileId":"abc123"})
4. Extract the ACTUAL information from file contents to answer the question
5. NEVER just list files - you MUST read and summarize their contents
6. Include direct quotes and the file URL as sources

REQUIRED WORKFLOW:
Step 1: gdrive_search({"query":"topic"}) - find files
Step 2: gdrive_read({"fileId":"<id from search>"}) - read top 2-3 files  
Step 3: Synthesize answer from the content you read
Step 4: Include source URLs`;
    } else {
      // Fallback to filesystem mode
      let gdriveBase = path.join(HOME, 'Library/CloudStorage/GoogleDrive-*');
      try {
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
  
  // Progress callback (optional)
  const onProgress = options.onProgress || (() => {});
  
  while (iterations < maxIterations) {
    iterations++;
    
    // Notify thinking
    onProgress({ type: 'thinking', iteration: iterations });
    
    try {
      if (!refreshApiClient()) {
        throw new Error('Not authenticated. Run: devsai login');
      }

      let result;
      try {
        result = await apiClient.streamChatWithTools(
          {
            model,
            messages,
            tools,
            source: 'CLI',
          },
          // Streaming callback for partial content
          (chunk) => {
            if (chunk && chunk.trim()) {
              onProgress({ type: 'content', content: chunk });
            }
          }
        );
      } catch (err) {
        if (err?.message?.includes('Unauthorized') && refreshApiClient()) {
          result = await apiClient.streamChatWithTools(
            {
              model,
              messages,
              tools,
              source: 'CLI',
            },
            (chunk) => {
              if (chunk && chunk.trim()) {
                onProgress({ type: 'content', content: chunk });
              }
            }
          );
        } else {
          throw err;
        }
      }
      
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
      
      // Execute tool calls IN PARALLEL for speed
      const toolPromises = toolCalls.map(async (toolCall) => {
        const toolName = toolCall.function.name;
        let toolResult = '';
        
        // Parse args for display
        let argsObj = {};
        try {
          argsObj = JSON.parse(toolCall.function.arguments || '{}');
        } catch (e) {}
        
        // Notify tool call start
        onProgress({ 
          type: 'tool_start', 
          tool: toolName, 
          args: argsObj,
          description: getToolDescription(toolName, argsObj)
        });
        
        try {
          const args = argsObj;
          
          if (isMCPTool(toolName)) {
            const result = await executeMCPTool(toolName, args);
            toolResult = result.message || JSON.stringify(result);
          } else if (toolName.startsWith('gdrive_') && gdriveMcpAvailable) {
            const result = await executeGdriveMcpTool(toolName, args);
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
          
          onProgress({ 
            type: 'tool_complete', 
            tool: toolName,
            success: true,
            resultPreview: toolResult.substring(0, 200)
          });
        } catch (err) {
          toolResult = `Tool error: ${err.message}`;
          onProgress({ 
            type: 'tool_complete', 
            tool: toolName,
            success: false,
            error: err.message
          });
        }
        
        return {
          role: 'tool',
          tool_call_id: toolCall.id,
          content: toolResult,
        };
      });
      
      const toolResults = await Promise.all(toolPromises);
      messages.push(...toolResults);
    } catch (err) {
      throw new Error(`API error: ${err.message}`);
    }
  }
  
  onProgress({ type: 'done', iterations });
  
  return {
    response: finalResponse,
    iterations,
  };
}

/**
 * Get human-readable description of a tool call
 */
function getToolDescription(toolName, args) {
  const name = toolName.toLowerCase();
  
  // Slack tools
  if (name.includes('slack')) {
    if (name.includes('search') || name.includes('messages')) {
      return `Searching Slack${args.query ? `: "${args.query}"` : ''}`;
    }
    if (name.includes('channels') || name.includes('conversations')) {
      return 'Listing Slack channels';
    }
    if (name.includes('history')) {
      return 'Reading Slack messages';
    }
    return 'Querying Slack';
  }
  
  // Atlassian tools
  if (name.includes('atlassian') || name.includes('jira') || name.includes('confluence')) {
    if (name.includes('accessible') || name.includes('resources')) {
      return 'Getting Atlassian workspace info';
    }
    if (name.includes('jira') && name.includes('search')) {
      return `Searching Jira${args.jql ? `: ${args.jql.substring(0, 50)}` : ''}`;
    }
    if (name.includes('confluence') && name.includes('search')) {
      return `Searching Confluence${args.cql ? `: ${args.cql.substring(0, 50)}` : ''}`;
    }
    if (name.includes('issue')) {
      return `Reading Jira issue${args.issueKey ? `: ${args.issueKey}` : ''}`;
    }
    if (name.includes('page')) {
      return 'Reading Confluence page';
    }
    return 'Querying Atlassian';
  }
  
  // Gmail tools
  if (name.includes('gmail') || name.includes('email')) {
    if (name.includes('search') || name.includes('list')) {
      return `Searching Gmail${args.query ? `: "${args.query}"` : ''}`;
    }
    if (name.includes('read') || name.includes('get')) {
      return 'Reading email';
    }
    return 'Querying Gmail';
  }
  
  // GitHub MCP tools
  if (name.includes('github')) {
    if (name.includes('search_repositories')) {
      return `Searching GitHub repos${args.query ? `: "${args.query}"` : ''}`;
    }
    if (name.includes('search_code')) {
      return `Searching GitHub code${args.query ? `: "${args.query}"` : ''}`;
    }
    if (name.includes('search_issues')) {
      return `Searching GitHub issues${args.query ? `: "${args.query}"` : ''}`;
    }
    if (name.includes('search_pull_requests') || name.includes('pull_request')) {
      return `Searching GitHub PRs${args.query ? `: "${args.query}"` : ''}`;
    }
    if (name.includes('get_file_contents')) {
      return `Reading file${args.path ? `: ${args.path}` : ''}`;
    }
    if (name.includes('list_commits')) {
      return 'Listing commits';
    }
    return `Querying GitHub`;
  }
  
  // GDrive MCP tools
  if (name === 'gdrive_search') {
    return `Searching Google Drive${args.query ? `: "${args.query}"` : ''}`;
  }
  if (name === 'gdrive_read') {
    return `Reading Drive file${args.file_id ? ` (${args.file_id.substring(0, 10)}...)` : ''}`;
  }
  if (name === 'gdrive_list') {
    return 'Listing Drive folder';
  }
  
  // File tools (Drive fallback)
  if (name === 'search_files' || name === 'find_files') {
    return `Searching files${args.pattern ? `: ${args.pattern}` : ''}`;
  }
  if (name === 'read_file') {
    return `Reading file${args.path ? `: ${args.path.split('/').pop()}` : ''}`;
  }
  if (name === 'list_directory') {
    return 'Listing directory';
  }
  
  // Default
  return `Running ${toolName}`;
}

/**
 * Parse JSON body from request
 */
export function parseBody(req) {
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
export function sendJson(res, data, status = 200) {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(JSON.stringify(data));
}

/**
 * Handle HTTP requests
 */
export async function handleRequest(req, res) {
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

    // DevsAI status (auth + config)
    if (path === '/devsai/status') {
      if (!devsaiLoaded) {
        const loaded = await loadDevsaiModules();
        if (!loaded) {
          sendJson(res, {
            installed: false,
            authenticated: false,
            error: 'DevsAI not installed',
          });
          return;
        }
      }

      const config = getConfig ? getConfig() : {};
      sendJson(res, {
        installed: true,
        authenticated: isAuthenticated ? isAuthenticated() : false,
        configPath: getConfigPath ? getConfigPath() : null,
        userEmail: config.userEmail || null,
        orgName: config.orgName || null,
        apiUrl: config.apiUrl || null,
        initError,
      });
      return;
    }

    // DevsAI login (open browser + exit without REPL)
    if (path === '/devsai/login' && req.method === 'POST') {
      if (!devsaiLoaded) {
        await loadDevsaiModules();
      }

      if (isAuthenticated && isAuthenticated()) {
        sendJson(res, { success: true, alreadyAuthenticated: true });
        return;
      }

      const devsaiCli = resolveDevsaiCliPath();
      if (!devsaiCli) {
        sendJson(res, { success: false, error: 'DevsAI CLI not found' }, 404);
        return;
      }

      try {
        const child = spawn(devsaiCli, ['login', '--no-repl'], {
          detached: true,
          stdio: 'ignore',
          env: { ...process.env, HOME },
        });
        child.unref();
        sendJson(res, { success: true, launched: true });
      } catch (err) {
        sendJson(res, { success: false, error: err.message }, 500);
      }
      return;
    }

    // Gmail MCP auth (open browser for Google OAuth)
    if (path === '/gmail/auth' && req.method === 'POST') {
      const gmailMcpPath = `${BRIEFDESK_DIR}/gmail-mcp/dist/index.js`;
      const nodePath = process.execPath;
      
      // Check if gmail-mcp exists
      if (!fs.existsSync(gmailMcpPath)) {
        sendJson(res, { success: false, error: 'Gmail MCP not found. Please reinstall BriefDesk.' }, 404);
        return;
      }
      
      // Check if already authenticated
      const credentialsPath = `${HOME}/.gmail-mcp/credentials.json`;
      if (fs.existsSync(credentialsPath)) {
        sendJson(res, { success: true, alreadyAuthenticated: true });
        return;
      }
      
      try {
        console.log('[SearchService] Starting Gmail MCP auth flow...');
        const child = spawn(nodePath, [gmailMcpPath, 'auth'], {
          detached: true,
          stdio: 'ignore',
          env: { ...process.env, HOME },
        });
        child.unref();
        sendJson(res, { success: true, launched: true, message: 'OAuth flow started in browser' });
      } catch (err) {
        sendJson(res, { success: false, error: err.message }, 500);
      }
      return;
    }

    // Gmail auth status check
    if (path === '/gmail/status') {
      const credentialsPath = `${HOME}/.gmail-mcp/credentials.json`;
      const keysPath = `${HOME}/.gmail-mcp/gcp-oauth.keys.json`;
      const gmailMcpPath = `${BRIEFDESK_DIR}/gmail-mcp/dist/index.js`;
      
      let scope = null;
      if (fs.existsSync(credentialsPath)) {
        try {
          const creds = JSON.parse(fs.readFileSync(credentialsPath, 'utf-8'));
          scope = creds.scope || null;
        } catch {}
      }
      
      sendJson(res, {
        authenticated: fs.existsSync(credentialsPath),
        hasOAuthKeys: fs.existsSync(keysPath),
        mcpAvailable: fs.existsSync(gmailMcpPath),
        scope,
        isReadOnly: scope ? scope.includes('gmail.readonly') && !scope.includes('gmail.modify') : null,
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
        gdriveMcp: {
          available: gdriveMcpAvailable,
          tokenPath: GDRIVE_TOKEN_PATH,
          mcpPath: GDRIVE_MCP_PATH,
        },
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
    
    // Force reconnect a specific MCP server (after re-auth)
    if (path === '/reconnect') {
      if (!mcpManager) {
        sendJson(res, { error: 'MCP manager not initialized' }, 503);
        return;
      }
      
      const serverName = url.searchParams.get('mcp');
      if (!serverName) {
        sendJson(res, { error: 'Missing mcp parameter' }, 400);
        return;
      }
      
      console.log(`[SearchService] Reconnect requested for: ${serverName}`);
      const result = await reconnectServer(serverName);
      
      if (result.success) {
        sendJson(res, {
          success: true,
          message: `${serverName} reconnected successfully`,
          server: result.status,
        });
      } else {
        sendJson(res, {
          success: false,
          error: result.error,
          server: result.status,
        });
      }
      return;
    }
    
    // Search endpoint (non-streaming)
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
    
    // Search endpoint with SSE streaming for live progress
    if (path === '/search-stream' && req.method === 'POST') {
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
      
      console.log(`[SearchService] Stream Search: "${query.substring(0, 50)}..." sources=${sources?.join(',') || 'all'}`);
      
      // Set up SSE headers
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
      });
      
      const sendEvent = (event, data) => {
        res.write(`event: ${event}\n`);
        res.write(`data: ${JSON.stringify(data)}\n\n`);
      };
      
      const startTime = Date.now();
      
      try {
        const result = await executeQuery(query, { 
          sources, 
          model,
          onProgress: (progress) => {
            sendEvent('progress', progress);
          }
        });
        
        const elapsed = Date.now() - startTime;
        console.log(`[SearchService] Stream completed in ${elapsed}ms`);
        
        sendEvent('complete', {
          response: result.response,
          iterations: result.iterations,
          elapsed_ms: elapsed,
        });
      } catch (err) {
        console.error('[SearchService] Stream error:', err.message);
        sendEvent('error', { error: err.message });
      }
      
      res.end();
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
export async function main() {
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
  
  return server;
}

// Export constants for testing
export { PORT, HOST, HOME, DEVSAI_BASE_PATH };

// Only run if executed directly (not imported)
const isMainModule = import.meta.url === `file://${process.argv[1]}`;
if (isMainModule) {
  main().catch(err => {
    console.error('[SearchService] Fatal error:', err);
    process.exit(1);
  });
}
