"""
api/websearch.py
================
DuckDuckGo web search fallback — no API key required.
Used when the knowledge base returns no relevant results (score < threshold).

Requires: duckduckgo-search  (pip install duckduckgo-search)
"""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Score assigned to web results (neutral — below high-confidence KB results)
WEB_RESULT_SCORE = 0.25


def web_search(query: str, n: int = 4) -> list[dict]:
    """
    Search DuckDuckGo and return results in the same dict format as hybrid_search().

    Returns empty list on any failure so callers can treat it as graceful degradation.

    Return format matches hybrid_search() output:
        {
            chunk_id: str,
            title: str,
            text: str,           # snippet / body text
            start_time: float,   # always 0 for web results
            timestamp_str: str,  # domain name, e.g. "techcrunch.com"
            timestamp_url: str,  # full page URL
            score: float,
        }
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logger.warning("duckduckgo-search not installed — web search unavailable. Run: pip install duckduckgo-search")
        return []

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=n))
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")
        return []

    results = []
    for i, r in enumerate(raw):
        url = r.get("href", "") or r.get("url", "")
        # Extract domain for timestamp_str (shown as the "source" label)
        try:
            domain = urlparse(url).netloc.lstrip("www.") if url else "web"
        except Exception:
            domain = "web"

        results.append({
            "chunk_id": f"web_{i}",
            "title": r.get("title", "Web Result"),
            "text": r.get("body", r.get("description", "")),
            "start_time": 0.0,
            "timestamp_str": domain,
            "timestamp_url": url,
            "score": WEB_RESULT_SCORE,
            "is_web_result": True,  # flag so synthesize can note the source type
        })

    logger.info(f"Web search returned {len(results)} results for: {query!r}")
    return results
