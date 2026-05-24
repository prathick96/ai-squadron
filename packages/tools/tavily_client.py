"""
packages/tools/tavily_client.py
Tavily web search for niche intelligence (Day 3).
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)


def tavily_available() -> bool:
    key = os.getenv("TAVILY_API_KEY", "")
    return bool(key) and len(key) > 10 and "your_" not in key


def _search_sync(query: str, max_results: int) -> list[dict[str, Any]]:
    from tavily import TavilyClient  # type: ignore[import-untyped]

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_answer=True,
    )

    results: list[dict[str, Any]] = []
    if response.get("answer"):
        results.append({
            "title": "Tavily synthesis",
            "url": "",
            "snippet": response["answer"],
            "score": 1.0,
        })

    for item in response.get("results", []) or []:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", "")[:500],
            "score": float(item.get("score", 0) or 0),
        })
    return results


async def search_niche_intelligence(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    """Run Tavily search and return normalised result rows."""
    import asyncio

    if not tavily_available():
        return []

    try:
        return await asyncio.to_thread(_search_sync, query, max_results)
    except ImportError:
        log.warning("tavily-python not installed — pip install tavily-python")
        return []
