"""
packages/revenue/confidence.py
Portfolio confidence score (0-100) and conservative 12-month MRR forecast bands.
"""
from __future__ import annotations

from datetime import date
from typing import Any

# Phase targets from REVENUE_REALITY.md (month-indexed cumulative MRR ceilings)
_PHASE_P50_BY_MONTH = {
    3: 300,
    6: 3000,
    9: 8000,
    12: 12000,
    18: 40000,
    24: 150000,
}


def _tier(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def _forecast_bands(mrr_current: float, months_elapsed: int, confidence_score: int) -> tuple[float, float, float]:
    """
    p10 / p50 / p90 for 12-month MRR outlook.
    Anchored to phase table, scaled by current traction and confidence.
    """
    phase_cap = 12000
    for m, cap in sorted(_PHASE_P50_BY_MONTH.items()):
        if months_elapsed <= m:
            phase_cap = cap
            break
    else:
        phase_cap = _PHASE_P50_BY_MONTH[24]

    traction = min(1.0, mrr_current / 500.0) if mrr_current > 0 else 0.05
    conf_factor = confidence_score / 100.0

    p50 = round(max(mrr_current, phase_cap * traction * conf_factor * 0.35), 2)
    p10 = round(p50 * 0.25, 2)
    p90 = round(min(p50 * 2.5, phase_cap * 0.85), 2)
    return p10, p50, p90


def build_confidence_report(
    scorecards: list[dict],
    portfolio: list[dict],
) -> dict[str, Any]:
    mrr_total = sum(v["mrr_usd"] for v in portfolio)
    burn_total = sum(v["burn_usd"] for v in portfolio)
    burn_earn = round(burn_total / mrr_total, 4) if mrr_total > 0 else 0.0

    ventures_with_revenue = sum(1 for v in portfolio if v["mrr_usd"] > 0)
    live_count = sum(1 for v in portfolio if v.get("status") in ("LIVE", "SCALING", "DEVELOPMENT"))
    qa_rates = [s.get("qa_first_pass_rate_pct", 0) for s in scorecards if s.get("qa_first_pass_rate_pct")]
    avg_qa = round(sum(qa_rates) / len(qa_rates), 1) if qa_rates else 0.0

    scale_count = sum(1 for s in scorecards if s.get("signal") == "SCALE")
    kill_count = sum(1 for s in scorecards if s.get("signal") == "KILL")

    months_elapsed = max((v.get("days_live", 0) for v in portfolio), default=0) // 30

    from packages.revenue import store

    pending_reviews = store.list_manual_reviews(status="PENDING")

    score = 0
    score += min(25, int(avg_qa * 0.25))                    # QA up to 25
    score += min(25, ventures_with_revenue * 12)            # revenue ventures up to 25
    score += 15 if mrr_total >= 500 else (8 if mrr_total > 0 else 0)
    score += 15 if burn_earn < 0.4 and mrr_total > 0 else (5 if mrr_total == 0 else 0)
    score += 10 if scale_count > 0 else 0
    score -= min(20, len(pending_reviews) * 5)
    score -= kill_count * 3
    score = max(0, min(100, score))

    p10, p50, p90 = _forecast_bands(mrr_total, months_elapsed, score)

    indicators = {
        "qa_first_pass_rate_pct": avg_qa,
        "ventures_with_revenue": ventures_with_revenue,
        "live_venture_count": live_count,
        "burn_earn_ratio": burn_earn,
        "mrr_total_usd": round(mrr_total, 2),
        "burn_total_usd": round(burn_total, 2),
        "manual_review_pending": len(pending_reviews),
        "scale_signals": scale_count,
        "kill_signals": kill_count,
        "months_elapsed": months_elapsed,
    }

    actions = _recommended_actions(score, indicators, scorecards)

    report_week = date.today().isocalendar()
    week_start = date.fromisocalendar(report_week[0], report_week[1], 1)

    return {
        "report_week": week_start.isoformat(),
        "confidence_score": score,
        "confidence_tier": _tier(score),
        "mrr_current_usd": round(mrr_total, 2),
        "burn_current_usd": round(burn_total, 2),
        "burn_earn_ratio": burn_earn,
        "forecast_p10_mrr_12mo": p10,
        "forecast_p50_mrr_12mo": p50,
        "forecast_p90_mrr_12mo": p90,
        "leading_indicators": indicators,
        "recommended_actions": actions,
        "scale_ventures": [s["venture_id"] for s in scorecards if s.get("signal") == "SCALE"],
        "kill_ventures": [s["venture_id"] for s in scorecards if s.get("signal") == "KILL"],
    }


def _recommended_actions(score: int, indicators: dict, scorecards: list[dict]) -> list[str]:
    actions: list[str] = []

    if indicators["mrr_total_usd"] == 0:
        actions.append("Ship one wedge (SaaS + channel) and run pipeline with live deploy keys.")
    if indicators["qa_first_pass_rate_pct"] < 60:
        actions.append("Raise QA first-pass rate above 60% before launching venture #2.")
    if indicators["manual_review_pending"] > 0:
        actions.append(
            f"Resolve {indicators['manual_review_pending']} manual review item(s) in Command Center."
        )
    if indicators["kill_signals"] > 0:
        actions.append("Execute KILL signals and reallocate API budget to SCALE ventures.")
    if indicators["scale_signals"] > 0:
        actions.append("Double content + pSEO on SCALE ventures only.")
    if score < 40:
        actions.append("Do not increase MAX_PARALLEL_PIPELINES until confidence tier reaches MEDIUM.")
    if not actions:
        actions.append("Hold course: monitor weekly leading indicators and update forecasts.")

    return actions
