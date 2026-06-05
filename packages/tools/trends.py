"""
packages/tools/trends.py
Live trend snapshot: Google Trends (pytrends) + Tavily web search.

Design principles:
  - NO hardcoded niches or biased seed keywords in fallbacks.
  - Seed keywords rotate across a large pool of verticals each run so the
    Research Council sees different opportunity spaces on every invocation.
  - Tavily enrichment runs on 3 independent queries targeting different signals:
    trending niches, competitor gaps, and underserved audiences.
  - Mock snapshot is structurally valid but niche-neutral — scouts must use their
    own reasoning to find niches, not read them off a hardcoded list.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
from datetime import date
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exploration verticals — the system rotates through these each run.
# By covering many verticals, the council discovers diverse opportunities
# instead of always circling back to the same seeded niche.
# ---------------------------------------------------------------------------
_VERTICALS: list[list[str]] = [
    # Productivity & operations
    ["AI productivity tools 2026", "solopreneur automation software", "async work tools"],
    # Finance & payments
    ["small business invoicing software", "expense tracking SaaS", "B2B payments tool"],
    # Marketing & growth
    ["content marketing automation", "social media scheduling AI", "SEO audit tool SaaS"],
    # HR & recruiting
    ["freelance marketplace tools", "remote team management SaaS", "contractor management"],
    # E-commerce & retail
    ["dropshipping automation tool", "ecommerce analytics SaaS", "print on demand software"],
    # Legal & compliance
    ["contract management software SMB", "GDPR compliance tool small business", "legal document AI"],
    # Education & training
    ["online course platform alternatives", "corporate training LMS SaaS", "micro-learning app"],
    # Media & content
    ["faceless YouTube automation 2026", "podcast editing AI", "short-form video tools"],
    # Real estate & property
    ["property management software indie", "real estate lead generation SaaS", "rental automation"],
    # Healthcare-adjacent
    ["mental wellness app SaaS", "telehealth scheduling software", "health coach platform"],
    # Developer tools
    ["developer productivity SaaS", "API monitoring tool", "code review automation"],
    # Local business
    ["local service business software", "appointment scheduling SaaS small business", "salon management tool"],
    # Community & membership
    ["community platform SaaS", "membership site software", "creator monetisation tools"],
    # Security & privacy
    ["cybersecurity SaaS small business", "password manager B2B", "privacy compliance tool"],
    # Analytics & data
    ["website analytics alternative", "customer data platform SMB", "A/B testing tool SaaS"],
]

# Tavily search templates — each targets a different intelligence signal
_TAVILY_QUERIES = [
    "trending micro SaaS niches {year} reddit Indie Hackers Product Hunt low competition",
    "underserved SaaS market gaps {year} bootstrapper success stories $1000 MRR",
    "fastest growing software categories {year} solo founder profitable",
]


def _pick_verticals(n: int = 3) -> list[str]:
    """
    Pick n verticals from the pool. Uses run date + a random salt so each
    daily run explores different categories. Within the same day, multiple
    runs will still get different verticals because of the random component.
    """
    today = date.today().isoformat()
    # Deterministic shuffle for the day, random pick per-call
    seed = int(hashlib.md5(today.encode()).hexdigest(), 16)
    rng = random.Random(seed ^ random.getrandbits(32))
    pool = _VERTICALS.copy()
    rng.shuffle(pool)
    chosen: list[str] = []
    for vertical in pool[:n]:
        # Pick one keyword from the vertical
        chosen.append(rng.choice(vertical))
    return chosen


def _empty_snapshot() -> dict:
    """
    Structurally valid but niche-neutral fallback snapshot.
    Scouts must use their own reasoning — no hardcoded niche hints here.
    """
    return {
        "source": "empty_fallback",
        "sources": [],
        "top_trending_topics": [],
        "high_rpm_niches": ["B2B SaaS", "productivity tools", "content automation", "developer tools"],
        "emerging_keywords": [],
        "competitor_gap_signals": [],
        "tavily_results": [],
        "note": "Live trend data unavailable — scouts should rely on general market knowledge",
    }


def _fetch_pytrends_sync(keywords: list[str]) -> dict[str, Any]:
    from pytrends.request import TrendReq

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload(keywords[:5], timeframe="today 3-m", geo="US")

    interest = pytrends.interest_over_time()
    related = pytrends.related_queries()

    topics: list[dict[str, Any]] = []
    if interest is not None and not interest.empty:
        latest = interest.iloc[-1]
        for term in keywords:
            if term in latest.index:
                topics.append({
                    "topic": term,
                    "volume_index": int(latest[term]),
                    "region": "US",
                })
        topics.sort(key=lambda x: x["volume_index"], reverse=True)

    emerging: list[str] = []
    for term in keywords:
        rq = related.get(term, {}) if isinstance(related, dict) else {}
        rising = rq.get("rising") if isinstance(rq, dict) else None
        if rising is not None and not rising.empty:
            col = "query" if "query" in rising.columns else rising.columns[0]
            emerging.extend(rising[col].head(5).astype(str).tolist())

    return {
        "pytrends_keywords": keywords,
        "top_trending_topics": topics,
        "emerging_keywords": list(dict.fromkeys(emerging))[:20],
        "high_rpm_niches": ["B2B SaaS", "finance tools", "productivity AI", "developer tools"],
    }


async def fetch_trend_snapshot(
    seed_keywords: list[str] | None = None,
    exhausted_niches: list[str] | None = None,
) -> dict:
    """
    Aggregate trend intelligence for the Research Council.

    Args:
        seed_keywords:   Override the auto-picked verticals (for testing or forced exploration).
        exhausted_niches: Niches already evaluated/KILL'd — included in snapshot so scouts avoid them.

    Set TRENDS_LIVE=false to skip live APIs (CI/testing).
    """
    if os.getenv("TRENDS_LIVE", "true").lower() in ("0", "false", "no"):
        snap = _empty_snapshot()
        snap["exhausted_niches"] = exhausted_niches or []
        return snap

    sources: list[str] = []
    snapshot: dict[str, Any] = {
        "sources": sources,
        "competitor_gap_signals": [],
        "tavily_results": [],
        "exhausted_niches": exhausted_niches or [],
        "run_date": date.today().isoformat(),
    }

    # Pick seed keywords — rotate verticals each run for diversity
    kw = seed_keywords or _pick_verticals(3)
    log.info("[trends] Exploring verticals: %s", kw)

    # ── Google Trends ──────────────────────────────────────────────────────────
    try:
        google = await asyncio.to_thread(_fetch_pytrends_sync, kw)
        snapshot.update(google)
        sources.append("pytrends")
        log.info("[trends] pytrends OK | topics=%d emerging=%d",
                 len(google.get("top_trending_topics", [])),
                 len(google.get("emerging_keywords", [])))
    except Exception as exc:
        log.warning("[trends] pytrends failed: %s", exc)
        snapshot["top_trending_topics"] = []
        snapshot["emerging_keywords"] = []

    # ── Tavily — 3 independent queries targeting different signals ─────────────
    if os.getenv("TAVILY_API_KEY"):
        try:
            from packages.tools.tavily_client import search_niche_intelligence, tavily_available

            if tavily_available():
                year = date.today().year
                all_results: list[dict] = []
                gap_signals: list[str] = []

                # Run 3 Tavily queries in parallel, each targeting a different signal
                tavily_tasks = [
                    search_niche_intelligence(q.format(year=year), max_results=5)
                    for q in _TAVILY_QUERIES
                ]
                tavily_batches = await asyncio.gather(*tavily_tasks, return_exceptions=True)

                for batch in tavily_batches:
                    if isinstance(batch, Exception):
                        log.warning("[trends] Tavily query failed: %s", batch)
                        continue
                    for row in batch:
                        snippet = (row.get("snippet") or "")[:300]
                        all_results.append(row)
                        # Extract competitor gap signals from the search results
                        if snippet and any(w in snippet.lower() for w in
                                           ("gap", "underserved", "no tool", "missing", "nobody")):
                            gap_signals.append(snippet[:200])

                snapshot["tavily_results"] = all_results[:15]  # cap total
                snapshot["competitor_gap_signals"] = gap_signals[:5]
                sources.append("tavily")
                log.info("[trends] Tavily OK | results=%d gap_signals=%d",
                         len(all_results), len(gap_signals))
        except Exception as exc:
            log.warning("[trends] Tavily enrichment failed: %s", exc)

    snapshot["sources"] = sources
    if not sources:
        log.info("[trends] No live sources — using empty snapshot")
        empty = _empty_snapshot()
        empty["exhausted_niches"] = exhausted_niches or []
        return empty

    snapshot["source"] = "+".join(sources)
    return snapshot


async def fetch_tavily_for_scout(role_name: str, niche_candidates: list[str]) -> list[dict]:
    """
    Per-scout Tavily enrichment. Each scout can call this with specific queries
    to validate or discover evidence for its niche candidates.

    Returns up to 5 results relevant to the scout's specific lens.
    """
    if not os.getenv("TAVILY_API_KEY"):
        return []

    from packages.tools.tavily_client import search_niche_intelligence, tavily_available
    if not tavily_available():
        return []

    year = date.today().year
    candidates_str = ", ".join(niche_candidates[:3])

    scout_queries: dict[str, str] = {
        "trend_hunter":      f"fastest growing SaaS niches {year} search volume trends: {candidates_str}",
        "competitor_analyst": f"competitor reviews gaps weaknesses {candidates_str} SaaS {year} reddit trustpilot",
        "skeptic":           f"SaaS failure case studies market saturation: {candidates_str} indie hackers fails",
        "audience_analyst":  f"who buys {candidates_str} pain points willingness to pay reddit quora",
        "execution_scout":   f"build {candidates_str} SaaS technical complexity APIs needed stack requirements",
    }

    query = scout_queries.get(role_name, f"{candidates_str} SaaS market {year}")
    try:
        results = await search_niche_intelligence(query, max_results=5)
        log.info("[trends] Scout %s Tavily OK | %d results", role_name, len(results))
        return results
    except Exception as exc:
        log.warning("[trends] Scout %s Tavily failed: %s", role_name, exc)
        return []
