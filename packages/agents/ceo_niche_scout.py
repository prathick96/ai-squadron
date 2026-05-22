"""
packages/agents/ceo_niche_scout.py
CEO Node — Niche Scout
Model: gemini-2.5-pro
Consumes Research Dossier from Market Research Council → outputs VentureBrief
"""
from __future__ import annotations

import json
import logging
import uuid

from packages.db.client import log_agent_event, upsert_venture
from packages.schemas.events import (
    AgentID, EventType, VentureBriefPayload, make_event
)
from packages.state.agent_state import AgentState, VentureBrief, append_event, update_stage
from packages.tools.llm import call_llm

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the CEO Agent of AI Squadron — the sole decision maker for venture selection.

You receive a Research Dossier from the Market Research Council (3 Kimi scouts + debate).
The scouts may be wrong. Your job is to synthesize, challenge weak evidence, and output
one VentureBrief JSON object.

Rules:
- Only recommend niches with feasibility_score >= 0.65 and competition_score <= 0.55
- venture_type must be exactly one of: MICRO_SAAS, MEDIA_CHANNEL, AFFILIATE_SITE
- go_decision must be true only if feasibility >= 0.70 AND council evidence supports it
- Reject the council's primary niche if skeptic evidence outweighs opportunity evidence
- All numeric scores between 0.0 and 1.0; tam_usd_millions must be conservative
- Output ONLY valid JSON — no markdown, no preamble
"""

_USER_PROMPT_TEMPLATE = """
Research Dossier (from Market Research Council):
{research_dossier}

Council recommended primary niche: {primary_niche}
Council confidence: {council_confidence}
Council recommended venture type: {venture_type}

Synthesis from debate:
{debate_synthesis}

Generate ONE VentureBrief for the best niche you approve (may differ from council pick).

Return ONLY this JSON structure:
{{
  "venture_id": "ven_{short_id}",
  "venture_type": "MICRO_SAAS | MEDIA_CHANNEL | AFFILIATE_SITE",
  "niche": "...",
  "target_region": ["US", "..."],
  "target_audience": "...",
  "rpm_estimate_usd": 0.0,
  "competition_score": 0.0,
  "feasibility_score": 0.0,
  "tam_usd_millions": 0.0,
  "top_competitors": [{{"name": "...", "weakness": "...", "moat_gap": "..."}}],
  "recommended_monetization": ["..."],
  "content_angles": ["..."],
  "go_decision": true,
  "go_rationale": "Reference council disagreements and your override if any"
}}
"""


async def ceo_niche_scout_node(state: AgentState) -> AgentState:
    """LangGraph node — CEO refinement after Research Council."""
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    dossier = state.get("research_dossier") or {}

    if not dossier:
        log.error("[CEO_NODE] No research_dossier — run RESEARCH_NODE first")
        return {**state, "last_error": "missing research_dossier"}

    log.info("[CEO_NODE] Refining council dossier | run=%s", run_id)
    log_agent_event(
        run_id, venture_id, "CEO_NICHE_SCOUT", "RUNNING",
        current_task="CEO synthesis from Research Council dossier",
    )

    debate = dossier.get("debate_summary") or {}
    if isinstance(debate, dict):
        synthesis = debate.get("synthesis", "")
    else:
        synthesis = ""

    short_id = uuid.uuid4().hex[:8]
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        research_dossier=json.dumps(
            {k: v for k, v in dossier.items() if k != "debate_transcript"},
            indent=2,
        ),
        primary_niche=dossier.get("recommended_primary_niche", "unknown"),
        council_confidence=dossier.get("council_confidence", 0.0),
        venture_type=dossier.get("recommended_venture_type", "MICRO_SAAS"),
        debate_synthesis=synthesis,
        short_id=short_id,
    )

    try:
        response = await call_llm(
            agent_role="CEO_NICHE_SCOUT",
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.35,
        )
        brief_data: dict = json.loads(response.text)
    except (json.JSONDecodeError, Exception) as exc:
        log.error("[CEO_NODE] LLM call failed: %s", exc)
        log_agent_event(run_id, venture_id, "CEO_NICHE_SCOUT", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    brief_payload = VentureBriefPayload(**brief_data)

    upsert_venture({
        "venture_id": brief_payload.venture_id,
        "venture_type": brief_payload.venture_type,
        "niche": brief_payload.niche,
        "status": "IDEATION",
        "go_decision": brief_payload.go_decision,
        "feasibility_score": brief_payload.feasibility_score,
        "competition_score": brief_payload.competition_score,
        "target_regions": brief_payload.target_region,
    })

    event = make_event(
        event_type=EventType.VENTURE_BRIEF_READY,
        source_agent=AgentID.CEO_NICHE_SCOUT,
        target_agent=AgentID.PRODUCT_TEAM,
        payload=brief_payload,
        run_id=run_id,
        venture_id=brief_payload.venture_id,
        pipeline_stage="CEO_NODE",
        token_cost=response.total_tokens,
        latency_ms=response.latency_ms,
    )

    log_agent_event(
        run_id, venture_id, "CEO_NICHE_SCOUT", "SUCCESS",
        tokens_used=response.total_tokens,
        latency_ms=response.latency_ms,
    )
    log.info(
        "[CEO_NODE] ✓ VentureBrief | niche=%s go=%s (council was %s)",
        brief_payload.niche,
        brief_payload.go_decision,
        dossier.get("recommended_primary_niche"),
    )

    venture_brief: VentureBrief = brief_data  # type: ignore[assignment]
    new_state = update_stage(state, "PRODUCT_NODE")
    new_state = {
        **new_state,
        "venture_id": brief_payload.venture_id,
        "venture_brief": venture_brief,
    }
    return append_event(new_state, event.model_dump())
