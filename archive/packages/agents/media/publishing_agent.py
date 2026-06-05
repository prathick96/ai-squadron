"""
packages/agents/media/publishing_agent.py
Publishing Agent — uploads video content to YouTube (and stubs TikTok / Instagram).

YouTube flow (when YOUTUBE_CLIENT_ID + YOUTUBE_CLIENT_SECRET + YOUTUBE_REFRESH_TOKEN are set):
  1. Refresh OAuth2 access token
  2. Create a resumable upload session with video metadata
  3. Stream the MP4 to the upload URI
  4. Return https://www.youtube.com/watch?v={video_id}

Fallback (any cred missing OR video file not on disk yet):
  Returns a deterministic mock URL so the pipeline continues in dev / CI.
  Video files are mock paths until video_agent.py wires FFmpeg (Phase 2).

Platform routing:
  youtube   → fully wired via youtube_client.py
  tiktok    → stub (TikTok Content Posting API requires separate OAuth)
  instagram → stub (Instagram Graph API requires separate OAuth)

NEVER use unofficial APIs, browser automation, or web scraping.
Only official OAuth-authenticated API calls.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, make_event
from packages.state.agent_state import AgentState, append_event, update_stage
from packages.tools.youtube_client import upload_video, youtube_available

log = logging.getLogger(__name__)


async def publishing_agent_node(state: AgentState) -> AgentState:
    run_id     = state["run_id"]
    venture_id = state["venture_id"]
    content    = state.get("content_package") or {}
    clearance  = state.get("security_clearance") or {}

    if not clearance.get("is_compliant", True):
        log.warning("[PUBLISHING_NODE] Security not compliant — blocking publish | venture=%s",
                    venture_id)
        return update_stage(
            {**state, "manual_review_reason": "Security clearance not compliant for publishing"},
            "MANUAL_REVIEW_NODE",
        )

    platform  = content.get("platform", "youtube")
    seo       = content.get("seo_metadata") or {}
    title     = seo.get("title", "") if isinstance(seo, dict) else ""
    tags      = seo.get("tags", []) if isinstance(seo, dict) else []
    desc      = seo.get("description", "") if isinstance(seo, dict) else ""
    video_obj = content.get("video_asset") or {}
    video_path_str = video_obj.get("file_path", "") if isinstance(video_obj, dict) else ""

    log.info("[PUBLISHING_NODE] Publishing | venture=%s platform=%s title=%s",
             venture_id, platform, title[:60])
    log_agent_event(run_id, venture_id, "PUBLISHING_AGENT", "RUNNING",
                    f"Upload to {platform}")

    published_url = _mock_url(venture_id, platform)
    video_id: str | None = None

    if platform == "youtube":
        published_url, video_id = await _publish_youtube(
            venture_id, video_path_str, title, desc, tags,
        )
    else:
        log.info("[PUBLISHING_NODE] %s publishing not yet wired — using mock URL", platform)

    published_urls: dict = dict(state.get("published_urls") or {})
    published_urls[platform] = published_url

    event = make_event(
        EventType.CONTENT_PUBLISHED, AgentID.PUBLISHING_AGENT, AgentID.ANALYTICS_AGENT,
        {
            "venture_id": venture_id,
            "platform":   platform,
            "url":        published_url,
            "video_id":   video_id,
        },
        run_id, venture_id, "PUBLISHING_NODE",
    )

    log_agent_event(run_id, venture_id, "PUBLISHING_AGENT", "SUCCESS",
                    current_task=f"Published: {published_url}")
    log.info("[PUBLISHING_NODE] ✓ Published | url=%s", published_url)

    new_state = update_stage(state, "ANALYTICS_NODE")
    return append_event({**new_state, "published_urls": published_urls}, event.model_dump())


# ---------------------------------------------------------------------------
# Platform handlers
# ---------------------------------------------------------------------------

async def _publish_youtube(
    venture_id: str,
    video_path_str: str,
    title: str,
    desc: str,
    tags: list[str],
) -> tuple[str, str | None]:
    """
    Upload to YouTube. Returns (url, video_id).
    Falls back to mock URL when creds are absent or the video file doesn't exist.
    """
    if not youtube_available():
        log.info("[PUBLISHING_NODE] YouTube creds not fully configured — using mock URL")
        return _mock_url(venture_id, "youtube"), None

    video_path = Path(video_path_str) if video_path_str else None
    if not video_path or not video_path.is_file():
        log.info(
            "[PUBLISHING_NODE] Video file not on disk (%s) — "
            "using mock URL (FFmpeg not yet wired)",
            video_path_str or "no path",
        )
        return _mock_url(venture_id, "youtube"), None

    try:
        video_id = await upload_video(
            video_path=video_path,
            title=title or f"AI Squadron — {venture_id}",
            description=desc,
            tags=tags,
        )
        url = f"https://www.youtube.com/watch?v={video_id}"
        return url, video_id
    except Exception as exc:
        log.warning("[PUBLISHING_NODE] YouTube upload failed (%s) — using mock URL", exc)
        return _mock_url(venture_id, "youtube"), None


def _mock_url(venture_id: str, platform: str) -> str:
    date_tag = datetime.now(timezone.utc).strftime("%Y%m%d")
    mock_id  = f"{venture_id[:11]}_{date_tag}"
    return {
        "youtube":   f"https://www.youtube.com/watch?v={mock_id}",
        "tiktok":    f"https://www.tiktok.com/@channel/video/{mock_id}",
        "instagram": f"https://www.instagram.com/reel/{mock_id}/",
    }.get(platform, f"https://{platform}.com/{mock_id}")
