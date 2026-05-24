"""
packages/orchestrator/runner.py
In-memory pipeline run registry — tracks active and recent runs for live status queries.

Thread-safe: uses threading.Lock so it is safe inside FastAPI's asyncio event loop
and from sync test code alike.

Lives for the lifetime of the process only.  Supabase pipeline_runs table is the
durable record; this is the low-latency read path for the status API and WebSocket.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

RunStatus = Literal["STARTED", "RUNNING", "COMPLETED", "FAILED", "MANUAL_REVIEW"]

_MAX_EVENTS_PER_RUN = 50
_MAX_RUNS = 100


@dataclass
class RunRecord:
    run_id: str
    venture_id: str
    department: str
    status: RunStatus = "STARTED"
    current_stage: str = "RESEARCH_NODE"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    recent_events: list[dict] = field(default_factory=list)
    last_error: str | None = None


class RunRegistry:
    """Singleton in-memory store for pipeline run state."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._order: list[str] = []   # insertion-order; oldest first
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def start(self, run_id: str, venture_id: str, department: str) -> RunRecord:
        with self._lock:
            rec = RunRecord(run_id=run_id, venture_id=venture_id, department=department)
            self._runs[run_id] = rec
            self._order.append(run_id)
            if len(self._order) > _MAX_RUNS:
                evicted = self._order.pop(0)
                self._runs.pop(evicted, None)
            return rec

    def update_stage(self, run_id: str, stage: str) -> None:
        with self._lock:
            rec = self._runs.get(run_id)
            if rec:
                rec.current_stage = stage
                rec.status = "RUNNING"
                rec.updated_at = datetime.now(timezone.utc).isoformat()

    def complete(
        self,
        run_id: str,
        final_stage: str,
        status: RunStatus,
        error: str | None = None,
    ) -> None:
        with self._lock:
            rec = self._runs.get(run_id)
            if rec:
                rec.current_stage = final_stage
                rec.status = status
                rec.last_error = error
                now = datetime.now(timezone.utc).isoformat()
                rec.completed_at = now
                rec.updated_at = now

    def append_event(self, run_id: str, event: dict) -> None:
        with self._lock:
            rec = self._runs.get(run_id)
            if rec:
                rec.recent_events.append(event)
                if len(rec.recent_events) > _MAX_EVENTS_PER_RUN:
                    rec.recent_events = rec.recent_events[-_MAX_EVENTS_PER_RUN:]

    # ------------------------------------------------------------------
    # Reads (no lock needed for immutable snapshots)
    # ------------------------------------------------------------------

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def list_recent(self, n: int = 20) -> list[RunRecord]:
        with self._lock:
            recent_ids = list(self._order[-n:])
        return [self._runs[rid] for rid in reversed(recent_ids) if rid in self._runs]

    def active_count(self) -> int:
        return sum(
            1 for r in self._runs.values()
            if r.status in ("STARTED", "RUNNING")
        )


# Process-wide singleton
registry = RunRegistry()
