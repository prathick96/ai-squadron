#!/usr/bin/env python3
"""
scripts/day3_verify.py
Day 3 readiness check: Supabase, migrations, trends, Stripe status.

Usage:
  python scripts/day3_verify.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return ok


async def main() -> int:
    print("\nAI Squadron — Day 3 Verification\n" + "=" * 40)

    from packages.db.client import get_db, is_supabase_connected

    supa_ok = is_supabase_connected()
    _check("Supabase client", supa_ok, os.getenv("SUPABASE_URL", "")[:40] + "..." if supa_ok else "NullDB")

    tables = [
        "ventures",
        "pipeline_runs",
        "events",
        "agent_logs",
        "revenue_ledger",
        "venture_scorecards",
        "confidence_reports",
        "manual_review_queue",
        "research_dossiers",
    ]
    if supa_ok:
        db = get_db()
        for table in tables:
            try:
                db.table(table).select("*").limit(1).execute()
                _check(f"Table {table}", True)
            except Exception as exc:
                _check(f"Table {table}", False, str(exc)[:80])
    else:
        print("  (skip table checks — Supabase not connected)")

    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_ready = bool(stripe_key) and "your_" not in stripe_key and not stripe_key.startswith("sk_test_xxx")
    _check("Stripe configured", stripe_ready, "optional — use manual revenue until ready")

    tavily = bool(os.getenv("TAVILY_API_KEY", "")) and "your_" not in os.getenv("TAVILY_API_KEY", "")
    _check("Tavily API key", tavily, "recommended for live trends")

    trends_live = os.getenv("TRENDS_LIVE", "true").lower() not in ("0", "false")
    _check("TRENDS_LIVE", trends_live)

    try:
        from packages.tools.trends import fetch_trend_snapshot

        snap = await fetch_trend_snapshot()
        src = snap.get("sources", [snap.get("source")])
        _check("Trend snapshot", bool(snap.get("top_trending_topics")), f"sources={src}")
    except Exception as exc:
        _check("Trend snapshot", False, str(exc)[:80])

    gemini = bool(os.getenv("GEMINI_API_KEY"))
    anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    _check("GEMINI_API_KEY", gemini)
    _check("ANTHROPIC_API_KEY", anthropic)

    kimi = any(
        os.getenv(k, "")
        for k in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "MOONSHOT_API_KEY")
    )
    _check("Kimi provider key", kimi, "optional — mock council without")

    print("\n" + "=" * 40)
    if not supa_ok:
        print("Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env")
        return 1
    print("Day 3 base checks complete. Run: python -m apps.orchestrator.main --mode single")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
