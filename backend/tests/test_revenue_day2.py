"""
tests/test_revenue_day2.py
Day 2 revenue cycle, scorecards, and confidence report tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.revenue.confidence import build_confidence_report
from packages.revenue.cycle import run_day2_cycle
from packages.revenue.scorecard import build_venture_scorecards
from packages.revenue.store import _STORE_PATH, _load_local, _save_local, is_local_mode


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Use temp JSON store for each test."""
    store_file = tmp_path / "day2_store.json"
    monkeypatch.setattr("packages.revenue.store._STORE_PATH", store_file)
    _save_local({
        "ventures": [
            {
                "venture_id": "ven_test_001",
                "venture_type": "MICRO_SAAS",
                "niche": "test niche",
                "status": "DEVELOPMENT",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        ],
        "revenue_ledger": [],
        "venture_scorecards": [],
        "confidence_reports": [],
        "manual_review_queue": [],
        "qa_reports": [
            {"venture_id": "ven_test_001", "is_passed": True},
            {"venture_id": "ven_test_001", "is_passed": False},
        ],
        "revenue_sync_runs": [],
    })
    yield store_file


def test_local_store_mode():
    assert is_local_mode() is True


@pytest.mark.asyncio
async def test_day2_cycle_runs(isolated_store):
    result = await run_day2_cycle()
    assert result["storage_mode"] == "local"
    assert "confidence_report" in result
    assert result["confidence_report"]["confidence_score"] >= 0
    assert isolated_store.exists()


def test_scorecard_signals():
    from packages.revenue.store import upsert_ledger_row
    from datetime import date

    today = date.today()
    upsert_ledger_row({
        "venture_id": "ven_test_001",
        "period_start": today.replace(day=1).isoformat(),
        "period_end": today.isoformat(),
        "revenue_source": "STRIPE",
        "amount_usd": 250.0,
        "burn_usd": 50.0,
    })
    cards = build_venture_scorecards()
    assert len(cards) >= 1
    assert cards[0]["signal"] == "SCALE"


def test_confidence_forecast_bands():
    scorecards = [{"qa_first_pass_rate_pct": 50, "signal": "HOLD", "venture_id": "v1"}]
    portfolio = [{"venture_id": "v1", "mrr_usd": 100, "burn_usd": 40, "days_live": 60, "status": "LIVE"}]
    report = build_confidence_report(scorecards, portfolio)
    assert report["forecast_p10_mrr_12mo"] <= report["forecast_p50_mrr_12mo"]
    assert report["forecast_p50_mrr_12mo"] <= report["forecast_p90_mrr_12mo"]
    assert report["confidence_tier"] in ("LOW", "MEDIUM", "HIGH")


def test_manual_review_enqueue():
    from packages.revenue.store import enqueue_manual_review, list_manual_reviews

    enqueue_manual_review({
        "id": "rev-1",
        "venture_id": "ven_test_001",
        "run_id": "run-1",
        "review_reason": "QA exhausted",
        "artifact_type": "BUILD",
    })
    pending = list_manual_reviews(status="PENDING")
    assert len(pending) == 1
