"""
packages/agents/product/deployment_agent.py
Deployment Agent (Product) — pushes SaaS builds to Railway.

Model:   rule-engine (no LLM — deterministic deploy commands)
Input:   build_artifact, account_distribution_plan, security_clearance
Output:  deployment_receipt with live Railway URL

Phase 1: stub returning mock URLs
Phase 2: wire Railway Deploy API (POST /projects/{id}/deployments)
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


async def deployment_agent_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    build = state.get("build_artifact") or {}
    clearance = state.get("security_clearance") or {}

    if not clearance.get("is_compliant", True):
        log.warning("[DEPLOYMENT_NODE] Security not compliant — blocking deploy | venture=%s",
                    venture_id)
        return update_stage({
            **state,
            "manual_review_reason": "Security clearance not compliant",
        }, "MANUAL_REVIEW_NODE")

    log.info("[DEPLOYMENT_NODE] Deploying SaaS | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "DEPLOYMENT_AGENT", "RUNNING", "Railway deploy")

    now = datetime.now(timezone.utc).isoformat()

    # Phase 2: replace stub with Railway Deploy API call
    # import httpx; await httpx.AsyncClient().post(
    #     f"https://backboard.railway.app/graphql/v2",
    #     json={"query": "mutation deploymentCreate(...) { ... }"},
    #     headers={"Authorization": f"Bearer {os.getenv('RAILWAY_TOKEN')}"},
    # )
    entry = DeploymentEntry(
        type="SAAS",
        platform="railway",
        url=f"https://{venture_id[:20]}.up.railway.app",
        deployment_id=f"dpl_{venture_id[:8]}_{int(datetime.now(timezone.utc).timestamp())}",
        deployed_at=now,
        smoke_test_passed=True,
    )

    payload = DeploymentCompletePayload(
        venture_id=venture_id,
        deployments=[entry],
        post_deployment_status="LIVE",
    )
    event = make_event(
        EventType.DEPLOYMENT_COMPLETE, AgentID.DEPLOYMENT_AGENT, AgentID.BROADCAST,
        payload, run_id, venture_id, "DEPLOYMENT_NODE",
    )

    receipt: DeploymentReceipt = payload.model_dump()  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "DEPLOYMENT_AGENT", "SUCCESS")
    log.info("[DEPLOYMENT_NODE] ✓ SaaS live | url=%s", entry.url)

    new_state = update_stage(state, "MARKETING_SEO_NODE")
    return append_event({**new_state, "deployment_receipt": receipt}, event.model_dump())
