"""
apps/api/main.py
Command Center API — read-only dashboard + manual review actions.

Run: uvicorn apps.api.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.api.data.mock_dashboard import (
    agent_grid,
    portfolio_slots,
    revenue_plan,
    revenue_summary,
    security_alerts,
    trend_heatmap,
)
from apps.api.data.revenue_dashboard import (
    live_confidence,
    live_revenue_plan,
    live_revenue_summary,
)

log = logging.getLogger("squadron.api")

app = FastAPI(
    title="AI Squadron Command Center API",
    version="0.2.0",
    description="Agent health, revenue truth, confidence forecasts, manual review queue.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


class ReviewResolveBody(BaseModel):
    status: str  # APPROVED | REJECTED | DEFERRED
    notes: str = ""


def _try_supabase_agents() -> list[dict] | None:
    try:
        from packages.db.pipeline import fetch_recent_agent_logs

        rows = fetch_recent_agent_logs(50)
        return rows if rows else None
    except Exception as exc:
        log.debug("Supabase agent_logs unavailable: %s", exc)
    return None


def _portfolio_from_supabase() -> dict | None:
    from packages.db.pipeline import fetch_ventures_for_portfolio

    ventures = fetch_ventures_for_portfolio(450)
    if not ventures:
        return None
    slots = []
    for i, v in enumerate(ventures):
        slots.append({
            "slot": i + 1,
            "venture_id": v.get("venture_id"),
            "status": v.get("status", "IDEATION"),
            "niche": v.get("niche", ""),
            "mrr_usd": 0.0,
        })
    while len(slots) < 450:
        slots.append({
            "slot": len(slots) + 1,
            "venture_id": None,
            "status": "IDEATION",
            "niche": "",
            "mrr_usd": 0.0,
        })
    live = sum(1 for s in slots if s["status"] in ("LIVE", "SCALING"))
    return {"total_slots": 450, "live_count": live, "slots": slots, "source": "supabase"}


def _revenue_payload() -> tuple[dict, str]:
    live = live_revenue_summary()
    if live:
        return live, "ledger"
    return revenue_summary(), "mock"


@app.get("/api/health")
def health() -> dict:
    from packages.revenue.store import is_local_mode

    return {
        "status": "ok",
        "service": "command-center-api",
        "version": "0.2.0",
        "storage": "local_json" if is_local_mode() else "supabase",
    }


@app.get("/api/agents")
def get_agents() -> dict:
    live = _try_supabase_agents()
    agents = live if live else agent_grid()
    return {"agents": agents, "source": "supabase" if live else "mock"}


@app.get("/api/revenue")
def get_revenue() -> dict:
    payload, source = _revenue_payload()
    return {**payload, "source": source}


@app.get("/api/revenue/plan")
def get_revenue_plan() -> dict:
    try:
        return live_revenue_plan()
    except Exception:
        return revenue_plan()


@app.get("/api/confidence")
def get_confidence() -> dict:
    try:
        report = live_confidence()
        return {**report, "source": "computed"}
    except Exception as exc:
        log.warning("confidence fallback: %s", exc)
        return {
            "confidence_score": 0,
            "confidence_tier": "LOW",
            "forecast_p10_mrr_12mo": 0,
            "forecast_p50_mrr_12mo": 300,
            "forecast_p90_mrr_12mo": 3000,
            "leading_indicators": {},
            "recommended_actions": ["Run: python apps/revenue-engine/main.py --mode once"],
            "source": "fallback",
        }


@app.get("/api/scorecards")
def get_scorecards() -> dict:
    from packages.revenue.store import list_scorecards

    cards = list_scorecards()
    return {"scorecards": cards, "count": len(cards)}


@app.get("/api/manual-review")
def get_manual_review(status: str | None = "PENDING") -> dict:
    from packages.revenue.store import list_manual_reviews

    items = list_manual_reviews(status=status)
    return {"items": items, "count": len(items)}


@app.patch("/api/manual-review/{review_id}")
def resolve_review(review_id: str, body: ReviewResolveBody) -> dict:
    from packages.revenue.store import resolve_manual_review

    if body.status not in ("APPROVED", "REJECTED", "DEFERRED"):
        raise HTTPException(400, "status must be APPROVED, REJECTED, or DEFERRED")
    ok = resolve_manual_review(review_id, body.status, body.notes)
    if not ok:
        raise HTTPException(404, "Review item not found")
    return {"ok": True, "review_id": review_id, "status": body.status}


@app.post("/api/revenue/run-cycle")
async def trigger_cycle() -> dict:
    """Trigger Day 2 revenue cycle on demand (dev convenience)."""
    from packages.revenue.cycle import run_day2_cycle

    return await run_day2_cycle()


@app.get("/api/portfolio")
def get_portfolio() -> dict:
    live_data = _portfolio_from_supabase()
    if live_data:
        return live_data
    slots = portfolio_slots()
    live = sum(1 for s in slots if s["status"] == "LIVE")
    return {"total_slots": len(slots), "live_count": live, "slots": slots, "source": "mock"}


@app.get("/api/trends")
def get_trends() -> dict:
    return trend_heatmap()


@app.get("/api/security/alerts")
def get_security_alerts() -> dict:
    return {"alerts": security_alerts()}


@app.websocket("/api/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            rev, _ = _revenue_payload()
            try:
                conf = live_confidence()
                confidence_score = conf.get("confidence_score", 0)
            except Exception:
                confidence_score = 0
            payload = {
                "type": "tick",
                "revenue": rev,
                "confidence_score": confidence_score,
                "agents_running": sum(1 for a in agent_grid() if a["status"] == "RUNNING"),
            }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        log.debug("WebSocket client disconnected")
