"""
packages/revenue/cycle.py
Day 2 revenue cycle: sync → scorecards → confidence → kill/scale signals.
"""
from __future__ import annotations

import logging

from packages.revenue import store
from packages.revenue.adsense_sync import sync_adsense
from packages.revenue.confidence import build_confidence_report
from packages.revenue.scorecard import build_venture_scorecards
from packages.revenue.stripe_sync import sync_stripe

log = logging.getLogger(__name__)


async def run_day2_cycle() -> dict:
    """
    Full Day 2 cycle. Safe to run daily via Revenue Engine scheduler.
    """
    log.info("DAY 2 CYCLE | sync → scorecards → confidence → signals")

    stripe_result = sync_stripe()
    adsense_result = sync_adsense()
    log.info("Stripe sync: %s", stripe_result)
    log.info("AdSense sync: %s", adsense_result)

    scorecards = build_venture_scorecards()
    portfolio = store.portfolio_snapshot()
    report = build_confidence_report(scorecards, portfolio)
    store.save_confidence_report(report)

    scale, kill, hold = [], [], []
    for card in scorecards:
        sig = card.get("signal", "HOLD")
        vid = card["venture_id"]
        if sig == "SCALE":
            scale.append(vid)
        elif sig == "KILL":
            kill.append(vid)
        else:
            hold.append(vid)

    log.info(
        "Confidence %d (%s) | MRR $%.2f | 12mo p50 $%.2f",
        report["confidence_score"],
        report["confidence_tier"],
        report["mrr_current_usd"],
        report["forecast_p50_mrr_12mo"],
    )
    log.info("Signals SCALE=%s KILL=%s HOLD=%s", scale, kill, hold)

    for action in report.get("recommended_actions", []):
        log.info("ACTION → %s", action)

    return {
        "stripe": stripe_result,
        "adsense": adsense_result,
        "scorecards": scorecards,
        "confidence_report": report,
        "scale_ventures": scale,
        "kill_ventures": kill,
        "hold_ventures": hold,
        "storage_mode": "local" if store.is_local_mode() else "supabase",
    }
