"""
packages/agents/deployment_team.py
Deployment Team Node — Vercel deploy (SaaS) + platform media publishing.
No LLM needed — pure deterministic tool execution.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from packages.db.client import log_agent_event
from packages.schemas.events import (
    AgentID, DeploymentCompletePayload, DeploymentEntry, EventType, make_event,
)
from packages.state.agent_state import AgentState, DeploymentReceipt, append_event, update_stage

log = logging.getLogger(__name__)


async def deployment_team_node(state: AgentState) -> AgentState:
    run_id     = state["run_id"]
    venture_id = state["venture_id"]
    build      = state.get("build_artifact") or {}
    content    = state.get("content_package") or {}
    clearance  = state.get("security_clearance") or {}
    tech_spec  = state.get("tech_spec") or {}

    is_saas    = tech_spec.get("product_type") == "MICRO_SAAS"
    is_media   = bool(content)

    log.info("[DEPLOYMENT_NODE] Deploying venture=%s saas=%s media=%s",
             venture_id, is_saas, is_media)
    log_agent_event(run_id, venture_id, "DEPLOYMENT_TEAM", "RUNNING", "Executing deployments")

    deployments: list[DeploymentEntry] = []
    now = datetime.now(timezone.utc).isoformat()

    if is_saas:
        # Stub: replace with live Vercel Deploy API call in Phase 1 Day 21
        saas_entry = DeploymentEntry(
            type            = "SAAS",
            platform        = "vercel",
            url             = f"https://{venture_id}.yourdomain.com",
            deployment_id   = f"dpl_{venture_id[:8]}",
            deployed_at     = now,
            smoke_test_passed = True,
        )
        deployments.append(saas_entry)
        log.info("[DEPLOYMENT_NODE] SaaS deployed → %s", saas_entry.url)

    if is_media:
        platform = content.get("platform", "youtube")
        seo      = content.get("seo_metadata") or {}
        title    = seo.get("title", "") if isinstance(seo, dict) else ""

        # Stub: replace with live YouTube Data API v3 / TikTok Content Posting API in Phase 2
        media_entry = DeploymentEntry(
            type        = "MEDIA",
            platform    = platform,
            url         = f"https://{platform}.com/watch?v={venture_id[:11]}",
            video_id    = venture_id[:11],
            deployed_at = now,
        )
        deployments.append(media_entry)
        log.info("[DEPLOYMENT_NODE] Media published → %s | title=%s", platform, title[:60])

    status = "LIVE" if deployments else "FAILED"

    payload = DeploymentCompletePayload(
        venture_id            = venture_id,
        deployments           = deployments,
        post_deployment_status = status,  # type: ignore[arg-type]
    )

    event = make_event(
        EventType.DEPLOYMENT_COMPLETE, AgentID.DEPLOYMENT_TEAM, AgentID.BROADCAST,
        payload, run_id, venture_id, "DEPLOYMENT_NODE",
    )

    receipt: DeploymentReceipt = payload.model_dump()  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "DEPLOYMENT_TEAM", "SUCCESS")
    log.info("[DEPLOYMENT_NODE] ✓ %d deployments live", len(deployments))

    new_state = update_stage(state, "MARKETING_NODE")
    return append_event({**new_state, "deployment_receipt": receipt}, event.model_dump())
