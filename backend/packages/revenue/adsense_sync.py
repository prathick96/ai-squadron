"""
packages/revenue/adsense_sync.py
AdSense revenue ingestion stub.
Wire YouTube Analytics + AdSense Management API in Phase 2 Week 8.
"""
from __future__ import annotations

import logging
import os
from datetime import date

from packages.revenue import store

log = logging.getLogger(__name__)


def sync_adsense() -> dict:
    """
    Phase Day 2: manual/demo path only.
  Set ADSENSE_REPORT_CSV_PATH to import a monthly CSV export.
    """
    csv_path = os.getenv("ADSENSE_REPORT_CSV_PATH", "")
    if csv_path and os.path.isfile(csv_path):
        return _import_csv(csv_path)

    log.info("[adsense_sync] No CSV configured — demo row for media ventures")
    period_end = date.today()
    period_start = period_end.replace(day=1)
    rows = 0
    for v in store.list_ventures():
        if v.get("venture_type") != "MEDIA_CHANNEL":
            continue
        store.upsert_ledger_row({
            "venture_id": v["venture_id"],
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "revenue_source": "ADSENSE",
            "amount_usd": 0.0,
            "burn_usd": 0,
        })
        rows += 1

    store.log_sync_run("ADSENSE", "SUCCESS", rows)
    return {"status": "SUCCESS", "rows_upserted": rows, "mode": "demo"}


def _import_csv(path: str) -> dict:
    import csv

    rows = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vid = row.get("venture_id") or row.get("ventureId")
            if not vid:
                continue
            store.upsert_ledger_row({
                "venture_id": vid,
                "period_start": row.get("period_start", date.today().replace(day=1).isoformat()),
                "period_end": row.get("period_end", date.today().isoformat()),
                "revenue_source": "ADSENSE",
                "amount_usd": float(row.get("amount_usd", 0)),
                "burn_usd": float(row.get("burn_usd", 0)),
            })
            rows += 1
    store.log_sync_run("ADSENSE", "SUCCESS", rows)
    return {"status": "SUCCESS", "rows_upserted": rows, "mode": "csv"}
