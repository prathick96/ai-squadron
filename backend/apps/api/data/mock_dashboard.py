"""
Mock dashboard payloads when Supabase is not configured.
Replace with live queries in Phase 1.
"""
from __future__ import annotations

from datetime import datetime, timezone

AGENT_IDS = [
    "CEO_NICHE_SCOUT",
    "PRODUCT_TEAM",
    "ENGINEERING_TEAM",
    "CONTENT_TEAM",
    "QA_AUDITOR",
    "SECURITY_AGENT",
    "ACCOUNT_DISTRIBUTION",
    "DEPLOYMENT_TEAM",
    "MARKETING_TEAM",
    "GLOBAL_TEAM",
    "GROWTH_TEAM",
    "REVENUE_ENGINE",
]

_STATUSES = ["IDLE", "RUNNING", "SUCCESS", "FAILED", "RETRYING"]


def agent_grid() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    tasks = {
        "CEO_NICHE_SCOUT": "Scanning Google Trends: AI finance tools",
        "PRODUCT_TEAM": "Idle — awaiting Venture Brief",
        "ENGINEERING_TEAM": "Idle",
        "CONTENT_TEAM": "Idle",
        "QA_AUDITOR": "Idle",
        "SECURITY_AGENT": "Idle",
        "ACCOUNT_DISTRIBUTION": "Idle",
        "DEPLOYMENT_TEAM": "Idle",
        "MARKETING_TEAM": "Idle",
        "GLOBAL_TEAM": "Idle",
        "GROWTH_TEAM": "Idle",
        "REVENUE_ENGINE": "Next cycle 00:00 UTC",
    }
    return [
        {
            "agent_name": aid,
            "status": "RUNNING" if aid == "CEO_NICHE_SCOUT" else "IDLE",
            "current_task": tasks.get(aid, "Idle"),
            "tokens_used": 1240 if aid == "CEO_NICHE_SCOUT" else 0,
            "latency_ms": 2100 if aid == "CEO_NICHE_SCOUT" else 0,
            "retry_count": 0,
            "success_ratio": 0.94 if aid != "REVENUE_ENGINE" else 1.0,
            "updated_at": now,
        }
        for aid in AGENT_IDS
    ]


def revenue_summary() -> dict:
    return {
        "mrr_usd": 0.0,
        "arr_usd": 0.0,
        "burn_usd": 47.20,
        "net_mrr_usd": -47.20,
        "burn_earn_ratio": 0.0,
        "by_source": {
            "stripe": 0.0,
            "adsense": 0.0,
            "affiliate": 0.0,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def portfolio_slots(total: int = 450) -> list[dict]:
    stages = ["IDEATION", "DEVELOPMENT", "QA", "LIVE", "SCALING", "KILLED"]
    slots = []
    for i in range(total):
        if i == 0:
            stage = "DEVELOPMENT"
            niche = "AI finance micro-tools"
        elif i < 5:
            stage = "IDEATION"
            niche = f"Reserved slot {i + 1}"
        else:
            stage = "IDEATION"
            niche = ""
        slots.append({
            "slot": i + 1,
            "venture_id": f"ven_slot_{i + 1:03d}" if i < 5 else None,
            "status": stage,
            "niche": niche,
            "mrr_usd": 0.0,
        })
    return slots


def trend_heatmap() -> dict:
    """Global trends vs portfolio coverage (mock)."""
    trends = [
        {"topic": "AI agents", "score": 92, "region": "US", "covered": False},
        {"topic": "Personal finance automation", "score": 78, "region": "US", "covered": True},
        {"topic": "Faceless YouTube automation", "score": 85, "region": "GLOBAL", "covered": False},
        {"topic": "Micro-SaaS calculators", "score": 65, "region": "DE", "covered": False},
        {"topic": "Short-form crypto explainers", "score": 71, "region": "BR", "covered": False},
    ]
    return {
        "trends": trends,
        "coverage_pct": 20.0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def security_alerts() -> list[dict]:
    return [
        {
            "severity": "INFO",
            "platform": "youtube",
            "message": "ToS snapshot current — no policy changes in last 7 days",
            "at": datetime.now(timezone.utc).isoformat(),
        },
    ]


def revenue_plan() -> dict:
    return {
        "headline": "Phase 0 — prove one wedge before scaling portfolio",
        "actions": [
            "Complete first MICRO_SAAS + MEDIA_CHANNEL pipeline run",
            "Target $500 MRR by month 6 via 1–2 retained products",
            "Keep burn under $100/mo until Stripe revenue > $200",
            "Do not open >5 concurrent ventures until QA pass rate > 60%",
        ],
        "kill_candidates": [],
        "scale_candidates": [],
    }
