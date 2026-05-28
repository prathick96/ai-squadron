"""
tests/test_revenue_ledger.py
Week 8 — Revenue ledger API and store tests.

Run: pytest tests/test_revenue_ledger.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.revenue.store import _save_local

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    store_file = tmp_path / "day2_store.json"
    monkeypatch.setattr("packages.revenue.store._STORE_PATH", store_file)
    _save_local({
        "ventures": [{"venture_id": "ven_ledger_test", "venture_type": "MICRO_SAAS",
                       "niche": "test", "status": "LIVE", "created_at": "2026-01-01T00:00:00+00:00"}],
        "revenue_ledger": [],
        "venture_scorecards": [],
        "confidence_reports": [],
        "manual_review_queue": [],
        "qa_reports": [],
        "revenue_sync_runs": [],
    })
    yield store_file


# ---------------------------------------------------------------------------
# GET /api/revenue/ledger
# ---------------------------------------------------------------------------

def test_get_ledger_empty():
    resp = client.get("/api/revenue/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entries"] == []
    assert body["count"] == 0


# ---------------------------------------------------------------------------
# POST /api/revenue/ledger
# ---------------------------------------------------------------------------

def test_post_ledger_manual_entry():
    payload = {
        "venture_id": "ven_ledger_test",
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "revenue_source": "MANUAL",
        "amount_usd": 120.0,
        "burn_usd": 20.0,
        "notes": "PayPal payment May",
    }
    resp = client.post("/api/revenue/ledger", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    entry = body["entry"]
    assert entry["venture_id"] == "ven_ledger_test"
    assert entry["amount_usd"] == 120.0
    assert entry["revenue_source"] == "MANUAL"
    assert entry["notes"] == "PayPal payment May"


def test_post_ledger_entry_appears_in_get():
    payload = {
        "venture_id": "ven_ledger_test",
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "revenue_source": "STRIPE",
        "amount_usd": 99.0,
        "burn_usd": 0.0,
        "notes": "",
    }
    client.post("/api/revenue/ledger", json=payload)
    resp = client.get("/api/revenue/ledger")
    body = resp.json()
    assert body["count"] == 1
    assert body["entries"][0]["amount_usd"] == 99.0


def test_post_ledger_upsert_same_key():
    """Posting the same (venture_id, period_start, revenue_source) twice should overwrite."""
    base = {
        "venture_id": "ven_ledger_test",
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "revenue_source": "ADSENSE",
        "burn_usd": 0.0,
        "notes": "",
    }
    client.post("/api/revenue/ledger", json={**base, "amount_usd": 50.0})
    client.post("/api/revenue/ledger", json={**base, "amount_usd": 75.0})

    resp = client.get("/api/revenue/ledger")
    body = resp.json()
    assert body["count"] == 1
    assert body["entries"][0]["amount_usd"] == 75.0


def test_post_ledger_invalid_source():
    payload = {
        "venture_id": "ven_ledger_test",
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "revenue_source": "PAYPAL",  # not in Literal
        "amount_usd": 10.0,
        "burn_usd": 0.0,
        "notes": "",
    }
    resp = client.post("/api/revenue/ledger", json=payload)
    assert resp.status_code == 422


def test_get_ledger_venture_filter():
    for vid in ("ven_a", "ven_b"):
        client.post("/api/revenue/ledger", json={
            "venture_id": vid,
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "revenue_source": "MANUAL",
            "amount_usd": 10.0,
            "burn_usd": 0.0,
            "notes": "",
        })

    resp = client.get("/api/revenue/ledger?venture_id=ven_a")
    body = resp.json()
    assert body["count"] == 1
    assert body["entries"][0]["venture_id"] == "ven_a"


def test_post_ledger_zero_amount_allowed():
    payload = {
        "venture_id": "ven_ledger_test",
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "revenue_source": "MANUAL",
        "amount_usd": 0.0,
        "burn_usd": 5.0,
        "notes": "burn-only month",
    }
    resp = client.post("/api/revenue/ledger", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# Store-level upsert conflict test
# ---------------------------------------------------------------------------

def test_upsert_ledger_row_on_conflict_local():
    from packages.revenue.store import list_ledger, upsert_ledger_row

    row = {
        "venture_id": "ven_conflict",
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "revenue_source": "STRIPE",
        "amount_usd": 100.0,
        "burn_usd": 0.0,
        "notes": "",
    }
    upsert_ledger_row(row)
    upsert_ledger_row({**row, "amount_usd": 200.0})
    entries = [e for e in list_ledger() if e["venture_id"] == "ven_conflict"]
    assert len(entries) == 1
    assert entries[0]["amount_usd"] == 200.0
