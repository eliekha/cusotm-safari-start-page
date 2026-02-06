"""Atlassian (Jira/Confluence) and MCP integration for BriefDesk."""

import json
import os
import re
import subprocess
import select
import threading
import time

from .config import logger, MCP_CONFIG_PATH

# =============================================================================
# Global State
# =============================================================================

_atlassian_process = None
_atlassian_lock = threading.Lock()
_atlassian_msg_id = 0
_atlassian_initialized = False
_mcp_config_cache = None

# Load config for Atlassian domain
_config_data = None

def _get_atlassian_domain():
    """Get Atlassian domain from config (re-reads each time to pick up auto-detected domain)."""
    global _config_data
    _config_data = load_config()
    return _config_data.get('atlassian_domain', 'your-domain.atlassian.net')

ATLASSIAN_DOMAIN = property(lambda self: _get_atlassian_domain())

# =============================================================================
# Config Loading
# =============================================================================

def load_mcp_config():
    """Load MCP server configuration."""
    global _mcp_config_cache
    if _mcp_config_cache is not None:
        return _mcp_config_cache
    
    try:
        # Check local config first
        local_config = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.devsai.json')
        if os.path.exists(local_config):
            with open(local_config, 'r') as f:
                _mcp_config_cache = json.load(f).get('mcpServers', {})
                return _mcp_config_cache
        
        # Fall back to global config
        if os.path.exists(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, 'r') as f:
                _mcp_config_cache = json.load(f).get('mcpServers', {})
                return _mcp_config_cache
    except Exception as e:
        logger.debug(f"Error loading MCP config: {e}")
    
    return {}


def load_config():
    """Load general config from file or environment variables."""
    config = {"slack_workspace": "your-workspace", "atlassian_domain": "your-domain.atlassian.net"}
    config_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json'),
        os.path.expanduser('~/.local/share/briefdesk/config.json'),
        os.path.expanduser('~/.config/briefdesk/config.json')
    ]
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    config.update(json.load(f))
                break
            except: 
                pass
    # Environment variables override config file
    config['slack_workspace'] = os.environ.get("SLACK_WORKSPACE", config.get('slack_workspace', 'your-workspace'))
    config['atlassian_domain'] = os.environ.get("ATLASSIAN_DOMAIN", config.get('atlassian_domain', 'your-domain.atlassian.net'))
    return config

# =============================================================================
# Atlassian MCP Process Management
# =============================================================================

def get_atlassian_process():
    """Get or create persistent Atlassian MCP process."""
    global _atlassian_process, _atlassian_initialized, _atlassian_msg_id
    
    with _atlassian_lock:
        # Check if process is still running
        if _atlassian_process and _atlassian_process.poll() is None:
            return _atlassian_process
        
        # Start new process
        config = load_mcp_config()
        server_config = config.get('atlassian')
        if not server_config:
            return None
        
        command = server_config.get('command')
        args = server_config.get('args', [])
        
        if not command:
            return None
        
        try:
            env = os.environ.copy()
            env['PATH'] = '/usr/local/bin:/usr/bin:/bin:' + env.get('PATH', '')
            
            _atlassian_process = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0
            )
            
            _atlassian_initialized = False
            _atlassian_msg_id = 0
            
            # Wait a moment for the process to start
            time.sleep(2)
            
            # Initialize MCP session
            _atlassian_msg_id += 1
            init_request = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": _atlassian_msg_id,
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "briefdesk", "version": "1.0.0"}
                }
            }
            
            _atlassian_process.stdin.write((json.dumps(init_request) + '\n').encode())
            _atlassian_process.stdin.flush()
            
            # Read initialization response (may take a moment for OAuth)
            response_line = _atlassian_process.stdout.readline().decode().strip()
            if response_line:
                try:
                    response = json.loads(response_line)
                    if 'result' in response:
                        _atlassian_initialized = True
                        # Send initialized notification
                        _atlassian_process.stdin.write((json.dumps({
                            "jsonrpc": "2.0", 
                            "method": "notifications/initialized"
                        }) + '\n').encode())
                        _atlassian_process.stdin.flush()
                except json.JSONDecodeError:
                    pass
            
            return _atlassian_process
            
        except Exception as e:
            logger.error(f"Failed to start Atlassian MCP: {e}")
            return None


def call_atlassian_tool(tool_name, arguments, timeout=15):
    """Call an Atlassian MCP tool using the persistent process."""
    global _atlassian_msg_id
    
    proc = get_atlassian_process()
    if not proc or proc.poll() is not None:
        return {"error": "Atlassian MCP not available"}
    
    if not _atlassian_initialized:
        return {"error": "Atlassian MCP not initialized"}
    
    with _atlassian_lock:
        try:
            _atlassian_msg_id += 1
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": _atlassian_msg_id,
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            proc.stdin.write((json.dumps(request) + '\n').encode())
            proc.stdin.flush()
            
            # Read response with timeout
            ready, _, _ = select.select([proc.stdout], [], [], timeout)
            if ready:
                response_line = proc.stdout.readline().decode().strip()
                if response_line:
                    response = json.loads(response_line)
                    if 'error' in response:
                        return {"error": response['error']}
                    return response.get('result', {})
            
            return {"error": "Atlassian MCP timeout"}
            
        except Exception as e:
            return {"error": f"Atlassian MCP error: {e}"}


def call_mcp_tool(server_name, tool_name, arguments):
    """Call an MCP tool via subprocess and return the result."""
    config = load_mcp_config()
    server_config = config.get(server_name)
    if not server_config:
        return {"error": f"MCP server '{server_name}' not configured"}
    
    command = server_config.get('command')
    args = server_config.get('args', [])
    env_vars = server_config.get('env', {})
    
    if not command:
        return {"error": f"No command specified for MCP server '{server_name}'"}
    
    # Build the MCP request
    mcp_request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": 1,
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    
    try:
        # Set up environment
        env = os.environ.copy()
        env.update(env_vars)
        # Ensure PATH includes node
        if 'PATH' not in env_vars:
            env['PATH'] = '/usr/local/bin:/usr/bin:/bin:' + env.get('PATH', '')
        
        # Use shell pipe approach which works better with stdio MCP servers
        full_cmd = f'echo {repr(json.dumps(mcp_request))} | {command} {" ".join(args)}'
        
        proc = subprocess.Popen(
            full_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        
        stdout, stderr = proc.communicate(timeout=30)
        
        # Parse response - may have multiple JSON objects, get the last valid one with result/error
        response_text = stdout.decode().strip()
        result = None
        
        for line in response_text.split('\n'):
            line = line.strip()
            if line and line.startswith('{'):
                try:
                    parsed = json.loads(line)
                    if 'result' in parsed or 'error' in parsed:
                        result = parsed
                except json.JSONDecodeError:
                    continue
        
        if result:
            if 'error' in result:
                return {"error": result['error']}
            return result.get('result', {})
        
        # If no result found, return raw stdout for debugging
        return {"error": f"No valid MCP response. stdout={response_text[:200]}"}
        
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"error": "MCP call timed out"}
    except Exception as e:
        return {"error": str(e)}

# =============================================================================
# Content Extraction
# =============================================================================

def extract_mcp_content(result):
    """Extract text content from MCP tool result."""
    if not result:
        return None
    
    # Check for content array (standard MCP format)
    if 'content' in result and isinstance(result['content'], list):
        for item in result['content']:
            if isinstance(item, dict) and item.get('type') == 'text':
                return item.get('text', '')
    
    # Fallback - return as is
    return result

# =============================================================================
# Atlassian Search Functions
# =============================================================================

def search_atlassian(query, limit=5):
    """Search both Jira and Confluence using Rovo unified search."""
    atlassian_domain = _get_atlassian_domain()
    result = call_atlassian_tool('search', {'query': query})
    
    if isinstance(result, dict) and 'error' not in result:
        jira_items = []
        confluence_items = []
        
        content = result.get('content', [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    text = item.get('text', '')
                    # The response may be JSON-formatted
                    try:
                        data = json.loads(text)
                        results = data.get('results', [])
                        for r in results[:limit*2]:
                            ari = r.get('id', '')
                            title = r.get('title', '')
                            url = r.get('url', '')
                            
                            # Determine if Jira or Confluence based on ARI
                            if ':jira:' in ari or ':issue/' in ari:
                                # Extract issue key from title or generate from ARI
                                key_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', title)
                                key = key_match.group(1) if key_match else ''
                                jira_items.append({
                                    'title': title[:150],
                                    'key': key,
                                    'url': url or (f'https://{atlassian_domain}/browse/{key}' if key else ''),
                                    'ari': ari
                                })
                            elif ':confluence:' in ari or ':page/' in ari:
                                confluence_items.append({
                                    'title': title[:150],
                                    'space': r.get('space', {}).get('name', ''),
                                    'url': url or '',
                                    'ari': ari
                                })
                    except json.JSONDecodeError:
                        # Fallback to line-based parsing
                        lines = text.strip().split('\n')
                        for line in lines[:limit*2]:
                            line = line.strip()
                            if not line:
                                continue
                            key_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', line)
                            if key_match:
                                key = key_match.group(1)
                                jira_items.append({
                                    'title': line[:150],
                                    'key': key,
                                    'url': f'https://{atlassian_domain}/browse/{key}'
                                })
        
        return {
            'jira': jira_items[:limit],
            'confluence': confluence_items[:limit]
        }
    
    return {'jira': [], 'confluence': [], 'error': result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'}


def get_jira_context(query, limit=5):
    """Search Jira for issues related to a query."""
    result = search_atlassian(query, limit)
    if isinstance(result, dict):
        return result.get('jira', [])
    return []


def search_confluence(query, limit=5):
    """Search Confluence for pages related to a query."""
    result = search_atlassian(query, limit)
    if isinstance(result, dict):
        return result.get('confluence', [])
    return []


def list_atlassian_tools():
    """List available Atlassian MCP tools - useful for debugging."""
    global _atlassian_msg_id
    
    proc = get_atlassian_process()
    if not proc or proc.poll() is not None:
        return {"error": "Atlassian MCP not available"}
    
    with _atlassian_lock:
        try:
            _atlassian_msg_id += 1
            request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": _atlassian_msg_id,
                "params": {}
            }
            
            proc.stdin.write((json.dumps(request) + '\n').encode())
            proc.stdin.flush()
            
            ready, _, _ = select.select([proc.stdout], [], [], 10)
            if ready:
                response_line = proc.stdout.readline().decode().strip()
                if response_line:
                    response = json.loads(response_line)
                    return response.get('result', {})
            
            return {"error": "Timeout listing tools"}
            
        except Exception as e:
            return {"error": f"Error listing tools: {e}"}
