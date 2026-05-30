"""
packages/agents/media/video_agent.py
Video Agent — voice + B-roll → final MP4 via FFmpeg.

Model:   FFmpeg (no LLM — deterministic media processing)
Input:   voice_package, script_package
Output:  video_package with encoded MP4 path

Phase 1: stub — returns mock video_package
Phase 2: wire FFmpeg pipeline
  1. Download voice audio from Supabase Storage
  2. Fetch B-roll clips (Pexels API or pre-downloaded stock)
  3. Burn in captions (whisper → SRT → ffmpeg subtitles filter)
  4. Encode: H.264, 1080p, 30fps, AAC 192kbps
  5. Upload final MP4 to Supabase Storage

Spec: 1920x1080, H.264 Baseline, < 500 MB per video
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, VideoReadyPayload, make_event
from packages.state.agent_state import AgentState, VideoPackage, append_event, update_stage

log = logging.getLogger(__name__)


async def video_agent_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    voice = state.get("voice_package") or {}

    duration_sec = voice.get("duration_sec", 480)
    platform = voice.get("platform", "youtube")

    log.info("[VIDEO_NODE] Assembling video | venture=%s duration=%ds",
             venture_id, duration_sec)
    log_agent_event(run_id, venture_id, "VIDEO_AGENT", "RUNNING",
                    f"FFmpeg encode | {duration_sec}s")

    # Phase 2: replace with live FFmpeg subprocess call
    # import subprocess, asyncio
    # cmd = [
    #     "ffmpeg", "-y",
    #     "-i", voice["file_path"],
    #     "-vf", "subtitles=captions.srt",
    #     "-c:v", "libx264", "-preset", "fast", "-crf", "23",
    #     "-c:a", "aac", "-b:a", "192k",
    #     "-r", "30", "-s", "1920x1080",
    #     output_path,
    # ]
    # proc = await asyncio.create_subprocess_exec(*cmd)
    # await proc.wait()

    video_package: VideoPackage = {
        "file_path": f"/assets/{venture_id}/video_{datetime.now(timezone.utc).strftime('%Y%m%d')}.mp4",
        "resolution": "1920x1080",
        "duration_sec": duration_sec,
        "has_captions": True,
        "codec": "H.264",
        "fps": 30,
        "size_mb": round(duration_sec * 0.5, 1),   # ~0.5 MB/sec at target bitrate
        "platform": platform,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    event = make_event(
        EventType.VIDEO_READY, AgentID.VIDEO_AGENT, AgentID.THUMBNAIL_AGENT,
        VideoReadyPayload(
            venture_id=venture_id,
            duration_sec=video_package["duration_sec"],
            resolution=video_package.get("resolution", "1920x1080"),
            size_mb=video_package.get("size_mb", 0.0),
        ),
        run_id, venture_id, "VIDEO_NODE",
    )

    log_agent_event(run_id, venture_id, "VIDEO_AGENT", "SUCCESS",
                    current_task=f"{video_package['size_mb']:.1f} MB | {duration_sec}s")
    log.info("[VIDEO_NODE] ✓ Video | size=%.1f MB resolution=%s",
             video_package["size_mb"], video_package["resolution"])

    new_state = update_stage(state, "THUMBNAIL_NODE")
    return append_event({**new_state, "video_package": video_package}, event.model_dump())
