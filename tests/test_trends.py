"""tests/test_trends.py — trend snapshot with TRENDS_LIVE=false."""
from __future__ import annotations

import pytest

from packages.tools.trends import fetch_trend_snapshot


@pytest.mark.asyncio
async def test_trend_snapshot_mock_mode(monkeypatch):
    monkeypatch.setenv("TRENDS_LIVE", "false")
    snap = await fetch_trend_snapshot()
    assert snap.get("top_trending_topics")
    assert "mock" in str(snap.get("sources", snap.get("source", "")))


@pytest.mark.asyncio
async def test_tavily_unavailable_returns_empty(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    from packages.tools.tavily_client import search_niche_intelligence

    rows = await search_niche_intelligence("test query")
    assert rows == []
