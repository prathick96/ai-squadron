"""
packages/agents/media/script_agent.py
Script Agent — channel_strategy → platform-optimised video script.

Model:   gemini-2.0-flash
Input:   channel_strategy from Media VP + venture_brief
Output:  script_package (hook, body sections, CTA, word count, duration)

Platform pacing:
  YouTube long-form : 1,800–2,500 words, 8–12 min
  TikTok            : 150–200 words,   45–60 sec
  Instagram Reels   : 100–150 words,   30–45 sec
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, make_event
from packages.state.agent_state import AgentState, ScriptPackage, append_event, update_stage
from packages.tools.llm import call_llm

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Script Agent for AI Squadron's Media Department.
You write viral, platform-optimised scripts for faceless AI channels.

Script structure:
- HOOK (first 5 seconds): one bold statement or question — must create pattern interrupt
- BODY: 3-5 clear sections answering the viewer's core question
- CTA: one specific action (subscribe, comment, follow link)

Rules:
- Never mention "I" as a person — faceless channel
- Never reveal the channel is AI-generated
- Use the hook formula from the channel strategy
- Optimise for watch time: end each section with a forward-hook

Output ONLY valid JSON — no markdown.
"""

_TEMPLATE = """
Channel Strategy:
{channel_strategy}

Primary platform: {platform}
Content pillar: {pillar}
Target keyword: {keyword}

Generate a complete script:
{{
  "title": "...",
  "hook": "First 5 seconds — one bold statement",
  "body_sections": [
    {{"section": 1, "heading": "...", "content": "...", "forward_hook": "..."}}
  ],
  "cta": "...",
  "word_count": 0,
  "estimated_duration_sec": 0,
  "platform": "{platform}",
  "target_keyword": "{keyword}",
  "thumbnail_concept": "Visual description for thumbnail agent"
}}
"""


async def script_agent_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    strategy = state.get("channel_strategy") or {}
    is_retry = state.get("qa_retry_count", 0) > 0

    platform = strategy.get("primary_platform", "youtube")
    pillars = strategy.get("content_pillars", [{}])
    pillar = pillars[0].get("pillar", "AI productivity") if pillars else "AI productivity"
    keywords = pillars[0].get("target_keywords", ["AI tools"]) if pillars else ["AI tools"]
    keyword = keywords[0] if keywords else "AI tools"

    task = "Regenerating script from QA critique" if is_retry else "Writing script"
    log.info("[SCRIPT_NODE] %s | venture=%s platform=%s", task, venture_id, platform)
    log_agent_event(run_id, venture_id, "SCRIPT_AGENT", "RUNNING", task)

    user_prompt = _TEMPLATE.format(
        channel_strategy=json.dumps(strategy, indent=2),
        platform=platform,
        pillar=pillar,
        keyword=keyword,
    )

    try:
        response = await call_llm("SCRIPT_AGENT", _SYSTEM_PROMPT, user_prompt, temperature=0.6)
        script_data: dict = json.loads(response.text)
    except Exception as exc:
        log.error("[SCRIPT_NODE] failed: %s", exc)
        log_agent_event(run_id, venture_id, "SCRIPT_AGENT", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    script_package: ScriptPackage = {
        "hook": script_data.get("hook", ""),
        "body_sections": script_data.get("body_sections", []),
        "cta": script_data.get("cta", ""),
        "word_count": script_data.get("word_count", 0),
        "estimated_duration_sec": script_data.get("estimated_duration_sec", 0),
        "platform": platform,
        "title": script_data.get("title", ""),
        "target_keyword": keyword,
        "thumbnail_concept": script_data.get("thumbnail_concept", ""),
    }

    log_agent_event(run_id, venture_id, "SCRIPT_AGENT", "SUCCESS", tokens_used=response.total_tokens)
    log.info("[SCRIPT_NODE] ✓ Script | words=%d duration=%ds platform=%s",
             script_package["word_count"], script_package["estimated_duration_sec"], platform)

    event = make_event(
        EventType.SCRIPT_READY, AgentID.SCRIPT_AGENT, AgentID.VOICE_AGENT,
        {}, run_id, venture_id, "SCRIPT_NODE",
        token_cost=response.total_tokens, latency_ms=response.latency_ms,
    )

    new_state = update_stage(state, "VOICE_NODE")
    return append_event({**new_state, "script_package": script_package}, event.model_dump())
