"""
packages/tools/trends.py
Live trend snapshot: Google Trends (pytrends) + Tavily web search.
Falls back to mock data when APIs unavailable or TRENDS_LIVE=false.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_SEED_KEYWORDS = [
    "AI SaaS tools",
    "freelancer tax software",
    "faceless YouTube automation",
    "micro SaaS ideas 2026",
]


def _mock_snapshot() -> dict:
    return {
        "source": "mock_trends_v1",
        "sources": ["mock"],
        "top_trending_topics": [
            {"topic": "AI tax automation for freelancers", "volume_index": 84, "region": "US"},
            {"topic": "no-code SaaS for solopreneurs", "volume_index": 71, "region": "US,IN"},
            {"topic": "faceless YouTube finance channel", "volume_index": 67, "region": "US,CA"},
        ],
        "high_rpm_niches": ["personal finance", "B2B software", "legal automation"],
        "emerging_keywords": ["AI deduction scanner", "1099 tax tool", "solopreneur CRM"],
        "competitor_gap_signals": [
            "No AI-native tool for freelancer quarterly tax estimation",
            "Existing tools lack real-time bank transaction classification",
        ],
        "tavily_results": [],
    }


def _fetch_pytrends_sync(keywords: list[str] | None = None) -> dict[str, Any]:
    from pytrends.request import TrendReq

    kw = keywords or _DEFAULT_SEED_KEYWORDS[:3]
    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload(kw, timeframe="today 3-m", geo="US")

    interest = pytrends.interest_over_time()
    related = pytrends.related_queries()

    topics: list[dict[str, Any]] = []
    if interest is not None and not interest.empty:
        latest = interest.iloc[-1]
        for term in kw:
            if term in latest.index:
                topics.append({
                    "topic": term,
                    "volume_index": int(latest[term]),
                    "region": "US",
                })
        topics.sort(key=lambda x: x["volume_index"], reverse=True)

    emerging: list[str] = []
    for term in kw:
        rq = related.get(term, {}) if isinstance(related, dict) else {}
        rising = rq.get("rising") if isinstance(rq, dict) else None
        if rising is not None and not rising.empty:
            col = "query" if "query" in rising.columns else rising.columns[0]
            emerging.extend(rising[col].head(5).astype(str).tolist())

    return {
        "pytrends_keywords": kw,
        "top_trending_topics": topics or [
            {"topic": kw[0], "volume_index": 50, "region": "US"},
        ],
        "emerging_keywords": list(dict.fromkeys(emerging))[:15],
        "high_rpm_niches": ["personal finance", "B2B SaaS", "productivity AI"],
    }


async def fetch_trend_snapshot(seed_keywords: list[str] | None = None) -> dict:
    """
    Aggregate trend intelligence for the Research Council.
    Set TRENDS_LIVE=false to force mock data (tests/CI).
    """
    if os.getenv("TRENDS_LIVE", "true").lower() in ("0", "false", "no"):
        return _mock_snapshot()

    sources: list[str] = []
    snapshot: dict[str, Any] = {
        "sources": sources,
        "competitor_gap_signals": [],
        "tavily_results": [],
    }

    kw = seed_keywords or _DEFAULT_SEED_KEYWORDS

    try:
        google = await asyncio.to_thread(_fetch_pytrends_sync, kw[:5])
        snapshot.update(google)
        sources.append("pytrends")
        log.info("[trends] pytrends OK | topics=%d", len(google.get("top_trending_topics", [])))
    except Exception as exc:
        log.warning("[trends] pytrends failed: %s", exc)

    if os.getenv("TAVILY_API_KEY"):
        try:
            from packages.tools.tavily_client import search_niche_intelligence, tavily_available

            if tavily_available():
                query = (
                    "profitable micro SaaS and faceless YouTube niches 2026 "
                    "low competition high RPM: " + ", ".join(kw[:3])
                )
                tavily_rows = await search_niche_intelligence(query, max_results=8)
                snapshot["tavily_results"] = tavily_rows
                sources.append("tavily")
                for row in tavily_rows:
                    snippet = (row.get("snippet") or "")[:200]
                    if snippet and "gap" in snippet.lower():
                        snapshot["competitor_gap_signals"].append(snippet)
                log.info("[trends] Tavily OK | results=%d", len(tavily_rows))
        except Exception as exc:
            log.warning("[trends] Tavily failed: %s", exc)

    snapshot["sources"] = sources
    if not sources:
        log.info("[trends] No live sources — using mock snapshot")
        return _mock_snapshot()

    snapshot["source"] = "+".join(sources)
    if "top_trending_topics" not in snapshot:
        snapshot["top_trending_topics"] = _mock_snapshot()["top_trending_topics"]
    if "emerging_keywords" not in snapshot:
        snapshot["emerging_keywords"] = []
    if not snapshot.get("competitor_gap_signals"):
        snapshot["competitor_gap_signals"] = _mock_snapshot()["competitor_gap_signals"]

    return snapshot
