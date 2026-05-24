"""
packages/db/client.py
Supabase client wrapper with typed helper methods.
Falls back to local PostgreSQL when SUPABASE_URL is not set.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

try:
    from supabase import create_client, Client as SupabaseClient
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False

_client: Any = None


def is_supabase_connected() -> bool:
    """True when a live Supabase client is active (not NullDB)."""
    return get_db().__class__.__name__ != "_NullDB"


def get_db() -> Any:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))
        is_real_url = (
            url
            and "your-project" not in url
            and url.startswith("https://")
            and ".supabase.co" in url
        )
        is_real_key = key and len(key) > 20 and "your_" not in key
        if is_real_url and is_real_key and _SUPABASE_AVAILABLE:
            try:
                _client = create_client(url, key)
                log.info("Supabase client initialised → %s", url)
            except Exception as exc:
                log.warning("Supabase init failed (%s) — using NullDB fallback", exc)
                _client = _NullDB()
        else:
            log.info("Supabase not configured — DB writes are no-ops (NullDB mode)")
            _client = _NullDB()
    return _client


class _NullDB:
    """Stand-in DB client for local dev without Supabase credentials."""

    def table(self, name: str) -> "_NullTable":
        return _NullTable(name)


class _NullTable:
    def __init__(self, name: str):
        self._name = name

    def insert(self, data: dict[str, Any]) -> "_NullTable":
        log.debug("[NullDB] INSERT %s: %s", self._name, list(data.keys()))
        return self

    def upsert(self, data: dict[str, Any]) -> "_NullTable":
        log.debug("[NullDB] UPSERT %s: %s", self._name, list(data.keys()))
        return self

    def update(self, data: dict[str, Any]) -> "_NullTable":
        log.debug("[NullDB] UPDATE %s: %s", self._name, list(data.keys()))
        return self

    def select(self, cols: str = "*") -> "_NullTable":
        return self

    def eq(self, col: str, val: Any) -> "_NullTable":
        return self

    def execute(self) -> "_NullResult":
        return _NullResult()


class _NullResult:
    data: list[dict[str, Any]] = []
    error: None = None


# ---------------------------------------------------------------------------
# Typed helper functions used by agent nodes
# ---------------------------------------------------------------------------

def upsert_venture(venture_data: dict[str, Any]) -> None:
    db = get_db()
    db.table("ventures").upsert(venture_data).execute()


def log_agent_event(
    run_id: str,
    venture_id: str,
    agent_name: str,
    status: str,
    current_task: str = "",
    tokens_used: int = 0,
    latency_ms: int = 0,
    retry_count: int = 0,
    error_detail: str | None = None,
) -> None:
    db = get_db()
    db.table("agent_logs").insert({
        "run_id":       run_id,
        "venture_id":   venture_id,
        "agent_name":   agent_name,
        "status":       status,
        "current_task": current_task,
        "tokens_used":  tokens_used,
        "latency_ms":   latency_ms,
        "retry_count":  retry_count,
        "error_detail": error_detail,
    }).execute()


def store_event(
    envelope_dict: dict[str, Any],
    run_id: str = "",
    venture_id: str = "",
) -> None:
    """Persist bus event to Supabase events table (Day 3)."""
    if not is_supabase_connected():
        return

    meta = envelope_dict.get("metadata") or {}
    if isinstance(meta, dict):
        run_id = run_id or meta.get("run_id", "")
        venture_id = venture_id or meta.get("venture_id", "")

    row = {
        "event_id": envelope_dict.get("event_id"),
        "event_type": envelope_dict.get("event_type"),
        "source_agent": envelope_dict.get("source_agent"),
        "target_agent": envelope_dict.get("target_agent"),
        "correlation_id": envelope_dict.get("correlation_id"),
        "priority": envelope_dict.get("priority", "NORMAL"),
        "venture_id": venture_id,
        "run_id": run_id,
        "payload": envelope_dict.get("payload") or {},
        "token_cost": meta.get("token_cost", 0) if isinstance(meta, dict) else 0,
        "latency_ms": meta.get("latency_ms", 0) if isinstance(meta, dict) else 0,
    }
    db = get_db()
    try:
        db.table("events").insert(row).execute()
    except Exception as exc:
        log.warning("[store_event] insert failed: %s", exc)


def upsert_pipeline_run(run_data: dict[str, Any]) -> None:
    db = get_db()
    db.table("pipeline_runs").upsert(run_data).execute()


def save_qa_report(report_data: dict[str, Any]) -> None:
    db = get_db()
    db.table("qa_reports").insert(report_data).execute()
    if get_db().__class__.__name__ == "_NullDB":
        from packages.revenue.store import _load_local, _save_local

        data = _load_local()
        data.setdefault("qa_reports", []).append(report_data)
        _save_local(data)


def enqueue_manual_review(item: dict[str, Any]) -> None:
    from packages.revenue.store import enqueue_manual_review as _enqueue

    _enqueue(item)
