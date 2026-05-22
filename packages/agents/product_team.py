"""
packages/agents/product_team.py
Product Team Node — Translates VentureBrief → TechSpec or ContentStrategy
Model: gemini-2.0-flash
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, TechSpecPayload, make_event
from packages.state.agent_state import AgentState, TechSpec, append_event, update_stage
from packages.tools.llm import call_llm

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Product Team Agent. You receive a VentureBrief and produce a TechSpec.
For MICRO_SAAS ventures: define features, data models, API routes, and stack.
For MEDIA_CHANNEL ventures: define content strategy, upload cadence, and monetization hooks.
Output ONLY valid JSON — no markdown fences, no preamble.
Keep features to P0 (must-have) only. Max 5 features for MVP.
"""

_TEMPLATE = """
VentureBrief:
{venture_brief}

Produce a TechSpec JSON:
{{
  "venture_id": "{venture_id}",
  "product_type": "MICRO_SAAS",
  "stack": {{"frontend": "React 19 + Vite", "backend": "Python FastAPI",
             "database": "PostgreSQL", "auth": "Supabase Auth", "hosting": "Vercel"}},
  "features": [{{"feature_id": "feat_001", "name": "...", "priority": "P0",
                 "user_story": "...", "acceptance_criteria": ["..."],
                 "estimated_components": ["..."]}}],
  "data_models": {{"ModelName": {{"field": "type"}}}},
  "api_routes": [{{"method": "POST", "path": "/api/...", "description": "..."}}],
  "estimated_build_tokens": 0,
  "component_count": 0,
  "complexity": "LOW"
}}
"""


async def product_team_node(state: AgentState) -> AgentState:
    run_id     = state["run_id"]
    venture_id = state["venture_id"]
    brief      = state.get("venture_brief") or {}

    log.info("[PRODUCT_NODE] Building TechSpec | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "PRODUCT_TEAM", "RUNNING", "Generating TechSpec")

    user_prompt = _TEMPLATE.format(
        venture_brief=json.dumps(brief, indent=2),
        venture_id=venture_id,
    )

    try:
        response  = await call_llm("PRODUCT_TEAM", _SYSTEM_PROMPT, user_prompt, temperature=0.2)
        spec_data: dict = json.loads(response.text)
    except Exception as exc:
        log.error("[PRODUCT_NODE] failed: %s", exc)
        log_agent_event(run_id, venture_id, "PRODUCT_TEAM", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    spec_payload = TechSpecPayload(**spec_data)

    event = make_event(
        event_type    = EventType.TECH_SPEC_READY,
        source_agent  = AgentID.PRODUCT_TEAM,
        target_agent  = AgentID.ENGINEERING_TEAM,
        payload       = spec_payload,
        run_id        = run_id,
        venture_id    = venture_id,
        pipeline_stage= "PRODUCT_NODE",
        token_cost    = response.total_tokens,
        latency_ms    = response.latency_ms,
    )

    log_agent_event(run_id, venture_id, "PRODUCT_TEAM", "SUCCESS",
                    tokens_used=response.total_tokens)
    log.info("[PRODUCT_NODE] ✓ TechSpec ready | complexity=%s components=%d",
             spec_payload.complexity, spec_payload.component_count)

    tech_spec: TechSpec = spec_data  # type: ignore[assignment]
    new_state = update_stage(state, "ENGINEERING_NODE")
    return append_event({**new_state, "tech_spec": tech_spec}, event.model_dump())
