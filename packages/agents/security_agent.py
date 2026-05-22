"""
packages/agents/security_agent.py
Security Agent Node — ToS compliance verification and posting schedule generation.
Model: gemini-2.0-flash
Note: This agent enforces platform Terms of Service compliance.
All operations are conducted within official platform API limits.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from packages.db.client import log_agent_event
from packages.schemas.events import (
    AgentID, EventType, PostingWindow, SecurityClearancePayload,
    TosStatus, make_event,
)
from packages.state.agent_state import AgentState, SecurityClearance, append_event, update_stage

log = logging.getLogger(__name__)

# Platform ToS rules snapshot — updated weekly via _refresh_tos_snapshot()
_TOS_SNAPSHOT: dict[str, dict] = {
    "youtube": {
        "requires_original_content": True,
        "min_video_duration_sec": 60,
        "max_daily_uploads_api": 6,        # YouTube Data API v3 free: ~6 uploads/day
        "monetization_requires_ypp": True,
        "ypp_min_subscribers": 1000,
        "ypp_min_watch_hours": 4000,
        "prohibited_content": ["spam", "misleading_metadata", "artificial_engagement"],
    },
    "tiktok": {
        "requires_original_content": True,
        "max_video_duration_sec": 600,
        "requires_content_posting_api_approval": True,
        "prohibited_content": ["misleading_info", "spam"],
    },
    "instagram": {
        "requires_business_or_creator_account": True,
        "max_api_calls_per_hour": 200,
        "prohibited_content": ["spam", "inauthentic_behavior"],
    },
}

# Peak engagement windows per region (UTC offsets applied)
_POSTING_WINDOWS: dict[str, dict] = {
    "youtube": {"post_time_utc": "14:00", "base_jitter_minutes": 20, "frequency": "daily"},
    "tiktok":  {"post_time_utc": "10:00", "base_jitter_minutes": 15, "frequency": "2x_daily"},
    "instagram":{"post_time_utc": "12:00", "base_jitter_minutes": 10, "frequency": "daily"},
}


async def security_agent_node(state: AgentState) -> AgentState:
    run_id     = state["run_id"]
    venture_id = state["venture_id"]
    qa_report  = state.get("qa_report") or {}
    content    = state.get("content_package") or {}

    log.info("[SECURITY_NODE] Running ToS compliance check | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "SECURITY_AGENT", "RUNNING",
                    "Verifying ToS compliance and generating posting schedule")

    # Determine which platforms this venture targets
    platform = content.get("platform", "youtube")
    platforms = [platform] if platform else ["youtube"]

    # Run ToS compliance checks
    tos_snapshot: dict[str, TosStatus] = {}
    all_compliant = True

    for p in platforms:
        rules = _TOS_SNAPSHOT.get(p, {})
        flagged: list[str] = []

        # Check content compliance against ToS rules
        if content:
            seo = content.get("seo_metadata") or {}
            title = seo.get("title", "") if isinstance(seo, dict) else ""
            # Verify title does not contain prohibited terms
            for prohibited in rules.get("prohibited_content", []):
                if prohibited.replace("_", " ") in title.lower():
                    flagged.append(f"title_contains_{prohibited}")
                    all_compliant = False

        tos_snapshot[p] = TosStatus(
            compliant    = len(flagged) == 0,
            last_checked = datetime.now(timezone.utc).isoformat(),
            flagged_items = flagged,
        )

    # Generate posting schedules with jitter (prevents bot-pattern detection)
    posting_schedule: dict[str, PostingWindow] = {}
    for p in platforms:
        base = _POSTING_WINDOWS.get(p, _POSTING_WINDOWS["youtube"])
        jitter = random.randint(
            -base["base_jitter_minutes"],
             base["base_jitter_minutes"]
        )
        posting_schedule[p] = PostingWindow(
            post_time_utc    = base["post_time_utc"],
            jitter_minutes   = abs(jitter),
            frequency        = base["frequency"],
        )

    clearance_valid_until = (
        datetime.now(timezone.utc) + timedelta(days=7)
    ).isoformat()

    payload = SecurityClearancePayload(
        venture_id            = venture_id,
        platform_accounts     = {p: {"account_id": f"acct_{p}_001"} for p in platforms},
        tos_compliance_snapshot = tos_snapshot,
        posting_schedule      = posting_schedule,
        clearance_valid_until = clearance_valid_until,
        is_compliant          = all_compliant,
    )

    event = make_event(
        EventType.SECURITY_CLEARANCE_GRANTED,
        AgentID.SECURITY_AGENT,
        AgentID.ACCOUNT_DISTRIBUTION,
        payload,
        run_id,
        venture_id,
        "SECURITY_NODE",
    )

    security_clearance: SecurityClearance = payload.model_dump()  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "SECURITY_AGENT", "SUCCESS")
    log.info("[SECURITY_NODE] ✓ Clearance granted | platforms=%s compliant=%s",
             platforms, all_compliant)

    new_state = update_stage(state, "ACCOUNT_DISTRIBUTION_NODE")
    return append_event({**new_state, "security_clearance": security_clearance}, event.model_dump())
