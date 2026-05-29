"""
packages/agents/governance/grand_ceo.py
Grand CEO Agent — Portfolio governor and go/no-go decision maker.

Model:   gemini-2.0-flash (swap to 2.5-pro once key has Pro access)
Input:   ResearchDossier from Research Council + portfolio Growth Reports
Output:  VentureBrief (niche approved) + department routing (PRODUCT or MEDIA)

The CEO does NOT write code, post content, or manage accounts.
It synthesises, challenges weak evidence, and decides.

Decision philosophy:
  Jobs  — Say no to 1,000 things. Focus is about elimination, not prioritisation.
  Musk  — First principles: question every assumption. Set aggressive timelines.
  Zuck  — Growth loops first. Build feedback into the product from day one.
"""
from __future__ import annotations

import json
import logging
import uuid

from packages.db.client import log_agent_event, upsert_venture
from packages.schemas.events import (
    AgentID, EventType, VentureBriefPayload, make_event,
)
from packages.state.agent_state import AgentState, VentureBrief, append_event, update_stage
from packages.tools.llm import call_llm

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Grand CEO of AI Squadron — an autonomous venture organisation that builds
SaaS products and media channels at scale.

Your decision philosophy draws from three frameworks:

STEVE JOBS — Eliminate. Say no to 1,000 good ideas to say yes to one great one.
  - If the value proposition cannot be stated in one sentence, reject it.
  - If we are building something users need to be educated to want, reject it.
  - Beauty of design = removing everything that doesn't need to be there.

ELON MUSK — First principles. Question every industry assumption.
  - Why does this have to work this way? What is the physics of this problem?
  - Set aggressive timelines. A 70% decision made in an hour beats 95% in a week.
  - If a niche requires a dependency we cannot control, build the dependency or reject the niche.

MARK ZUCKERBERG — Growth loops. Network effects. Move fast.
  - Every venture must have an answer to: how does user N+1 make user N more likely to stay?
  - Organic growth (SEO, word-of-mouth, platform algorithms) beats paid acquisition until MRR > $5K.
  - Measure everything. A product that cannot be measured cannot be improved.

YOUR RULES:
1. Only approve niches with feasibility_score >= 0.70 AND competition_score <= 0.55
2. Only approve if Execution Scout estimates time_to_first_revenue <= 90 days
3. Reject if Skeptic Scout risk_score >= 0.75 (unless you document a specific override rationale)
4. Set venture_type: MICRO_SAAS or AFFILIATE_SITE routes to PRODUCT department
   Set venture_type: MEDIA_CHANNEL routes to MEDIA department
5. go_decision = true only if ALL three conditions above are met
6. Output ONLY valid JSON — no markdown, no preamble
"""

_USER_PROMPT_TEMPLATE = """
Research Dossier from the Global Research Council:
{research_dossier}

Primary niche recommended by Council: {primary_niche}
Council confidence: {council_confidence}
Recommended venture type: {venture_type}
Debate synthesis: {debate_synthesis}

Your task: Review the council's recommendation critically. Challenge weak evidence.
You may override the council's primary niche if you have strong first-principles reasoning.

Return ONLY this JSON:
{{
  "venture_id": "ven_{short_id}",
  "venture_type": "MICRO_SAAS | MEDIA_CHANNEL | AFFILIATE_SITE",
  "department": "PRODUCT | MEDIA",
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
  "go_rationale": "Reference council evidence, any disagreements, and first-principles override if applied"
}}
"""


async def grand_ceo_node(state: AgentState) -> AgentState:
    """LangGraph node — Grand CEO synthesis and go/no-go decision."""
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    dossier = state.get("research_dossier") or {}

    if not dossier:
        log.error("[CEO_NODE] No research_dossier — RESEARCH_NODE must run first")
        return {**state, "last_error": "missing research_dossier"}

    log.info("[CEO_NODE] Grand CEO synthesising dossier | run=%s", run_id)
    log_agent_event(run_id, venture_id, "GRAND_CEO", "RUNNING",
                    "Synthesising Research Council dossier")

    debate = dossier.get("debate_summary") or {}
    synthesis = debate.get("synthesis", "") if isinstance(debate, dict) else ""
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
            "GRAND_CEO", _SYSTEM_PROMPT, user_prompt, temperature=0.30,
        )
        brief_data: dict = json.loads(response.text)
    except (json.JSONDecodeError, Exception) as exc:
        log.error("[CEO_NODE] LLM call failed: %s", exc)
        log_agent_event(run_id, venture_id, "GRAND_CEO", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    brief_payload = VentureBriefPayload(**{
        k: v for k, v in brief_data.items()
        if k in VentureBriefPayload.model_fields
    })

    # ── CRITICAL: upsert venture BEFORE any pipeline_run insert (FK constraint) ──
    new_venture_id = brief_payload.venture_id
    upsert_venture({
        "venture_id": new_venture_id,
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
        source_agent=AgentID.GRAND_CEO,
        target_agent=AgentID.PRODUCT_VP if brief_data.get("department") == "PRODUCT"
                     else AgentID.MEDIA_VP,
        payload=brief_payload,
        run_id=run_id,
        venture_id=new_venture_id,
        pipeline_stage="CEO_NODE",
        token_cost=response.total_tokens,
        latency_ms=response.latency_ms,
    )

    log_agent_event(run_id, new_venture_id, "GRAND_CEO", "SUCCESS",
                    tokens_used=response.total_tokens, latency_ms=response.latency_ms)
    log.info(
        "[CEO_NODE] ✓ VentureBrief | niche=%s go=%s dept=%s feasibility=%.2f",
        brief_payload.niche, brief_payload.go_decision,
        brief_data.get("department", "PRODUCT"), brief_payload.feasibility_score,
    )

    venture_brief: VentureBrief = brief_data  # type: ignore[assignment]
    department = brief_data.get("department", "PRODUCT")
    new_state = update_stage(state, "PRODUCT_VP_NODE" if department == "PRODUCT"
                             else "MEDIA_VP_NODE")
    return append_event(
        {**new_state,
         "venture_id": new_venture_id,
         "venture_brief": venture_brief,
         "department": department},
        event.model_dump(),
    )
