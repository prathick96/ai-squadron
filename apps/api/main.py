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
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
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
    # Pre-warm the in-memory cache so the first Command Center load is instant.
    # Uses mock data — the real Supabase data populates on the first 60s TTL expiry.
    async def _prewarm():
        await asyncio.sleep(3)   # let DB pool settle first
        try:
            _cached("agents",       _CACHE_TTL, lambda: {"agents": agent_grid(),      "source": "mock"})
            _cached("revenue",      _CACHE_TTL, lambda: {**revenue_summary(),         "source": "mock"})
            _cached("trends",       _CACHE_TTL, trend_heatmap)
            _cached("security",     _CACHE_TTL, lambda: {"alerts": security_alerts()})
            _cached("revenue_plan", _CACHE_TTL, revenue_plan)
            log.info("[PREWARM] Cache warm — Command Center first load is now instant")
        except Exception as exc:
            log.debug("[PREWARM] skipped: %s", exc)
    asyncio.create_task(_prewarm())
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


async def _run_pipeline_background(state: dict, department: str, user_id: str | None = None) -> None:
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
        begin_pipeline_run(run_id, venture_id, department, user_id=user_id)
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
    """
    Build the agent health grid with REAL success_ratio computed server-side.

    The NaN% bug: the frontend received `success_ratio: undefined` because the
    raw agent_logs rows don't have an aggregated ratio field.  We now compute it
    here: for each agent, count SUCCESS vs total over the last 20 runs.
    """
    try:
        from packages.db.pipeline import fetch_recent_agent_logs
        rows = fetch_recent_agent_logs(200)   # more rows so we can compute ratios
        if not rows:
            return None

        # Aggregate per agent_name over the last 20 runs each
        from collections import defaultdict
        agent_runs: dict[str, list[str]] = defaultdict(list)
        agent_latest: dict[str, dict]    = {}

        for row in rows:
            name   = row.get("agent_name", "")
            status = row.get("status", "")
            if not name:
                continue
            if name not in agent_latest:
                agent_latest[name] = row   # newest row first
            if len(agent_runs[name]) < 20:
                agent_runs[name].append(status)

        result = []
        for name, latest in agent_latest.items():
            statuses     = agent_runs[name]
            total        = len(statuses)
            successes    = sum(1 for s in statuses if s == "SUCCESS")
            ratio        = round(successes / total, 3) if total > 0 else 0.0

            result.append({
                **latest,
                "success_ratio":  ratio,        # 0.0–1.0  — frontend multiplies by 100
                "tokens_used":    latest.get("tokens_used", 0) or 0,
                "latency_ms":     latest.get("latency_ms", 0)  or 0,
                "retry_count":    latest.get("retry_count", 0) or 0,
                "current_task":   latest.get("current_task", "") or "",
            })

        return result or None
    except Exception as exc:
        log.debug("Supabase agent_logs unavailable: %s", exc)
    return None


def _portfolio_from_supabase() -> dict | None:
    from packages.db.pipeline import fetch_ventures_for_portfolio
    all_ventures = fetch_ventures_for_portfolio(50)
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
    # Show live ventures + 10 empty slots max (previously padded to 450 — too slow)
    target = max(10, len(slots) + 10)
    while len(slots) < target:
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
# Simple TTL cache — avoids hammering Supabase on every 8s poll tick.
# Heavy endpoints (confidence, portfolio, trends) are cached for 30 seconds.
# The registry (live runs) is never cached — it's in-memory and instant.
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 60.0   # seconds — raised from 30s; agents/revenue now also cached


def _cached(key: str, ttl: float, fn):
    """Return cached value or recompute. Thread-safe via GIL for CPython."""
    now = _time.monotonic()
    if key in _cache:
        ts, val = _cache[key]
        if now - ts < ttl:
            return val
    val = fn()
    _cache[key] = (now, val)
    return val


# ---------------------------------------------------------------------------
# Dashboard endpoints (unchanged from Week 4)
# ---------------------------------------------------------------------------

def _railway_ok() -> bool:
    try:
        from packages.tools.railway_client import railway_available
        return railway_available()
    except Exception:
        return False


def _vercel_ok() -> bool:
    try:
        from packages.tools.vercel_client import vercel_available
        return vercel_available()
    except Exception:
        return False


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
        "status":               "ok",
        "service":              "command-center-api",
        "version":              "0.5.0",
        "storage":              storage,
        "active_pipeline_runs": active,
        "railway_available":    _railway_ok(),
        "vercel_available":     _vercel_ok(),
    }


@app.get("/api/agents")
def get_agents() -> dict:
    def _compute():
        from packages.db.client import is_supabase_connected
        live = _try_supabase_agents()
        if live:
            return {"agents": live, "source": "supabase"}
        source = "supabase_empty" if is_supabase_connected() else "mock"
        return {"agents": agent_grid(), "source": source}
    return _cached("agents", _CACHE_TTL, _compute)


@app.get("/api/revenue")
def get_revenue() -> dict:
    def _compute():
        try:
            payload, source = _revenue_payload()
            return {**payload, "source": source}
        except Exception as exc:
            log.warning("[API] /api/revenue failed (%s) — returning mock", exc)
            return {**revenue_summary(), "source": "mock"}
    return _cached("revenue", _CACHE_TTL, _compute)


@app.get("/api/revenue/plan")
def get_revenue_plan() -> dict:
    def _compute():
        try:
            return live_revenue_plan()
        except Exception:
            return revenue_plan()
    return _cached("revenue_plan", _CACHE_TTL, _compute)


@app.get("/api/confidence")
def get_confidence() -> dict:
    def _compute():
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
    return _cached("confidence", _CACHE_TTL, _compute)


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


# ---------------------------------------------------------------------------
# Customer user API — profile, ventures, plan enforcement
# ---------------------------------------------------------------------------

_PLAN_RUN_LIMITS = {"starter": 1, "builder": 10, "studio": -1}  # -1 = unlimited


def _get_user_profile(user_id: str) -> dict | None:
    """Fetch user_profiles row for this Supabase auth user."""
    from packages.db.client import get_db, is_supabase_connected
    if not is_supabase_connected():
        return None
    try:
        result = get_db().table("user_profiles").select("*").eq("id", user_id).single().execute()
        return result.data
    except Exception:
        return None


def _count_user_runs_this_month(user_id: str) -> int:
    """Count non-failed pipeline runs for this user in the current calendar month."""
    from packages.db.client import get_db, is_supabase_connected
    from datetime import date
    if not is_supabase_connected():
        return 0
    try:
        month_start = date.today().replace(day=1).isoformat()
        result = get_db() \
            .table("pipeline_runs") \
            .select("run_id", count="exact") \
            .eq("user_id", user_id) \
            .gte("started_at", month_start) \
            .neq("status", "FAILED") \
            .execute()
        return result.count or 0
    except Exception:
        return 0


@app.get("/api/user/profile")
def get_user_profile(request: Request) -> dict:
    """
    Return the authenticated customer's plan, run usage, and venture summary.
    Reads the Supabase JWT from the Authorization header.
    """
    from supabase import create_client

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Authorization header required")

    jwt = auth_header[7:]

    # Verify JWT and get user_id from Supabase
    try:
        import os as _os
        supa = create_client(
            _os.getenv("SUPABASE_URL", ""),
            _os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        )
        user_resp = supa.auth.get_user(jwt)
        user_id   = user_resp.user.id
        user_email = user_resp.user.email or ""
    except Exception as exc:
        raise HTTPException(401, f"Invalid session: {exc}")

    profile = _get_user_profile(user_id)
    plan    = (profile or {}).get("plan", "starter")
    limit   = _PLAN_RUN_LIMITS.get(plan, 1)
    used    = _count_user_runs_this_month(user_id)

    return {
        "user_id":           user_id,
        "email":             user_email,
        "plan":              plan,
        "runs_used":         used,
        "runs_limit":        limit,
        "runs_remaining":    max(0, limit - used) if limit != -1 else -1,
        "unlimited":         limit == -1,
        "onboarding_done":   (profile or {}).get("onboarding_done", False),
    }


@app.get("/api/user/ventures")
def get_user_ventures(request: Request) -> dict:
    """
    Return this user's pipeline runs (their ventures) with live_url if deployed.
    """
    import os as _os
    from supabase import create_client

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Authorization header required")

    jwt = auth_header[7:]
    try:
        supa      = create_client(_os.getenv("SUPABASE_URL", ""), _os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
        user_resp = supa.auth.get_user(jwt)
        user_id   = user_resp.user.id
    except Exception as exc:
        raise HTTPException(401, f"Invalid session: {exc}")

    from packages.db.client import get_db, is_supabase_connected
    if not is_supabase_connected():
        return {"ventures": [], "count": 0}

    try:
        runs = get_db() \
            .table("pipeline_runs") \
            .select("run_id,venture_id,status,current_stage,started_at,completed_at,department") \
            .eq("user_id", user_id) \
            .order("started_at", desc=True) \
            .limit(20) \
            .execute()

        ventures = []
        for r in (runs.data or []):
            vid = r.get("venture_id", "")
            # Fetch live_url from ventures table
            v_res = get_db().table("ventures").select("niche,live_url,status,venture_type") \
                .eq("venture_id", vid).execute()
            v_data = (v_res.data or [{}])[0]
            ventures.append({
                **r,
                "niche":        v_data.get("niche", ""),
                "live_url":     v_data.get("live_url"),
                "venture_status": v_data.get("status", ""),
                "venture_type": v_data.get("venture_type", "MICRO_SAAS"),
            })

        return {"ventures": ventures, "count": len(ventures)}
    except Exception as exc:
        log.warning("[USER_VENTURES] failed: %s", exc)
        return {"ventures": [], "count": 0}


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


@app.post("/api/webhooks/paddle")
async def paddle_webhook(request: Request) -> dict:
    """
    Paddle webhook handler — updates user_subscriptions when Paddle fires events.
    Events handled: subscription.created, subscription.updated, subscription.cancelled.

    Set in Paddle Dashboard → Notifications → add endpoint:
      https://ai-squadron-production.up.railway.app/api/webhooks/paddle
    """
    import json as _json
    import hmac
    import hashlib

    body = await request.body()
    paddle_sig = request.headers.get("Paddle-Signature", "")
    secret     = os.getenv("PADDLE_WEBHOOK_SECRET", "")

    # Verify signature when secret is set
    if secret and paddle_sig:
        ts_part, h1_part = "", ""
        for part in paddle_sig.split(";"):
            if part.startswith("ts="):
                ts_part = part[3:]
            elif part.startswith("h1="):
                h1_part = part[3:]
        signed  = f"{ts_part}:{body.decode()}"
        expected = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, h1_part):
            raise HTTPException(401, "Invalid Paddle signature")

    try:
        payload  = _json.loads(body)
        evt_type = payload.get("event_type", "")
        data     = payload.get("data", {})

        if evt_type in ("subscription.created", "subscription.updated"):
            _upsert_subscription(data)
        elif evt_type == "subscription.cancelled":
            _cancel_subscription(data)

        return {"ok": True, "event_type": evt_type}
    except Exception as exc:
        log.exception("[WEBHOOK] Paddle webhook error: %s", exc)
        raise HTTPException(500, str(exc))


def _upsert_subscription(data: dict) -> None:
    from packages.db.client import get_db, is_supabase_connected
    if not is_supabase_connected():
        return
    db = get_db()
    custom = data.get("custom_data") or {}
    user_id = custom.get("user_id")  # set this when creating Paddle checkout
    if not user_id:
        return
    plan = custom.get("plan", "builder")
    items = data.get("items", [])
    price_id = items[0]["price"]["id"] if items else None
    billing   = (items[0].get("price", {}).get("billing_cycle", {}).get("interval", "month")) if items else "month"
    try:
        db.table("user_subscriptions").upsert({
            "user_id":               user_id,
            "paddle_subscription_id": data.get("id"),
            "paddle_customer_id":    data.get("customer_id"),
            "plan":                  plan,
            "status":                data.get("status", "active"),
            "price_id":              price_id,
            "billing_interval":      billing,
            "current_period_end":    data.get("current_billing_period", {}).get("ends_at"),
            "cancel_at_period_end":  data.get("scheduled_change", {}).get("action") == "cancel",
        }, on_conflict="paddle_subscription_id").execute()
        # Update the user's plan in their profile
        db.table("user_profiles").update({"plan": plan}).eq("id", user_id).execute()
    except Exception as exc:
        log.warning("[WEBHOOK] upsert_subscription failed: %s", exc)


def _cancel_subscription(data: dict) -> None:
    from packages.db.client import get_db, is_supabase_connected
    if not is_supabase_connected():
        return
    db = get_db()
    try:
        db.table("user_subscriptions").update({
            "status": "cancelled",
            "cancel_at_period_end": True,
        }).eq("paddle_subscription_id", data.get("id")).execute()
    except Exception as exc:
        log.warning("[WEBHOOK] cancel_subscription failed: %s", exc)


@app.post("/api/ventures/{venture_id}/deploy")
async def deploy_venture(venture_id: str) -> dict:
    """
    Deploy a venture's built React app to Railway (primary) or Vercel (fallback).

    Provider priority:
      1. Railway — if RAILWAY_TOKEN is set (MUST be a User Account Token).
                   Get from: railway.app → avatar → Account Settings → Tokens → New Token
                   NOT a Project Token (those return 'Not Authorized').
      2. Vercel  — if VERCEL_TOKEN is set. Zero-config fallback.

    Required Railway Variable:
      RAILWAY_TOKEN = <User Account Token from Account Settings>
    """
    from packages.db.pipeline import fetch_build_artifact
    from packages.tools.railway_client import deploy_to_railway, railway_available
    from packages.tools.vercel_client import deploy_to_vercel, vercel_available
    import os as _os

    builds_root = Path(_os.getenv("BUILDS_DIR", "/tmp/squadron-builds"))
    build_dir   = builds_root / venture_id

    # ── Restore build from Supabase if disk was wiped ──────────────────────
    if not build_dir.is_dir():
        log.info("[DEPLOY] Build not on disk, fetching from Supabase | venture=%s", venture_id)
        artifact = fetch_build_artifact(venture_id)
        if not artifact or not artifact.get("files"):
            raise HTTPException(
                404,
                f"No build found for {venture_id}. "
                "Run a PRODUCT pipeline first."
            )
        build_dir.mkdir(parents=True, exist_ok=True)

        # Write scaffold files first (package.json, vite.config.ts, tsconfig, etc.)
        # These are NOT in Supabase — they come from the hardcoded scaffold dict.
        from packages.agents.product.engineering_team import _SCAFFOLD
        for rel_path, content in _SCAFFOLD.items():
            dest = build_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        log.info("[DEPLOY] Scaffold files written for %s (%d files)", venture_id, len(_SCAFFOLD))

        # Then restore the LLM-generated source files on top
        for f in artifact["files"]:
            fpath = build_dir / f.get("path", "")
            if fpath.name:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(f.get("content", ""), encoding="utf-8")
        log.info("[DEPLOY] Restored %d LLM files from Supabase for %s",
                 len(artifact["files"]), venture_id)

    # ── Also run npm install + vite build if dist/ is missing ──────────────
    dist_dir = build_dir / "dist"
    if not dist_dir.is_dir():
        import asyncio
        import sys
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        log.info("[DEPLOY] Building dist/ for %s...", venture_id)
        try:
            npm_cache = str(builds_root.parent / ".npm-cache")
            proc = await asyncio.create_subprocess_exec(
                npm, "install", "--no-audit", "--no-fund",
                "--cache", npm_cache, "--legacy-peer-deps",
                cwd=str(build_dir), stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=300)
            proc2 = await asyncio.create_subprocess_exec(
                npm, "run", "build", cwd=str(build_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc2.communicate(), timeout=300)
            if proc2.returncode != 0:
                raise RuntimeError(f"vite build failed: {stderr.decode(errors='replace')[-300:]}")
            log.info("[DEPLOY] dist/ built successfully for %s", venture_id)
        except Exception as exc:
            raise HTTPException(500, f"Build step failed: {exc}")

    # ── Deploy — Railway first, Vercel as fallback ─────────────────────────
    url      = ""
    last_err = ""

    if railway_available():
        try:
            log.info("[DEPLOY] Deploying to Railway | venture=%s", venture_id)
            url = await deploy_to_railway(venture_id, build_dir)
            log.info("[DEPLOY] ✓ Railway | url=%s", url)
        except Exception as exc:
            last_err = str(exc)
            log.warning("[DEPLOY] Railway failed (%s) — trying Vercel fallback", exc)

    if not url and vercel_available():
        try:
            log.info("[DEPLOY] Deploying to Vercel (fallback) | venture=%s", venture_id)
            url = await deploy_to_vercel(venture_id, build_dir)
            log.info("[DEPLOY] ✓ Vercel | url=%s", url)
        except Exception as exc:
            last_err = str(exc)
            log.exception("[DEPLOY] Vercel fallback also failed: %s", exc)

    if not url:
        raise HTTPException(
            500,
            f"Deployment failed.\nLast error: {last_err}\n\n"
            "RAILWAY_TOKEN required (User Account Token — NOT a Project Token):\n"
            "  1. railway.app → click your avatar → Account Settings → Tokens\n"
            "  2. New Token → name 'AI Squadron' → Full Access → Create\n"
            "  3. Add RAILWAY_TOKEN=<token> in Railway → your service → Variables\n"
            "  4. Click Launch Product again"
        )

    # ── Persist live_url to Supabase ─────────────────────────────────────────
    try:
        from packages.db.client import get_db, is_supabase_connected
        if is_supabase_connected():
            get_db().table("ventures").update({
                "live_url": url,
                "status":   "LIVE",
            }).eq("venture_id", venture_id).execute()
            log.info("[DEPLOY] ventures.live_url updated | venture=%s", venture_id)
    except Exception as exc:
        log.warning("[DEPLOY] Could not update ventures table: %s", exc)

    return {"ok": True, "url": url, "venture_id": venture_id}


@app.post("/api/ventures/cleanup")
def bulk_cleanup_ventures() -> dict:
    """
    Kill all non-revenue ventures that are IDEATION, stale DEVELOPMENT, or FAILED.
    Keeps: LIVE, SCALING, and any venture with a live_url (deployed product).
    Returns: {killed_count, kept_count, details}
    """
    from packages.db.client import get_db, is_supabase_connected
    from packages.revenue.store import list_ventures

    all_v = list_ventures()
    keep_statuses  = {"LIVE", "SCALING"}
    killed_ids:  list[str] = []
    kept_ids:    list[str] = []

    for v in all_v:
        vid    = v.get("venture_id", "")
        status = v.get("status", "")
        live   = v.get("live_url")

        # Keep anything live or deployed
        if status in keep_statuses or live:
            kept_ids.append(vid)
            continue

        # Kill stale/incomplete ventures
        if status in ("IDEATION", "DEVELOPMENT", "QA", "KILLED") or not v.get("go_decision"):
            killed_ids.append(vid)

    if killed_ids and is_supabase_connected():
        try:
            db = get_db()
            for vid in killed_ids:
                db.table("ventures").update({"status": "KILLED"}).eq("venture_id", vid).execute()
            _cache.pop("portfolio", None)   # invalidate portfolio cache
            log.info("[CLEANUP] Killed %d stale ventures", len(killed_ids))
        except Exception as exc:
            log.warning("[CLEANUP] DB update failed: %s", exc)
    elif killed_ids:
        # Local mode — update in JSON store
        from packages.revenue.store import kill_venture_local
        for vid in killed_ids:
            try:
                kill_venture_local(vid)
            except Exception:
                pass

    return {
        "killed_count": len(killed_ids),
        "kept_count":   len(kept_ids),
        "killed":       killed_ids,
        "kept":         kept_ids,
    }


@app.post("/api/waitlist/{product_id}/join")
async def join_waitlist_post(product_id: str, request: Request) -> dict:
    """
    POST /api/waitlist/{product_id}/join   body: {"email": "..."}
    """
    import re as _re
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Request body must be JSON with 'email' field")

    email = (body.get("email") or "").strip().lower()
    if not email or not _re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        raise HTTPException(422, "Valid email address required")

    from packages.db.client import get_db, is_supabase_connected
    if not is_supabase_connected():
        # Store locally — will be pushed to Supabase once connected
        log.info("[WAITLIST] %s signed up for %s (local mode)", email, product_id)
        return {"ok": True, "product_id": product_id, "email": email, "mode": "local"}

    try:
        db = get_db()
        db.table("product_waitlist").upsert(
            {"product_id": product_id, "email": email},
            on_conflict="product_id,email",
        ).execute()
        log.info("[WAITLIST] %s → %s", email, product_id)
        return {"ok": True, "product_id": product_id, "email": email}
    except Exception as exc:
        log.warning("[WAITLIST] insert failed: %s", exc)
        raise HTTPException(500, "Could not save your email. Please try again.")


@app.get("/api/products")
def get_products() -> dict:
    """
    Public storefront API — returns ventures suitable for display as products.
    Filters: go_decision=True, status NOT KILLED, niche not 'pending'.
    Used by the public landing page and /products route.
    """
    from packages.revenue.store import list_ventures
    all_ventures = list_ventures()
    products = [
        v for v in all_ventures
        if v.get("go_decision") and v.get("status") != "KILLED" and v.get("niche", "pending") != "pending"
    ]
    # Sort: LIVE first, then SCALING, then others
    order = {"LIVE": 0, "SCALING": 1, "DEVELOPMENT": 2, "QA": 3, "IDEATION": 4}
    products.sort(key=lambda v: order.get(v.get("status", ""), 9))
    return {"products": products, "count": len(products)}


@app.get("/api/portfolio")
def get_portfolio() -> dict:
    def _compute():
        live_data = _portfolio_from_supabase()
        if live_data:
            return live_data
        slots = portfolio_slots()
        live = sum(1 for s in slots if s["status"] == "LIVE")
        return {"total_slots": len(slots), "live_count": live, "slots": slots, "source": "mock"}
    return _cached("portfolio", _CACHE_TTL, _compute)


@app.get("/api/trends")
def get_trends() -> dict:
    return _cached("trends", _CACHE_TTL, trend_heatmap)


@app.get("/api/security/alerts")
def get_security_alerts() -> dict:
    return _cached("security", _CACHE_TTL, lambda: {"alerts": security_alerts()})


# ---------------------------------------------------------------------------
# Pipeline control endpoints (Week 5)
# ---------------------------------------------------------------------------

@app.post("/api/pipeline/run")
async def trigger_pipeline(
    body: PipelineRunBody,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict:
    """
    Launch a pipeline run.
    - If called with a valid customer JWT (Authorization header): enforces plan limits.
    - If called from the admin Command Center (no JWT or admin email): unlimited.
    Returns {run_id, venture_id, status: 'STARTED'}.
    """
    from packages.state.agent_state import init_state
    import os as _os

    # ── Customer plan enforcement ────────────────────────────────────────────
    user_id: str | None = None
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        jwt = auth_header[7:]
        try:
            from supabase import create_client as _sc
            supa      = _sc(_os.getenv("SUPABASE_URL", ""), _os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
            user_resp = supa.auth.get_user(jwt)
            caller    = user_resp.user

            # Admin callers: skip limit checks
            admin_email = _os.getenv("VITE_ADMIN_EMAIL", "")
            if caller.email and caller.email != admin_email:
                user_id = caller.id
                profile = _get_user_profile(user_id)
                plan    = (profile or {}).get("plan", "starter")
                limit   = _PLAN_RUN_LIMITS.get(plan, 1)
                used    = _count_user_runs_this_month(user_id)

                if limit != -1 and used >= limit:
                    raise HTTPException(
                        429,
                        f"Monthly run limit reached ({used}/{limit} for {plan} plan). "
                        "Upgrade to Builder ($49/mo) for 10 runs, or Studio for unlimited."
                    )
        except HTTPException:
            raise
        except Exception as exc:
            log.debug("[PIPELINE_RUN] Auth check skipped: %s", exc)

    # ── Launch ───────────────────────────────────────────────────────────────
    state = init_state(body.venture_id)
    run_id     = state["run_id"]
    venture_id = state["venture_id"]

    # Tag the run with user_id so it appears in their dashboard
    if user_id:
        state["_user_id"] = user_id  # passed to background task

    registry.start(run_id, venture_id, body.department)
    background_tasks.add_task(_run_pipeline_background, state, body.department, user_id)

    log.info("[PIPELINE_API] Launched run_id=%s venture_id=%s dept=%s user=%s",
             run_id, venture_id, body.department, user_id or "admin")
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
