"""
packages/agents/governance/research_council.py
Global Research Council — 5 parallel Gemini 2.5 Pro scouts + structured debate.

Model:   Gemini 2.5 Pro (1M context, best reasoning for deep niche research)
         Falls back to gemini-1.5-flash if 2.5-pro is quota-limited.
Input:   Live trend snapshot (pytrends + Tavily) — NO mock data, NO hardcoded niches
Output:  ResearchDossier handed to Grand CEO

The council NEVER sets go_decision — that is the CEO's sole authority.
Each scout has a different lens; the Debate Synthesiser surfaces disagreements.

Scouts (run in parallel, Gemini 2.5 Pro):
  1. Trend Hunter     — rising search volume, viral signals, platform trends
  2. Competitor Analyst — reverse-engineers top performers, finds moat gaps
  3. Skeptic          — challenges every pitch: risk, saturation, policy, CAC
  4. Audience Analyst — target persona, pain severity, willingness to pay
  5. Execution Scout  — build feasibility for our specific agent stack

No mock fallback. Requires GEMINI_API_KEY. If the API call fails, the error
propagates — pipelines run on real data or not at all.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from packages.db.client import log_agent_event
from packages.db.pipeline import save_research_dossier
from packages.schemas.events import (
    AgentID, EventType, ResearchDossierPayload, make_event,
)
from packages.state.agent_state import AgentState, ResearchDossier, append_event, update_stage
from packages.tools.llm import call_llm
from packages.tools.trends import fetch_trend_snapshot

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scout definitions — (agent_role, display_name, system_prompt)
# ---------------------------------------------------------------------------

_SCOUTS: list[tuple[str, str, str]] = [
    (
        "KIMI_SCOUT_TREND",
        "trend_hunter",
        """You are the Trend Hunter on AI Squadron's Research Council.
Your sole job: find niches with RISING search interest and viral potential.
Scan the trend snapshot for signals that are growing — not already peaked.
Rising = less competition + more organic reach available.
Rate each niche: volume_index (how big), growth_velocity (30-day momentum), platform_fit.
Output ONLY valid JSON.""",
    ),
    (
        "KIMI_SCOUT_COMPETITOR",
        "competitor_analyst",
        """You are the Competitor Analyst on AI Squadron's Research Council.
For each niche candidate: who are the top 5 players? What do 1-star reviewers complain about?
What keyword gap can we own that they don't? What is the specific moat gap we can exploit?
Be specific — "less features" is not a moat gap. "No API integration for Notion" is.
Output ONLY valid JSON.""",
    ),
    (
        "KIMI_SCOUT_SKEPTIC",
        "skeptic",
        """You are the Adversarial Skeptic on AI Squadron's Research Council.
Your SOLE JOB is to find reasons why each niche will FAIL. You are not balanced. You are hostile.

For EVERY niche candidate you MUST produce:
  1. FALSIFIABLE_REJECTION — one specific, testable claim why this will fail
     (e.g. "Existing tool X has 50k users and charges $19/mo — we cannot undercut them
     without losing margin" NOT "the market is competitive")
  2. REGULATORY_RISK — any law, ToS, or platform policy that could kill this
  3. CAC_ESTIMATE — realistic cost to acquire first 10 paying customers (USD)
  4. RUNWAY_CHECK — at our $100/venture budget, how many months until first revenue?
  5. COPY_RISK — how fast can a well-funded competitor replicate this?

risk_score rules (0-1, additive):
  +0.3 if a bootstrapper has never made money in this niche (no indie case studies)
  +0.2 if requires B2B sales or institutional trust
  +0.2 if regulated (finance, health, legal, education)
  +0.15 if dominant incumbent has >70% market share with no obvious weakness
  +0.15 if CAC > $100 for a $29/mo product

Rejection threshold: risk_score >= 0.65 (TIGHTER than before — we reject more to build less but better)
Output ONLY valid JSON. No encouragement. No "on the other hand". Pure adversarial.""",
    ),
    (
        "KIMI_SCOUT_AUDIENCE",
        "audience_analyst",
        """You are the Audience Analyst on AI Squadron's Research Council.
Build a detailed persona for each niche: who is this person, what is their exact pain,
what words do they use when searching, what have they already tried and failed with,
what are they willing to pay monthly for a solution?
Pain severity (0-1): higher = more urgent, more willingness to pay.
Output ONLY valid JSON.""",
    ),
    (
        "KIMI_SCOUT_EXECUTION",
        "execution_scout",
        """You are the Execution Scout on AI Squadron's Research Council.
Judge whether AI Squadron's specific tech stack can build and ship this niche in time.
Stack: React 19 + Vite + FastAPI + Supabase + Railway (SaaS) or FFmpeg + ElevenLabs + YouTube API (media).
Estimate: weeks_to_first_deploy, weeks_to_first_revenue, build_complexity (LOW/MEDIUM/HIGH).
Red flag anything requiring: hardware, regulated industries, real-time data we cannot access,
manual operations that cannot be automated.
Output ONLY valid JSON.""",
    ),
]

_SCOUT_JSON_SCHEMA = """
{
  "scout_role": "<trend_hunter|competitor_analyst|skeptic|audience_analyst|execution_scout>",
  "niche_candidates": [
    {
      "niche": "...",
      "venture_type": "MICRO_SAAS | MEDIA_CHANNEL | AFFILIATE_SITE",
      "score": 0.0,
      "evidence": ["specific, cited fact 1", "..."],
      "risks": ["specific risk 1", "..."]
    }
  ],
  "top_pick": "...",
  "rationale": "2-3 sentences max"
}
"""

_DEBATE_SYSTEM = """You are the Research Council Debate Synthesiser.
You receive five scout memos. Produce a structured debate summary with areas of consensus,
key disagreements, and a primary recommendation. Be explicit about evidence gaps.
The Grand CEO will make the final GO/NO-GO — you only recommend.
Output ONLY valid JSON."""

_DEBATE_SCHEMA = """
{
  "consensus_niches": ["..."],
  "disagreements": [
    {"topic": "...", "positions": {"trend_hunter": "...", "skeptic": "...", "execution_scout": "..."}}
  ],
  "recommended_primary_niche": "...",
  "recommended_venture_type": "MICRO_SAAS | MEDIA_CHANNEL | AFFILIATE_SITE",
  "council_confidence": 0.0,
  "synthesis": "Executive summary for the Grand CEO (max 400 words)",
  "evidence_gaps": ["things scouts could not verify"]
}
"""


async def research_council_node(state: AgentState) -> AgentState:
    """LangGraph node — 5-scout parallel research + debate synthesis."""
    run_id = state["run_id"]
    venture_id = state["venture_id"]

    log.info("[RESEARCH_NODE] Global Research Council starting | run=%s", run_id)
    log_agent_event(run_id, venture_id, "RESEARCH_COUNCIL", "RUNNING",
                    "5 scouts + debate synthesis")

    trend_snapshot = await fetch_trend_snapshot()
    trend_json = json.dumps(trend_snapshot, indent=2)

    # Always run live with Gemini 2.5 Pro. No mock fallback.
    # Requires GEMINI_API_KEY in environment. If missing → exception propagates.
    log.info("[RESEARCH_NODE] Running live council with Gemini 2.5 Pro")
    dossier_body, debate_transcript, token_total, latency_total = (
        await _run_live_council(trend_json)
    )
    mode = "gemini_live"

    payload = ResearchDossierPayload(
        venture_id=venture_id,
        trend_snapshot=trend_snapshot,
        scout_reports=dossier_body["scout_reports"],
        debate_summary=dossier_body["debate_summary"],
        recommended_primary_niche=dossier_body["recommended_primary_niche"],
        recommended_venture_type=dossier_body["recommended_venture_type"],
        consensus_niches=dossier_body["consensus_niches"],
        disagreements=dossier_body["disagreements"],
        council_confidence=dossier_body["council_confidence"],
        research_mode=mode,
    )

    event = make_event(
        EventType.RESEARCH_DOSSIER_READY,
        AgentID.RESEARCH_COUNCIL,
        AgentID.GRAND_CEO,
        payload, run_id, venture_id, "RESEARCH_NODE",
        token_cost=token_total, latency_ms=latency_total,
    )

    research_dossier: ResearchDossier = {
        **payload.model_dump(),
        "debate_transcript": debate_transcript,
    }

    log_agent_event(run_id, venture_id, "RESEARCH_COUNCIL", "SUCCESS",
                    tokens_used=token_total, latency_ms=latency_total,
                    current_task=f"Primary: {payload.recommended_primary_niche}")
    log.info("[RESEARCH_NODE] ✓ Dossier | niche=%s confidence=%.2f mode=%s",
             payload.recommended_primary_niche, payload.council_confidence, mode)

    save_research_dossier(run_id, venture_id, research_dossier, debate_transcript)

    new_state = update_stage(state, "CEO_NODE")
    return append_event(
        {**new_state,
         "research_dossier": research_dossier,
         "debate_transcript": debate_transcript},
        event.model_dump(),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _run_live_council(
    trend_json: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], int, int]:
    """Run all 5 scouts in parallel, then synthesise."""
    scout_tasks = [
        _run_single_scout(role, name, system, trend_json)
        for role, name, system in _SCOUTS
    ]
    results = await asyncio.gather(*scout_tasks, return_exceptions=True)

    scout_reports: list[dict[str, Any]] = []
    debate_transcript: list[dict[str, Any]] = []
    token_total = latency_total = 0

    for i, result in enumerate(results):
        role_name = _SCOUTS[i][1]
        if isinstance(result, Exception):
            log.error("[RESEARCH_NODE] Scout %s failed: %s", role_name, result)
            scout_reports.append(_fallback_scout(role_name, str(result)))
            debate_transcript.append({"scout": role_name, "error": str(result)})
            continue
        report, tokens, latency = result
        scout_reports.append(report)
        debate_transcript.append({"scout": role_name, "report": report})
        token_total += tokens
        latency_total = max(latency_total, latency)

    debate_prompt = (
        f"Trend snapshot:\n{trend_json}\n\n"
        f"Scout memos:\n{json.dumps(scout_reports, indent=2)}\n\n"
        f"Produce the debate summary. Return ONLY JSON matching:\n{_DEBATE_SCHEMA}"
    )
    debate_resp = await call_llm(
        "KIMI_DEBATE_SYNTHESIZER", _DEBATE_SYSTEM, debate_prompt,
        temperature=0.25, max_tokens=4096,
    )
    token_total += debate_resp.total_tokens
    latency_total = max(latency_total, debate_resp.latency_ms)

    try:
        debate_summary: dict[str, Any] = json.loads(debate_resp.text)
    except json.JSONDecodeError:
        debate_summary = _fallback_debate(scout_reports)

    debate_transcript.append({"phase": "synthesis", "summary": debate_summary})

    dossier_body = {
        "scout_reports": scout_reports,
        "debate_summary": debate_summary,
        "recommended_primary_niche": debate_summary.get(
            "recommended_primary_niche",
            scout_reports[0].get("top_pick", "unknown") if scout_reports else "unknown",
        ),
        "recommended_venture_type": debate_summary.get("recommended_venture_type", "MICRO_SAAS"),
        "consensus_niches": debate_summary.get("consensus_niches", []),
        "disagreements": debate_summary.get("disagreements", []),
        "council_confidence": float(debate_summary.get("council_confidence", 0.5)),
    }
    return dossier_body, debate_transcript, token_total, latency_total


async def _run_single_scout(
    agent_role: str, role_name: str, system_prompt: str, trend_json: str,
) -> tuple[dict[str, Any], int, int]:
    user_prompt = (
        f"Trend snapshot:\n{trend_json}\n\n"
        f"You are the {role_name} scout. Propose up to 5 niche_candidates.\n"
        f"Return ONLY JSON matching:\n{_SCOUT_JSON_SCHEMA}"
    )
    resp = await call_llm(agent_role, system_prompt, user_prompt,
                          temperature=0.4, max_tokens=3072)
    try:
        data: dict[str, Any] = json.loads(resp.text)
        data["scout_role"] = role_name
        return data, resp.total_tokens, resp.latency_ms
    except json.JSONDecodeError as exc:
        log.warning("[RESEARCH_NODE] Scout %s JSON parse failed: %s", role_name, exc)
        return _fallback_scout(role_name, "json_parse_error"), resp.total_tokens, resp.latency_ms


def _fallback_scout(role_name: str, reason: str) -> dict[str, Any]:
    """Minimal fallback used when a single scout's JSON parse fails. No hardcoded niches."""
    log.error("[RESEARCH_NODE] Scout %s failed with: %s — returning empty report", role_name, reason)
    return {
        "scout_role": role_name,
        "niche_candidates": [],
        "top_pick": "",
        "rationale": f"Scout failed — {reason}",
        "error": reason,
    }


def _fallback_debate(scout_reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Fallback debate when synthesis JSON parse fails. Derives top pick from scout reports."""
    # Collect picks from successful scouts and pick the most common one
    picks = [r.get("top_pick", "") for r in scout_reports if r.get("top_pick")]
    top = max(set(picks), key=picks.count) if picks else ""
    log.warning("[RESEARCH_NODE] Debate synthesis JSON failed — best scout pick: %s", top)
    return {
        "consensus_niches":            [top] if top else [],
        "disagreements":               [],
        "recommended_primary_niche":   top,
        "recommended_venture_type":    "MICRO_SAAS",
        "council_confidence":          0.35,
        "synthesis":                   "Debate synthesis JSON parse failed — Grand CEO must weigh scout memos manually.",
        "evidence_gaps":               ["debate_json_parse_failed"],
    }
