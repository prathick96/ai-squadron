"""
packages/agents/media/analytics_agent.py
Analytics Agent — fetches channel metrics after publishing.

Model:   rule-engine + YouTube/TikTok APIs (no LLM)
Input:   published_urls, venture_brief
Output:  channel_analytics dict (views, subs, revenue, strikes)

Phase 1: stub — returns mock analytics
Phase 2: wire live APIs
  YouTube: GET /youtube/v3/videos?part=statistics&id={video_id}
  YouTube: GET /youtube/v3/channels?part=statistics&mine=true
  TikTok:  GET https://open.tiktokapis.com/v2/video/query/

Feeds: Anti-Ban Agent (for strike monitoring), Media Growth Agent (for signals)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, make_event
from packages.state.agent_state import AgentState, append_event, update_stage

log = logging.getLogger(__name__)


async def analytics_agent_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    published_urls = state.get("published_urls") or {}
    brief = state.get("venture_brief") or {}

    log.info("[ANALYTICS_NODE] Fetching channel analytics | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "ANALYTICS_AGENT", "RUNNING",
                    "Fetching platform metrics")

    platform = list(published_urls.keys())[0] if published_urls else "youtube"

    # Phase 2: replace with live YouTube Data API v3 call
    # youtube = build("youtube", "v3", credentials=get_oauth_creds(venture_id, platform))
    # channel_resp = youtube.channels().list(part="statistics", mine=True).execute()
    # stats = channel_resp["items"][0]["statistics"]

    analytics: dict = {
        "venture_id": venture_id,
        "platform": platform,
        "views_total": 0,
        "views_last_28d": 0,
        "subscribers": 0,
        "watch_time_hours": 0.0,
        "avg_view_duration_sec": 0,
        "rpm_usd": brief.get("rpm_estimate_usd", 3.0),
        "estimated_revenue_usd": 0.0,
        "copyright_strikes": 0,
        "community_strikes": 0,
        "dispute_rate_pct": 0.0,
        "api_quota_used_pct": 15.0,
        "mrr_usd": 0.0,
        "days_live": 1,
        "last_fetched": datetime.now(timezone.utc).isoformat(),
    }

    event = make_event(
        EventType.ANALYTICS_UPDATED, AgentID.ANALYTICS_AGENT, AgentID.MEDIA_GROWTH,
        analytics, run_id, venture_id, "ANALYTICS_NODE",
    )

    log_agent_event(run_id, venture_id, "ANALYTICS_AGENT", "SUCCESS",
                    current_task=f"Views: {analytics['views_total']} | Subs: {analytics['subscribers']}")
    log.info("[ANALYTICS_NODE] ✓ Analytics | views=%d subs=%d strikes=%d",
             analytics["views_total"], analytics["subscribers"], analytics["copyright_strikes"])

    new_state = update_stage(state, "ANTI_BAN_NODE")
    return append_event({**new_state, "channel_analytics": analytics}, event.model_dump())
