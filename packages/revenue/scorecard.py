"""
packages/revenue/scorecard.py
Compute per-venture leading indicators and SCALE/HOLD/KILL/WATCH signals.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from packages.revenue import store

KILL_MRR = float(os.getenv("KILL_THRESHOLD_MRR", "50"))
KILL_DAYS = int(os.getenv("KILL_THRESHOLD_DAYS", "90"))
SCALE_MRR = float(os.getenv("SCALE_THRESHOLD_MRR", "200"))
KILL_EARLY_DAYS = int(os.getenv("KILL_EARLY_DAYS", "60"))
KILL_EARLY_VISITS = int(os.getenv("KILL_EARLY_VISITS", "100"))


def _qa_first_pass_rate(venture_id: str) -> float:
    reports = [r for r in store.list_qa_reports() if r.get("venture_id") == venture_id]
    if not reports:
        return 0.0
    passed = sum(1 for r in reports if r.get("is_passed"))
    return round(100.0 * passed / len(reports), 1)


def _signal_for_venture(v: dict, mrr: float, burn: float, qa_rate: float, visits: int) -> tuple[str, str]:
    days = v.get("days_live", 0)

    if mrr >= SCALE_MRR:
        return "SCALE", f"MRR ${mrr:.2f} >= scale threshold ${SCALE_MRR}"

    if mrr < KILL_MRR and days >= KILL_DAYS:
        return "KILL", f"MRR ${mrr:.2f} below ${KILL_MRR} for {days} days"

    if (
        mrr <= 0
        and days >= KILL_EARLY_DAYS
        and visits < KILL_EARLY_VISITS
    ):
        return "KILL", f"No revenue and <{KILL_EARLY_VISITS} visits after {days} days"

    if mrr > 0 and qa_rate >= 60:
        return "WATCH", "Revenue positive — validate retention before scale"

    if days < 30:
        return "HOLD", "Early stage — gather leading indicators"

    return "HOLD", f"MRR ${mrr:.2f} — continue distribution tests"


def build_venture_scorecards() -> list[dict]:
    period_end = date.today()
    period_start = period_end - timedelta(days=7)
    portfolio = store.portfolio_snapshot()
    built: list[dict] = []

    for v in portfolio:
        mrr = v["mrr_usd"]
        burn = v["burn_usd"]
        qa_rate = _qa_first_pass_rate(v["venture_id"])
        visits = v.get("organic_visits_monthly", 0)
        signal, reason = _signal_for_venture(v, mrr, burn, qa_rate, visits)

        margin = 0.0
        if mrr > 0:
            margin = round(100.0 * (mrr - burn) / mrr, 1)

        row = {
            "venture_id": v["venture_id"],
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "mrr_usd": mrr,
            "burn_usd": burn,
            "gross_margin_pct": margin,
            "organic_visits_monthly": visits,
            "retention_30d_pct": None,
            "qa_first_pass_rate_pct": qa_rate,
            "days_live": v["days_live"],
            "platform_monetization": "NONE",
            "ltv_usd": None,
            "cac_usd": None,
            "signal": signal,
            "signal_reason": reason,
        }
        store.save_scorecard(row)
        built.append(row)

    return built
