"""tests/test_trends.py — trend snapshot tests."""
from __future__ import annotations

import pytest

from packages.tools.trends import fetch_trend_snapshot, _pick_verticals


@pytest.mark.asyncio
async def test_trend_snapshot_offline_mode_is_structurally_valid(monkeypatch):
    """
    When TRENDS_LIVE=false the snapshot must be structurally valid but niche-neutral.
    No hardcoded niche names should appear — that would bias the Research Council.
    """
    monkeypatch.setenv("TRENDS_LIVE", "false")
    snap = await fetch_trend_snapshot()

    # Must have the required keys
    assert "sources" in snap
    assert "high_rpm_niches" in snap
    assert "exhausted_niches" in snap
    assert "competitor_gap_signals" in snap

    # top_trending_topics is intentionally empty in offline mode (no biased seed data)
    # The Research Council uses its own reasoning when live trends are unavailable
    assert isinstance(snap.get("top_trending_topics", []), list)

    # Source must indicate offline/fallback state
    source = str(snap.get("source", "") + str(snap.get("sources", "")))
    assert "empty_fallback" in source or source == "[]"


@pytest.mark.asyncio
async def test_trend_snapshot_accepts_exhausted_niches(monkeypatch):
    """Exhausted niches are passed through to the snapshot for scout awareness."""
    monkeypatch.setenv("TRENDS_LIVE", "false")
    exhausted = ["niche A", "niche B"]
    snap = await fetch_trend_snapshot(exhausted_niches=exhausted)
    assert snap.get("exhausted_niches") == exhausted


def test_vertical_picker_returns_diverse_keywords():
    """_pick_verticals returns the requested number of unique keywords."""
    picks = _pick_verticals(3)
    assert len(picks) == 3
    assert all(isinstance(k, str) and len(k) > 5 for k in picks)
    # Keywords should be distinct (no duplicates)
    assert len(set(picks)) == len(picks)


def test_vertical_picker_varies_across_calls():
    """Multiple calls return different picks (random component prevents lock-in)."""
    samples = [tuple(_pick_verticals(3)) for _ in range(10)]
    # At least 2 distinct samples in 10 calls — should be much more, but 2 is the floor
    assert len(set(samples)) >= 2


@pytest.mark.asyncio
async def test_tavily_unavailable_returns_empty(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    from packages.tools.tavily_client import search_niche_intelligence

    rows = await search_niche_intelligence("test query")
    assert rows == []
