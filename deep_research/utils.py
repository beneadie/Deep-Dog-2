

"""Research Utilities and Tools.

This module provides search and content processing utilities for the research agent,
including web search capabilities and content summarization tools.
"""

from pathlib import Path
from datetime import datetime
from typing_extensions import Annotated, Dict, List, Literal, Optional
import requests
import aiohttp
import asyncio
import json
from pydantic import BaseModel, Field

from langchain_core.tools import tool, InjectedToolArg
from tavily import TavilyClient

from deep_research.config import EXA_SEARCH_MAX_CHARS
from deep_research.observability import log_source
from deep_research.time_utils import get_today_str  # re-export (canonical def lives in time_utils.py)

# ===== UTILITY FUNCTIONS =====

import logging
logger = logging.getLogger(__name__)

# ANSI color codes for tool-specific log highlighting
_ORANGE = "\033[38;5;208m"  # Orange for Substack
_DARK_ORANGE = "\033[38;5;166m"  # Dark orange/red for Reddit
_RESET = "\033[0m"

def extract_text_from_response(content) -> str:
    """
    Safely extract text from a model response, handling different provider formats.

    Different LLM providers return content in different formats:
    - OpenAI: Returns plain string
    - Gemini: May return list of dicts with 'type' and 'text' keys
    - Anthropic: May return list of content blocks

    This function normalizes all formats to a plain string, logging warnings
    for unexpected formats but never discarding data.

    Args:
        content: The .content attribute from a model response

    Returns:
        A plain string with the extracted text content
    """
    # Case 1: Already a string - most common, return as-is
    if isinstance(content, str):
        return content

    # Case 2: None or empty
    if content is None:
        logger.warning("Model returned None content")
        return ""

    # Case 3: List (Gemini structured content, Anthropic content blocks)
    if isinstance(content, list):
        logger.info(f"Model returned list content with {len(content)} items - extracting text")
        extracted_parts = []
        for i, item in enumerate(content):
            if isinstance(item, str):
                extracted_parts.append(item)
            elif isinstance(item, dict):
                # Look for standard text keys used by various providers
                text = item.get('text') or item.get('content') or item.get('value') or item.get('message')
                if text:
                    extracted_parts.append(str(text))
                else:
                    # Unknown dict structure - log and stringify
                    keys = list(item.keys())
                    logger.warning(f"Unknown dict structure in response item {i}, keys: {keys}")
                    # Try to extract meaningful content, skip metadata like 'signature', 'extras'
                    meaningful_keys = [k for k in keys if k not in ('extras', 'signature', 'type', 'metadata')]
                    if meaningful_keys:
                        extracted_parts.append(str({k: item[k] for k in meaningful_keys}))
            else:
                # Unknown type - stringify it
                logger.warning(f"Unexpected type in response list item {i}: {type(item).__name__}")
                extracted_parts.append(str(item))
        return "\n".join(extracted_parts)

    # Case 4: Dictionary (single structured response)
    if isinstance(content, dict):
        logger.info(f"Model returned dict content with keys: {list(content.keys())}")
        text = content.get('text') or content.get('content') or content.get('value') or content.get('message')
        if text:
            return str(text)
        # Fallback: stringify without metadata
        meaningful = {k: v for k, v in content.items() if k not in ('extras', 'signature', 'type', 'metadata')}
        logger.warning(f"Could not find text key in dict, using fallback stringification")
        return str(meaningful) if meaningful else str(content)

    # Case 5: Unknown type - log warning and stringify to preserve data
    logger.warning(f"Unexpected response content type: {type(content).__name__}. Preserving as string.")
    return str(content)


def get_current_dir() -> Path:
    """Get the current directory of the module.

    This function is compatible with Jupyter notebooks and regular Python scripts.

    Returns:
        Path object representing the current directory
    """
    try:
        return Path(__file__).resolve().parent
    except NameError:  # __file__ is not defined
        return Path.cwd()

# ===== CONFIGURATION =====

tavily_client = TavilyClient()
MAX_CONTEXT_LENGTH = 250000
TAVILY_TIMEOUT = 30.0  # 30 seconds for Tavily API calls
EXA_TIMEOUT = 35.0

# ===== SEARCH FUNCTIONS =====

async def tavily_search_multiple(
    search_queries: List[str],
    max_results: int = 3,
    topic: Literal["general", "news", "finance"] = "general",
    days: Optional[int] = None,
    include_raw_content: bool = True,
) -> List[dict]:
    """Perform search using Tavily API for multiple queries.

    Args:
        search_queries: List of search queries to execute
        max_results: Maximum number of results per query
        topic: Topic filter for search results
        days: Limit search to the last N days (for recency). this number can be as big as you want it to be.
        include_raw_content: Whether to include raw webpage content

    Returns:
        List of search result dictionaries
    """
    import time

    # Execute searches sequentially with timeout + retry protection
    search_docs = []
    for query in search_queries:
        search_start = time.time()
        max_retries = 3
        result = None
        for attempt in range(max_retries):
            try:
                # Tavily SDK call is sync, so run in a thread and enforce a hard timeout.
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        tavily_client.search,
                        query,
                        max_results=max_results,
                        include_raw_content=include_raw_content,
                        topic=topic,
                        days=days,
                    ),
                    timeout=TAVILY_TIMEOUT,
                )
                break
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    backoff = 2 * (attempt + 1)
                    logger.warning(
                        f"Tavily search timeout for '{query}' after {TAVILY_TIMEOUT:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries}). Retrying in {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    search_elapsed = time.time() - search_start
                    logger.error(
                        f"Tavily search timed out for '{query}' after {search_elapsed:.2f}s "
                        f"across {max_retries} attempts"
                    )
            except Exception as e:
                if attempt < max_retries - 1:
                    backoff = 2 * (attempt + 1)
                    logger.warning(
                        f"Tavily search failed for '{query}' on attempt {attempt + 1}/{max_retries}: {e}. "
                        f"Retrying in {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    search_elapsed = time.time() - search_start
                    logger.error(
                        f"Tavily search failed for '{query}' after {search_elapsed:.2f}s "
                        f"across {max_retries} attempts: {e}"
                    )

        if result is None:
            # Return empty result to avoid breaking the pipeline.
            search_docs.append({'results': []})
        else:
            search_elapsed = time.time() - search_start
            logger.debug(f"Tavily search for '{query}' completed in {search_elapsed:.2f}s")
            search_docs.append(result)

    return search_docs


def _normalize_search_item(item: dict, provider: str) -> dict:
    """Normalize provider result formats into a shared internal schema."""
    url = item.get("url") or item.get("link") or item.get("source") or ""
    title = item.get("title") or item.get("name") or "Untitled"
    published_date = item.get("published_date") or item.get("date") or item.get("published") or ""

    if provider == "exa":
        # Exa returns the extracted page text in `text`. Full text = `text`;
        # preview = truncated full text.
        raw_content = item.get("text") or item.get("content") or ""
    else:
        # Tavily returns a short `content` snippet plus `raw_content` (full text
        # when include_raw_content=True). Full text = `raw_content`; preview =
        # truncated full text (Tavily has no summary field).
        raw_content = item.get("raw_content") or item.get("text") or item.get("content") or ""

    if raw_content and len(raw_content) > MAX_CONTEXT_LENGTH:
        raw_content = raw_content[:MAX_CONTEXT_LENGTH]

    return {
        "url": url,
        "title": title,
        "raw_content": raw_content,
        "content": raw_content[:1000],
        "published_date": published_date,
        "provider": provider,
    }


async def _exa_search_multiple(search_queries: List[str], max_results: int = 10) -> List[dict]:
    """Execute Exa deep search requests for multiple queries."""
    import os

    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        raise ValueError("EXA_API_KEY not found in environment variables.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    responses = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=EXA_TIMEOUT)) as session:
        for query in search_queries:
            payload = {
                "query": query,
                "num_results": max_results,
                "contents": {
                    "text": {
                        "max_characters": EXA_SEARCH_MAX_CHARS,
                    }
                },
            }
            try:
                async with session.post("https://api.exa.ai/search", json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.warning(f"Exa search error {response.status} for '{query}': {error_text}")
                        responses.append({"results": []})
                        continue
                    data = await response.json()
                    raw_results = data.get("results", []) if isinstance(data, dict) else []
                    normalized = [_normalize_search_item(item, provider="exa") for item in raw_results]
                    responses.append({"results": [r for r in normalized if r.get("url")]})
            except Exception as e:
                logger.warning(f"Exa search failed for '{query}': {e}")
                responses.append({"results": []})

    return responses


def deduplicate_search_results(search_results: List[dict]) -> dict:
    """Deduplicate search results by URL to avoid processing duplicate content.

    Args:
        search_results: List of search result dictionaries

    Returns:
        Dictionary mapping URLs to unique results
    """
    unique_results = {}

    for response in search_results:
        for result in response['results']:
            url = result['url']
            if url not in unique_results:
                unique_results[url] = result

    return unique_results

async def process_search_results(unique_results: dict, tool_name: str = "tavily") -> dict:
    """Build the source list for search results without an LLM summarization pass.

    Returns each search engine result with its own snippet/content so the
    agent can judge relevance and read full text via read_*/fetch_urls when
    it wants depth. Falls back to a truncated slice of raw_content when the
    engine returned no snippet.

    Args:
        unique_results: Dictionary of unique search results

    Returns:
        Dictionary mapping URLs to {title, content} entries
    """
    processed_results = {}

    for url, result in unique_results.items():
        content = (result.get("content") or "").strip()
        full_text = (result.get("raw_content") or "").strip()
        if not content:
            content = (full_text or "")[:MAX_CONTEXT_LENGTH]

        log_source(tool_name=tool_name, link=url, content=content)

        processed_results[url] = {
            'title': result['title'],
            'content': content,
            'full_text': full_text,
        }

    return processed_results

def format_search_output(summarized_results: dict) -> str:
    """Format search results into a well-structured string output.

    Args:
        summarized_results: Dictionary of processed search results

    Returns:
        Formatted string of search results with clear source separation
    """
    if not summarized_results:
        return "No valid search results found. Please try different search queries or use a different search API."

    formatted_output = "Search results: \n\n"

    for i, (url, result) in enumerate(summarized_results.items(), 1):
        formatted_output += f"\n\n--- SOURCE {i}: {result['title']} ---\n"
        formatted_output += f"URL: {url}\n\n"
        formatted_output += f"SUMMARY:\n{result['content']}\n\n"
        formatted_output += "-" * 80 + "\n"

    return formatted_output

# ===== RESEARCH TOOLS =====

@tool(parse_docstring=True)
async def tavily_search(
    query: str,
    max_results: int = 5,
    topic: Annotated[Literal["general", "news", "finance", "environment", "technology"], InjectedToolArg] = "general",
    days: Annotated[Optional[int], InjectedToolArg] = None,
) -> str:
    """Fetch results from Tavily search API with content summarization.

    Args:
        query: A single search query to execute
        max_results: Number of results to return (default 6). Can be increased up to 20 if needed.
        topic: Topic to filter results by ('general', 'news', 'finance')
        days: Limit results to the last N days. Use this for time-sensitive queries or market data.

    Returns:
        Formatted string of search results with summaries
    """
    import time
    search_start = time.time()
    max_results = min(max(max_results, 1), 20)  # Clamp to Tavily's 1-20 range

    # Execute search for single query
    logger.info(f"🔍 Executing Tavily search for query: '{query}'")
    search_results = await tavily_search_multiple(
        [query],  # Convert single query to list for the internal function
        max_results=max_results,
        topic=topic,
        days=days,
        include_raw_content=True,
    )
    logger.info(f"Search returned {len(search_results)} result object(s)")

    # Deduplicate results by URL to avoid processing duplicate content
    unique_results = deduplicate_search_results(search_results)
    logger.info(f"Found {len(unique_results)} unique URLs from search results")
    for url in unique_results.keys():
        logger.debug(f"Found URL: {url}")

    # Process results with summarization (now async and parallel)
    summarized_results = await process_search_results(unique_results, tool_name="tavily")

    search_elapsed = time.time() - search_start
    logger.info(f"✓ Search complete for '{query}' in {search_elapsed:.2f}s (found {len(summarized_results)} sources)")

    # Format output for consumption
    return format_search_output(summarized_results)


@tool(parse_docstring=True)
async def exa_deep_search(
    query: str,
    max_results: int = 10,
) -> str:
    """Run Exa deep web search and return summarized, deduplicated source results.

    Use this for broad and high-recall web exploration when you want a wider net
    than a normal search query, while still returning concise source summaries.

    Args:
        query: Search query for Exa deep search
        max_results: Desired number of results (1-25)

    Returns:
        Formatted search result block with source summaries and URLs.
    """
    import time

    start_time = time.time()
    max_results = min(max(max_results, 1), 25)
    logger.info(f"🔎 Executing Exa deep search for query: '{query}'")

    search_results = await _exa_search_multiple([query], max_results=max_results)
    unique_results = deduplicate_search_results(search_results)
    summarized_results = await process_search_results(unique_results, tool_name="exa")

    elapsed = time.time() - start_time
    logger.info(f"✓ Exa search complete for '{query}' in {elapsed:.2f}s (found {len(summarized_results)} sources)")
    return format_search_output(summarized_results)


@tool(parse_docstring=True)
async def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    You can use this tool after searches to analyze results and plan next steps systematically.
    This creates a deliberate pause in the research workflow for quality decision-making.

    When to use:
    - After receiving search results: What key information did I find?
    - Before deciding next steps: Do I have enough to answer comprehensively?
    - When assessing research gaps: What specific information am I still missing?
    - Before concluding research: Can I provide a complete answer now?

    Reflection should address:
    1. Analysis of current findings - What concrete information have I gathered?
    2. Gap assessment - What crucial information is still missing?
    3. Quality evaluation - Do I have sufficient evidence/examples for a good answer?
    4. Strategic decision - Should I continue searching or provide my answer?

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps

    Returns:
        Confirmation that reflection was recorded for decision-making
    """
    return f"Reflection recorded: {reflection}"

# no-op to trigger a refinement of the draft report in the supervisor subgraph.
# The actual refinement is done in the multi_agent_supervisor.supervisor_tools.refine_draft_model tool,
# which is called directly by the supervisor model against the cached conversation prefix.
# This stub keeps the tool registered so the supervisor model can still select it.
@tool(parse_docstring=True)
async def refine_draft_report(research_brief: Annotated[str, InjectedToolArg],
                        findings: Annotated[str, InjectedToolArg],
                        draft_report: Annotated[str, InjectedToolArg],
                        target_language: Annotated[str, InjectedToolArg]):
    """Refine draft report

    Synthesizes all research findings into a comprehensive draft report

    Args:
        research_brief: user's research request
        findings: collected research findings for the user request
        draft_report: draft report based on the findings and user request

    Returns:
        refined draft report
    """

    # Intentional no-op: the supervisor subgraph executes refine_draft_report
    # directly against the cached conversation prefix (refine_draft_model in
    # multi_agent_supervisor.supervisor_tools). This schema-only stub keeps the
    # tool registered so the supervisor model can still select it.
    return ""


@tool(parse_docstring=True)
async def get_subreddit_posts(
    subreddit: str,
    listing: Literal["hot", "new", "top"] = "hot",
    limit: int = 200
) -> str:
    """Fetch a list of post titles and URLs from a specific subreddit.

    This tool is useful for discovering current trending topics, news, or
    discussions within a specific community (e.g., r/StockMarket, r/Technology).
    It returns titles, URLs, and engagement metrics (score, comments).
    Supports fetching up to 200 posts via automatic pagination.

    Args:
        subreddit: The name of the subreddit (e.g., 'StockMarket', 'pennystocks')
        listing: The category of posts to fetch ('hot', 'new', 'top')
        limit: Number of posts to fetch (max 200, will paginate automatically)

    Returns:
        Formatted string containing a list of posts with titles and URLs
    """
    import time

    # Clean subreddit name (remove r/ if present)
    subreddit = subreddit.lower().replace("r/", "").strip()
    limit = min(max(1, limit), 200)  # Allow up to 200 posts

    base_url = f"https://www.reddit.com/r/{subreddit}/{listing}.json"

    # Reddit requires a custom User-Agent to avoid 429 errors
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 DeepResearchAgent/1.0"
    }

    logger.info(f"🔍 Fetching up to {limit} {listing} posts from {_DARK_ORANGE}Reddit{_RESET} r/{subreddit}")

    all_posts = []
    after_token = None
    batch_size = 50  # Fetch in batches of 50

    try:
        while len(all_posts) < limit:
            # Build URL with pagination
            params = {"limit": min(batch_size, limit - len(all_posts))}
            if after_token:
                params["after"] = after_token

            # Run the synchronous request in a thread to keep it async-friendly
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda p=params: requests.get(base_url, headers=headers, params=p, timeout=15)
            )

            if response.status_code != 200:
                logger.error(f"Reddit JSON fetch failed with status {response.status_code}")
                break  # Return what we have so far

            data = response.json()
            posts_raw = data.get('data', {}).get('children', [])
            after_token = data.get('data', {}).get('after')

            if not posts_raw:
                break  # No more posts

            all_posts.extend(posts_raw)
            logger.info(f"   Fetched {len(posts_raw)} posts (Total: {len(all_posts)})")

            if not after_token:
                break  # End of feed

            # Small delay to be polite to Reddit servers
            await asyncio.sleep(0.5)

        if not all_posts:
            return f"No posts found in r/{subreddit}."

        output = [f"Found {len(all_posts)} {listing} posts in r/{subreddit}:\n"]

        # Helper to format relative time
        import time as time_module
        current_time = time_module.time()

        def format_age(created_utc):
            age_seconds = current_time - created_utc
            if age_seconds < 3600:
                mins = int(age_seconds / 60)
                return f"{mins} min ago"
            elif age_seconds < 86400:
                hours = int(age_seconds / 3600)
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif age_seconds < 604800:
                days = int(age_seconds / 86400)
                return f"{days} day{'s' if days != 1 else ''} ago"
            else:
                weeks = int(age_seconds / 604800)
                return f"{weeks} week{'s' if weeks != 1 else ''} ago"

        for i, post in enumerate(all_posts, 1):
            p = post.get('data', {})
            title = p.get('title')
            post_url = f"https://www.reddit.com{p.get('permalink')}"
            score = p.get('score')
            comments = p.get('num_comments')
            created_utc = p.get('created_utc', 0)
            age_str = format_age(created_utc)

            output.append(f"{i}. {title}")
            output.append(f"   URL: {post_url}")
            output.append(f"   Score: {score} | Comments: {comments} | Posted: {age_str}\n")

        formatted_output = "\n".join(output)

        # Log the source for persistence
        log_source(
            tool_name="reddit_subreddit",
            link=f"https://www.reddit.com/r/{subreddit}/{listing}",
            content=formatted_output
        )

        return formatted_output

    except Exception as e:
        logger.error(f"Error in get_subreddit_posts: {e}")
        return f"Error fetching subreddit data: {str(e)}"


# ===== REDDIT POST EXTRACTION TOOL =====

@tool(parse_docstring=True)
async def get_reddit_post(url: str) -> str:
    """Fetch the full content and comments from a Reddit post URL.

    Use this tool when:
    - You have a Reddit post URL from get_subreddit_posts and want the full discussion
    - You need to read the post body and community comments with usernames
    - Tavily returned a Reddit URL but gave insufficient detail about the discussion

    The tool returns:
    - Post title, author, score, and body text
    - All comments with usernames, scores, and who they're replying to
    - Nested replies showing the conversation thread

    Args:
        url: A Reddit post URL (e.g., https://www.reddit.com/r/stocks/comments/abc123/title/)

    Returns:
        Formatted post content and full comment thread with usernames and reply structure
    """
    import time

    start_time = time.time()
    logger.info(f"🔍 Fetching {_DARK_ORANGE}Reddit{_RESET} post: {url}")

    # Reddit requires a custom User-Agent to avoid 429 errors
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 DeepResearchAgent/1.0"
    }

    try:
        # Normalize URL and append .json
        json_url = url.rstrip('/')
        if not json_url.endswith('.json'):
            json_url = json_url + '.json'

        # Run the synchronous request in a thread to keep it async-friendly
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(json_url, headers=headers, timeout=15)
        )

        if response.status_code != 200:
            logger.error(f"Reddit post fetch failed with status {response.status_code}")
            return f"Error: Could not fetch Reddit post (HTTP {response.status_code}). URL: {url}"

        data = response.json()

        # Validate response structure
        if not isinstance(data, list) or len(data) < 2:
            return f"Error: Unexpected response format from Reddit. URL: {url}"

        # Extract post data
        post_data = data[0]['data']['children'][0]['data']
        comments_data = data[1]['data']['children']

        # Format post header
        output = []
        output.append(f"# {post_data.get('title', '[No Title]')}")
        output.append(f"**Author:** u/{post_data.get('author', '[deleted]')} | **Score:** {post_data.get('score', 0)} | **Comments:** {post_data.get('num_comments', 0)}")
        output.append("")

        # Add post body if present
        selftext = post_data.get('selftext', '')
        if selftext:
            output.append("## Post Content")
            output.append(selftext[:3000])  # Limit body length
            if len(selftext) > 3000:
                output.append("... [truncated]")
            output.append("")

        # Add external link if this is a link post
        if post_data.get('is_self') is False and post_data.get('url'):
            output.append(f"**Link:** {post_data.get('url')}")
            output.append("")

        output.append("---")
        output.append("## Comments")
        output.append("")

        # Helper function to format comments recursively
        def format_comments(comments: list, depth: int = 0, parent_author: str = None) -> list:
            lines = []
            for comment in comments:
                if comment.get('kind') != 't1':  # Skip non-comments
                    continue

                c = comment.get('data', {})
                author = c.get('author', '[deleted]')
                body = c.get('body', '[removed]')
                score = c.get('score', 0)

                # Create indentation based on depth
                indent = "  " * depth
                reply_info = f" (replying to u/{parent_author})" if parent_author and depth > 0 else ""

                # Format the comment
                lines.append(f"{indent}**u/{author}** [{score:+d}]{reply_info}:")
                # Indent the body text and limit length
                body_preview = body[:500] if len(body) > 500 else body
                for body_line in body_preview.split('\n')[:5]:  # Max 5 lines per comment
                    lines.append(f"{indent}> {body_line}")
                if len(body) > 500 or len(body.split('\n')) > 5:
                    lines.append(f"{indent}> ... [truncated]")
                lines.append("")

                # Recursively process replies (limit depth to 3)
                if depth < 3:
                    replies = c.get('replies')
                    if replies and isinstance(replies, dict):
                        reply_children = replies.get('data', {}).get('children', [])
                        lines.extend(format_comments(reply_children, depth + 1, author))

            return lines

        # Format top 25 comment threads
        comment_lines = format_comments(comments_data[:25])
        output.extend(comment_lines)

        if len(comments_data) > 25:
            output.append(f"... and {len(comments_data) - 25} more top-level comments")

        elapsed = time.time() - start_time
        logger.info(f"✓ {_DARK_ORANGE}Reddit{_RESET} post fetched in {elapsed:.2f}s ({len(comments_data)} top-level comments)")

        formatted_output = "\n".join(output)

        # Log the source for persistence
        log_source(
            tool_name="reddit_post",
            link=url,
            content=formatted_output
        )

        return formatted_output

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"✗ Reddit post fetch failed after {elapsed:.2f}s: {str(e)}")
        return f"Error fetching Reddit post: {str(e)}. URL: {url}"


@tool(parse_docstring=True)
async def search_term_in_subreddit(
    query: str,
    sort: Literal["relevance", "new", "top", "comments"] = "relevance",
    time_filter: Literal["hour", "day", "week", "month", "year", "all"] = "year",
    limit: int = 50,
    subreddit: Optional[str] = None
) -> str:
    """Search Reddit for posts matching a query.

    Use this tool to find discussions, opinions, and news across Reddit or within a specific subreddit.
    It returns a list of posts with their titles, scores, comment counts, dates, and URLs.
    Supports fetching up to 200 posts via automatic pagination.

    Args:
        query: The search query (e.g., 'Google OR GOOG OR GOOGL')
        sort: Sort order for results ('relevance', 'new', 'top', 'comments')
        time_filter: Time period to search ('hour', 'day', 'week', 'month', 'year', 'all')
        limit: Total number of posts to fetch (max 200, will paginate if needed)
        subreddit: Optional subreddit to restrict search to (e.g., 'stocks')

    Returns:
        Formatted string containing a list of search results
    """
    import time
    from datetime import datetime

    # Clean subreddit name (remove r/ if present)
    if subreddit:
        subreddit = subreddit.lower().replace("r/", "").strip()
        base_url = f"https://www.reddit.com/r/{subreddit}/search.json"
    else:
        base_url = "https://www.reddit.com/search.json"

    limit = min(max(1, limit), 200)

    params = {
        "q": query,
        "restrict_sr": "on" if subreddit else "off",
        "limit": min(100, limit), # Batch size
        "sort": sort,
        "t": time_filter
    }

    # Reddit requires a custom User-Agent
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 DeepResearchAgent/1.0"
    }

    logger.info(f"🔍 Searching {_DARK_ORANGE}Reddit{_RESET} for '{query}' (limit: {limit}, sort: {sort}, time: {time_filter})")

    all_posts = []
    after_token = None

    try:
        while len(all_posts) < limit:
            if after_token:
                params["after"] = after_token

            # Run the synchronous request in a thread
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda p=params: requests.get(base_url, headers=headers, params=p, timeout=15)
            )

            if response.status_code == 429:
                logger.warning("Reddit API rate limited (429). Returning partial results.")
                break

            if response.status_code != 200:
                logger.error(f"Reddit search failed with status {response.status_code}")
                break

            data = response.json()
            posts_raw = data.get('data', {}).get('children', [])
            after_token = data.get('data', {}).get('after')

            if not posts_raw:
                break

            for post in posts_raw:
                p = post.get('data', {})
                created_date = datetime.fromtimestamp(p.get("created_utc", 0)).strftime('%Y-%m-%d')
                all_posts.append({
                    "title": p.get("title"),
                    "score": p.get("score"),
                    "comments": p.get("num_comments"),
                    "date": created_date,
                    "url": f"https://reddit.com{p.get('permalink')}"
                })

            if len(all_posts) >= limit or not after_token:
                break

            # Small delay before next page
            await asyncio.sleep(1)

        if not all_posts:
            return f"No Reddit posts found for query: '{query}'"

        # Format output as a table-like structure
        output = [f"Found {len(all_posts)} Reddit posts for '{query}':\n"]
        output.append(f"{'Date':<12} | {'Score':>6} | {'Comments':>8} | {'Title':<40} | {'URL'}")
        output.append("-" * 150)

        for p in all_posts[:limit]:
            output.append(f"{p['date']:<12} | {p['score']:>6} | {p['comments']:>8} | {p['title'][:40]:<40} | {p['url']}")

        formatted_output = "\n".join(output)

        # Log the source for persistence
        log_source(
            tool_name="search_term_in_subreddit",
            link=f"{base_url}?q={query}",
            content=formatted_output
        )

        return formatted_output

    except Exception as e:
        logger.error(f"Error in search_term_in_subreddit: {e}")
        return f"Error searching Reddit: {str(e)}"


# ===== SUBSTACK TOOLS (Discovery Agent Only) =====

VALID_SUBSTACK_RECENCY_FILTERS = ["hour", "day", "week", "month", "year"]


async def _search_perplexity_substack(query: str, recency_filter: str = "month") -> dict:
    """
    Internal helper: Search Substack articles via Perplexity API.

    Args:
        query: The search query string
        recency_filter: One of 'hour', 'day', 'week', 'month', 'year'

    Returns:
        API response as dict with 'results' array
    """
    import os

    api_key = os.getenv("PERPLEXITY_KEY")
    if not api_key:
        raise ValueError("PERPLEXITY_KEY not found in environment variables.")

    if recency_filter not in VALID_SUBSTACK_RECENCY_FILTERS:
        recency_filter = "month"  # Default fallback

    url = "https://api.perplexity.ai/search"

    payload = {
        "query": query,
        "search_domain_filter": ["substack.com"],
        "search_recency_filter": recency_filter
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Use aiohttp for async HTTP request
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Perplexity API error {response.status}: {error_text}")
            return await response.json()


async def _scrape_substack(url: str) -> dict:
    """
    Internal helper: Scrape a Substack article and return structured data.

    Args:
        url: The Substack article URL

    Returns:
        Dict with title, subtitle, author, date, content, and url
    """
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(url, headers=headers, timeout=15)
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. Title
        title = soup.find('h1', class_='post-title')
        if not title:
            title_meta = soup.find('meta', attrs={'property': 'og:title'})
            title_text = title_meta['content'] if title_meta else "Title not found"
        else:
            title_text = title.text.strip()

        # 2. Subtitle
        subtitle = soup.find('h3', class_='subtitle')
        subtitle_text = subtitle.text.strip() if subtitle else ""

        # 3. Author
        author_meta = soup.find('meta', attrs={'name': 'author'})
        if author_meta:
            author_text = author_meta['content']
        else:
            author_span = soup.find('span', class_='byline-names')
            if not author_span:
                author_span = soup.find('a', class_='pencraft')
            author_text = author_span.get_text().strip() if author_span else "Author not found"

        # 4. Date
        date_meta = soup.find('meta', attrs={'property': 'article:published_time'})
        if date_meta:
            date_text = date_meta['content']
        else:
            date_div = soup.find('div', class_='post-date')
            date_text = date_div.text.strip() if date_div else "Date not found"

        # 5. Content
        content_div = soup.find('div', class_='available-content')
        if not content_div:
            content_div = soup.find('div', class_='body')

        body_text = ""
        if content_div:
            paragraphs = content_div.find_all(['p', 'h1', 'h2', 'h3', 'li'])
            body_text = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
        else:
            body_text = "Content not found."

        return {
            "url": url,
            "title": title_text,
            "subtitle": subtitle_text,
            "author": author_text,
            "date": date_text,
            "content": body_text
        }

    except Exception as e:
        return {"error": str(e), "url": url}


@tool(parse_docstring=True)
async def search_substack(
    search_term: str,
    recency_filter: Literal["hour", "day", "week", "month", "year"] = "month"
) -> str:
    """Search for Substack newsletter articles using Perplexity API.

    Use simple, specific search terms like company names, product names, or person names.
    Examples: "NVIDIA", "ozempic", "Peter Thiel", "Tesla earnings", "AI", "Sam Altman", "Berkshire Hathaway"

    The tool searches only substack.com and returns a list of articles or sometimes publishers for you to choose from.
    After reviewing the results, select 3-5 articles (prefer 3 or fewer) to read using read_substack_article.

    Args:
        search_term: A simple search term like a company name, product name, or person name.
                     Do NOT use complex queries - just the core topic.
        recency_filter: Time filter for results. Options: "hour", "day", "week", "month", "year".
                        Default is "month".

    Returns:
        Formatted list of Substack articles with titles, snippets, URLs, and dates for selection.
    """
    import time

    start_time = time.time()
    logger.info(f"🔍 Searching {_ORANGE}Substack{_RESET} for: '{search_term}' (recency: {recency_filter})")

    try:
        results_data = await _search_perplexity_substack(search_term, recency_filter)

        # Extract results from API response
        results = []
        if isinstance(results_data, dict) and 'results' in results_data:
            results = results_data['results']
        elif isinstance(results_data, list):
            for item in results_data:
                if 'results' in item:
                    results.extend(item['results'])

        # Filter for substack.com URLs only
        substack_results = [r for r in results if r.get('url') and 'substack.com' in r.get('url', '')]

        if not substack_results:
            return f"No Substack articles found for search term: '{search_term}'. Try a different search term."

        # Format output for agent selection (up to 10 results)
        output = [f"Found {len(substack_results)} Substack articles for '{search_term}':\n"]
        output.append("Review these results and select 3-5 articles (prefer ≤3) to read with read_substack_article.\n")
        output.append("-" * 80)

        for i, result in enumerate(substack_results[:10], 1):
            title = result.get('title', 'No title')
            url = result.get('url', '')
            snippet = result.get('snippet', 'No snippet available')
            date = result.get('date', 'Unknown date')

            output.append(f"\n{i}. **{title}**")
            output.append(f"   Date: {date}")
            output.append(f"   URL: {url}")
            output.append(f"   Preview: {snippet[:200]}{'...' if len(snippet) > 200 else ''}")
            output.append("")

        output.append("-" * 80)
        output.append("\nTo read an article, call: read_substack_article(url=\"<URL>\")")

        elapsed = time.time() - start_time
        logger.info(f"✓ {_ORANGE}Substack{_RESET} search completed in {elapsed:.2f}s ({len(substack_results)} results)")

        formatted_output = "\n".join(output)

        # Log source for traceability
        log_source(
            tool_name="substack_search",
            link=f"perplexity_search:{search_term}",
            content=formatted_output
        )

        return formatted_output

    except Exception as e:
        logger.error(f"Error in search_substack: {e}")
        return f"Error searching Substack: {str(e)}"


@tool(parse_docstring=True)
async def read_substack_article(url: str) -> str:
    """Read the full content of a Substack article.

    Use this after search_substack to read selected articles in full.
    Select 3-5 articles maximum (prefer 3 or fewer) from search results.

    After reading all selected articles, use think_tool to reflect on the findings
    before proceeding with your next action.

    Args:
        url: The Substack article URL to read (from search_substack results)

    Returns:
        The full article content including title, author, date, and body text.
    """
    import time

    start_time = time.time()
    logger.info(f"📖 Reading {_ORANGE}Substack{_RESET} article: {url}")

    try:
        data = await _scrape_substack(url)

        if "error" in data:
            return f"Error reading article at {url}: {data['error']}"

        # Format the article content
        output = []
        output.append(f"# {data['title']}")
        if data['subtitle']:
            output.append(f"*{data['subtitle']}*")
        output.append(f"\n**Author:** {data['author']}")
        output.append(f"**Date:** {data['date']}")
        output.append(f"**URL:** {data['url']}")
        output.append("\n---\n")
        output.append(data['content'])
        output.append("\n---")

        elapsed = time.time() - start_time
        logger.info(f"✓ {_ORANGE}Substack{_RESET} article read in {elapsed:.2f}s ({len(data['content'])} chars)")

        formatted_output = "\n".join(output)

        # Log source for traceability
        log_source(
            tool_name="substack_article",
            link=url,
            content=formatted_output
        )

        return formatted_output

    except Exception as e:
        logger.error(f"Error reading Substack article: {e}")
        return f"Error reading Substack article at {url}: {str(e)}"

