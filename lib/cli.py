"""CLI integration for BriefDesk - devsai CLI calls for meeting prep.

This module provides AI-powered search capabilities via:
1. Node.js search service (preferred - keeps MCP connections warm, ~10s)
2. Subprocess fallback (spawns devsai CLI, ~30-60s)
"""

import json
import os
import re
import shutil
import subprocess
import urllib.request
import urllib.error

from .cache import get_prompt
from .config import CONFIG_DIR, logger, get_hub_model
from .utils import extract_json_array

# =============================================================================
# Search Service Configuration
# =============================================================================

SEARCH_SERVICE_URL = "http://127.0.0.1:19765"
SEARCH_SERVICE_TIMEOUT = 60  # seconds

# Cache the search service availability check
_search_service_available = None
_search_service_check_time = 0

# =============================================================================
# Constants
# =============================================================================

# Default devsai paths
DEVSAI_LOCAL_PATH = os.path.expanduser('~/.local/share/devsai/devsai.sh')
DEVSAI_NVM_PATH = os.path.expanduser('~/.nvm/versions/node/v20.18.0/bin/devsai')
NVM_BIN_PATH = os.path.expanduser('~/.nvm/versions/node/v20.18.0/bin')

# Skip words for keyword extraction
MEETING_SKIP_WORDS = {
    'meeting', 'call', 'sync', 'weekly', 'daily', 'standup', 'stand-up',
    '1:1', '1-1', 'one', 'on', 'with', 'and', 'the', 'for', 'to', 'a', 'an'
}

# CLI output patterns to filter out
CLI_SKIP_PATTERNS = [
    'Connecting to MCP',
    'MCP server(s) connected',
    '[mcp_',
    '✓ Output delivered',
    'Output delivered',
    '✓ MCP',
    'Loading MCP',
    'Starting MCP',
]

# =============================================================================
# Search Service Functions
# =============================================================================

def _is_search_service_available():
    """Check if the Node.js search service is available.
    
    Caches the result for 30 seconds to avoid repeated checks.
    """
    global _search_service_available, _search_service_check_time
    import time
    
    now = time.time()
    if _search_service_available is not None and (now - _search_service_check_time) < 30:
        return _search_service_available
    
    try:
        req = urllib.request.Request(f"{SEARCH_SERVICE_URL}/health", method='GET')
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            _search_service_available = data.get("status") == "ok"
            _search_service_check_time = now
            return _search_service_available
    except Exception:
        _search_service_available = False
        _search_service_check_time = now
        return False


def _call_search_service(prompt, sources=None, system_prompt=None, timeout=60, max_iterations=5, model=None):
    """Call the search service to execute an AI query.
    
    Args:
        prompt: The query prompt
        sources: Optional list of sources to filter tools (e.g., ['slack', 'jira'])
        system_prompt: Optional custom system prompt
        timeout: Request timeout in seconds
        max_iterations: Max tool call iterations (default 5, use 8+ for complex queries)
        model: AI model to use (default: from hub config)
        
    Returns:
        Dict with 'response' and 'elapsed_ms', or None on failure
    """
    try:
        # Use configured model if not specified
        if model is None:
            model = get_hub_model()
        
        payload = {
            "prompt": prompt,
            "maxIterations": max_iterations,
            "model": model,
        }
        if sources:
            payload["sources"] = sources
        if system_prompt:
            payload["systemPrompt"] = system_prompt
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{SEARCH_SERVICE_URL}/query",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode())
            
    except urllib.error.URLError as e:
        logger.debug(f"[CLI] Search service error: {e}")
        return None
    except Exception as e:
        logger.debug(f"[CLI] Search service exception: {e}")
        return None


# =============================================================================
# CLI Helper Functions
# =============================================================================

def _get_devsai_path():
    """Get the path to the devsai binary.
    
    Prefers local bundled version (has Full Disk Access),
    falls back to system-installed if not found.
    """
    # Prefer local bundled devsai (has Full Disk Access)
    if os.path.exists(DEVSAI_LOCAL_PATH):
        return DEVSAI_LOCAL_PATH
    # Fall back to system devsai
    return shutil.which('devsai') or DEVSAI_NVM_PATH


def _get_cli_env():
    """Get environment variables for CLI execution.
    
    Sets up PATH for Node.js/Homebrew and prevents interactive prompts.
    """
    env = os.environ.copy()
    # Include NVM path, Homebrew paths, and existing PATH
    extra_paths = [
        NVM_BIN_PATH,
        '/opt/homebrew/bin',
        '/usr/local/bin',
    ]
    env['PATH'] = ':'.join(extra_paths) + ':' + env.get('PATH', '')
    # Prevent interactive OAuth prompts
    env['CI'] = 'true'
    env['BROWSER'] = 'false'
    return env


def _strip_ansi_codes(text):
    """Remove ANSI color/formatting codes from text."""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _filter_cli_output(output):
    """Filter out CLI progress/status messages from output.
    
    Args:
        output: Raw CLI output string
        
    Returns:
        Filtered output with progress messages removed
    """
    filtered_lines = []
    for line in output.split('\n'):
        line_stripped = line.strip()
        if not any(pattern in line_stripped for pattern in CLI_SKIP_PATTERNS):
            filtered_lines.append(line)
    return '\n'.join(filtered_lines).strip()


# =============================================================================
# Keyword Extraction
# =============================================================================

def extract_meeting_keywords(event):
    """Extract search keywords from a calendar event.
    
    Args:
        event: Calendar event dict with 'title', 'description', and 'attendees'
        
    Returns:
        List of unique keywords extracted from the event
    """
    keywords = []
    
    title = event.get('title', '')
    description = event.get('description', '')
    attendees = event.get('attendees', [])
    
    # Add title words (skip common meeting words)
    title_words = [w.strip().lower() for w in re.split(r'[\s\-/:|]+', title) if len(w) > 2]
    keywords.extend([w for w in title_words if w not in MEETING_SKIP_WORDS])
    
    # Extract project names, ticket IDs from description
    if description:
        # Look for Jira-style ticket IDs
        tickets = re.findall(r'\b([A-Z]+-\d+)\b', description)
        keywords.extend(tickets)
        
        # Look for URLs with project names
        urls = re.findall(r'https?://[^\s<>"]+', description)
        for url in urls:
            if 'jira' in url or 'confluence' in url:
                # Extract project key from Jira/Confluence URLs
                match = re.search(r'/([A-Z]+-\d+)', url)
                if match:
                    keywords.append(match.group(1))
    
    # Add attendee names (for Slack search)
    for attendee in attendees:
        name = attendee.get('name', '')
        if name and '@' not in name:
            keywords.append(name.split()[0])  # First name only
    
    return list(set(keywords))


# =============================================================================
# CLI Source Search
# =============================================================================

def call_cli_for_source(source, meeting_title, attendees_str, description='', timeout=90, max_retries=2, attendee_emails=None):
    """Call the CLI to search a specific source for meeting context.
    
    Uses the Node.js search service when available (faster, ~10s).
    Falls back to devsai CLI subprocess if service is unavailable (~30-60s).
    
    Args:
        source: Source to search ('jira', 'confluence', 'slack', 'gmail', 'drive')
        meeting_title: Title of the meeting
        attendees_str: Comma-separated string of attendee names
        description: Meeting description (optional)
        timeout: Timeout in seconds for CLI call (default 90)
        max_retries: Number of retry attempts on failure (default 2)
        attendee_emails: List of attendee email addresses (optional)
        
    Returns:
        List of results on success, each with 'title', 'url', 'type' keys.
        Returns {'error': str} dict on failure after all retries.
        Returns empty list if no results found.
    """
    # Build meeting context for the AI
    meeting_context = f"Meeting: {meeting_title}"
    if attendees_str:
        meeting_context += f"\nAttendees: {attendees_str}"
    if description:
        meeting_context += f"\nDescription: {description[:300]}"
    
    # Get prompt template (custom or default)
    prompt_template = get_prompt(source)
    if not prompt_template:
        return []
    
    # Build format variables that match the prompt templates
    emails_str = ', '.join(attendee_emails) if attendee_emails else ''
    format_vars = {
        'title': meeting_title,
        'attendees': attendees_str,
        'description': description[:300] if description else '',
        'limit': 5,  # Default limit
        'emails': emails_str,
        'context': meeting_context,
        'meeting_context': meeting_context,  # Legacy support
        'meeting_title': meeting_title,  # Legacy support
    }
    
    # Handle drive-specific variables
    if source == 'drive':
        from lib.config import GOOGLE_DRIVE_BASE
        if not GOOGLE_DRIVE_BASE:
            logger.warning("[CLI] Google Drive path not configured")
            return []
        format_vars['drive_path'] = GOOGLE_DRIVE_BASE
    
    # Format the prompt with all variables
    try:
        prompt = prompt_template.format(**format_vars)
    except KeyError as e:
        logger.warning(f"[CLI] Missing prompt variable {e}, using empty string")
        format_vars[str(e).strip("'")] = ''
        prompt = prompt_template.format(**format_vars)
    
    # Try the search service first (fast path)
    if _is_search_service_available():
        logger.info(f"[CLI] Using search service for {source}: {meeting_title[:50]}")
        
        # Map source names to MCP server tool prefixes
        source_mapping = {
            'jira': ['atlassian'],
            'confluence': ['atlassian'],
            'slack': ['slack'],
            'gmail': ['gmail'],
            'drive': ['drive'],  # Drive uses gdrive MCP (API) or CLI file tools (fallback)
            'github': ['github'],  # GitHub MCP server (search_code, search_repositories, etc.)
        }
        sources_filter = source_mapping.get(source, [source])
        
        result = _call_search_service(prompt, sources=sources_filter, timeout=timeout)
        if result:
            response = result.get('response', '')
            elapsed = result.get('elapsed_ms', '?')
            logger.info(f"[CLI] Search service {source} completed in {elapsed}ms")
            
            # Try to extract JSON array from response
            items = extract_json_array(response)
            if items is not None:
                logger.info(f"[CLI] {source} returned {len(items)} items via search service")
                return items
            
            # No JSON array found - return empty
            logger.info(f"[CLI] {source} returned empty from search service")
            return []
        else:
            logger.warning(f"[CLI] Search service failed for {source}, falling back to subprocess")
    
    # Fallback to subprocess (slow path)
    return _call_cli_subprocess(source, prompt, timeout, max_retries)


def _call_cli_subprocess(source, prompt, timeout=90, max_retries=2):
    """Execute CLI search via subprocess (fallback when search service unavailable).
    
    Args:
        source: Source name for logging
        prompt: The formatted prompt
        timeout: Timeout in seconds
        max_retries: Number of retry attempts
        
    Returns:
        List of results or error dict
    """
    devsai_path = _get_devsai_path()
    last_error = None
    env = _get_cli_env()
    model = get_hub_model()  # Use configured model
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.info(f"[CLI] Retry {attempt + 1}/{max_retries} for {source}")
            logger.info(f"[CLI] Starting {source} subprocess call")
            
            logger.debug(f"[CLI] devsai_path: {devsai_path}, cwd: {CONFIG_DIR}")
            
            proc = subprocess.Popen(
                [devsai_path, '-p', prompt, '--max-iterations', '5', '-m', model],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=CONFIG_DIR
            )
            
            stdout, stderr = proc.communicate(timeout=timeout)
            output = (stdout.decode() + stderr.decode()).strip()
            
            logger.debug(f"[CLI] {source} output length: {len(output)}")
            logger.debug(f"[CLI] {source} output preview: {output[:300] if output else '(empty)'}")
            
            # Try to extract JSON array from output
            result = extract_json_array(output)
            if result is not None:
                logger.info(f"[CLI] {source} returned {len(result)} items via subprocess")
                return result
            
            # If no JSON found but no error, return empty
            if output and 'error' not in output.lower():
                logger.info(f"[CLI] {source} returned empty (no JSON array found)")
                return []
            
            last_error = "No JSON array found in output"
            
        except subprocess.TimeoutExpired:
            proc.kill()
            last_error = f'timeout after {timeout}s'
            logger.error(f"[CLI] {source} {last_error} (attempt {attempt + 1}/{max_retries})")
        except Exception as e:
            last_error = str(e)
            logger.error(f"[CLI] {source} exception: {e} (attempt {attempt + 1}/{max_retries})")
    
    logger.error(f"[CLI] {source} failed after {max_retries} attempts: {last_error}")
    return {'error': f'{source} search failed: {last_error}'}


# =============================================================================
# Meeting Summary Generation
# =============================================================================

def call_cli_for_meeting_summary(meeting_title, attendees_str, attendee_emails, description='', timeout=120):
    """Call the CLI to generate a comprehensive meeting prep summary.
    
    Uses the Node.js search service when available (faster, ~15-30s).
    Falls back to devsai CLI subprocess if service is unavailable (~60-90s).
    
    Args:
        meeting_title: Title of the meeting
        attendees_str: Comma-separated string of attendee names
        attendee_emails: List of attendee email addresses
        description: Meeting description (optional)
        timeout: Timeout in seconds for CLI call (default 120)
        
    Returns:
        Dict with:
            - 'summary': The generated summary text
            - 'status': 'success', 'empty', 'timeout', or 'error'
            - 'error': Error message if status is 'error'
    """
    # Build meeting context
    meeting_context = f"Meeting: {meeting_title}"
    if attendees_str:
        meeting_context += f"\nAttendees: {attendees_str}"
    if attendee_emails:
        meeting_context += f"\nAttendee emails: {', '.join(attendee_emails[:5])}"
    if description:
        meeting_context += f"\nDescription: {description[:500]}"
    
    # Get prompt template (custom or default)
    prompt_template = get_prompt('summary')
    prompt = prompt_template.format(
        title=meeting_title,
        attendees=attendees_str or '',
        description=description or '',
        context=meeting_context
    )
    
    # Try the search service first (fast path)
    if _is_search_service_available():
        logger.info(f"[CLI] Using search service for summary: {meeting_title[:50]}")
        
        # Custom system prompt for summary generation (not JSON output)
        summary_system = """You are a meeting prep assistant. You MUST use the available MCP tools to search for context before generating any response.

CRITICAL: You MUST call at least 2-3 search tools before responding. DO NOT respond with generic messages like "How can I help?" - always search first, then summarize findings.

REQUIRED STEPS:
1. Call mcp_slack__search_messages to find relevant Slack discussions
2. Call mcp_atlassian__search_jira or mcp_atlassian__get_issues for related tickets
3. Call mcp_atlassian__search_confluence for relevant docs (optional)
4. Then synthesize findings into a brief

OUTPUT FORMAT (markdown, under 200 words):
**Quick Context**: 1-2 sentences on meeting purpose

**What to Know**:
- Key bullet points from your searches (tickets, discussions, blockers)
- Be specific: include ticket IDs, channel names, dates
- Max 4-5 bullets

**Suggested Topics**:
1. First discussion topic
2. Second topic  
3. Third topic (optional)

If a search returns no results, note that briefly and move on. Always provide SOME summary based on what you found."""
        
        # Use all sources for summary generation (more iterations for complex task)
        result = _call_search_service(
            prompt, 
            sources=['slack', 'atlassian', 'gmail'],
            system_prompt=summary_system,
            timeout=timeout,
            max_iterations=8
        )
        
        if result:
            response = result.get('response', '')
            elapsed = result.get('elapsed_ms', '?')
            logger.info(f"[CLI] Summary completed via search service in {elapsed}ms")
            
            # Clean up the response
            response = _strip_ansi_codes(response)
            response = _filter_cli_output(response)
            
            if response:
                return {'summary': response, 'status': 'success'}
            else:
                return {'summary': '', 'status': 'empty'}
        else:
            logger.warning(f"[CLI] Search service failed for summary, falling back to subprocess")
    
    # Fallback to subprocess (slow path)
    return _call_cli_subprocess_summary(prompt, timeout)


def _call_cli_subprocess_summary(prompt, timeout=120):
    """Execute summary generation via subprocess (fallback).
    
    Args:
        prompt: The formatted prompt
        timeout: Timeout in seconds
        
    Returns:
        Dict with summary, status, and optional error
    """
    devsai_path = _get_devsai_path()
    model = get_hub_model()  # Use configured model
    
    try:
        env = _get_cli_env()
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        proc = subprocess.Popen(
            [devsai_path, '-p', prompt, '--max-iterations', '8', '-m', model],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=project_dir
        )
        
        stdout, stderr = proc.communicate(timeout=timeout)
        output = (stdout.decode() + stderr.decode()).strip()
        
        # Clean up the output
        output = _strip_ansi_codes(output)
        output = _filter_cli_output(output)
        
        if output:
            return {'summary': output, 'status': 'success'}
        else:
            return {'summary': '', 'status': 'empty', 'stderr': stderr.decode()[:500] if stderr else ''}
            
    except subprocess.TimeoutExpired:
        proc.kill()
        return {'summary': '', 'status': 'timeout'}
    except Exception as e:
        return {'summary': '', 'status': 'error', 'error': str(e)}
