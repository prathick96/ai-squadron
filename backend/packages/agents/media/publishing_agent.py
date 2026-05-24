"""
packages/agents/media/publishing_agent.py
Publishing Agent — uploads content to YouTube / TikTok / Instagram.

Model:   rule-engine + official platform APIs (no LLM)
Input:   content_package, account_distribution_plan, security_clearance
Output:  published_urls dict with live video URLs

Phase 1: stub — returns mock URLs
Phase 2: wire live APIs
  YouTube: POST /youtube/v3/videos (multipart upload with resumable session)
  TikTok:  POST https://open.tiktokapis.com/v2/post/publish/video/init/
  Instagram: POST /v19.0/{ig-user-id}/media then /v19.0/{ig-user-id}/media_publish

NEVER use unofficial APIs, browser automation, or web scraping.
Only official OAuth-authenticated API calls.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, make_event
from packages.state.agent_state import AgentState, append_event, update_stage

log = logging.getLogger(__name__)


async def publishing_agent_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    content = state.get("content_package") or {}
    clearance = state.get("security_clearance") or {}
    dist_plan = state.get("account_distribution_plan") or {}

    if not clearance.get("is_compliant", True):
        log.warning("[PUBLISHING_NODE] Security not compliant — blocking publish | venture=%s",
                    venture_id)
        return update_stage({
            **state,
            "manual_review_reason": "Security clearance not compliant for publishing",
        }, "MANUAL_REVIEW_NODE")

    platform = content.get("platform", "youtube")
    seo = content.get("seo_metadata") or {}
    title = seo.get("title", "") if isinstance(seo, dict) else ""
    video_path = (content.get("video_asset") or {}).get("file_path", "")

    log.info("[PUBLISHING_NODE] Publishing | venture=%s platform=%s title=%s",
             venture_id, platform, title[:60])
    log_agent_event(run_id, venture_id, "PUBLISHING_AGENT", "RUNNING",
                    f"Upload to {platform}")

    # Phase 2: replace with live API call matching platform
    # For YouTube:
    # service = build("youtube", "v3", credentials=get_oauth_creds(venture_id, "youtube"))
    # request = service.videos().insert(
    #     part="snippet,status",
    #     body={"snippet": {"title": title, "description": seo.get("description",""),
    #                       "tags": seo.get("tags",[])},
    #           "status": {"privacyStatus": "public"}},
    #     media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
    # )
    # response = request.execute()
    # video_id = response["id"]

    now = datetime.now(timezone.utc)
    mock_video_id = f"{venture_id[:11]}_{now.strftime('%Y%m%d')}"
    platform_url = {
        "youtube":   f"https://www.youtube.com/watch?v={mock_video_id}",
        "tiktok":    f"https://www.tiktok.com/@channel/video/{mock_video_id}",
        "instagram": f"https://www.instagram.com/reel/{mock_video_id}/",
    }.get(platform, f"https://{platform}.com/{mock_video_id}")

    published_urls = state.get("published_urls") or {}
    published_urls[platform] = platform_url

    event = make_event(
        EventType.CONTENT_PUBLISHED, AgentID.PUBLISHING_AGENT, AgentID.ANALYTICS_AGENT,
        {"venture_id": venture_id, "platform": platform, "url": platform_url},
        run_id, venture_id, "PUBLISHING_NODE",
    )

    log_agent_event(run_id, venture_id, "PUBLISHING_AGENT", "SUCCESS",
                    current_task=f"Published: {platform_url}")
    log.info("[PUBLISHING_NODE] ✓ Published | url=%s", platform_url)

    new_state = update_stage(state, "ANALYTICS_NODE")
    return append_event({**new_state, "published_urls": published_urls}, event.model_dump())
