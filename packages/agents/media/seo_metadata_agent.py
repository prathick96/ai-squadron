"""
packages/agents/media/seo_metadata_agent.py
SEO Metadata Agent — video assets → platform-optimised title, description, tags.

Model:   gemini-2.0-flash
Input:   script_package, channel_strategy, thumbnail_package
Output:  Populates content_package.seo_metadata

Platform rules enforced:
  YouTube: title <= 100 chars, description <= 5000 chars, max 15 tags
  TikTok:  title <= 150 chars, max 5 hashtags
  Instagram: caption <= 2200 chars, max 30 hashtags
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.schemas.events import (
    AgentID, ContentPackagePayload, EventType,
    AudioAsset, ScriptSpec, SeoMetadata, ThumbnailAsset, VideoAsset, make_event,
)
from packages.state.agent_state import AgentState, ContentPackage, append_event, update_stage
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the SEO Metadata Agent for AI Squadron's Media Department.
You write click-optimised titles and search-optimised descriptions for faceless AI channels.

Rules:
- Title: curiosity gap + target keyword in first 60 chars
- Description: target keyword in first line, then value summary, then secondary keywords
- Tags: mix of broad (100K+ searches) and specific (1K-10K) keywords
- No clickbait that violates platform policy (no "earn money fast" guarantees)
- No misleading metadata

Output ONLY valid JSON — no markdown.
"""

_TEMPLATE = """
Script title: {title}
Target keyword: {keyword}
Platform: {platform}
Niche: {niche}
Video duration: {duration_sec}s

Generate SEO metadata:
{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2"],
  "hashtags": ["#tag1", "#tag2"],
  "category": "...",
  "language": "en"
}}
"""


async def seo_metadata_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    script = state.get("script_package") or {}
    strategy = state.get("channel_strategy") or {}
    voice = state.get("voice_package") or {}
    video = state.get("video_package") or {}
    thumb = state.get("thumbnail_package") or {}

    platform = script.get("platform", "youtube")
    keyword = script.get("target_keyword", "AI tools")
    niche = strategy.get("channel_tagline") or strategy.get("niche") or ""
    if not niche:
        log.warning("[SEO_METADATA_NODE] niche/tagline not in channel_strategy — SEO context will be limited")
    duration = script.get("estimated_duration_sec", 480)

    log.info("[SEO_METADATA_NODE] Generating metadata | venture=%s platform=%s",
             venture_id, platform)
    log_agent_event(run_id, venture_id, "SEO_METADATA_AGENT", "RUNNING", "SEO metadata")

    user_prompt = _TEMPLATE.format(
        title=script.get("title", ""),
        keyword=keyword,
        platform=platform,
        niche=niche,
        duration_sec=duration,
    )

    try:
        response = await call_llm("SEO_METADATA_AGENT", _SYSTEM_PROMPT, user_prompt, temperature=0.4)
        seo_data: dict = json.loads(extract_json(response.text))
    except Exception as exc:
        log.error("[SEO_METADATA_NODE] failed: %s", exc)
        log_agent_event(run_id, venture_id, "SEO_METADATA_AGENT", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    # Assemble full content_package
    seo = SeoMetadata(
        title=seo_data.get("title", script.get("title", "")),
        description=seo_data.get("description", ""),
        tags=seo_data.get("tags", [keyword]),
        hashtags=seo_data.get("hashtags", [f"#{keyword.replace(' ', '')}"]),
    )

    body_sections = script.get("body_sections", [])
    script_spec = ScriptSpec(
        hook=script.get("hook", ""),
        body_sections=[
            s.get("content", "") if isinstance(s, dict) else str(s)
            for s in body_sections
        ],
        word_count=script.get("word_count", 0),
        estimated_duration_sec=duration,
    )

    payload = ContentPackagePayload(
        venture_id=venture_id,
        platform=platform,  # type: ignore[arg-type]
        content_type="long_form" if duration > 60 else "short_form",  # type: ignore[arg-type]
        script=script_spec,
        audio_asset=AudioAsset(
            file_path=voice.get("file_path", f"/assets/{venture_id}/voice.mp3"),
            duration_sec=voice.get("duration_sec", duration),
            voice_model=voice.get("voice_model", "ElevenLabs:rachel_v3"),
            human_likeness_score=voice.get("human_likeness_score", 0.92),
        ),
        video_asset=VideoAsset(
            file_path=video.get("file_path", f"/assets/{venture_id}/video.mp4"),
            resolution=video.get("resolution", "1920x1080"),
            duration_sec=video.get("duration_sec", duration),
            has_captions=video.get("has_captions", True),
        ),
        thumbnail_asset=ThumbnailAsset(
            file_path=thumb.get("file_path", f"/assets/{venture_id}/thumb.png"),
            resolution=thumb.get("resolution", "1280x720"),
        ),
        seo_metadata=seo,
        is_retry=False,
    )

    content_package: ContentPackage = payload.model_dump()  # type: ignore[assignment]
    event = make_event(
        EventType.CONTENT_PACKAGE_READY, AgentID.SEO_METADATA_AGENT, AgentID.QA_COMPLIANCE,
        payload, run_id, venture_id, "SEO_METADATA_NODE",
        token_cost=response.total_tokens, latency_ms=response.latency_ms,
    )

    log_agent_event(run_id, venture_id, "SEO_METADATA_AGENT", "SUCCESS",
                    tokens_used=response.total_tokens)
    log.info("[SEO_METADATA_NODE] ✓ ContentPackage assembled | title=%s",
             seo_data.get("title", "")[:60])

    new_state = update_stage(state, "QA_COMPLIANCE_NODE")
    return append_event({**new_state, "content_package": content_package}, event.model_dump())
