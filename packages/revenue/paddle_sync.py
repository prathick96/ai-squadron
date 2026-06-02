"""
packages/revenue/paddle_sync.py
Paddle subscription sync → revenue_ledger rows.

Paddle is the payment provider for Indian-resident founders collecting USD.
As a Merchant of Record, Paddle handles all global tax (VAT, GST, US sales
tax) — no US/CA entity required.

Setup:
  1. Create account at https://www.paddle.com
  2. Add products with metadata.venture_id = "ven_XXXXXXXX"
  3. Set PADDLE_API_KEY in Railway env vars
  4. Set PADDLE_ENVIRONMENT=sandbox for testing, production for live

API reference: https://developer.paddle.com/api-reference
"""
from __future__ import annotations

import logging
import os
from datetime import date

from packages.revenue import store

log = logging.getLogger(__name__)

_SANDBOX_BASE = "https://sandbox-api.paddle.com"
_PROD_BASE    = "https://api.paddle.com"


def _paddle_base() -> str:
    env = os.getenv("PADDLE_ENVIRONMENT", "sandbox").lower()
    return _PROD_BASE if env == "production" else _SANDBOX_BASE


def sync_paddle() -> dict:
    """
    Pull active Paddle subscriptions and map them to ventures via
    custom_data.venture_id on the subscription or product.

    Returns: {status, rows_upserted, mrr_total_usd, mode, error?}
    """
    key = os.getenv("PADDLE_API_KEY", "")
    if not key or "your_" in key:
        log.info("[paddle_sync] No live key — recording demo row")
        return _sync_demo()

    try:
        return _sync_live(key)
    except ImportError:
        log.warning("[paddle_sync] httpx not installed — pip install httpx")
        return {"status": "FAILED", "rows_upserted": 0, "error": "httpx not installed"}
    except Exception as exc:
        log.exception("[paddle_sync] failed: %s", exc)
        store.log_sync_run("STRIPE", "FAILED", 0, str(exc))   # reuse STRIPE key in ledger
        return {"status": "FAILED", "rows_upserted": 0, "error": str(exc)}


def _sync_demo() -> dict:
    period_end   = date.today()
    period_start = period_end.replace(day=1)
    store.upsert_ledger_row({
        "venture_id":     "ven_wedge_001",
        "period_start":   period_start.isoformat(),
        "period_end":     period_end.isoformat(),
        "revenue_source": "STRIPE",   # maps to existing enum
        "amount_usd":     0.0,
        "burn_usd":       float(os.getenv("MONTHLY_BURN_USD", "47.20")),
    })
    store.log_sync_run("STRIPE", "SUCCESS", 1)
    return {"status": "SUCCESS", "rows_upserted": 1, "mrr_total_usd": 0.0, "mode": "demo"}


def _sync_live(api_key: str) -> dict:
    """
    Paddle Billing API v2 — list active subscriptions, map to ventures.

    Paddle subscription custom_data should contain:
      {"venture_id": "ven_XXXXXXXX"}
    Set this in the Paddle dashboard on each product or subscription.
    """
    import httpx

    base        = _paddle_base()
    period_end  = date.today()
    period_start = period_end.replace(day=1)
    rows        = 0
    mrr_total   = 0.0

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    # Paginate through active subscriptions
    after_cursor: str | None = None
    while True:
        params: dict = {"status": "active", "per_page": 200}
        if after_cursor:
            params["after"] = after_cursor

        resp = httpx.get(f"{base}/subscriptions", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()

        for sub in body.get("data", []):
            # Extract venture_id from custom_data on subscription or its items
            custom = sub.get("custom_data") or {}
            vid    = custom.get("venture_id")
            if not vid:
                # Try the product's custom_data
                for item in sub.get("items", []):
                    prod_custom = item.get("product", {}).get("custom_data") or {}
                    vid = prod_custom.get("venture_id")
                    if vid:
                        break
            if not vid:
                continue

            # Calculate monthly MRR from recurring price
            mrr = 0.0
            for item in sub.get("items", []):
                price   = item.get("price") or {}
                unit    = int((price.get("unit_price") or {}).get("amount", 0)) / 100
                qty     = int(item.get("quantity", 1))
                billing = price.get("billing_cycle", {})
                interval = billing.get("interval", "month")
                freq     = int(billing.get("frequency", 1))

                monthly = unit * qty
                if interval == "year":
                    monthly = monthly / (12 * freq)
                elif interval == "week":
                    monthly = monthly * (4.33 / freq)
                elif interval == "day":
                    monthly = monthly * (30 / freq)
                mrr += monthly

            mrr_total += mrr
            store.upsert_ledger_row({
                "venture_id":     vid,
                "period_start":   period_start.isoformat(),
                "period_end":     period_end.isoformat(),
                "revenue_source": "STRIPE",   # reuse existing enum
                "amount_usd":     round(mrr, 2),
                "burn_usd":       0,
            })
            rows += 1

        # Pagination
        meta = body.get("meta", {})
        pagination = meta.get("pagination", {})
        if pagination.get("has_more"):
            after_cursor = pagination.get("estimated_total")  # Paddle uses cursor
            next_url = pagination.get("next")
            if next_url:
                # Extract cursor from next URL
                import urllib.parse
                parsed = urllib.parse.urlparse(next_url)
                qs     = urllib.parse.parse_qs(parsed.query)
                after_cursor = qs.get("after", [None])[0]
            if not after_cursor:
                break
        else:
            break

    store.log_sync_run("STRIPE", "SUCCESS", rows)
    return {
        "status":        "SUCCESS",
        "rows_upserted": rows,
        "mrr_total_usd": round(mrr_total, 2),
        "mode":          "live",
        "provider":      "paddle",
    }
