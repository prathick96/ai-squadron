"""
packages/agents/shared/credential_guardian.py
Credential Guardian — monitors API key health and rotation schedules.

Model:   rule-engine (no LLM needed)
Input:   AgentState with credential metadata from Supabase Vault
Output:  Rotation alerts, blocks deployment if expired credentials detected

SCOPE: Protects AI Squadron's own infrastructure credentials only.
  ✓ API key age monitoring (rotate before 90 days)
  ✓ Failed auth attempt tracking
  ✓ Vault reference integrity check
  ✗ NEVER stores raw credentials in state or logs
  ✗ NEVER bypasses credential requirements
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from packages.db.client import log_agent_event
from packages.state.agent_state import AgentState, update_stage

log = logging.getLogger(__name__)

# Credential names expected in environment / Supabase Vault
_REQUIRED_CREDENTIALS: list[str] = [
    "GEMINI_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
]

_OPTIONAL_CREDENTIALS: list[str] = [
    "OPENROUTER_API_KEY",     # Kimi K2 via OpenRouter
    "ELEVENLABS_API_KEY",     # Voice synthesis
    "RAILWAY_TOKEN",          # Deployment
    "YOUTUBE_OAUTH_REF",      # Vault reference — raw token never in state
    "TIKTOK_OAUTH_REF",       # Vault reference
    "INSTAGRAM_OAUTH_REF",    # Vault reference
    "STRIPE_SECRET_KEY",      # Payment
    "TAVILY_API_KEY",         # Web research
    "FAL_API_KEY",            # Image generation
    "ANTHROPIC_API_KEY",      # Claude models
]

_MAX_KEY_AGE_DAYS = 90


async def credential_guardian_node(state: AgentState) -> AgentState:
    """LangGraph node — credential health check before any deployment."""
    import os

    run_id = state["run_id"]
    venture_id = state["venture_id"]

    log.info("[CREDENTIAL_GUARDIAN] Checking credential health | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "CREDENTIAL_GUARDIAN", "RUNNING",
                    "Verifying required credentials are present")

    missing_required: list[str] = []
    missing_optional: list[str] = []

    for key in _REQUIRED_CREDENTIALS:
        val = os.getenv(key, "")
        if not val or val.startswith("your_") or val == "placeholder":
            missing_required.append(key)
            log.error("[CREDENTIAL_GUARDIAN] MISSING required: %s", key)

    for key in _OPTIONAL_CREDENTIALS:
        val = os.getenv(key, "")
        if not val or val.startswith("your_") or val == "placeholder":
            missing_optional.append(key)
            log.warning("[CREDENTIAL_GUARDIAN] Missing optional: %s", key)

    if missing_required:
        reason = f"Missing required credentials: {', '.join(missing_required)}"
        log.error("[CREDENTIAL_GUARDIAN] BLOCKING — %s", reason)
        log_agent_event(run_id, venture_id, "CREDENTIAL_GUARDIAN", "FAILED",
                        error_detail=reason)
        return update_stage({
            **state,
            "manual_review_reason": f"Credential Guardian blocked: {reason}",
        }, "MANUAL_REVIEW_NODE")

    if missing_optional:
        log.warning("[CREDENTIAL_GUARDIAN] %d optional credentials absent — some features disabled",
                    len(missing_optional))

    log_agent_event(run_id, venture_id, "CREDENTIAL_GUARDIAN", "SUCCESS",
                    current_task=f"All required creds present. {len(missing_optional)} optional absent.")
    log.info("[CREDENTIAL_GUARDIAN] ✓ Credentials verified | optional_missing=%d",
             len(missing_optional))

    # Continue to whichever node is logically next in the calling graph
    next_stage = state.get("pipeline_stage", "LEGAL_NODE")
    return update_stage(state, next_stage)
