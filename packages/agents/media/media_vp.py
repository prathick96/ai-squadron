"""
packages/agents/media/media_vp.py
Media VP — department head for all faceless content channels.

Model:   gemini-2.0-flash
Input:   VentureBrief from Grand CEO
Output:  Content strategy memo routed to Script Agent

The Media VP owns channel identity, content pillars, upload cadence,
monetisation strategy (AdSense + affiliate + sponsorships), and
the platform-specific growth playbook.
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, MediaVPBriefPayload, make_event
from packages.state.agent_state import AgentState, append_event, update_stage
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Media VP of AI Squadron's Media Department.
You create faceless AI content channels that generate consistent AdSense + affiliate revenue.

Your role: channel strategy.
- Define 3 content pillars (recurring topic clusters that build authority)
- Set upload cadence: YouTube 3x/week, TikTok 1x/day
- Choose the primary monetisation path: AdSense (high-RPM niche) vs affiliate vs both
- Identify the #1 competitor channel to reverse-engineer
- Define the hook formula that works for this niche

Output ONLY valid JSON — no markdown.
"""

_TEMPLATE = """
VentureBrief from Grand CEO:
{venture_brief}

Produce a Channel Strategy Memo:
{{
  "venture_id": "{venture_id}",
  "channel_name": "...",
  "channel_tagline": "One sentence channel promise",
  "primary_platform": "youtube | tiktok | instagram",
  "secondary_platforms": ["..."],
  "content_pillars": [
    {{"pillar": "...", "topics": ["...", "..."], "target_keywords": ["..."]}}
  ],
  "upload_cadence": {{
    "youtube": "3x_weekly | daily | 2x_weekly",
    "tiktok": "daily | 2x_daily"
  }},
  "hook_formula": "...",
  "monetisation": {{
    "primary": "adsense | affiliate | sponsorship",
    "affiliate_programs": ["..."],
    "rpm_target_usd": 0.0
  }},
  "competitor_to_reverse_engineer": "channel_url_or_name",
  "target_subs_month_3": 0,
  "target_views_month_1": 0
}}
"""


async def media_vp_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    brief = state.get("venture_brief") or {}

    log.info("[MEDIA_VP_NODE] Building channel strategy | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "MEDIA_VP", "RUNNING", "Channel strategy memo")

    user_prompt = _TEMPLATE.format(
        venture_brief=json.dumps(brief, indent=2),
        venture_id=venture_id,
    )

    try:
        response = await call_llm("MEDIA_VP", _SYSTEM_PROMPT, user_prompt, temperature=0.3)
        memo: dict = json.loads(extract_json(response.text))
    except Exception as exc:
        log.error("[MEDIA_VP_NODE] failed: %s", exc)
        log_agent_event(run_id, venture_id, "MEDIA_VP", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    payload = MediaVPBriefPayload(
        venture_id=venture_id,
        department="MEDIA",
        strategy_memo=memo,
        approved_budget_usd=200.0,
    )
    event = make_event(
        EventType.MEDIA_VP_BRIEFED, AgentID.MEDIA_VP, AgentID.SCRIPT_AGENT,
        payload, run_id, venture_id, "MEDIA_VP_NODE",
        token_cost=response.total_tokens, latency_ms=response.latency_ms,
    )

    log_agent_event(run_id, venture_id, "MEDIA_VP", "SUCCESS", tokens_used=response.total_tokens)
    log.info("[MEDIA_VP_NODE] ✓ Strategy memo | channel=%s platform=%s",
             memo.get("channel_name"), memo.get("primary_platform"))

    new_state = update_stage(state, "SCRIPT_NODE")
    return append_event({**new_state, "channel_strategy": memo}, event.model_dump())
