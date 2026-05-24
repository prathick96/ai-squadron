"""
packages/agents/shared/account_distribution.py
Account Distribution — maps ventures to platform accounts with rate limits.

Model:   rule-engine (no LLM)
Input:   security_clearance, content_package, venture_brief
Output:  account_distribution_plan with posting caps and OAuth vault refs

SCOPE: Official OAuth-backed accounts only.
  ✓ Per-platform daily post caps
  ✓ Minimum hours between posts
  ✓ Vault reference for OAuth tokens (raw token NEVER in state)
  ✗ NO automated mass signup
  ✗ NO proxy or alternate identity accounts
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from packages.db.client import log_agent_event
from packages.schemas.events import (
    AccountProvisionedPayload,
    AgentID,
    EventType,
    PlatformAccountEntry,
    make_event,
)
from packages.state.agent_state import (
    AccountDistributionPlan,
    AgentState,
    append_event,
    update_stage,
)

log = logging.getLogger(__name__)

_DAILY_POST_CAP: dict[str, int] = {
    "youtube":   2,
    "tiktok":    3,
    "instagram": 2,
    "x":         5,
}

_MIN_HOURS_BETWEEN_POSTS = 4


async def account_distribution_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    clearance = state.get("security_clearance") or {}
    content = state.get("content_package") or {}
    brief = state.get("venture_brief") or {}

    if not clearance.get("is_compliant", True):
        log.warning("[ACCOUNT_DIST] Skipped — security not compliant | venture=%s", venture_id)
        return update_stage(state, "MANUAL_REVIEW_NODE")

    log.info("[ACCOUNT_DIST] Provisioning account mapping | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "ACCOUNT_DISTRIBUTION", "RUNNING",
                    "Mapping venture to platform accounts with rate limits")

    platform = content.get("platform", "youtube") if content else "youtube"
    regions = brief.get("target_region", ["US"]) if isinstance(brief, dict) else ["US"]
    if not isinstance(regions, list):
        regions = ["US"]

    accounts: list[PlatformAccountEntry] = []
    for p in ([platform] if platform else ["youtube"]):
        cap = _DAILY_POST_CAP.get(p, 1)
        accounts.append(PlatformAccountEntry(
            platform=p,
            account_handle=f"@{venture_id[:12]}_{p}",
            oauth_token_ref=f"vault://platform_accounts/{venture_id}/{p}",
            max_posts_today=cap,
            min_hours_between_posts=_MIN_HOURS_BETWEEN_POSTS,
            target_regions=regions,
        ))

    plan: AccountDistributionPlan = {
        "venture_id": venture_id,
        "accounts": [a.model_dump() if hasattr(a, "model_dump") else a for a in accounts],
        "duplicate_content_window_hours": 72,
        "provisioned_at": datetime.now(timezone.utc).isoformat(),
    }

    payload = AccountProvisionedPayload(
        venture_id=venture_id,
        accounts=accounts,
        policy_version="1.0.0",
    )
    event = make_event(
        EventType.ACCOUNTS_PROVISIONED,
        AgentID.ACCOUNT_DISTRIBUTION,
        AgentID.DEPLOYMENT_AGENT,
        payload, run_id, venture_id, "ACCOUNT_DISTRIBUTION_NODE",
    )

    log_agent_event(run_id, venture_id, "ACCOUNT_DISTRIBUTION", "SUCCESS")
    log.info("[ACCOUNT_DIST] ✓ %d accounts provisioned", len(accounts))

    new_state = update_stage(state, "DEPLOYMENT_NODE")
    return append_event({**new_state, "account_distribution_plan": plan}, event.model_dump())
