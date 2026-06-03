"""
packages/agents/governance/grand_ceo.py
Grand CEO Agent — Operator-aware niche scout, scorer, and go/no-go arbiter.

Model:   claude-haiku-4-5 (cost-efficient; swap CEO_MODEL_OVERRIDE to Sonnet for higher stakes)
Input:   ResearchDossier from Research Council + niche memory (exhausted_niches from Supabase)
Output:  VentureBrief with go_decision + ranked niche_shortlist stored for future runs

LLM Council design (2026-05-31):
  - Operator profile injected into every decision (constraints-aware analysis)
  - 4-dimension scoring rubric: TAM + CompetitionGap + BuildScore + RevenueVelocity
  - GO_THRESHOLD = 65 / 100 (raises bar from previous always-pass heuristic)
  - CEO outputs ranked shortlist of 3 niches — #2 and #3 stored for next run
  - Skeptic's best argument quoted and explicitly answered (cannot be hand-waved)
  - Niche memory: exhausted/KILL'd niches excluded before evaluation
  - PRODUCT focus only: MICRO_SAAS | AFFILIATE_SITE (MEDIA_CHANNEL held for media line)
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
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Operator profile — injected into every CEO decision
# Ensures the CEO evaluates niches relative to THIS builder's constraints,
# not a hypothetical well-funded startup.
# ---------------------------------------------------------------------------
_OPERATOR_PROFILE = """
OPERATOR CONSTRAINTS (evaluate every niche against these — non-negotiable):
  Builder:      Solo operator, no team, no investors
  Location:     India (can sell globally in USD via Paddle MoR)
  Stack:        React 19 + FastAPI + Supabase + Railway (cannot change per venture)
  Budget:       $100 USD per venture for API costs
  Time target:  First paying customer within 90 days of deployment
  Excluded:     Healthcare (HIPAA), fintech-licensed, enterprise sales, hardware
  Advantage:    Can build fast, deploy globally, automate ops with AI agents
"""

# ---------------------------------------------------------------------------
# 4-dimension scoring rubric
# ---------------------------------------------------------------------------
_SCORING_RUBRIC = """
SCORING RUBRIC (score each dimension 0-25, total out of 100):

TAM_SCORE (0-25): Total addressable market
  25 = >$5B global TAM with underserved online segment
  15 = $500M-$5B TAM, segment accessible via SEO/Product Hunt
  8  = <$500M or B2B requiring enterprise sales
  0  = Too niche, regulated, or hardware-dependent

COMPETITION_GAP (0-25): Specific moat gap that exists RIGHT NOW
  25 = Clear gap: existing tools are old/clunky/expensive, buyers actively complaining on Reddit
  15 = Gap exists but incumbents are aware of it
  8  = Market has one dominant player with 80%+ share and no obvious weakness
  0  = Saturated: 10+ well-funded SaaS tools in the same niche

BUILD_SCORE (0-25): Can our stack build a competitive MVP in one Engineering sprint?
  25 = Buildable with React + Supabase + FastAPI in < 3 days, no exotic APIs needed
  15 = Buildable but requires 1-2 third-party APIs (ElevenLabs, Stripe, etc.)
  8  = Requires proprietary data, ML models, or complex integrations
  0  = Requires hardware, mobile app, browser extension, or real-time infra

REVENUE_VELOCITY (0-25): Realistic path to first paid customer within 90 days
  25 = Self-serve, card-on-file, paywall possible — buyer decides alone
  15 = Self-serve but requires some trust-building (free trial, demo)
  8  = Requires sales calls, procurement, or institutional approval
  0  = No clear monetisation path without significant marketing spend

GO_THRESHOLD: Total score >= 65 to issue go_decision: true
"""

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = f"""
You are the Grand CEO of AI Squadron — an autonomous venture organisation.

Decision philosophy:
  JOBS  — Say no to 1,000 things. If the value prop needs explanation, reject it.
  MUSK  — First principles. Question every industry assumption. Set aggressive timelines.
  ZUCK  — Growth loops first. Organic acquisition until MRR > $5K.

{_OPERATOR_PROFILE}

{_SCORING_RUBRIC}

CRITICAL RULES:
1. Evaluate ONLY MICRO_SAAS or AFFILIATE_SITE venture types (MEDIA_CHANNEL is held — do not propose it)
2. You MUST quote the Skeptic Scout's strongest argument and provide a specific rebuttal
   If you cannot rebut it, lower COMPETITION_GAP or BUILD_SCORE accordingly
3. You MUST produce a ranked shortlist of exactly 3 niches — the top scorer gets go_decision
4. Exclude any niche that appears in the EXHAUSTED_NICHES list
5. Output ONLY valid JSON — no markdown, no preamble, no explanation
   First character MUST be {{
"""

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
_USER_PROMPT_TEMPLATE = """
Research Dossier from the Global Research Council:
{research_dossier}

Council's recommended primary niche: {primary_niche}
Council confidence: {council_confidence}
Council debate synthesis: {debate_synthesis}

EXHAUSTED NICHES (do NOT propose these — already evaluated or KILL'd):
{exhausted_niches}

Your task:
1. Critically evaluate the council's recommendation
2. Identify 3 candidate niches (can include the council's pick or substitutes)
3. Score each using the 4-dimension rubric
4. Rank them by total score
5. Only set go_decision: true if the top-ranked niche scores >= 65

RETURN ONLY this JSON (no markdown, first char must be {{):
{{
  "niche_shortlist": [
    {{
      "rank": 1,
      "niche": "...",
      "venture_type": "MICRO_SAAS | AFFILIATE_SITE",
      "tam_score": 0,
      "competition_gap": 0,
      "build_score": 0,
      "revenue_velocity": 0,
      "confidence_score": 0,
      "skeptic_best_argument": "Quote the strongest reason NOT to build this",
      "skeptic_rebuttal": "Specific response to the skeptic — concrete, not hand-wavy",
      "audience_persona": "Named buyer, specific pain in one sentence, WTP estimate",
      "build_estimate_days": 0,
      "trend_evidence": "Specific search trend or Reddit signal"
    }},
    {{
      "rank": 2,
      "niche": "...",
      "venture_type": "MICRO_SAAS | AFFILIATE_SITE",
      "tam_score": 0,
      "competition_gap": 0,
      "build_score": 0,
      "revenue_velocity": 0,
      "confidence_score": 0,
      "skeptic_best_argument": "...",
      "skeptic_rebuttal": "...",
      "audience_persona": "...",
      "build_estimate_days": 0,
      "trend_evidence": "..."
    }},
    {{
      "rank": 3,
      "niche": "...",
      "venture_type": "MICRO_SAAS | AFFILIATE_SITE",
      "tam_score": 0,
      "competition_gap": 0,
      "build_score": 0,
      "revenue_velocity": 0,
      "confidence_score": 0,
      "skeptic_best_argument": "...",
      "skeptic_rebuttal": "...",
      "audience_persona": "...",
      "build_estimate_days": 0,
      "trend_evidence": "..."
    }}
  ],
  "venture_id": "ven_{short_id}",
  "venture_type": "MICRO_SAAS | AFFILIATE_SITE",
  "department": "PRODUCT",
  "niche": "The rank-1 niche string",
  "target_region": ["US", "CA", "AU", "IN"],
  "target_audience": "Specific named persona and their exact pain point",
  "rpm_estimate_usd": 0.0,
  "competition_score": 0.0,  (0.0–1.0 scale: 0=no competition, 1=saturated)
  "feasibility_score": 0.0,  (0.0–1.0 scale: 0=impossible, 1=trivially easy)
  "tam_usd_millions": 0.0,
  "top_competitors": [{{"name": "...", "weakness": "specific weakness", "moat_gap": "specific gap we exploit"}}],
  "recommended_monetization": ["freemium", "subscription", "one_time"],
  "content_angles": ["SEO angle 1", "Reddit angle 2"],
  "go_decision": true,
  "go_rationale": "Score: TAM=XX/25 Gap=XX/25 Build=XX/25 Revenue=XX/25 Total=XX/100. [Specific rationale citing dossier evidence]"
}}
"""


async def grand_ceo_node(state: AgentState) -> AgentState:
    """LangGraph node — Grand CEO niche scoring and go/no-go decision."""
    run_id     = state["run_id"]
    venture_id = state["venture_id"]
    dossier    = state.get("research_dossier") or {}

    if not dossier:
        log.error("[CEO_NODE] No research_dossier — RESEARCH_NODE must run first")
        return {**state, "last_error": "missing research_dossier"}

    log.info("[CEO_NODE] Grand CEO evaluating niches | run=%s", run_id)
    log_agent_event(run_id, venture_id, "GRAND_CEO", "RUNNING",
                    "Scoring niches with 4-dimension rubric")

    # Fetch niche memory — avoid re-evaluating KILL'd / already-built niches
    try:
        from packages.db.pipeline import get_exhausted_niches
        exhausted = get_exhausted_niches()
    except Exception:
        exhausted = []

    debate    = dossier.get("debate_summary") or {}
    synthesis = debate.get("synthesis", "") if isinstance(debate, dict) else str(debate)
    short_id  = uuid.uuid4().hex[:8]

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        research_dossier=json.dumps(
            {k: v for k, v in dossier.items() if k != "debate_transcript"},
            indent=2,
        ),
        primary_niche    = dossier.get("recommended_primary_niche", "unknown"),
        council_confidence = dossier.get("council_confidence", 0.0),
        debate_synthesis = synthesis[:600] if synthesis else "No debate synthesis available",
        exhausted_niches = ", ".join(exhausted[:20]) if exhausted else "none",
        short_id         = short_id,
    )

    try:
        response = await call_llm(
            "GRAND_CEO", _SYSTEM_PROMPT, user_prompt, temperature=0.25,
        )
        brief_data: dict = json.loads(extract_json(response.text))
    except (json.JSONDecodeError, Exception) as exc:
        log.error("[CEO_NODE] LLM call failed: %s", exc)
        log_agent_event(run_id, venture_id, "GRAND_CEO", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    # ── Normalise 0-25 rubric scores → 0.0-1.0 range for VentureBriefPayload ──
    # The CEO scoring rubric uses 0-25 per dimension, but the schema expects
    # competition_score and feasibility_score as floats in [0.0, 1.0].
    for field in ("competition_score", "feasibility_score"):
        raw = brief_data.get(field, 0.5)
        if isinstance(raw, (int, float)):
            if raw > 1.0:
                brief_data[field] = round(min(1.0, float(raw) / 25.0), 3)
            elif raw < 0.0:
                brief_data[field] = 0.0

    # ── Enforce PRODUCT-only: override any MEDIA_CHANNEL suggestion ──────────
    if brief_data.get("venture_type") == "MEDIA_CHANNEL":
        brief_data["venture_type"] = "MICRO_SAAS"
        brief_data["department"]   = "PRODUCT"
        log.info("[CEO_NODE] MEDIA_CHANNEL overridden to MICRO_SAAS (product focus phase)")

    # ── Validate go_decision against GO_THRESHOLD ────────────────────────────
    shortlist  = brief_data.get("niche_shortlist", [])
    top_niche  = shortlist[0] if shortlist else {}
    total_score = top_niche.get("confidence_score", 0)
    if total_score < 65 and brief_data.get("go_decision") is True:
        brief_data["go_decision"] = False
        brief_data["go_rationale"] = (
            f"Score {total_score}/100 below GO_THRESHOLD of 65. "
            + brief_data.get("go_rationale", "")
        )
        log.warning("[CEO_NODE] go_decision overridden to False — score %d < 65", total_score)

    brief_payload = VentureBriefPayload(**{
        k: v for k, v in brief_data.items()
        if k in VentureBriefPayload.model_fields
    })

    # ── CRITICAL: upsert venture BEFORE pipeline_run FK insert ───────────────
    new_venture_id = brief_payload.venture_id
    upsert_venture({
        "venture_id":       new_venture_id,
        "venture_type":     brief_payload.venture_type,
        "niche":            brief_payload.niche,
        "status":           "IDEATION",
        "go_decision":      brief_payload.go_decision,
        "feasibility_score": brief_payload.feasibility_score,
        "competition_score": brief_payload.competition_score,
        "target_regions":   brief_payload.target_region,
    })

    # ── Persist niche evaluation to Supabase memory ──────────────────────────
    try:
        from packages.db.pipeline import persist_niche_evaluation
        run_shortlist_id = str(uuid.uuid4())
        for i, n in enumerate(shortlist[:3], start=1):
            persist_niche_evaluation(
                niche        = n.get("niche", ""),
                venture_type = n.get("venture_type", "MICRO_SAAS"),
                scores       = {
                    "tam_score":       n.get("tam_score", 0),
                    "competition_gap": n.get("competition_gap", 0),
                    "build_score":     n.get("build_score", 0),
                    "revenue_velocity":n.get("revenue_velocity", 0),
                },
                go_decision  = (i == 1 and brief_payload.go_decision),
                go_rationale = brief_payload.go_rationale if i == 1 else "Shortlist rank 2/3",
                scout_summary = {
                    "trend":    n.get("trend_evidence", ""),
                    "skeptic":  n.get("skeptic_best_argument", ""),
                    "audience": n.get("audience_persona", ""),
                    "build_days": n.get("build_estimate_days"),
                },
                run_id           = run_id,
                venture_id       = new_venture_id if i == 1 else None,
                niche_rank       = i,
                run_shortlist_id = run_shortlist_id,
            )
    except Exception as exc:
        log.debug("[CEO_NODE] Niche persistence failed (non-blocking): %s", exc)

    event = make_event(
        event_type    = EventType.VENTURE_BRIEF_READY,
        source_agent  = AgentID.GRAND_CEO,
        target_agent  = AgentID.PRODUCT_VP,   # product-only phase
        payload       = brief_payload,
        run_id        = run_id,
        venture_id    = new_venture_id,
        pipeline_stage = "CEO_NODE",
        token_cost    = response.total_tokens,
        latency_ms    = response.latency_ms,
    )

    log_agent_event(run_id, new_venture_id, "GRAND_CEO", "SUCCESS",
                    tokens_used=response.total_tokens, latency_ms=response.latency_ms,
                    current_task=(
                        f"Primary: {brief_payload.niche} | "
                        f"Score: {total_score}/100 | "
                        f"Go: {brief_payload.go_decision}"
                    ))
    log.info(
        "[CEO_NODE] ✓ VentureBrief | niche=%s score=%d go=%s shortlist=%d",
        brief_payload.niche, total_score, brief_payload.go_decision, len(shortlist),
    )

    venture_brief: VentureBrief = brief_data  # type: ignore[assignment]
    new_state = update_stage(state, "PRODUCT_VP_NODE")
    return append_event(
        {**new_state,
         "venture_id":     new_venture_id,
         "venture_brief":  venture_brief,
         "department":     "PRODUCT",
         "niche_shortlist": shortlist,
         },
        event.model_dump(),
    )
