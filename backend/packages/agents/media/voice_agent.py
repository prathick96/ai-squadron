"""
packages/agents/media/voice_agent.py
Voice Agent — script → AI voiceover via ElevenLabs TTS.

Model:   ElevenLabs API (no LLM inference)
Input:   script_package
Output:  voice_package with audio file path, duration, quality score

Phase 1: stub — returns mock voice_package
Phase 2: wire ElevenLabs text-to-speech API
         POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}

Quality gate: human_likeness_score >= 0.85 (checked by QA Compliance)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, make_event
from packages.state.agent_state import AgentState, VoicePackage, append_event, update_stage

log = logging.getLogger(__name__)

_VOICE_MODEL = "eleven_multilingual_v2"
_DEFAULT_VOICE_ID = "rachel_v3"    # Neutral, professional, North American


async def voice_agent_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    script = state.get("script_package") or {}

    duration_sec = script.get("estimated_duration_sec", 480)
    word_count = script.get("word_count", 1800)
    platform = script.get("platform", "youtube")

    log.info("[VOICE_NODE] Generating voiceover | venture=%s words=%d", venture_id, word_count)
    log_agent_event(run_id, venture_id, "VOICE_AGENT", "RUNNING",
                    f"ElevenLabs TTS | {word_count} words")

    # Phase 2: replace with live ElevenLabs call
    # import httpx, os
    # script_text = _flatten_script(script)
    # async with httpx.AsyncClient() as client:
    #     resp = await client.post(
    #         f"https://api.elevenlabs.io/v1/text-to-speech/{_DEFAULT_VOICE_ID}",
    #         headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY")},
    #         json={"text": script_text, "model_id": _VOICE_MODEL,
    #               "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
    #     )
    #     audio_bytes = resp.content
    #     # upload to Supabase Storage, get signed URL

    voice_package: VoicePackage = {
        "file_path": f"/assets/{venture_id}/voice_{datetime.now(timezone.utc).strftime('%Y%m%d')}.mp3",
        "duration_sec": duration_sec,
        "voice_model": f"ElevenLabs:{_DEFAULT_VOICE_ID}:{_VOICE_MODEL}",
        "human_likeness_score": 0.92,   # Phase 2: real score from quality classifier
        "word_count": word_count,
        "platform": platform,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    event = make_event(
        EventType.VOICE_READY, AgentID.VOICE_AGENT, AgentID.VIDEO_AGENT,
        {}, run_id, venture_id, "VOICE_NODE",
    )

    log_agent_event(run_id, venture_id, "VOICE_AGENT", "SUCCESS",
                    current_task=f"human_likeness={voice_package['human_likeness_score']:.2f}")
    log.info("[VOICE_NODE] ✓ Voice | duration=%ds hls=%.2f",
             duration_sec, voice_package["human_likeness_score"])

    new_state = update_stage(state, "VIDEO_NODE")
    return append_event({**new_state, "voice_package": voice_package}, event.model_dump())


def _flatten_script(script: dict) -> str:
    """Concatenate script sections into a single TTS string."""
    parts = [script.get("hook", "")]
    for section in script.get("body_sections", []):
        if isinstance(section, dict):
            parts.append(section.get("content", ""))
    parts.append(script.get("cta", ""))
    return " ".join(p for p in parts if p)
