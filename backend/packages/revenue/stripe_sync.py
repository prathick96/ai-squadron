"""
packages/revenue/stripe_sync.py
Pull subscription MRR from Stripe → revenue_ledger rows.
Requires STRIPE_SECRET_KEY. No-op with demo data when key missing.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

from packages.revenue import store

log = logging.getLogger(__name__)


def sync_stripe() -> dict:
    """
    Returns summary: {status, rows_upserted, mrr_total_usd, error?}
    """
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key or key.startswith("sk_test_xxx") or "your_" in key:
        log.info("[stripe_sync] No live key — recording demo ledger row for wedge venture")
        return _sync_demo()

    try:
        import stripe  # type: ignore[import-untyped]

        stripe.api_key = key
        return _sync_live(stripe)
    except ImportError:
        log.warning("[stripe_sync] stripe package not installed — pip install stripe")
        return {"status": "FAILED", "rows_upserted": 0, "error": "stripe not installed"}
    except Exception as exc:
        log.exception("[stripe_sync] failed: %s", exc)
        store.log_sync_run("STRIPE", "FAILED", 0, str(exc))
        return {"status": "FAILED", "rows_upserted": 0, "error": str(exc)}


def _sync_demo() -> dict:
    period_end = date.today()
    period_start = period_end.replace(day=1)
    store.upsert_ledger_row({
        "venture_id": "ven_wedge_001",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "revenue_source": "STRIPE",
        "amount_usd": 0.0,
        "burn_usd": float(os.getenv("MONTHLY_BURN_USD", "47.20")),
    })
    store.log_sync_run("STRIPE", "SUCCESS", 1)
    return {"status": "SUCCESS", "rows_upserted": 1, "mrr_total_usd": 0.0, "mode": "demo"}


def _sync_live(stripe: object) -> dict:
    """Map Stripe subscriptions to ventures via metadata.venture_id."""
    period_end = date.today()
    period_start = period_end.replace(day=1)
    rows = 0
    mrr_total = 0.0

    ventures = {v["venture_id"]: v for v in store.list_ventures()}
    subs = stripe.Subscription.list(status="active", limit=100)  # type: ignore[attr-defined]

    for sub in subs.auto_paging_iter():  # type: ignore[attr-defined]
        meta = getattr(sub, "metadata", {}) or {}
        vid = meta.get("venture_id")
        if not vid:
            continue
        amount_cents = 0
        for item in sub["items"]["data"]:  # type: ignore[index]
            price = item.get("price") or {}
            unit = price.get("unit_amount") or 0
            qty = item.get("quantity") or 1
            interval = (price.get("recurring") or {}).get("interval", "month")
            monthly = int(unit) * qty / 100.0
            if interval == "year":
                monthly /= 12
            amount_cents += monthly

        mrr = round(amount_cents, 2)
        mrr_total += mrr
        store.upsert_ledger_row({
            "venture_id": vid,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "revenue_source": "STRIPE",
            "amount_usd": mrr,
            "burn_usd": 0,
        })
        if mrr > 0 and ventures.get(vid, {}).get("first_revenue_at") is None:
            _mark_first_revenue(vid)
        rows += 1

    store.log_sync_run("STRIPE", "SUCCESS", rows)
    return {"status": "SUCCESS", "rows_upserted": rows, "mrr_total_usd": round(mrr_total, 2), "mode": "live"}


def _mark_first_revenue(venture_id: str) -> None:
    from datetime import datetime, timezone

    if store.is_local_mode():
        from packages.revenue.store import _load_local, _save_local

        data = _load_local()
        for v in data.get("ventures", []):
            if v["venture_id"] == venture_id:
                v["first_revenue_at"] = datetime.now(timezone.utc).isoformat()
        _save_local(data)
    else:
        db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
        db.table("ventures").update({
            "first_revenue_at": datetime.now(timezone.utc).isoformat(),
        }).eq("venture_id", venture_id).execute()
