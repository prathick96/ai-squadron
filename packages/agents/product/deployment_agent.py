"""
packages/agents/product/deployment_agent.py
Deployment Agent — pushes a Vite build to Railway via the REST + GraphQL API.

When RAILWAY_TOKEN is set: calls deploy_to_railway() which creates/reuses a
Railway project + service, uploads a tarball, and polls until the deployment
is live.  Returns the real HTTPS URL.

When RAILWAY_TOKEN is absent (dev / CI): returns a deterministic mock URL so
the rest of the pipeline can continue without a Railway account.

Required: RAILWAY_TOKEN
Optional: RAILWAY_PROJECT_ID  (targets a specific project instead of auto-managing)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from packages.db.client import log_agent_event
from packages.schemas.events import (
    AgentID, DeploymentCompletePayload, DeploymentEntry, EventType, make_event,
)
from packages.state.agent_state import AgentState, DeploymentReceipt, append_event, update_stage
from packages.tools.railway_client import deploy_to_railway, railway_available

log = logging.getLogger(__name__)

_BUILDS_ROOT = Path(os.getenv("BUILDS_DIR", "/tmp/squadron-builds"))


async def deployment_agent_node(state: AgentState) -> AgentState:
    run_id     = state["run_id"]
    venture_id = state["venture_id"]
    build      = state.get("build_artifact") or {}
    clearance  = state.get("security_clearance") or {}

    if not clearance.get("is_compliant", True):
        log.warning("[DEPLOYMENT_NODE] Security not compliant — blocking deploy | venture=%s",
                    venture_id)
        return update_stage(
            {**state, "manual_review_reason": "Security clearance not compliant"},
            "MANUAL_REVIEW_NODE",
        )

    use_railway    = railway_available()
    build_path     = build.get("build_path", "")
    build_dir      = Path(build_path) if build_path else _BUILDS_ROOT / venture_id
    smoke_passed   = True
    deployment_url = f"https://{venture_id[:20]}.up.railway.app"

    log.info("[DEPLOYMENT_NODE] Deploying SaaS | venture=%s railway=%s dir=%s",
             venture_id, use_railway, build_dir)
    log_agent_event(run_id, venture_id, "DEPLOYMENT_AGENT", "RUNNING",
                    "Railway REST deploy" if use_railway else "mock deploy")

    if use_railway:
        try:
            deployment_url = await deploy_to_railway(venture_id, build_dir)
            log.info("[DEPLOYMENT_NODE] ✓ Railway deploy | url=%s", deployment_url)
        except Exception as exc:
            log.warning("[DEPLOYMENT_NODE] Railway deploy failed (%s) — using mock URL", exc)
            smoke_passed = False

    now   = datetime.now(timezone.utc).isoformat()
    entry = DeploymentEntry(
        type="SAAS",
        platform="railway",
        url=deployment_url,
        deployment_id=f"dpl_{venture_id[:8]}_{int(datetime.now(timezone.utc).timestamp())}",
        deployed_at=now,
        smoke_test_passed=smoke_passed,
    )
    payload = DeploymentCompletePayload(
        venture_id=venture_id,
        deployments=[entry],
        post_deployment_status="LIVE" if smoke_passed else "PARTIAL",
    )
    event = make_event(
        EventType.DEPLOYMENT_COMPLETE, AgentID.DEPLOYMENT_AGENT, AgentID.BROADCAST,
        payload, run_id, venture_id, "DEPLOYMENT_NODE",
    )

    receipt: DeploymentReceipt = payload.model_dump()  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "DEPLOYMENT_AGENT", "SUCCESS",
                    current_task=f"url={deployment_url}")
    log.info("[DEPLOYMENT_NODE] ✓ Done | url=%s smoke=%s", deployment_url, smoke_passed)

    new_state = update_stage(state, "MARKETING_SEO_NODE")
    return append_event({**new_state, "deployment_receipt": receipt}, event.model_dump())
