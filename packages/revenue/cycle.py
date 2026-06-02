"""
packages/revenue/cycle.py
Day 2 revenue cycle: sync → scorecards → confidence → kill/scale signals.

Payment provider auto-detection (in priority order):
  1. PADDLE_API_KEY set  → use Paddle (recommended for Indian founders, USD payments)
  2. STRIPE_SECRET_KEY set → use Stripe (for when you have a US/CA entity)
  3. Neither set → demo mode (records $0 MRR + burn for ven_wedge_001)
"""
from __future__ import annotations

import logging
import os

from packages.revenue import store
from packages.revenue.adsense_sync import sync_adsense
from packages.revenue.confidence import build_confidence_report
from packages.revenue.scorecard import build_venture_scorecards

log = logging.getLogger(__name__)


def _sync_subscriptions() -> dict:
    """
    Auto-detect the configured payment provider and sync subscriptions.
    Paddle takes priority over Stripe when both keys are set.
    """
    paddle_key = os.getenv("PADDLE_API_KEY", "")
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")

    if paddle_key and "your_" not in paddle_key:
        log.info("Payment provider: Paddle")
        from packages.revenue.paddle_sync import sync_paddle
        return sync_paddle()

    if stripe_key and "your_" not in stripe_key and not stripe_key.startswith("sk_test_xxx"):
        log.info("Payment provider: Stripe")
        from packages.revenue.stripe_sync import sync_stripe
        return sync_stripe()

    log.info("Payment provider: demo (set PADDLE_API_KEY or STRIPE_SECRET_KEY for live)")
    from packages.revenue.stripe_sync import sync_stripe  # handles demo mode internally
    return sync_stripe()


async def run_day2_cycle() -> dict:
    """
    Full Day 2 cycle. Safe to run daily via Revenue Engine scheduler.
    """
    log.info("DAY 2 CYCLE | sync → scorecards → confidence → signals")

    payment_result = _sync_subscriptions()
    adsense_result = sync_adsense()
    log.info("Payment sync: %s", payment_result)
    log.info("AdSense sync: %s", adsense_result)

    scorecards = build_venture_scorecards()
    portfolio  = store.portfolio_snapshot()
    report     = build_confidence_report(scorecards, portfolio)
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
        "payment":          payment_result,
        "adsense":          adsense_result,
        "scorecards":       scorecards,
        "confidence_report": report,
        "scale_ventures":   scale,
        "kill_ventures":    kill,
        "hold_ventures":    hold,
        "storage_mode":     "local" if store.is_local_mode() else "supabase",
    }
