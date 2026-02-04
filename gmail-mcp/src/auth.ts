/**
 * Google OAuth Authentication for Gmail
 * 
 * Handles OAuth 2.0 flow for Gmail API access.
 * Uses READ-ONLY scope only - no ability to send or modify emails.
 * Credentials are stored locally - never sent anywhere except Google.
 */

import { google } from 'googleapis';
import { OAuth2Client } from 'google-auth-library';
import * as fs from 'fs';
import * as path from 'path';
import * as http from 'http';
import { URL } from 'url';

// Paths for credential storage - use existing Gmail MCP location
const HOME = process.env.HOME || '';
const GMAIL_MCP_DIR = path.join(HOME, '.gmail-mcp');
const OAUTH_KEYS_PATH = path.join(GMAIL_MCP_DIR, 'gcp-oauth.keys.json');
const TOKEN_PATH = path.join(GMAIL_MCP_DIR, 'credentials.json');

// READ-ONLY scope - cannot send, modify, or delete emails
const SCOPES = ['https://www.googleapis.com/auth/gmail.readonly'];

interface OAuthKeys {
  installed?: {
    client_id: string;
    client_secret: string;
    redirect_uris: string[];
  };
  web?: {
    client_id: string;
    client_secret: string;
    redirect_uris: string[];
  };
}

interface TokenData {
  access_token: string;
  refresh_token: string;
  scope: string;
  token_type: string;
  expiry_date: number;
}

/**
 * Load OAuth keys from the credentials file
 */
function loadOAuthKeys(): OAuthKeys {
  if (!fs.existsSync(OAUTH_KEYS_PATH)) {
    throw new Error(
      `OAuth keys not found at ${OAUTH_KEYS_PATH}\n` +
      'Please download your OAuth credentials from Google Cloud Console and save them there.\n' +
      'See README.md for setup instructions.'
    );
  }
  
  const content = fs.readFileSync(OAUTH_KEYS_PATH, 'utf-8');
  return JSON.parse(content);
}

/**
 * Create an OAuth2 client from saved keys
 */
function createOAuth2Client(): OAuth2Client {
  const keys = loadOAuthKeys();
  const config = keys.installed || keys.web;
  
  if (!config) {
    throw new Error('Invalid OAuth keys format. Expected "installed" or "web" credentials.');
  }
  
  return new google.auth.OAuth2(
    config.client_id,
    config.client_secret,
    'http://localhost:3334/callback'  // Different port than GDrive MCP
  );
}

/**
 * Load saved token if it exists
 */
function loadToken(): TokenData | null {
  if (!fs.existsSync(TOKEN_PATH)) {
    return null;
  }
  
  try {
    const content = fs.readFileSync(TOKEN_PATH, 'utf-8');
    const token = JSON.parse(content);
    
    // Verify scope is read-only
    if (token.scope && !token.scope.includes('gmail.readonly')) {
      console.error('Warning: Token has non-readonly scope. Re-authentication recommended.');
    }
    
    return token;
  } catch {
    return null;
  }
}

/**
 * Save token to local file
 */
function saveToken(token: TokenData): void {
  // Ensure config directory exists
  if (!fs.existsSync(GMAIL_MCP_DIR)) {
    fs.mkdirSync(GMAIL_MCP_DIR, { recursive: true });
  }
  
  fs.writeFileSync(TOKEN_PATH, JSON.stringify(token, null, 2));
  console.log('Token saved to', TOKEN_PATH);
}

/**
 * Get authenticated OAuth2 client
 * Returns null if not authenticated yet
 */
export async function getAuthenticatedClient(): Promise<OAuth2Client | null> {
  const oauth2Client = createOAuth2Client();
  const token = loadToken();
  
  if (!token) {
    return null;
  }
  
  oauth2Client.setCredentials(token);
  
  // Check if token needs refresh
  if (token.expiry_date && token.expiry_date < Date.now()) {
    try {
      const { credentials } = await oauth2Client.refreshAccessToken();
      saveToken(credentials as TokenData);
      oauth2Client.setCredentials(credentials);
    } catch (err) {
      console.error('Failed to refresh token:', err);
      return null;
    }
  }
  
  return oauth2Client;
}

/**
 * Run interactive OAuth flow
 * Opens browser for user to authenticate
 */
export async function runAuthFlow(): Promise<void> {
  const oauth2Client = createOAuth2Client();
  
  const authUrl = oauth2Client.generateAuthUrl({
    access_type: 'offline',
    scope: SCOPES,
    prompt: 'consent', // Force consent to get refresh token
  });
  
  console.log('\n=== Gmail MCP Authentication (READ-ONLY) ===\n');
  console.log('This will grant READ-ONLY access to Gmail.');
  console.log('No ability to send, modify, or delete emails.\n');
  console.log('Opening browser for authentication...');
  console.log('If browser does not open, visit this URL:\n');
  console.log(authUrl);
  console.log('\n');
  
  // Open browser
  const { exec } = await import('child_process');
  exec(`open "${authUrl}"`);
  
  // Start local server to receive callback
  const code = await waitForAuthCode();
  
  console.log('Received authorization code, exchanging for token...');
  
  const { tokens } = await oauth2Client.getToken(code);
  saveToken(tokens as TokenData);
  
  console.log('\n✓ Authentication successful!');
  console.log('You can now use the Gmail MCP server.\n');
}

/**
 * Start a temporary local server to receive OAuth callback
 */
function waitForAuthCode(): Promise<string> {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const url = new URL(req.url || '', 'http://localhost:3334');
      
      if (url.pathname === '/callback') {
        const code = url.searchParams.get('code');
        const error = url.searchParams.get('error');
        
        if (error) {
          res.writeHead(400, { 'Content-Type': 'text/html' });
          res.end('<h1>Authentication Failed</h1><p>Error: ' + error + '</p>');
          server.close();
          reject(new Error(`OAuth error: ${error}`));
          return;
        }
        
        if (code) {
          res.writeHead(200, { 'Content-Type': 'text/html' });
          res.end(`
            <html>
              <body style="font-family: system-ui; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #1a1a2e; color: #fff;">
                <div style="text-align: center;">
                  <h1 style="color: #4ade80;">✓ Gmail Authentication Successful</h1>
                  <p>Read-only access granted. You can close this window.</p>
                </div>
              </body>
            </html>
          `);
          server.close();
          resolve(code);
          return;
        }
      }
      
      res.writeHead(404);
      res.end('Not found');
    });
    
    server.listen(3334, () => {
      console.log('Waiting for authentication callback on http://localhost:3334/callback');
    });
    
    // Timeout after 5 minutes
    setTimeout(() => {
      server.close();
      reject(new Error('Authentication timed out'));
    }, 5 * 60 * 1000);
  });
}

/**
 * Check if we have valid credentials
 */
export function isAuthenticated(): boolean {
  const token = loadToken();
  return token !== null && token.refresh_token !== undefined;
}
