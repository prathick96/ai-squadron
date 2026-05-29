"""Live revenue + confidence payloads for Command Center."""
from __future__ import annotations

from packages.revenue import store
from packages.revenue.confidence import build_confidence_report
from packages.revenue.scorecard import build_venture_scorecards


def live_revenue_summary() -> dict | None:
    portfolio = store.portfolio_snapshot()
    if not portfolio and store.is_local_mode():
        return None

    mrr = sum(v["mrr_usd"] for v in portfolio)
    burn = sum(v["burn_usd"] for v in portfolio)
    ledger = store.list_ledger()
    by_source = {"stripe": 0.0, "adsense": 0.0, "affiliate": 0.0, "other": 0.0}
    for row in ledger:
        src = (row.get("revenue_source") or "OTHER").lower()
        key = "stripe" if src == "stripe" else "adsense" if src == "adsense" else "affiliate" if src == "affiliate" else "other"
        by_source[key] += float(row.get("amount_usd", 0))

    latest = store.latest_confidence_report()
    return {
        "mrr_usd": round(mrr, 2),
        "arr_usd": round(mrr * 12, 2),
        "burn_usd": round(burn, 2),
        "net_mrr_usd": round(mrr - burn, 2),
        "burn_earn_ratio": round(burn / mrr, 4) if mrr > 0 else 0.0,
        "by_source": by_source,
        "updated_at": latest.get("created_at") if latest else None,
    }


def live_confidence() -> dict:
    from datetime import date

    report = store.latest_confidence_report()
    if report:
        # Only use the cached report if it was computed this week; otherwise recalculate.
        current_week = date.today().isocalendar()
        current_week_start = date.fromisocalendar(current_week[0], current_week[1], 1).isoformat()
        if report.get("report_week") == current_week_start:
            return report

    scorecards = store.list_scorecards() or build_venture_scorecards()
    portfolio = store.portfolio_snapshot()
    return build_confidence_report(scorecards, portfolio)


def live_revenue_plan() -> dict:
    report = live_confidence()
    return {
        "headline": f"Confidence {report.get('confidence_score', 0)}/100 ({report.get('confidence_tier', 'LOW')})",
        "actions": report.get("recommended_actions", []),
        "kill_candidates": report.get("kill_ventures", []),
        "scale_candidates": report.get("scale_ventures", []),
    }
