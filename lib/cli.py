"""CLI integration for BriefDesk - devsai CLI calls for meeting prep."""

import glob
import os
import re
import shutil
import subprocess

from .cache import get_prompt
from .config import CONFIG_DIR, logger
from .utils import extract_json_array

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
# Helper Functions
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
    
    Uses the devsai CLI to search external sources (Jira, Confluence, Slack, etc.)
    for content relevant to an upcoming meeting.
    
    Args:
        source: Source to search ('jira', 'confluence', 'slack', 'gmail', 'drive')
        meeting_title: Title of the meeting
        attendees_str: Comma-separated string of attendee names
        description: Meeting description (optional)
        timeout: Timeout in seconds for CLI call (default 60)
        max_retries: Number of retry attempts on failure (default 2)
        
    Returns:
        List of results on success, each with 'title', 'url', 'type' keys.
        Returns {'error': str} dict on failure after all retries.
        Returns empty list if no results found.
    """
    devsai_path = _get_devsai_path()
    
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
        # Add missing key with empty string and retry
        format_vars[str(e).strip("'")] = ''
        prompt = prompt_template.format(**format_vars)
    
    last_error = None
    env = _get_cli_env()
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.info(f"[CLI] Retry {attempt + 1}/{max_retries} for {source}")
            logger.info(f"[CLI] Starting {source} call for meeting: {meeting_title[:50]}")
            
            logger.debug(f"[CLI] devsai_path: {devsai_path}, cwd: {CONFIG_DIR}")
            
            proc = subprocess.Popen(
                [devsai_path, '-p', prompt, '--max-iterations', '5', '-m', 'anthropic-claude-4-5-haiku'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=CONFIG_DIR
            )
            
            stdout, stderr = proc.communicate(timeout=timeout)
            # devsai outputs to stderr, combine both for parsing
            output = (stdout.decode() + stderr.decode()).strip()
            
            logger.debug(f"[CLI] {source} output length: {len(output)}")
            logger.debug(f"[CLI] {source} output preview: {output[:300] if output else '(empty)'}")
            
            # Try to extract JSON array from output
            result = extract_json_array(output)
            if result is not None:
                logger.info(f"[CLI] {source} returned {len(result)} items")
                return result
            
            # If no JSON found but no error, return empty (don't retry for empty results)
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
    
    # All retries failed
    logger.error(f"[CLI] {source} failed after {max_retries} attempts: {last_error}")
    return {'error': f'{source} search failed: {last_error}'}


# =============================================================================
# Meeting Summary Generation
# =============================================================================

def call_cli_for_meeting_summary(meeting_title, attendees_str, attendee_emails, description='', timeout=90):
    """Call the CLI to generate a comprehensive meeting prep summary.
    
    This searches all sources, READS the actual content, and generates a summary
    using the AI to synthesize relevant information for meeting preparation.
    
    Args:
        meeting_title: Title of the meeting
        attendees_str: Comma-separated string of attendee names
        attendee_emails: List of attendee email addresses
        description: Meeting description (optional)
        timeout: Timeout in seconds for CLI call (default 90)
        
    Returns:
        Dict with:
            - 'summary': The generated summary text
            - 'status': 'success', 'empty', 'timeout', or 'error'
            - 'error': Error message if status is 'error'
            - 'stderr': Stderr output if status is 'empty'
    """
    devsai_path = _get_devsai_path()
    
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
    
    try:
        env = _get_cli_env()
        # Use the module's directory for cwd (same as original behavior)
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        proc = subprocess.Popen(
            [devsai_path, '-p', prompt, '--max-iterations', '8', '-m', 'anthropic-claude-4-5-haiku'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=project_dir
        )
        
        stdout, stderr = proc.communicate(timeout=timeout)
        # devsai outputs to stderr, combine both
        output = (stdout.decode() + stderr.decode()).strip()
        
        # Strip ANSI color codes from CLI output
        output = _strip_ansi_codes(output)
        
        # Filter out CLI progress/status messages
        output = _filter_cli_output(output)
        
        # Return the summary text
        if output:
            return {'summary': output, 'status': 'success'}
        else:
            return {'summary': '', 'status': 'empty', 'stderr': stderr.decode()[:500] if stderr else ''}
            
    except subprocess.TimeoutExpired:
        proc.kill()
        return {'summary': '', 'status': 'timeout'}
    except Exception as e:
        return {'summary': '', 'status': 'error', 'error': str(e)}
