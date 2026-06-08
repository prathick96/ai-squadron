"""
packages/revenue/razorpay_sync.py
Pull Razorpay subscription MRR → revenue_ledger rows.

Replaces both stripe_sync.py and paddle_sync.py.

Razorpay Subscriptions API reference:
  https://razorpay.com/docs/api/subscriptions/

Settlement note:
  Razorpay settles in INR to your Indian bank account regardless of the
  customer's payment currency. We record revenue in USD (converted at the
  exchange rate Razorpay applied) so the rest of the system can track MRR
  consistently. The amount_usd field is derived from the subscription plan's
  USD-denominated price — not the INR settlement amount.
"""
from __future__ import annotations

import logging
import os
from datetime import date

from packages.revenue import store

log = logging.getLogger(__name__)


def sync_razorpay() -> dict:
    """
    Pull active Razorpay subscriptions and map them to ventures via
    subscription notes.venture_id.

    Returns: {status, rows_upserted, mrr_total_usd, mode, error?}
    """
    key_id     = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")

    if not key_id or not key_secret or "your_" in key_id:
        log.info("[razorpay_sync] No live keys — recording demo ledger row")
        return _sync_demo()

    try:
        import razorpay  # type: ignore[import-untyped]
        client = razorpay.Client(auth=(key_id, key_secret))
        return _sync_live(client)
    except ImportError:
        log.warning("[razorpay_sync] razorpay package not installed — pip install razorpay")
        return {"status": "FAILED", "rows_upserted": 0, "error": "razorpay not installed"}
    except Exception as exc:
        log.exception("[razorpay_sync] failed: %s", exc)
        store.log_sync_run("RAZORPAY", "FAILED", 0, str(exc))
        return {"status": "FAILED", "rows_upserted": 0, "error": str(exc)}


def _sync_demo() -> dict:
    period_end   = date.today()
    period_start = period_end.replace(day=1)
    store.upsert_ledger_row({
        "venture_id":     "ven_wedge_001",
        "period_start":   period_start.isoformat(),
        "period_end":     period_end.isoformat(),
        "revenue_source": "RAZORPAY",
        "amount_usd":     0.0,
        "burn_usd":       float(os.getenv("MONTHLY_BURN_USD", "47.20")),
    })
    store.log_sync_run("RAZORPAY", "SUCCESS", 1)
    return {"status": "SUCCESS", "rows_upserted": 1, "mrr_total_usd": 0.0, "mode": "demo"}


# Plan price map — used to determine USD revenue from subscription plan_id.
# These are populated from env vars; updated when you run setup_plans().
def _plan_amount_usd(plan_id: str) -> float:
    """Return the monthly USD equivalent for a given Razorpay plan_id."""
    plan_map = {
        os.getenv("RAZORPAY_PLAN_BUILDER_MONTHLY", ""): 49.0,
        os.getenv("RAZORPAY_PLAN_BUILDER_ANNUAL",  ""): 39.0,   # $468/yr ÷ 12
        os.getenv("RAZORPAY_PLAN_STUDIO_MONTHLY",  ""): 149.0,
        os.getenv("RAZORPAY_PLAN_STUDIO_ANNUAL",   ""): 119.0,  # $1428/yr ÷ 12
    }
    # Remove empty-string keys (unset env vars)
    plan_map = {k: v for k, v in plan_map.items() if k}
    return plan_map.get(plan_id, 0.0)


def _sync_live(client: object) -> dict:
    """
    Razorpay Subscriptions API — paginate active subscriptions.

    Notes on subscription records:
      - venture_id is stored in subscription notes.venture_id when the subscription
        is created by our backend (packages.tools.razorpay_client.create_subscription).
      - plan_id is used to determine the USD price.
    """
    period_end   = date.today()
    period_start = period_end.replace(day=1)
    rows         = 0
    mrr_total    = 0.0

    # Razorpay list subscriptions — paginate with skip/count
    skip = 0
    count = 100

    while True:
        response = client.subscription.all({  # type: ignore[attr-defined]
            "status": "active",
            "count":  count,
            "skip":   skip,
        })

        items = response.get("items", []) if isinstance(response, dict) else []
        if not items:
            break

        for sub in items:
            notes   = sub.get("notes") or {}
            plan_id = sub.get("plan_id", "")
            vid     = notes.get("venture_id")

            if not vid:
                continue  # subscription not linked to a venture — skip

            mrr = _plan_amount_usd(plan_id)
            mrr_total += mrr

            store.upsert_ledger_row({
                "venture_id":     vid,
                "period_start":   period_start.isoformat(),
                "period_end":     period_end.isoformat(),
                "revenue_source": "RAZORPAY",
                "amount_usd":     round(mrr, 2),
                "burn_usd":       0,
            })
            rows += 1

        if len(items) < count:
            break
        skip += count

    store.log_sync_run("RAZORPAY", "SUCCESS", rows)
    return {
        "status":        "SUCCESS",
        "rows_upserted": rows,
        "mrr_total_usd": round(mrr_total, 2),
        "mode":          "live",
        "provider":      "razorpay",
    }
