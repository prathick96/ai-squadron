"""
packages/agents/product/product_vp.py
Product VP — department head for all SaaS and affiliate builds.

Model:   gemini-2.0-flash
Input:   VentureBrief from Grand CEO
Output:  Product strategy memo routed to Product Manager

The Product VP translates the CEO's venture brief into an executable
product strategy: prioritised feature list, monetisation mechanics,
launch sequence, and success metrics for the quarter.
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, ProductVPBriefPayload, make_event
from packages.state.agent_state import AgentState, append_event, update_stage
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Product VP of AI Squadron's Product Department.
You receive a VentureBrief and produce a product strategy memo.

Your role: translate CEO vision into actionable P0 requirements.
- Maximum 5 P0 features for MVP. Ruthlessly cut anything nice-to-have.
- Define the one metric that proves product-market fit (activation rate, D7 retention, etc.)
- Define the monetisation hook: freemium gate, trial length, upgrade trigger
- Set a realistic 30-day go-live target

Output ONLY valid JSON — no markdown.
"""

_TEMPLATE = """
VentureBrief from Grand CEO:
{venture_brief}

Produce a Product Strategy Memo:
{{
  "venture_id": "{venture_id}",
  "product_name": "...",
  "tagline": "One sentence value prop",
  "p0_features": [
    {{"id": "feat_01", "name": "...", "why": "...", "acceptance": "..."}}
  ],
  "monetisation": {{
    "model": "freemium | subscription | one_time | usage_based",
    "price_usd": 0.0,
    "trial_days": 14,
    "upgrade_trigger": "..."
  }},
  "north_star_metric": "...",
  "target_activation_rate_pct": 0.0,
  "go_live_target_days": 30,
  "stack_notes": "Any stack constraints or preferences"
}}
"""


async def product_vp_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    brief = state.get("venture_brief") or {}

    log.info("[PRODUCT_VP_NODE] Building product strategy | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "PRODUCT_VP", "RUNNING", "Translating VentureBrief → strategy")

    user_prompt = _TEMPLATE.format(
        venture_brief=json.dumps(brief, indent=2),
        venture_id=venture_id,
    )

    try:
        response = await call_llm("PRODUCT_VP", _SYSTEM_PROMPT, user_prompt, temperature=0.2)
        memo: dict = json.loads(extract_json(response.text))
    except Exception as exc:
        log.error("[PRODUCT_VP_NODE] failed: %s", exc)
        log_agent_event(run_id, venture_id, "PRODUCT_VP", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    payload = ProductVPBriefPayload(
        venture_id=venture_id,
        department="PRODUCT",
        strategy_memo=memo,
        approved_budget_usd=500.0,
    )
    event = make_event(
        EventType.PRODUCT_VP_BRIEFED, AgentID.PRODUCT_VP, AgentID.PRODUCT_MANAGER,
        payload, run_id, venture_id, "PRODUCT_VP_NODE",
        token_cost=response.total_tokens, latency_ms=response.latency_ms,
    )

    log_agent_event(run_id, venture_id, "PRODUCT_VP", "SUCCESS", tokens_used=response.total_tokens)
    log.info("[PRODUCT_VP_NODE] ✓ Strategy memo ready | product=%s", memo.get("product_name"))

    new_state = update_stage(state, "PRODUCT_MANAGER_NODE")
    return append_event({**new_state, "product_strategy": memo}, event.model_dump())
