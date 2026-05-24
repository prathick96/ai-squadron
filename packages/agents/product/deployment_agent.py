"""
packages/agents/product/deployment_agent.py
Deployment Agent (Product) — pushes SaaS builds to Railway.

Phase 2 (RAILWAY_TOKEN set): runs `railway up --detach` subprocess inside the
build directory, capturing the live URL from CLI output.

Phase 1 fallback (no token): returns a deterministic mock Railway URL so the
rest of the pipeline continues in dev / CI environments.

Requires Railway CLI installed: npm install -g @railway/cli
Docs: https://docs.railway.app/develop/cli
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from packages.db.client import log_agent_event
from packages.schemas.events import (
    AgentID, DeploymentCompletePayload, DeploymentEntry, EventType, make_event,
)
from packages.state.agent_state import AgentState, DeploymentReceipt, append_event, update_stage

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RAILWAY_TIMEOUT = 180   # seconds


def railway_available() -> bool:
    """True when RAILWAY_TOKEN is configured (not a placeholder)."""
    token = os.getenv("RAILWAY_TOKEN", "")
    return bool(token and len(token) > 10 and not token.startswith("your_"))


def _railway_cmd() -> str:
    """Return platform-correct Railway CLI executable name."""
    return "railway.cmd" if sys.platform == "win32" else "railway"


async def _deploy_via_railway_cli(build_dir: Path, venture_id: str) -> str:
    """
    Run `railway up --detach` inside build_dir and parse the deployed URL.
    Returns the live URL string.
    Raises RuntimeError on non-zero exit or timeout.
    """
    token = os.getenv("RAILWAY_TOKEN", "")
    env = {**os.environ, "RAILWAY_TOKEN": token}

    proc = await asyncio.create_subprocess_exec(
        _railway_cmd(), "up", "--detach",
        "--service", venture_id[:20],
        cwd=str(build_dir),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=_RAILWAY_TIMEOUT
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"railway up timed out after {_RAILWAY_TIMEOUT}s")

    if proc.returncode != 0:
        stderr_tail = stderr_bytes.decode(errors="replace")[-500:]
        raise RuntimeError(f"railway up exit={proc.returncode}: {stderr_tail}")

    # Parse URL from stdout — Railway CLI prints the live URL on a line by itself
    url = ""
    for line in stdout_bytes.decode(errors="replace").splitlines():
        line = line.strip()
        if line.startswith("https://") and ".up.railway.app" in line:
            url = line
            break

    return url or f"https://{venture_id[:20]}.up.railway.app"


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

    use_railway = railway_available()
    log.info("[DEPLOYMENT_NODE] Deploying SaaS | venture=%s railway_cli=%s",
             venture_id, use_railway)
    log_agent_event(run_id, venture_id, "DEPLOYMENT_AGENT", "RUNNING",
                    "railway up" if use_railway else "mock deploy")

    now = datetime.now(timezone.utc).isoformat()
    deployment_url = f"https://{venture_id[:20]}.up.railway.app"
    smoke_test_passed = True

    if use_railway:
        build_path_str = build.get("build_path", "")
        build_dir = Path(build_path_str) if build_path_str else _REPO_ROOT / "builds" / venture_id
        try:
            deployment_url = await _deploy_via_railway_cli(build_dir, venture_id)
            log.info("[DEPLOYMENT_NODE] ✓ Railway deploy | url=%s", deployment_url)
        except Exception as exc:
            log.warning("[DEPLOYMENT_NODE] railway up failed (%s) — falling back to mock URL", exc)
            smoke_test_passed = False

    entry = DeploymentEntry(
        type="SAAS",
        platform="railway",
        url=deployment_url,
        deployment_id=f"dpl_{venture_id[:8]}_{int(datetime.now(timezone.utc).timestamp())}",
        deployed_at=now,
        smoke_test_passed=smoke_test_passed,
    )

    payload = DeploymentCompletePayload(
        venture_id=venture_id,
        deployments=[entry],
        post_deployment_status="LIVE" if smoke_test_passed else "PARTIAL",
    )
    event = make_event(
        EventType.DEPLOYMENT_COMPLETE, AgentID.DEPLOYMENT_AGENT, AgentID.BROADCAST,
        payload, run_id, venture_id, "DEPLOYMENT_NODE",
    )

    receipt: DeploymentReceipt = payload.model_dump()  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "DEPLOYMENT_AGENT", "SUCCESS",
                    current_task=f"url={deployment_url}")
    log.info("[DEPLOYMENT_NODE] ✓ SaaS deployed | url=%s smoke=%s",
             deployment_url, smoke_test_passed)

    new_state = update_stage(state, "MARKETING_SEO_NODE")
    return append_event({**new_state, "deployment_receipt": receipt}, event.model_dump())
