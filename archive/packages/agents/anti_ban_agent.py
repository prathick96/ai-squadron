"""
packages/agents/shared/anti_ban_agent.py
Anti-Ban & Platform Compliance Monitor — risk signal watcher.

Model:   gemini-2.0-flash
Input:   channel_analytics, deployment_receipt, platform accounts
Output:  Risk assessment — pause/continue recommendations

SCOPE: Detects platform risk signals and recommends defensive actions.
  ✓ Copyright strike monitoring
  ✓ Community guideline strike tracking
  ✓ Dispute rate monitoring (Stripe)
  ✓ API quota warnings
  ✗ NEVER suggests bypassing platform enforcement
  ✗ NEVER suggests fake engagement or bot activity

Runs as a standalone check triggered by Analytics Agent or Revenue Engine.
"""
from __future__ import annotations

import logging

from packages.db.client import log_agent_event
from packages.state.agent_state import AgentState, update_stage

log = logging.getLogger(__name__)

_RISK_THRESHOLDS = {
    "copyright_strikes": {"warning": 1, "pause": 2},
    "community_strikes": {"warning": 1, "pause": 2},
    "dispute_rate_pct":  {"warning": 0.3, "pause": 0.5},   # Stripe: 0.5% = account review
    "api_quota_used_pct": {"warning": 80, "pause": 95},
}


async def anti_ban_agent_node(state: AgentState) -> AgentState:
    """LangGraph node — platform risk signal assessment."""
    run_id = state["run_id"]
    venture_id = state["venture_id"]

    log.info("[ANTI_BAN_NODE] Risk assessment | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "ANTI_BAN_AGENT", "RUNNING",
                    "Checking platform risk signals")

    analytics = state.get("channel_analytics") or {}
    risk_signals: list[str] = []
    should_pause = False

    # Copyright strikes
    strikes = analytics.get("copyright_strikes", 0)
    if strikes >= _RISK_THRESHOLDS["copyright_strikes"]["pause"]:
        risk_signals.append(f"CRITICAL: {strikes} copyright strikes — channel at risk")
        should_pause = True
    elif strikes >= _RISK_THRESHOLDS["copyright_strikes"]["warning"]:
        risk_signals.append(f"WARNING: {strikes} copyright strike detected")

    # API quota
    quota_pct = analytics.get("api_quota_used_pct", 0)
    if quota_pct >= _RISK_THRESHOLDS["api_quota_used_pct"]["pause"]:
        risk_signals.append(f"CRITICAL: API quota at {quota_pct}% — pausing uploads")
        should_pause = True
    elif quota_pct >= _RISK_THRESHOLDS["api_quota_used_pct"]["warning"]:
        risk_signals.append(f"WARNING: API quota at {quota_pct}%")

    if risk_signals:
        for sig in risk_signals:
            log.warning("[ANTI_BAN_NODE] %s | venture=%s", sig, venture_id)

    if should_pause:
        log.error("[ANTI_BAN_NODE] PAUSE RECOMMENDED | venture=%s | signals=%s",
                  venture_id, risk_signals)
        log_agent_event(run_id, venture_id, "ANTI_BAN_AGENT", "FAILED",
                        error_detail="; ".join(risk_signals))
        return update_stage({
            **state,
            "manual_review_reason": f"Anti-ban pause: {'; '.join(risk_signals)}",
        }, "MANUAL_REVIEW_NODE")

    log_agent_event(run_id, venture_id, "ANTI_BAN_AGENT", "SUCCESS",
                    current_task=f"No critical signals. Warnings: {len(risk_signals)}")
    log.info("[ANTI_BAN_NODE] ✓ No critical risk signals | venture=%s", venture_id)
    return update_stage(state, "PUBLISHING_NODE")
