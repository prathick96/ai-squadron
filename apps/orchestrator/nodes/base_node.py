"""
apps/orchestrator/nodes/base_node.py
──────────────────────────────────────
Abstract base class for all LangGraph agent nodes.

Every agent node:
  1. Inherits from BaseAgentNode
  2. Implements the `execute()` method with its domain logic
  3. Calls `self.log_start()` / `self.log_complete()` for agent_logs persistence
  4. Appends events to state["event_log"] via `self.make_log_entry()`
  5. The `__call__` method handles the outer try/except and timing

Nodes are pure functions from the LangGraph perspective — they accept
AgentState and return AgentState. The class structure is for code reuse only.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from packages.state.agent_state import AgentState, append_event, EventLogEntry

logger = logging.getLogger(__name__)


class BaseAgentNode(ABC):
    """Abstract base for all AI Squadron agent nodes."""

    agent_id: str      # Must be set on each subclass
    model: str         # Model used by this node (set in subclass __init__)

    def __init__(self) -> None:
        from packages.config.settings import get_settings
        self.settings = get_settings()

    async def __call__(self, state: AgentState) -> AgentState:
        """
        LangGraph calls this. Wraps execute() with timing, logging, and error handling.
        Subclasses implement execute() — not __call__.
        """
        start_ms = int(time.monotonic() * 1000)
        venture_id = state.get("venture_id", "unknown")
        run_id = state.get("run_id", "unknown")

        logger.info("[%s] Starting — venture_id=%s run_id=%s", self.agent_id, venture_id, run_id)

        try:
            updated_state = await self.execute(state)
            duration_ms = int(time.monotonic() * 1000) - start_ms
            logger.info(
                "[%s] Completed in %dms — venture_id=%s",
                self.agent_id, duration_ms, venture_id,
            )
            # Update pipeline_stage to this node's name
            updated_state["pipeline_stage"] = self.agent_id
            return updated_state

        except Exception as exc:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            logger.error(
                "[%s] FAILED after %dms — venture_id=%s error=%s",
                self.agent_id, duration_ms, venture_id, exc,
                exc_info=True,
            )
            # Append failure to event log without crashing the pipeline
            error_entry = append_event(
                state=state,
                event_type=f"{self.agent_id}_FAILED",
                source_agent=self.agent_id,
                target_agent="ORCHESTRATOR",
                payload_summary=f"Node failed: {exc!s}",
                latency_ms=duration_ms,
                success=False,
                error=str(exc),
            )
            state["event_log"] = state.get("event_log", []) + [error_entry]
            state["pipeline_stage"] = f"{self.agent_id}_FAILED"
            raise  # Re-raise so LangGraph can handle or surface the error

    @abstractmethod
    async def execute(self, state: AgentState) -> AgentState:
        """
        Implement all agent logic here.
        Must return the modified AgentState.
        Do not call super() — the base __call__ wrapper handles lifecycle.
        """
        ...

    def make_log_entry(
        self,
        state: AgentState,
        event_type: str,
        target_agent: str,
        payload_summary: str,
        token_cost: float = 0.0,
        latency_ms: int = 0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> EventLogEntry:
        """Convenience wrapper around append_event for use inside execute()."""
        return append_event(
            state=state,
            event_type=event_type,
            source_agent=self.agent_id,
            target_agent=target_agent,
            payload_summary=payload_summary,
            token_cost=token_cost,
            latency_ms=latency_ms,
            success=success,
            error=error,
        )

    def get_model_for_agent(self) -> str:
        """Returns the configured model string for this agent from settings."""
        model_map = {
            "CEO_NODE":         self.settings.model_ceo,
            "PRODUCT_NODE":     self.settings.model_product,
            "ENGINEERING_NODE": self.settings.model_engineering,
            "CONTENT_NODE":     self.settings.model_content_script,
            "QA_NODE":          self.settings.model_qa_critique,
            "SECURITY_NODE":    self.settings.model_security,
            "DEPLOYMENT_NODE":  "none",
            "MARKETING_NODE":   self.settings.model_marketing,
            "GLOBAL_NODE":      self.settings.model_global,
            "GROWTH_NODE":      self.settings.model_growth,
            "REVENUE_NODE":     self.settings.model_revenue,
        }
        return model_map.get(self.agent_id, "gemini-2.0-flash")


class StubNode(BaseAgentNode):
    """
    Drop-in stub for any agent node during development.
    Logs receipt of state and passes it through unchanged.
    Used to wire the full graph before implementing individual agents.

    Usage:
        class DeploymentNode(StubNode):
            agent_id = "DEPLOYMENT_NODE"
            model = "none"
    """

    async def execute(self, state: AgentState) -> AgentState:
        venture_id = state.get("venture_id", "unknown")
        logger.info(
            "[STUB:%s] Received state for venture_id=%s — passing through.",
            self.agent_id, venture_id,
        )
        entry = self.make_log_entry(
            state=state,
            event_type=f"{self.agent_id}_STUB_PASSTHROUGH",
            target_agent="NEXT_NODE",
            payload_summary=f"Stub node passthrough for venture_id={venture_id}",
            success=True,
        )
        state["event_log"] = state.get("event_log", []) + [entry]
        return state
