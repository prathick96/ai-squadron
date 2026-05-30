"""
packages/db/pipeline.py
Pipeline run lifecycle + event persistence to Supabase (Day 3).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from packages.db.client import get_db, is_supabase_connected, store_event

log = logging.getLogger(__name__)


def begin_pipeline_run(run_id: str, venture_id: str, department: str = "PRODUCT") -> None:
    if not is_supabase_connected():
        return
    db = get_db()
    row = {
        "run_id": run_id,
        "venture_id": venture_id,
        "pipeline_stage": "RESEARCH_NODE",
        "status": "RUNNING",
        "qa_retry_count": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "department": department,
    }
    try:
        db.table("pipeline_runs").upsert(row, on_conflict="run_id").execute()
    except TypeError:
        db.table("pipeline_runs").upsert(row).execute()
    log.debug("[pipeline] RUNNING run_id=%s dept=%s", run_id, department)


def update_pipeline_stage(run_id: str, venture_id: str, stage: str, qa_retry_count: int = 0) -> None:
    if not is_supabase_connected():
        return
    db = get_db()
    try:
        db.table("pipeline_runs").update({
            "pipeline_stage": stage,
            "qa_retry_count": qa_retry_count,
        }).eq("run_id", run_id).execute()
    except Exception as exc:
        log.debug("[pipeline] stage update failed: %s", exc)


def complete_pipeline_run(
    run_id: str,
    venture_id: str,
    final_stage: str,
    status: str,
    error_message: str | None = None,
) -> None:
    if not is_supabase_connected():
        return
    db = get_db()
    payload: dict[str, Any] = {
        "pipeline_stage": final_stage,
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if error_message:
        payload["error_message"] = error_message[:2000]
    try:
        db.table("pipeline_runs").update(payload).eq("run_id", run_id).execute()
    except Exception as exc:
        log.warning("[pipeline] complete failed: %s", exc)


def save_research_dossier(
    run_id: str,
    venture_id: str,
    dossier: dict[str, Any],
    debate_transcript: list[dict[str, Any]] | None = None,
) -> None:
    if not is_supabase_connected():
        return
    db = get_db()
    row = {
        "run_id": run_id,
        "venture_id": venture_id,
        "dossier": dossier,
        "debate_transcript": debate_transcript or dossier.get("debate_transcript", []),
        "research_mode": dossier.get("research_mode", "mock"),
        "council_confidence": dossier.get("council_confidence"),
        "recommended_primary_niche": dossier.get("recommended_primary_niche"),
    }
    try:
        db.table("research_dossiers").insert(row).execute()
    except Exception as exc:
        log.warning("[pipeline] research_dossier insert failed (run 003 migration?): %s", exc)


def persist_event_log(state: dict[str, Any]) -> int:
    """Write all events from state.event_log to Supabase events table."""
    if not is_supabase_connected():
        return 0
    run_id = state.get("run_id", "")
    venture_id = state.get("venture_id", "")
    count = 0
    for raw in state.get("event_log", []):
        try:
            store_event(raw, run_id=run_id, venture_id=venture_id)
            count += 1
        except Exception as exc:
            log.debug("[pipeline] event persist skip: %s", exc)
    return count


def fetch_recent_agent_logs(limit: int = 50) -> list[dict[str, Any]]:
    if not is_supabase_connected():
        return []
    db = get_db()
    try:
        result = (
            db.table("agent_logs")
            .select("*")
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def fetch_ventures_for_portfolio(limit: int = 450) -> list[dict[str, Any]]:
    if not is_supabase_connected():
        return []
    db = get_db()
    try:
        result = db.table("ventures").select("*").order("updated_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception:
        return []


def fetch_pipeline_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch recent pipeline runs from Supabase for persistent history display."""
    if not is_supabase_connected():
        return []
    db = get_db()
    try:
        result = (
            db.table("pipeline_runs")
            .select("*")
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        log.debug("[pipeline] fetch_pipeline_runs failed: %s", exc)
        return []


def venture_has_revenue(venture_id: str) -> bool:
    """Return True if the venture has any ledger entries with amount_usd > 0."""
    if not is_supabase_connected():
        return False
    db = get_db()
    try:
        result = (
            db.table("revenue_ledger")
            .select("amount_usd")
            .eq("venture_id", venture_id)
            .execute()
        )
        return any((row.get("amount_usd") or 0) > 0 for row in (result.data or []))
    except Exception as exc:
        log.debug("[pipeline] venture_has_revenue check failed: %s", exc)
        return False


def kill_venture(venture_id: str) -> bool:
    """Soft-delete a venture by setting its status to KILLED. Returns True on success."""
    if not is_supabase_connected():
        return False
    db = get_db()
    try:
        db.table("ventures").update({"status": "KILLED"}).eq("venture_id", venture_id).execute()
        log.info("[pipeline] venture KILLED: %s", venture_id)
        return True
    except Exception as exc:
        log.warning("[pipeline] kill_venture failed: %s", exc)
        return False


def persist_build_artifact(
    venture_id: str,
    run_id: str,
    build_hash: str,
    files: list[dict[str, Any]],
) -> None:
    """
    Persist generated SaaS source files to Supabase build_artifacts table.
    Called by engineering_team after successfully writing files to disk.
    Survives Railway redeploys — /tmp/ is ephemeral, Supabase is permanent.
    """
    if not is_supabase_connected():
        log.debug("[pipeline] Supabase not connected — build_artifact not persisted")
        return

    total_bytes = sum(len((f.get("content") or "").encode()) for f in files)
    row = {
        "venture_id": venture_id,
        "run_id":     run_id,
        "build_hash": build_hash,
        "files":      files,
        "file_count": len(files),
        "total_kb":   round(total_bytes / 1024, 1),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        db = get_db()
        db.table("build_artifacts").upsert(row, on_conflict="venture_id").execute()
        log.info("[pipeline] Build artifact persisted | venture=%s files=%d kb=%.1f",
                 venture_id, len(files), row["total_kb"])
    except TypeError:
        db = get_db()
        db.table("build_artifacts").upsert(row).execute()
        log.info("[pipeline] Build artifact persisted (no-conflict) | venture=%s", venture_id)
    except Exception as exc:
        log.warning("[pipeline] persist_build_artifact failed: %s", exc)


def fetch_build_artifact(venture_id: str) -> dict[str, Any] | None:
    """
    Fetch the most recent build artifact for a venture from Supabase.
    Returns None when Supabase is unavailable or no artifact found.
    """
    if not is_supabase_connected():
        return None
    try:
        db     = get_db()
        result = db.table("build_artifacts").select("*").eq("venture_id", venture_id).execute()
        rows   = result.data or []
        return rows[0] if rows else None
    except Exception as exc:
        log.warning("[pipeline] fetch_build_artifact failed: %s", exc)
        return None
