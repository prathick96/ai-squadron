"""
packages/agents/media/thumbnail_agent.py
Thumbnail Agent — script concept → high-CTR thumbnail via fal.ai Flux.

Model:   fal.ai flux/schnell or flux/dev (image generation)
Input:   script_package.thumbnail_concept, channel_strategy
Output:  thumbnail_package with 1280x720 PNG path

Phase 1: stub — returns mock thumbnail_package
Phase 2: wire fal.ai API
  POST https://fal.run/fal-ai/flux/schnell
  {"prompt": "...", "width": 1280, "height": 720, "num_images": 3}
  Select highest-contrast result, upload to Supabase Storage

CTR optimisation:
  - High contrast background (red, yellow, electric blue)
  - Large face or bold number (e.g. "$47K")
  - Max 3 words of text overlay
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, make_event
from packages.state.agent_state import AgentState, ThumbnailPackage, append_event, update_stage
from packages.tools.llm import call_llm

log = logging.getLogger(__name__)

_PROMPT_SYSTEM = """
You are a thumbnail art director for high-CTR YouTube thumbnails.
Given a video concept, write a detailed image generation prompt.

Rules:
- High contrast background (never grey or white)
- Include one bold element: large number, shocked face, or dramatic object
- Max 3 words of text overlay (describe placement and text)
- Photorealistic style unless explicitly otherwise

Output ONLY a single JSON object:
{"image_prompt": "...", "text_overlay": "max 3 words", "background_color": "hex"}
"""


async def thumbnail_agent_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    script = state.get("script_package") or {}
    strategy = state.get("channel_strategy") or {}

    concept = script.get("thumbnail_concept", "")
    niche = strategy.get("channel_tagline", "")

    log.info("[THUMBNAIL_NODE] Generating thumbnail | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "THUMBNAIL_AGENT", "RUNNING", "fal.ai image gen")

    # Generate optimised image prompt via LLM
    try:
        resp = await call_llm(
            "THUMBNAIL_AGENT",
            _PROMPT_SYSTEM,
            f"Video concept: {concept}\nChannel niche: {niche}",
            temperature=0.7,
        )
        import json
        prompt_data: dict = json.loads(resp.text)
        image_prompt = prompt_data.get("image_prompt", concept or "professional AI tech thumbnail")
    except Exception:
        image_prompt = concept or "professional AI tech thumbnail, high contrast, bold text"

    # Phase 2: replace stub with fal.ai call
    # import httpx, os
    # async with httpx.AsyncClient() as client:
    #     fal_resp = await client.post(
    #         "https://fal.run/fal-ai/flux/schnell",
    #         headers={"Authorization": f"Key {os.getenv('FAL_API_KEY')}"},
    #         json={"prompt": image_prompt, "width": 1280, "height": 720, "num_images": 3},
    #     )
    #     images = fal_resp.json()["images"]
    #     # Upload best image to Supabase Storage

    thumbnail_package: ThumbnailPackage = {
        "file_path": f"/assets/{venture_id}/thumb_{datetime.now(timezone.utc).strftime('%Y%m%d')}.png",
        "resolution": "1280x720",
        "image_prompt": image_prompt,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    event = make_event(
        EventType.THUMBNAIL_READY, AgentID.THUMBNAIL_AGENT, AgentID.SEO_METADATA_AGENT,
        {}, run_id, venture_id, "THUMBNAIL_NODE",
    )

    log_agent_event(run_id, venture_id, "THUMBNAIL_AGENT", "SUCCESS")
    log.info("[THUMBNAIL_NODE] ✓ Thumbnail | resolution=%s", thumbnail_package["resolution"])

    new_state = update_stage(state, "SEO_METADATA_NODE")
    return append_event({**new_state, "thumbnail_package": thumbnail_package}, event.model_dump())
