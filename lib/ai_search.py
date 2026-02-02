"""
AI Search Module

Provides fast AI-powered search across Slack, Jira, Gmail, Confluence, etc.
Uses the Node.js search service which keeps MCP connections warm.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Search service configuration
SEARCH_SERVICE_URL = "http://127.0.0.1:19765"
DEFAULT_TIMEOUT = 60  # seconds


def is_search_service_available() -> bool:
    """Check if the AI search service is running and ready."""
    try:
        req = urllib.request.Request(f"{SEARCH_SERVICE_URL}/health")
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            return data.get("status") == "ok"
    except Exception as e:
        logger.debug(f"[AISearch] Service not available: {e}")
        return False


def get_service_status() -> Dict[str, Any]:
    """Get detailed status of the search service including MCP connections."""
    try:
        req = urllib.request.Request(f"{SEARCH_SERVICE_URL}/status")
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        logger.error(f"[AISearch] Failed to get status: {e}")
        return {"error": str(e), "initialized": False}


def ai_search(
    query: str,
    sources: Optional[List[str]] = None,
    model: str = "gpt-4o",
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Perform AI-powered search across connected sources.
    
    Args:
        query: Natural language search query
        sources: List of sources to search (e.g., ['slack', 'jira', 'gmail'])
                 If None, searches all available sources
        model: AI model to use (default: gpt-4o)
        timeout: Request timeout in seconds
        
    Returns:
        Dict with:
            - response: AI-generated response (usually JSON array of results)
            - iterations: Number of tool call iterations
            - elapsed_ms: Time taken in milliseconds
            - error: Error message if failed
    """
    try:
        # Build request
        payload = {
            "query": query,
            "model": model,
        }
        if sources:
            payload["sources"] = sources
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{SEARCH_SERVICE_URL}/search",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        logger.info(f"[AISearch] Searching: {query[:50]}... sources={sources}")
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode())
            logger.info(f"[AISearch] Complete in {result.get('elapsed_ms', '?')}ms")
            return result
            
    except urllib.error.URLError as e:
        error_msg = f"Search service unavailable: {e.reason}"
        logger.error(f"[AISearch] {error_msg}")
        return {"error": error_msg, "response": None}
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[AISearch] Error: {error_msg}")
        return {"error": error_msg, "response": None}


def ai_query(
    prompt: str,
    system_prompt: Optional[str] = None,
    sources: Optional[List[str]] = None,
    model: str = "gpt-4o",
    max_iterations: int = 10,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Execute a raw AI query with MCP tools.
    
    More flexible than ai_search - allows custom system prompts and more control.
    
    Args:
        prompt: The user prompt
        system_prompt: Custom system prompt (overrides default)
        sources: List of sources to include tools from
        model: AI model to use
        max_iterations: Maximum tool call iterations
        timeout: Request timeout in seconds
        
    Returns:
        Dict with response and metadata
    """
    try:
        payload = {
            "prompt": prompt,
            "model": model,
            "maxIterations": max_iterations,
        }
        if system_prompt:
            payload["systemPrompt"] = system_prompt
        if sources:
            payload["sources"] = sources
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{SEARCH_SERVICE_URL}/query",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        logger.info(f"[AISearch] Query: {prompt[:50]}...")
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode())
            logger.info(f"[AISearch] Complete in {result.get('elapsed_ms', '?')}ms")
            return result
            
    except urllib.error.URLError as e:
        error_msg = f"Search service unavailable: {e.reason}"
        logger.error(f"[AISearch] {error_msg}")
        return {"error": error_msg, "response": None}
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[AISearch] Error: {error_msg}")
        return {"error": error_msg, "response": None}


def parse_search_results(response: str) -> List[Dict[str, Any]]:
    """
    Parse AI search response into structured results.
    
    The AI typically returns a JSON array, but might include explanation text.
    This function extracts and parses the JSON.
    
    Args:
        response: Raw response from AI
        
    Returns:
        List of result dicts, or empty list if parsing fails
    """
    if not response:
        return []
    
    # Try direct JSON parse
    try:
        data = json.loads(response)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON array from text
    import re
    match = re.search(r'\[[\s\S]*\]', response)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    
    # Return empty if can't parse
    logger.warning("[AISearch] Could not parse response as JSON array")
    return []
