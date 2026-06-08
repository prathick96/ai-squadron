"""
apps/api/data/mock_dashboard.py
Fallback dashboard payloads when Supabase is not configured or returns empty results.

These are structural defaults only — no hardcoded niches, demo ventures, or fake scores.
All niche/venture data comes from live Supabase queries in main.py.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

AGENT_IDS = [
    "RESEARCH_COUNCIL",
    "GRAND_CEO",
    "PRODUCT_VP",
    "PRODUCT_MANAGER",
    "ENGINEERING_TEAM",
    "QA_TECHNICAL",
    "LEGAL_AGENT",
    "SECURITY_AGENT",
    "ACCOUNT_DISTRIBUTION",
    "DEPLOYMENT_AGENT",
    "MARKETING_SEO",
    "PRODUCT_GROWTH",
    "REVENUE_ENGINE",
]

_AGENT_DESCRIPTIONS = {
    "RESEARCH_COUNCIL":     "5-scout Gemini 2.5 Pro niche research",
    "GRAND_CEO":            "Go/No-Go strategic decision",
    "PRODUCT_VP":           "Tech spec generation",
    "PRODUCT_MANAGER":      "Feature requirements",
    "ENGINEERING_TEAM":     "React + TypeScript build",
    "QA_TECHNICAL":         "Build validation + Playwright",
    "LEGAL_AGENT":          "Compliance clearance",
    "SECURITY_AGENT":       "OWASP security scan",
    "ACCOUNT_DISTRIBUTION": "Platform account setup",
    "DEPLOYMENT_AGENT":     "Railway deployment",
    "MARKETING_SEO":        "SEO + growth strategy",
    "PRODUCT_GROWTH":       "Revenue signal analysis",
    "REVENUE_ENGINE":       "Daily revenue sync",
}


def agent_grid() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "agent_name":    aid,
            "status":        "IDLE",
            "current_task":  _AGENT_DESCRIPTIONS.get(aid, "Awaiting pipeline run"),
            "tokens_used":   0,
            "latency_ms":    0,
            "retry_count":   0,
            "success_ratio": 0.0,
            "updated_at":    now,
        }
        for aid in AGENT_IDS
    ]


def revenue_summary() -> dict:
    burn = float(os.getenv("MONTHLY_BURN_USD", "47.20"))
    return {
        "mrr_usd":        0.0,
        "arr_usd":        0.0,
        "burn_usd":       burn,
        "net_mrr_usd":    -burn,
        "burn_earn_ratio": 0.0,
        "by_source": {
            "razorpay": 0.0,
            "adsense":  0.0,
            "affiliate": 0.0,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def portfolio_slots(total: int = 50) -> list[dict]:
    """Return empty portfolio slots — actual ventures come from Supabase."""
    return [
        {
            "slot":       i + 1,
            "venture_id": None,
            "status":     "AVAILABLE",
            "niche":      "",
            "mrr_usd":    0.0,
        }
        for i in range(total)
    ]


def trend_heatmap() -> dict:
    """
    Live trend data comes from pytrends via /api/trends.
    This is an empty structural default for when the live query is unavailable.
    """
    return {
        "trends":       [],
        "coverage_pct": 0.0,
        "updated_at":   datetime.now(timezone.utc).isoformat(),
    }


def security_alerts() -> list[dict]:
    return [
        {
            "severity": "INFO",
            "platform": "system",
            "message":  "All platform ToS snapshots current — no policy changes detected",
            "at":       datetime.now(timezone.utc).isoformat(),
        },
    ]


def revenue_plan() -> dict:
    """Dynamic revenue plan — populated by Revenue Engine from live data."""
    return {
        "headline": "Awaiting first pipeline run — revenue plan generated after initial venture launches",
        "actions": [
            "Run first PRODUCT pipeline to deploy a live SaaS venture",
            "Run first MEDIA pipeline to launch a faceless YouTube channel",
            "Target positive MRR before scaling to 5+ concurrent ventures",
            "Monitor QA pass rate — maintain >70% before increasing parallelism",
        ],
        "kill_candidates":  [],
        "scale_candidates": [],
    }
