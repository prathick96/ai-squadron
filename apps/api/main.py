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
    version="0.5.0",
    description="Agent health, revenue truth, confidence forecasts, manual review queue, pipeline control.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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
    from packages.db.client import upsert_venture
    from packages.db.pipeline import begin_pipeline_run, complete_pipeline_run, persist_event_log

    run_id = state["run_id"]
    venture_id = state["venture_id"]

    # Upsert venture row BEFORE pipeline_runs (FK constraint requires it to exist first).
    try:
        upsert_venture({
            "venture_id": venture_id,
            "venture_type": "MICRO_SAAS",
            "niche": "pending",
            "status": "DEVELOPMENT",
        })
    except Exception as exc:
        log.debug("[PIPELINE_BG] venture pre-upsert skipped: %s", exc)

    final_state: dict = dict(state)

    try:
        begin_pipeline_run(run_id, venture_id, department)
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
        if not rows:
            return None
        # Rows are ordered newest-first; keep only the most recent entry per agent_name.
        seen: dict[str, dict] = {}
        for row in rows:
            name = row.get("agent_name", "")
            if name and name not in seen:
                seen[name] = row
        return list(seen.values()) if seen else None
    except Exception as exc:
        log.debug("Supabase agent_logs unavailable: %s", exc)
    return None


def _portfolio_from_supabase() -> dict | None:
    from packages.db.pipeline import fetch_ventures_for_portfolio
    all_ventures = fetch_ventures_for_portfolio(450)
    if not all_ventures:
        return None
    ventures = [v for v in all_ventures if v.get("status") != "KILLED"]
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
        "version": "0.5.0",
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
    try:
        payload, source = _revenue_payload()
        return {**payload, "source": source}
    except Exception as exc:
        log.warning("[API] /api/revenue failed (%s) — returning mock", exc)
        return {**revenue_summary(), "source": "mock"}


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


@app.get("/api/ventures")
def list_all_ventures() -> dict:
    """List all ventures (non-killed) for the management panel."""
    from packages.revenue.store import list_ventures
    ventures = list_ventures()
    return {"ventures": ventures, "count": len(ventures)}


@app.delete("/api/ventures/{venture_id}")
def kill_venture_endpoint(venture_id: str) -> dict:
    """
    Soft-delete a venture by setting its status to KILLED.
    Blocked (409) if the venture has any revenue in the ledger.
    """
    from packages.revenue.store import is_local_mode, venture_has_revenue_local, kill_venture_local
    from packages.db.pipeline import venture_has_revenue, kill_venture

    if is_local_mode():
        if venture_has_revenue_local(venture_id):
            raise HTTPException(409, "Venture is generating revenue — cannot kill")
        kill_venture_local(venture_id)
    else:
        if venture_has_revenue(venture_id):
            raise HTTPException(409, "Venture is generating revenue — cannot kill")
        if not kill_venture(venture_id):
            raise HTTPException(500, "Kill failed — DB write error")
    return {"ok": True, "venture_id": venture_id, "status": "KILLED"}


# ---------------------------------------------------------------------------
# Build inspection — see and download generated SaaS code
# ---------------------------------------------------------------------------

@app.get("/api/builds/{venture_id}")
def get_build_files(venture_id: str) -> dict:
    """
    List generated SaaS source files for a venture.

    Source priority:
      1. /tmp/squadron-builds/{venture_id}/ — available immediately after run
      2. Supabase build_artifacts table      — survives Railway redeploys

    Each entry has path, size_bytes, and a 300-char preview.
    node_modules and dist/ are excluded from the listing.
    """
    import os as _bos
    from pathlib import Path as _P
    builds_root = _P(_bos.getenv("BUILDS_DIR", "/tmp/squadron-builds"))
    build_dir   = builds_root / venture_id

    source = "disk"
    files: list[dict] = []
    total_bytes = 0
    dist_exists = False
    dist_kb = 0.0

    # ── Priority 1: local disk (fast, current deployment only) ──────────────
    if build_dir.is_dir():
        for f in sorted(build_dir.rglob("*")):
            if not f.is_file():
                continue
            if "node_modules" in f.parts or ".git" in f.parts or "dist" in f.parts:
                continue
            rel  = f.relative_to(build_dir).as_posix()
            size = f.stat().st_size
            total_bytes += size
            try:
                preview = f.read_text(encoding="utf-8", errors="replace")[:300]
            except Exception:
                preview = ""
            files.append({"path": rel, "size_bytes": size, "preview": preview})

        dist_dir = build_dir / "dist"
        dist_exists = dist_dir.is_dir()
        if dist_exists:
            dist_kb = round(sum(f.stat().st_size for f in dist_dir.rglob("*") if f.is_file()) / 1024, 1)

    # ── Priority 2: Supabase build_artifacts (survives redeploys) ───────────
    if not files:
        try:
            from packages.db.pipeline import fetch_build_artifact
            artifact = fetch_build_artifact(venture_id)
            if artifact and artifact.get("files"):
                source = "supabase"
                raw_files = artifact["files"]
                for f in raw_files:
                    content = f.get("content", "")
                    size    = len(content.encode())
                    total_bytes += size
                    files.append({
                        "path":       f.get("path", ""),
                        "size_bytes": size,
                        "preview":    content[:300],
                    })
        except Exception as exc:
            log.warning("[API] fetch_build_artifact failed: %s", exc)

    if not files:
        raise HTTPException(
            404,
            f"No build found for {venture_id}. "
            "Run a PRODUCT pipeline first — files persist to Supabase going forward.",
        )

    return {
        "venture_id":  venture_id,
        "source":      source,       # "disk" | "supabase"
        "file_count":  len(files),
        "total_kb":    round(total_bytes / 1024, 1),
        "dist_exists": dist_exists,
        "dist_kb":     dist_kb,
        "validate": {
            "download_zip":  f"/api/builds/{venture_id}/download",
            "local_run":     "unzip then: npm install && npm run dev → http://localhost:5173",
            "local_build":   "npm run build && npx serve dist",
        },
        "files": files,
    }


@app.get("/api/builds/{venture_id}/file")
def get_build_file(venture_id: str, path: str) -> dict:
    """Full content of a single generated file. ?path=src/App.tsx"""
    import os as _bos
    from pathlib import Path as _P
    builds_root = _P(_bos.getenv("BUILDS_DIR", "/tmp/squadron-builds"))
    target = (builds_root / venture_id / path).resolve()
    guard  = (builds_root / venture_id).resolve()

    if not str(target).startswith(str(guard)):
        raise HTTPException(400, "Invalid path — directory traversal blocked")
    if "node_modules" in target.parts:
        raise HTTPException(400, "node_modules not served")
    if not target.is_file():
        raise HTTPException(404, f"File not found: {path}")

    content = target.read_text(encoding="utf-8", errors="replace")
    return {"venture_id": venture_id, "path": path,
            "size_bytes": target.stat().st_size, "content": content}


@app.get("/api/builds/{venture_id}/download")
def download_build(venture_id: str):
    """
    Download all source files as a ZIP (no node_modules/dist).
    Falls back to Supabase build_artifacts if disk files are gone.
    Unzip and run: npm install && npm run dev
    """
    import io
    import os as _bos
    import zipfile
    from pathlib import Path as _P
    from fastapi.responses import StreamingResponse

    builds_root = _P(_bos.getenv("BUILDS_DIR", "/tmp/squadron-builds"))
    build_dir   = builds_root / venture_id

    buf = io.BytesIO()

    if build_dir.is_dir():
        # Build from disk
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(build_dir.rglob("*")):
                if not f.is_file():
                    continue
                if "node_modules" in f.parts or ".git" in f.parts:
                    continue
                zf.write(f, arcname=f.relative_to(build_dir))
    else:
        # Fall back to Supabase
        try:
            from packages.db.pipeline import fetch_build_artifact
            artifact = fetch_build_artifact(venture_id)
            if not artifact or not artifact.get("files"):
                raise HTTPException(404, f"No build found for {venture_id}. Run a PRODUCT pipeline first.")
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in artifact["files"]:
                    path    = f.get("path", "unnamed.txt")
                    content = f.get("content", "").encode()
                    zf.writestr(path, content)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(500, f"Build retrieval failed: {exc}") from exc

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{venture_id}.zip"'},
    )


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
    """List the 50 most recent pipeline runs (newest first), merging memory + Supabase history."""
    # In-memory registry: live runs + recent from the current process
    runs_by_id: dict[str, dict] = {
        r.run_id: _run_to_dict(r) for r in registry.list_recent(50)
    }

    # Supabase: persistent history that survives server restarts
    try:
        from packages.db.pipeline import fetch_pipeline_runs
        for row in fetch_pipeline_runs(50):
            run_id = row.get("run_id", "")
            if not run_id or run_id in runs_by_id:
                continue  # live record takes priority
            runs_by_id[run_id] = {
                "run_id": run_id,
                "venture_id": row.get("venture_id", ""),
                "department": row.get("department", "PRODUCT"),
                "status": row.get("status", "COMPLETED"),
                "current_stage": row.get("pipeline_stage", "END"),
                "started_at": row.get("started_at", ""),
                "updated_at": row.get("completed_at") or row.get("started_at", ""),
                "completed_at": row.get("completed_at"),
                "event_count": 0,
                "recent_events": [],
                "last_error": row.get("error_message"),
            }
    except Exception as exc:
        log.debug("[pipeline] Supabase history unavailable: %s", exc)

    runs = sorted(runs_by_id.values(), key=lambda r: r.get("started_at", ""), reverse=True)[:50]
    return {"runs": runs, "count": len(runs)}


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
# Favicon — return empty icon to silence browser 404 noise
# ---------------------------------------------------------------------------

from fastapi.responses import Response  # noqa: E402

@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(content=b"", media_type="image/x-icon")


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
