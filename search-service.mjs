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

function isValidDevsaiLib(dir) {
  try {
    if (!fs.existsSync(dir)) return false;
    // Guard against npm link symlinks that redirect to a different devsai
    if (fs.lstatSync(dir).isSymbolicLink()) return false;
    return fs.existsSync(path.join(dir, 'mcp', 'index.js'));
  } catch {
    return false;
  }
}

/**
 * Find the devsai library path by checking multiple locations.
 * We deliberately avoid global npm locations so BriefDesk uses its
 * sandboxed, FDA-granted devsai even if the user runs npm link.
 */
function findDevsaiLibPath() {
  const sandboxBase = process.env.BRIEFDESK_DEVSAI_HOME || path.join(HOME, '.local/share/devsai');
  const candidates = [
    path.join(sandboxBase, 'node_modules/devsai/dist/lib'),
    path.join(sandboxBase, 'dist/lib'),
    path.join(HOME, 'Documents/GitHub/devs-ai-cli/dist/lib'),
  ];

  for (const dir of candidates) {
    if (isValidDevsaiLib(dir)) {
      return dir;
    }
  }

  // Default fallback (will fail gracefully in loadDevsaiModules)
  return path.join(sandboxBase, 'dist/lib');
}

// Resolve DEVSAI_BASE_PATH: use env var if it points to a valid location,
// otherwise auto-detect from multiple candidate locations
function resolveDevsaiBasePath() {
  if (process.env.DEVSAI_LIB_PATH) {
    const envPath = path.join(process.env.DEVSAI_LIB_PATH, 'dist', 'lib');
    if (isValidDevsaiLib(envPath)) {
      return envPath;
    }
    console.log(`[SearchService] DEVSAI_LIB_PATH env points to invalid or symlinked location: ${envPath}`);
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
let apiKeyCache = null;

// BriefDesk install directory
const BRIEFDESK_DIR = `${HOME}/.local/share/briefdesk`;

const DEVSAI_CHAT_TOOL_CACHE_TTL_MS = 5 * 60 * 1000;
const DEVSAI_TOOL_NAMES = {
  gmail: 'Gmail',
  drive: 'Google Drive',
};

let chatToolsCache = null;
let chatToolsCacheTime = 0;


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
export function _resetState() {
  mcpManager = null;
  apiClient = null;
  initialized = false;
  initError = null;
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

async function listChatToolsCached(force = false) {
  if (!devsaiLoaded) {
    await loadDevsaiModules();
  }
  if (!refreshApiClient()) {
    throw new Error('Not authenticated. Run: devsai login');
  }
  const now = Date.now();
  if (!force && chatToolsCache && now - chatToolsCacheTime < DEVSAI_CHAT_TOOL_CACHE_TTL_MS) {
    return chatToolsCache;
  }
  if (!apiClient?.listChatTools) {
    throw new Error('DevsAI API client missing listChatTools');
  }
  const result = await apiClient.listChatTools();
  chatToolsCache = Array.isArray(result?.data) ? result.data : [];
  chatToolsCacheTime = now;
  return chatToolsCache;
}

function findChatToolByName(tools, name) {
  const target = name.toLowerCase();
  return tools.find((tool) => (tool?.name || '').toLowerCase() === target);
}

async function getChatToolByName(name) {
  const tools = await listChatToolsCached();
  return findChatToolByName(tools, name);
}

async function getChatToolAuthStatus(toolId) {
  if (!apiClient?.getToolOAuthStatus) {
    throw new Error('DevsAI API client missing getToolOAuthStatus');
  }
  return apiClient.getToolOAuthStatus(toolId);
}

async function initiateChatToolAuth(toolId) {
  if (!apiClient?.initiateToolOAuth) {
    throw new Error('DevsAI API client missing initiateToolOAuth');
  }
  return apiClient.initiateToolOAuth(toolId);
}

async function revokeChatToolAuth(toolId) {
  if (!apiClient?.revokeToolOAuthToken) {
    throw new Error('DevsAI API client missing revokeToolOAuthToken');
  }
  return apiClient.revokeToolOAuthToken(toolId);
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

  let devsaiDriveEnabled = false;
  let devsaiGmailEnabled = false;
  
  // Get available MCP tools
  let tools = [];
  try {
    tools = getMCPToolDefinitions();
    
    // Filter tools by source if specified
    if (sources && sources.length > 0) {
      const beforeCount = tools.length;
      const normalizedSources = sources.map(s => s.toLowerCase());
      const wantsDrive = normalizedSources.includes('drive');
      const wantsGmail = normalizedSources.includes('gmail');

      if (wantsDrive || wantsGmail) {
        try {
          const chatTools = await listChatToolsCached();
          if (wantsGmail) {
            const gmailTool = findChatToolByName(chatTools, DEVSAI_TOOL_NAMES.gmail);
            if (!gmailTool) {
              throw new Error('tool_unavailable:gmail');
            }
            if (gmailTool.requiresAuth) {
              const status = await getChatToolAuthStatus(gmailTool.toolId).catch(() => null);
              if (!status?.hasToken) {
                throw new AuthRequiredError('gmail');
              }
            }
            tools = [...tools, { type: 'mcp_server', toolId: gmailTool.toolId }];
            devsaiGmailEnabled = true;
            console.log('[SearchService] Added DevsAI Gmail MCP tool');
          }
          if (wantsDrive) {
            const driveTool = findChatToolByName(chatTools, DEVSAI_TOOL_NAMES.drive);
            if (!driveTool) {
              throw new Error('tool_unavailable:drive');
            }
            if (driveTool.requiresAuth) {
              const status = await getChatToolAuthStatus(driveTool.toolId).catch(() => null);
              if (!status?.hasToken) {
                throw new AuthRequiredError('drive');
              }
            }
            tools = [...tools, { type: 'mcp_server', toolId: driveTool.toolId }];
            devsaiDriveEnabled = true;
            console.log('[SearchService] Added DevsAI Drive MCP tool');
          }
        } catch (err) {
          if (err instanceof AuthRequiredError) {
            throw err;
          }
          if (typeof err?.message === 'string' && err.message.startsWith('tool_unavailable:')) {
            throw err;
          }
          console.log(`[SearchService] DevsAI tool discovery failed: ${err.message}`);
        }
      }
      if (wantsGmail && !devsaiGmailEnabled) {
        throw new AuthRequiredError('gmail');
      }
      if (wantsDrive && !devsaiDriveEnabled) {
        throw new AuthRequiredError('drive');
      }
      tools = tools.filter(t => {
        if (t.type === 'mcp_server') {
          return true;
        }
        const name = t?.function?.name?.toLowerCase();
        if (!name) return false;

        // Remove local Gmail/Drive tools when using DevsAI MCP servers
        if (wantsGmail && name.includes('gmail')) return false;
        if (wantsDrive && name.startsWith('gdrive_')) return false;
        
        // Include all atlassian tools when jira or confluence is selected
        if (sources.some(s => ['jira', 'confluence'].includes(s.toLowerCase()))) {
          if (name.includes('atlassian')) {
            return true;
          }
        }
        
        return sources.some(s => name.includes(s.toLowerCase()));
      });
      
      if (sources.some(s => s.toLowerCase() === 'drive') && devsaiDriveEnabled) {
        console.log('[SearchService] Using DevsAI Drive MCP tool');
      }
      
      console.log(`[SearchService] Filtered tools: ${beforeCount} -> ${tools.length} for sources: ${sources.join(', ')}`);
    }
  } catch (err) {
    if (err instanceof AuthRequiredError) {
      throw err;
    }
    if (typeof err?.message === 'string' && err.message.startsWith('tool_unavailable:')) {
      throw err;
    }
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
    if (devsaiDriveEnabled) {
      defaultSystem += `

CRITICAL FOR GOOGLE DRIVE:
Use the Google Drive tool to search for relevant documents and read their contents.
Always open and summarize the most relevant files instead of just listing them.`;
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

class AuthRequiredError extends Error {
  constructor(tool) {
    super(`auth_required:${tool}`);
    this.name = 'AuthRequiredError';
    this.tool = tool;
    this.code = 'auth_required';
  }
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

    // Gmail MCP auth via DevsAI tool OAuth
    if (path === '/gmail/auth' && req.method === 'POST') {
      if (!devsaiLoaded) {
        await loadDevsaiModules();
      }
      if (!refreshApiClient()) {
        sendJson(res, { success: false, error: 'Not authenticated. Run: devsai login' }, 401);
        return;
      }
      const tool = await getChatToolByName(DEVSAI_TOOL_NAMES.gmail);
      if (!tool) {
        sendJson(res, { success: false, error: 'Gmail tool not found in DevsAI' }, 404);
        return;
      }
      const status = await getChatToolAuthStatus(tool.toolId).catch(() => null);
      if (status?.hasToken) {
        sendJson(res, { success: true, alreadyAuthenticated: true, toolId: tool.toolId });
        return;
      }
      const auth = await initiateChatToolAuth(tool.toolId);
      sendJson(res, { success: true, authUrl: auth.authUrl, toolId: tool.toolId });
      return;
    }

    // Gmail auth status check (DevsAI tool OAuth)
    if (path === '/gmail/status') {
      if (!devsaiLoaded) {
        await loadDevsaiModules();
      }
      if (!refreshApiClient()) {
        sendJson(res, { authenticated: false, error: 'Not authenticated. Run: devsai login' }, 401);
        return;
      }
      const tool = await getChatToolByName(DEVSAI_TOOL_NAMES.gmail);
      if (!tool) {
        sendJson(res, { authenticated: false, error: 'Gmail tool not found in DevsAI' }, 404);
        return;
      }
      const status = await getChatToolAuthStatus(tool.toolId).catch(() => null);
      sendJson(res, {
        authenticated: !!status?.hasToken,
        requiresAuth: tool.requiresAuth,
        toolId: tool.toolId,
        toolName: tool.name,
      });
      return;
    }

    if (path === '/gmail/disconnect' && req.method === 'POST') {
      if (!devsaiLoaded) {
        await loadDevsaiModules();
      }
      if (!refreshApiClient()) {
        sendJson(res, { success: false, error: 'Not authenticated. Run: devsai login' }, 401);
        return;
      }
      const tool = await getChatToolByName(DEVSAI_TOOL_NAMES.gmail);
      if (!tool) {
        sendJson(res, { success: false, error: 'Gmail tool not found in DevsAI' }, 404);
        return;
      }
      await revokeChatToolAuth(tool.toolId);
      sendJson(res, { success: true });
      return;
    }

    // Drive MCP auth via DevsAI tool OAuth
    if (path === '/drive/auth' && req.method === 'POST') {
      if (!devsaiLoaded) {
        await loadDevsaiModules();
      }
      if (!refreshApiClient()) {
        sendJson(res, { success: false, error: 'Not authenticated. Run: devsai login' }, 401);
        return;
      }
      const tool = await getChatToolByName(DEVSAI_TOOL_NAMES.drive);
      if (!tool) {
        sendJson(res, { success: false, error: 'Google Drive tool not found in DevsAI' }, 404);
        return;
      }
      const status = await getChatToolAuthStatus(tool.toolId).catch(() => null);
      if (status?.hasToken) {
        sendJson(res, { success: true, alreadyAuthenticated: true, toolId: tool.toolId });
        return;
      }
      const auth = await initiateChatToolAuth(tool.toolId);
      sendJson(res, { success: true, authUrl: auth.authUrl, toolId: tool.toolId });
      return;
    }

    // Drive auth status check (DevsAI tool OAuth)
    if (path === '/drive/status') {
      if (!devsaiLoaded) {
        await loadDevsaiModules();
      }
      if (!refreshApiClient()) {
        sendJson(res, { authenticated: false, error: 'Not authenticated. Run: devsai login' }, 401);
        return;
      }
      const tool = await getChatToolByName(DEVSAI_TOOL_NAMES.drive);
      if (!tool) {
        sendJson(res, { authenticated: false, error: 'Google Drive tool not found in DevsAI' }, 404);
        return;
      }
      const status = await getChatToolAuthStatus(tool.toolId).catch(() => null);
      sendJson(res, {
        authenticated: !!status?.hasToken,
        requiresAuth: tool.requiresAuth,
        toolId: tool.toolId,
        toolName: tool.name,
      });
      return;
    }

    if (path === '/drive/disconnect' && req.method === 'POST') {
      if (!devsaiLoaded) {
        await loadDevsaiModules();
      }
      if (!refreshApiClient()) {
        sendJson(res, { success: false, error: 'Not authenticated. Run: devsai login' }, 401);
        return;
      }
      const tool = await getChatToolByName(DEVSAI_TOOL_NAMES.drive);
      if (!tool) {
        sendJson(res, { success: false, error: 'Google Drive tool not found in DevsAI' }, 404);
        return;
      }
      await revokeChatToolAuth(tool.toolId);
      sendJson(res, { success: true });
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
        if (err instanceof AuthRequiredError || err?.code === 'auth_required') {
          sendEvent('error', { error: 'auth_required', tool: err.tool });
        } else {
          sendEvent('error', { error: err.message });
        }
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
    if (err instanceof AuthRequiredError || err?.code === 'auth_required') {
      sendJson(res, { error: 'auth_required', tool: err.tool }, 401);
    } else {
      sendJson(res, { error: err.message }, 500);
    }
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
