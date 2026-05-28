"""
packages/revenue/store.py
Persistence for revenue/scorecard data.
Uses Supabase when configured; otherwise JSON file at data/day2_store.json.
"""
from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "day2_store.json"

_DEFAULT_STORE: dict[str, Any] = {
    "ventures": [
        {
            "venture_id": "ven_wedge_001",
            "venture_type": "MICRO_SAAS",
            "niche": "AI finance micro-tools",
            "status": "DEVELOPMENT",
            "go_decision": True,
            "stripe_price_id": None,
            "live_url": None,
            "first_revenue_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ],
    "revenue_ledger": [],
    "venture_scorecards": [],
    "confidence_reports": [],
    "manual_review_queue": [],
    "qa_reports": [],
    "revenue_sync_runs": [],
}


def _load_local() -> dict[str, Any]:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STORE_PATH.exists():
        _save_local(deepcopy(_DEFAULT_STORE))
        return deepcopy(_DEFAULT_STORE)
    with _STORE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _save_local(data: dict[str, Any]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _STORE_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def is_local_mode() -> bool:
    from packages.db.client import is_supabase_connected

    return not is_supabase_connected()


def list_ventures() -> list[dict[str, Any]]:
    if is_local_mode():
        return _load_local().get("ventures", [])
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    result = db.table("ventures").select("*").execute()
    return result.data or []


def list_ledger() -> list[dict[str, Any]]:
    if is_local_mode():
        return _load_local().get("revenue_ledger", [])
    try:
        db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
        result = db.table("revenue_ledger").select("*").execute()
        return result.data or []
    except Exception as exc:
        log.warning("Supabase revenue_ledger read failed (%s) — run migration 001. Falling back to local.", exc)
        return _load_local().get("revenue_ledger", [])


def upsert_ledger_row(row: dict[str, Any]) -> None:
    if is_local_mode():
        data = _load_local()
        ledger = data.setdefault("revenue_ledger", [])
        key = (row["venture_id"], row["period_start"], row["revenue_source"])
        ledger[:] = [
            r
            for r in ledger
            if (r.get("venture_id"), r.get("period_start"), r.get("revenue_source")) != key
        ]
        ledger.append(row)
        _save_local(data)
        return
    try:
        db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
        db.table("revenue_ledger").upsert(
            row, on_conflict="venture_id,period_start,revenue_source"
        ).execute()
    except Exception as exc:
        log.warning("Supabase revenue_ledger upsert failed (%s) — saving to local store instead.", exc)
        data = _load_local()
        ledger = data.setdefault("revenue_ledger", [])
        key = (row["venture_id"], row["period_start"], row["revenue_source"])
        ledger[:] = [r for r in ledger if (r.get("venture_id"), r.get("period_start"), r.get("revenue_source")) != key]
        ledger.append(row)
        _save_local(data)


def list_qa_reports() -> list[dict[str, Any]]:
    if is_local_mode():
        return _load_local().get("qa_reports", [])
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    result = db.table("qa_reports").select("*").execute()
    return result.data or []


def save_scorecard(row: dict[str, Any]) -> None:
    if is_local_mode():
        data = _load_local()
        cards = data.setdefault("venture_scorecards", [])
        key = (row["venture_id"], row["period_start"])
        cards[:] = [
            c
            for c in cards
            if (c.get("venture_id"), c.get("period_start")) != key
        ]
        cards.append(row)
        _save_local(data)
        return
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    db.table("venture_scorecards").upsert(row).execute()


def list_scorecards() -> list[dict[str, Any]]:
    if is_local_mode():
        return _load_local().get("venture_scorecards", [])
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    result = db.table("venture_scorecards").select("*").execute()
    return result.data or []


def save_confidence_report(row: dict[str, Any]) -> None:
    if is_local_mode():
        data = _load_local()
        reports = data.setdefault("confidence_reports", [])
        reports[:] = [r for r in reports if r.get("report_week") != row.get("report_week")]
        reports.append(row)
        _save_local(data)
        return
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    db.table("confidence_reports").upsert(row).execute()


def latest_confidence_report() -> dict[str, Any] | None:
    reports = list_confidence_reports()
    if not reports:
        return None
    return sorted(reports, key=lambda r: r.get("report_week", ""), reverse=True)[0]


def list_confidence_reports() -> list[dict[str, Any]]:
    if is_local_mode():
        return _load_local().get("confidence_reports", [])
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    result = db.table("confidence_reports").select("*").execute()
    return result.data or []


def enqueue_manual_review(item: dict[str, Any]) -> None:
    if is_local_mode():
        data = _load_local()
        queue = data.setdefault("manual_review_queue", [])
        queue.append({**item, "status": "PENDING", "created_at": datetime.now(timezone.utc).isoformat()})
        _save_local(data)
        return
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    db.table("manual_review_queue").insert(item).execute()


def list_manual_reviews(status: str | None = None) -> list[dict[str, Any]]:
    if is_local_mode():
        items = _load_local().get("manual_review_queue", [])
        if status:
            return [i for i in items if i.get("status") == status]
        return items
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    q = db.table("manual_review_queue").select("*")
    if status:
        q = q.eq("status", status)
    result = q.execute()
    return result.data or []


def resolve_manual_review(review_id: str, status: str, notes: str = "") -> bool:
    if is_local_mode():
        data = _load_local()
        for item in data.get("manual_review_queue", []):
            if str(item.get("id", "")) == review_id or item.get("venture_id") == review_id:
                item["status"] = status
                item["notes"] = notes
                item["resolved_at"] = datetime.now(timezone.utc).isoformat()
                _save_local(data)
                return True
        return False
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    db.table("manual_review_queue").update({
        "status": status,
        "notes": notes,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", review_id).execute()
    return True


def log_sync_run(source: str, status: str, rows: int, error: str | None = None) -> None:
    row = {
        "source": source,
        "status": status,
        "rows_upserted": rows,
        "error_message": error,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if is_local_mode():
        data = _load_local()
        data.setdefault("revenue_sync_runs", []).append(row)
        _save_local(data)
        return
    db = __import__("packages.db.client", fromlist=["get_db"]).get_db()
    db.table("revenue_sync_runs").insert(row).execute()


def portfolio_snapshot() -> list[dict[str, Any]]:
    """Ventures joined with rolling MRR and days_live for kill/scale logic."""
    ventures = list_ventures()
    ledger = list_ledger()
    today = date.today()

    out: list[dict[str, Any]] = []
    for v in ventures:
        vid = v["venture_id"]
        rows = [r for r in ledger if r.get("venture_id") == vid]
        mrr = sum(float(r.get("amount_usd", 0)) for r in rows)
        burn = sum(float(r.get("burn_usd", 0)) for r in rows)
        created = v.get("created_at", today.isoformat())
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            days_live = (datetime.now(timezone.utc) - created_dt).days
        except (ValueError, TypeError):
            days_live = 0

        visits = 0
        cards = [c for c in list_scorecards() if c.get("venture_id") == vid]
        if cards:
            visits = int(cards[-1].get("organic_visits_monthly", 0))

        out.append({
            "venture_id": vid,
            "niche": v.get("niche", ""),
            "status": v.get("status", "IDEATION"),
            "mrr_usd": round(mrr, 2),
            "burn_usd": round(burn, 2),
            "days_live": days_live,
            "organic_visits_monthly": visits,
            "first_revenue_at": v.get("first_revenue_at"),
        })
    return out
