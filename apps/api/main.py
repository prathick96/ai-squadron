"""
apps/api/main.py
Command Center API — read-only dashboard + manual review actions + pipeline trigger.

Run: uvicorn apps.api.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
from packages.orchestrator.runner import RunRecord, registry

log = logging.getLogger("squadron.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    if os.getenv("ENVIRONMENT") == "production":
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from packages.revenue.cycle import run_day2_cycle

            scheduler = AsyncIOScheduler(timezone="UTC")
            scheduler.add_job(run_day2_cycle, "cron", hour=0, minute=0,
                              id="revenue_cycle", replace_existing=True)
            scheduler.add_job(run_day2_cycle, "cron", day_of_week="mon", hour=8, minute=0,
                              id="confidence_weekly", replace_existing=True)
            scheduler.start()
            log.info("Revenue Engine scheduler started (daily 00:00 UTC + Monday 08:00 UTC)")
        except ImportError:
            log.warning("APScheduler not installed — revenue scheduler not started")
    yield
    if scheduler:
        scheduler.shutdown()
        log.info("Revenue Engine scheduler stopped")


app = FastAPI(
    title="AI Squadron Command Center API",
    version="0.4.0",
    description="Agent health, revenue truth, confidence forecasts, manual review queue, pipeline control.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ReviewResolveBody(BaseModel):
    status: str  # APPROVED | REJECTED | DEFERRED
    notes: str = ""


class PipelineRunBody(BaseModel):
    department: Literal["PRODUCT", "MEDIA", "AUTO"] = "AUTO"
    venture_id: str | None = None


class LedgerEntryBody(BaseModel):
    venture_id: str
    period_start: str  # YYYY-MM-DD
    period_end: str    # YYYY-MM-DD
    revenue_source: Literal["STRIPE", "ADSENSE", "MANUAL"]
    amount_usd: float
    burn_usd: float = 0.0
    notes: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_to_dict(rec: RunRecord) -> dict:
    return {
        "run_id": rec.run_id,
        "venture_id": rec.venture_id,
        "department": rec.department,
        "status": rec.status,
        "current_stage": rec.current_stage,
        "started_at": rec.started_at,
        "updated_at": rec.updated_at,
        "completed_at": rec.completed_at,
        "event_count": len(rec.recent_events),
        "recent_events": rec.recent_events[-5:],
        "last_error": rec.last_error,
    }


async def _run_pipeline_background(state: dict, department: str) -> None:
    """Background task: stream the full pipeline and push updates to the registry."""
    from apps.orchestrator.graph import build_squadron_graph
    from packages.db.pipeline import begin_pipeline_run, complete_pipeline_run, persist_event_log

    run_id = state["run_id"]
    venture_id = state["venture_id"]

    begin_pipeline_run(run_id, venture_id)
    final_state: dict = dict(state)

    try:
        graph = build_squadron_graph(department)

        # Stream node-by-node: each chunk is {node_name: state_updates}
        async for chunk in graph.astream(state, stream_mode="updates"):
            for node_name, updates in (chunk or {}).items():
                if isinstance(node_name, str) and not node_name.startswith("__"):
                    registry.update_stage(run_id, node_name)
                    if isinstance(updates, dict):
                        final_state.update(updates)

        stage = final_state.get("pipeline_stage", "END")
        error = final_state.get("last_error")
        if stage == "MANUAL_REVIEW":
            status = "MANUAL_REVIEW"
        elif error:
            status = "FAILED"
        else:
            status = "COMPLETED"

        for event in (final_state.get("event_log") or [])[-10:]:
            registry.append_event(run_id, event)

        registry.complete(run_id, stage, status, error)
        persist_event_log(final_state)
        complete_pipeline_run(run_id, venture_id, stage, status, error)

    except Exception as exc:
        log.exception("[PIPELINE_BG] run_id=%s failed: %s", run_id, exc)
        registry.complete(run_id, "FAILED", "FAILED", str(exc))
        from packages.db.pipeline import complete_pipeline_run as _cp
        _cp(run_id, venture_id, "FAILED", "FAILED", str(exc))


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


# ---------------------------------------------------------------------------
# Dashboard endpoints (unchanged from Week 4)
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    # Wrapped in try/except: a broken optional import must never turn the
    # health endpoint into a 500, which would trigger Railway's restart loop.
    try:
        from packages.revenue.store import is_local_mode
        storage = "local_json" if is_local_mode() else "supabase"
    except Exception:
        storage = "unknown"
    try:
        active = registry.active_count()
    except Exception:
        active = 0
    return {
        "status": "ok",
        "service": "command-center-api",
        "version": "0.4.0",
        "storage": storage,
        "active_pipeline_runs": active,
    }


@app.get("/api/agents")
def get_agents() -> dict:
    from packages.db.client import is_supabase_connected
    live = _try_supabase_agents()
    if live:
        return {"agents": live, "source": "supabase"}
    # Supabase connected but agent_logs is empty (no pipeline runs yet)
    source = "supabase_empty" if is_supabase_connected() else "mock"
    return {"agents": agent_grid(), "source": source}


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
    from packages.revenue.cycle import run_day2_cycle
    return await run_day2_cycle()


@app.get("/api/revenue/ledger")
def get_ledger(venture_id: str | None = None) -> dict:
    from packages.revenue.store import list_ledger
    entries = list_ledger()
    if venture_id:
        entries = [e for e in entries if e.get("venture_id") == venture_id]
    return {"entries": entries, "count": len(entries)}


@app.post("/api/revenue/ledger")
def add_ledger_entry(body: LedgerEntryBody) -> dict:
    from packages.revenue.store import upsert_ledger_row
    row = {
        "venture_id": body.venture_id,
        "period_start": body.period_start,
        "period_end": body.period_end,
        "revenue_source": body.revenue_source,
        "amount_usd": body.amount_usd,
        "burn_usd": body.burn_usd,
        "notes": body.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    upsert_ledger_row(row)
    return {"ok": True, "entry": row}


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


# ---------------------------------------------------------------------------
# Pipeline control endpoints (Week 5)
# ---------------------------------------------------------------------------

@app.post("/api/pipeline/run")
async def trigger_pipeline(body: PipelineRunBody, background_tasks: BackgroundTasks) -> dict:
    """
    Launch a full pipeline run asynchronously.
    Returns immediately with {run_id, venture_id, status: "STARTED"}.
    Poll GET /api/pipeline/{run_id} for live status.
    """
    from packages.state.agent_state import init_state

    state = init_state(body.venture_id)
    run_id = state["run_id"]
    venture_id = state["venture_id"]

    registry.start(run_id, venture_id, body.department)
    background_tasks.add_task(_run_pipeline_background, state, body.department)

    log.info("[PIPELINE_API] Launched run_id=%s venture_id=%s dept=%s",
             run_id, venture_id, body.department)
    return {"run_id": run_id, "venture_id": venture_id, "status": "STARTED"}


@app.get("/api/pipeline/recent")
def get_recent_pipelines() -> dict:
    """List the 20 most recent pipeline runs (newest first)."""
    runs = registry.list_recent(20)
    return {"runs": [_run_to_dict(r) for r in runs], "count": len(runs)}


@app.get("/api/pipeline/{run_id}")
def get_pipeline_status(run_id: str) -> dict:
    """Return live status for a specific pipeline run."""
    rec = registry.get(run_id)
    if rec is None:
        raise HTTPException(404, f"Run '{run_id}' not found (may have expired after restart)")
    return _run_to_dict(rec)


# ---------------------------------------------------------------------------
# WebSocket — live ticker (updated in Week 5 to include pipeline state)
# ---------------------------------------------------------------------------

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

            active_runs = [
                {
                    "run_id": r.run_id,
                    "venture_id": r.venture_id,
                    "department": r.department,
                    "stage": r.current_stage,
                    "status": r.status,
                }
                for r in registry.list_recent(5)
                if r.status in ("STARTED", "RUNNING")
            ]

            payload = {
                "type": "tick",
                "revenue": rev,
                "confidence_score": confidence_score,
                "agents_running": sum(1 for a in agent_grid() if a["status"] == "RUNNING"),
                "active_pipeline_runs": active_runs,
            }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        log.debug("WebSocket client disconnected")


# ---------------------------------------------------------------------------
# SPA static file serving (Week 7)
# Registered LAST so API routes always take priority.
# Only activates when frontend/dist exists (i.e. after `npm run build`).
# In local dev, Vite runs separately on port 5173.
# ---------------------------------------------------------------------------

_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    _assets = _dist / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="static-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        candidate = _dist / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_dist / "index.html"))
