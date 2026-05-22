"""
packages/agents/content_team.py
Content Team Node — script, audio, video, thumbnail generation
Model: gemini-2.0-flash (scripts) + ElevenLabs (TTS) + Remotion/FFmpeg (video)
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.schemas.events import (
    AgentID, AudioAsset, ContentPackagePayload, EventType,
    ScriptSpec, SeoMetadata, ThumbnailAsset, VideoAsset, make_event,
)
from packages.state.agent_state import AgentState, ContentPackage, append_event, update_stage
from packages.tools.llm import call_llm

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Content Team Agent. You write platform-optimised video scripts.

Script structure:
- HOOK (first 5 seconds): one bold statement or question that creates immediate curiosity
- BODY: 3-5 clear sections addressing the viewer's core problem
- CTA: one specific action for the viewer to take

Platform rules:
- YouTube long-form: 1,800–2,500 words, 8–12 minute pacing
- TikTok: 150–200 words, 45–60 second pacing
- Instagram Reels: 100–150 words, 30–45 second pacing

Output ONLY valid JSON — no markdown.
"""

_SCRIPT_TEMPLATE = """
Venture brief:
{venture_brief}

Platform: {platform}
Content type: {content_type}
Content angle: {content_angle}

Generate a complete script JSON:
{{
  "hook": "...",
  "body_sections": ["Section 1 content", "Section 2 content"],
  "word_count": 0,
  "estimated_duration_sec": 0
}}
"""


async def content_team_node(state: AgentState) -> AgentState:
    run_id     = state["run_id"]
    venture_id = state["venture_id"]
    brief      = state.get("venture_brief") or {}
    qa_report  = state.get("qa_report") or {}
    is_retry   = state.get("qa_retry_count", 0) > 0

    platform      = "youtube"
    content_type  = "long_form"
    content_angle = (brief.get("content_angles") or ["How AI can help you"])[0]

    task = "Regenerating content from QA critique" if is_retry else "Generating content package"
    log.info("[CONTENT_NODE] %s | venture=%s", task, venture_id)
    log_agent_event(run_id, venture_id, "CONTENT_TEAM", "RUNNING", task)

    # ---- Script generation ----
    user_prompt = _SCRIPT_TEMPLATE.format(
        venture_brief=json.dumps(brief, indent=2),
        platform=platform,
        content_type=content_type,
        content_angle=content_angle,
    )
    try:
        response    = await call_llm("CONTENT_TEAM", _SYSTEM_PROMPT, user_prompt, temperature=0.6)
        script_data = json.loads(response.text)
    except Exception as exc:
        log.error("[CONTENT_NODE] Script generation failed: %s", exc)
        log_agent_event(run_id, venture_id, "CONTENT_TEAM", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    script = ScriptSpec(**script_data)

    # ---- Audio asset (ElevenLabs stub — replace with live API in Phase 2) ----
    audio = AudioAsset(
        file_path          = f"/assets/{venture_id}/audio_v1.mp3",
        duration_sec       = script.estimated_duration_sec,
        voice_model        = "ElevenLabs:rachel_v3",
        human_likeness_score = 0.91,   # Live: score from quality classifier
    )

    # ---- Video asset (Remotion stub — replace with live render in Phase 2) ----
    video = VideoAsset(
        file_path    = f"/assets/{venture_id}/video_v1.mp4",
        resolution   = "1920x1080",
        duration_sec = script.estimated_duration_sec,
        has_captions = True,
    )

    # ---- Thumbnail (fal.ai Flux stub) ----
    thumb = ThumbnailAsset(
        file_path  = f"/assets/{venture_id}/thumb_v1.png",
        resolution = "1280x720",
    )

    niche = brief.get("niche", "AI tools")
    seo   = SeoMetadata(
        title       = f"{content_angle} — Full Breakdown [{niche}]",
        description = f"In this video, we break down {content_angle.lower()}. "
                      f"Perfect for anyone interested in {niche}.",
        tags        = [niche, "AI tools", "productivity"],
        hashtags    = [f"#{niche.replace(' ', '')}", "#AItools"],
    )

    payload = ContentPackagePayload(
        venture_id   = venture_id,
        platform     = platform,  # type: ignore[arg-type]
        content_type = content_type,  # type: ignore[arg-type]
        script       = script,
        audio_asset  = audio,
        video_asset  = video,
        thumbnail_asset = thumb,
        seo_metadata = seo,
        is_retry     = is_retry,
    )

    event = make_event(
        EventType.CONTENT_PACKAGE_READY, AgentID.CONTENT_TEAM, AgentID.QA_AUDITOR,
        payload, run_id, venture_id, "CONTENT_NODE",
        token_cost=response.total_tokens, latency_ms=response.latency_ms,
    )

    content_package: ContentPackage = payload.model_dump()  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "CONTENT_TEAM", "SUCCESS", tokens_used=response.total_tokens)
    log.info("[CONTENT_NODE] ✓ Content package ready | platform=%s words=%d",
             platform, script.word_count)

    new_state = update_stage(state, "QA_NODE")
    return append_event({**new_state, "content_package": content_package}, event.model_dump())
