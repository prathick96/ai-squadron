"""
packages/agents/market_research.py
Market Research Council — 3 Kimi scouts + debate synthesizer → Research Dossier.
CEO (Gemini) consumes the dossier; this node never sets go_decision.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from packages.db.client import log_agent_event
from packages.db.pipeline import save_research_dossier
from packages.schemas.events import (
    AgentID,
    EventType,
    ResearchDossierPayload,
    make_event,
)
from packages.state.agent_state import AgentState, ResearchDossier, append_event, update_stage
from packages.tools.llm import call_llm, kimi_available
from packages.tools.trends import fetch_trend_snapshot

log = logging.getLogger(__name__)

_SCOUT_ROLES: list[tuple[str, str, str]] = [
    (
        "KIMI_SCOUT_OPPORTUNITY",
        "opportunity",
        """You are the Opportunity Scout on AI Squadron's Research Council.
Find high-RPM, growing niches with clear monetization (MICRO_SAAS, MEDIA_CHANNEL, or AFFILIATE_SITE).
Be aggressive but cite evidence from the trend snapshot. Output ONLY valid JSON.""",
    ),
    (
        "KIMI_SCOUT_SKEPTIC",
        "skeptic",
        """You are the Skeptic Scout on AI Squadron's Research Council.
Challenge every hyped niche: saturation, platform policy risk, demonetization, CAC, time-to-revenue.
Output ONLY valid JSON. Flag why niches fail.""",
    ),
    (
        "KIMI_SCOUT_EXECUTION",
        "execution",
        """You are the Execution Scout on AI Squadron's Research Council.
Judge build complexity, autonomous pipeline fit, and weeks-to-first-revenue.
Prefer niches our agent stack can ship without human ops. Output ONLY valid JSON.""",
    ),
]

_SCOUT_JSON_SCHEMA = """
{
  "scout_role": "<opportunity|skeptic|execution>",
  "niche_candidates": [
    {
      "niche": "...",
      "venture_type": "MICRO_SAAS | MEDIA_CHANNEL | AFFILIATE_SITE",
      "score": 0.0,
      "evidence": ["source-backed fact 1", "..."],
      "risks": ["..."]
    }
  ],
  "top_pick": "...",
  "rationale": "2-3 sentences"
}
"""

_DEBATE_SYSTEM = """You are the Research Council Debate Synthesizer.
You receive three scout memos (opportunity, skeptic, execution). Produce a structured debate summary.
The CEO will make the final GO/NO-GO — you only recommend, never decide.
Output ONLY valid JSON."""

_DEBATE_JSON_SCHEMA = """
{
  "consensus_niches": ["..."],
  "disagreements": [
    {"topic": "...", "positions": {"opportunity": "...", "skeptic": "...", "execution": "..."}}
  ],
  "recommended_primary_niche": "...",
  "recommended_venture_type": "MICRO_SAAS | MEDIA_CHANNEL | AFFILIATE_SITE",
  "council_confidence": 0.0,
  "synthesis": "Executive summary for the CEO (max 400 words)",
  "evidence_gaps": ["things scouts could not verify"]
}
"""


async def market_research_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]

    log.info("[RESEARCH_NODE] Starting Research Council | run=%s", run_id)
    log_agent_event(
        run_id, venture_id, "MARKET_RESEARCH_TEAM", "RUNNING",
        "Kimi council: 3 scouts + debate synthesis",
    )

    trend_snapshot = await fetch_trend_snapshot()
    trend_json = json.dumps(trend_snapshot, indent=2)

    if kimi_available():
        dossier_body, debate_transcript, token_total, latency_total = await _run_live_council(
            trend_json
        )
        mode = "kimi_openrouter"
    else:
        log.warning("[RESEARCH_NODE] OPENROUTER_API_KEY missing — using council mock dossier")
        dossier_body, debate_transcript = _mock_council_dossier(trend_snapshot)
        token_total, latency_total = 0, 0
        mode = "mock"

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
        AgentID.MARKET_RESEARCH_TEAM,
        AgentID.CEO_NICHE_SCOUT,
        payload,
        run_id,
        venture_id,
        "RESEARCH_NODE",
        token_cost=token_total,
        latency_ms=latency_total,
    )

    research_dossier: ResearchDossier = {
        **payload.model_dump(),
        "debate_transcript": debate_transcript,
    }

    log_agent_event(
        run_id, venture_id, "MARKET_RESEARCH_TEAM", "SUCCESS",
        tokens_used=token_total, latency_ms=latency_total,
        current_task=f"Primary niche: {payload.recommended_primary_niche}",
    )
    log.info(
        "[RESEARCH_NODE] ✓ Dossier ready | niche=%s confidence=%.2f mode=%s",
        payload.recommended_primary_niche,
        payload.council_confidence,
        mode,
    )

    save_research_dossier(run_id, venture_id, research_dossier, debate_transcript)

    new_state = update_stage(state, "CEO_NODE")
    return append_event(
        {**new_state, "research_dossier": research_dossier, "debate_transcript": debate_transcript},
        event.model_dump(),
    )


async def _run_live_council(
    trend_json: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], int, int]:
    """Parallel Kimi scouts, then debate synthesis."""
    scout_tasks = [
        _run_scout(agent_role, role_name, system, trend_json)
        for agent_role, role_name, system in _SCOUT_ROLES
    ]
    scout_results = await asyncio.gather(*scout_tasks, return_exceptions=True)

    scout_reports: list[dict[str, Any]] = []
    debate_transcript: list[dict[str, Any]] = []
    token_total = 0
    latency_total = 0

    for i, result in enumerate(scout_results):
        role_name = _SCOUT_ROLES[i][1]
        if isinstance(result, Exception):
            log.error("[RESEARCH_NODE] Scout %s failed: %s", role_name, result)
            scout_reports.append(_fallback_scout_report(role_name, str(result)))
            debate_transcript.append({"scout": role_name, "error": str(result)})
            continue
        report, tokens, latency = result
        scout_reports.append(report)
        debate_transcript.append({"scout": role_name, "report": report})
        token_total += tokens
        latency_total = max(latency_total, latency)

    debate_prompt = f"""
Trend snapshot:
{trend_json}

Scout memos:
{json.dumps(scout_reports, indent=2)}

Synthesize debate. Max 5 consensus niches.
Return ONLY JSON matching:
{_DEBATE_JSON_SCHEMA}
"""
    debate_resp = await call_llm(
        "KIMI_DEBATE_SYNTHESIZER",
        _DEBATE_SYSTEM,
        debate_prompt,
        temperature=0.3,
        max_tokens=4096,
    )
    token_total += debate_resp.total_tokens
    latency_total = max(latency_total, debate_resp.latency_ms)

    try:
        debate_summary = json.loads(debate_resp.text)
    except json.JSONDecodeError:
        debate_summary = _fallback_debate(scout_reports)

    debate_transcript.append({"phase": "synthesis", "summary": debate_summary})

    dossier_body = {
        "scout_reports": scout_reports,
        "debate_summary": debate_summary,
        "recommended_primary_niche": debate_summary.get(
            "recommended_primary_niche", scout_reports[0].get("top_pick", "unknown")
        ),
        "recommended_venture_type": debate_summary.get(
            "recommended_venture_type", "MICRO_SAAS"
        ),
        "consensus_niches": debate_summary.get("consensus_niches", []),
        "disagreements": debate_summary.get("disagreements", []),
        "council_confidence": float(debate_summary.get("council_confidence", 0.5)),
    }
    return dossier_body, debate_transcript, token_total, latency_total


async def _run_scout(
    agent_role: str,
    role_name: str,
    system_prompt: str,
    trend_json: str,
) -> tuple[dict[str, Any], int, int]:
    user_prompt = f"""
Trend snapshot:
{trend_json}

You are the {role_name} scout. Propose up to 5 niche_candidates ranked by your lens.
Return ONLY JSON matching:
{_SCOUT_JSON_SCHEMA}
"""
    resp = await call_llm(
        agent_role,
        system_prompt,
        user_prompt,
        temperature=0.5 if role_name == "opportunity" else 0.35,
        max_tokens=3072,
    )
    try:
        data = json.loads(resp.text)
        data["scout_role"] = role_name
        return data, resp.total_tokens, resp.latency_ms
    except json.JSONDecodeError as exc:
        log.warning("[RESEARCH_NODE] Scout %s JSON parse failed: %s", role_name, exc)
        return _fallback_scout_report(role_name, "json_parse_error"), resp.total_tokens, resp.latency_ms


def _fallback_scout_report(role_name: str, reason: str) -> dict[str, Any]:
    return {
        "scout_role": role_name,
        "niche_candidates": [],
        "top_pick": "AI finance micro-tools for freelancers",
        "rationale": f"Fallback due to: {reason}",
        "error": reason,
    }


def _fallback_debate(scout_reports: list[dict[str, Any]]) -> dict[str, Any]:
    top = scout_reports[0].get("top_pick", "AI finance micro-tools") if scout_reports else "unknown"
    return {
        "consensus_niches": [top],
        "disagreements": [],
        "recommended_primary_niche": top,
        "recommended_venture_type": "MICRO_SAAS",
        "council_confidence": 0.4,
        "synthesis": "Debate synthesis failed; CEO must weigh scout memos manually.",
        "evidence_gaps": ["debate_json_parse_failed"],
    }


def _mock_council_dossier(trend_snapshot: dict) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    primary = "AI tax automation for freelancers"
    scout_reports = [
        {
            "scout_role": "opportunity",
            "niche_candidates": [
                {
                    "niche": primary,
                    "venture_type": "MICRO_SAAS",
                    "score": 0.82,
                    "evidence": trend_snapshot.get("competitor_gap_signals", [])[:2],
                    "risks": ["crowded adjacent market"],
                }
            ],
            "top_pick": primary,
            "rationale": "High RPM finance niche with clear SaaS monetization.",
        },
        {
            "scout_role": "skeptic",
            "niche_candidates": [
                {
                    "niche": primary,
                    "venture_type": "MICRO_SAAS",
                    "score": 0.55,
                    "evidence": ["incumbents exist"],
                    "risks": ["tax seasonality", "compliance liability"],
                }
            ],
            "top_pick": primary,
            "rationale": "Viable if differentiated on AI automation; otherwise crowded.",
        },
        {
            "scout_role": "execution",
            "niche_candidates": [
                {
                    "niche": primary,
                    "venture_type": "MICRO_SAAS",
                    "score": 0.78,
                    "evidence": ["fits React+Vite micro-SaaS template"],
                    "risks": ["needs Stripe + clear UX"],
                }
            ],
            "top_pick": primary,
            "rationale": "Shippable in 2 weeks via autonomous engineering pipeline.",
        },
    ]
    debate_summary = {
        "consensus_niches": [primary, "faceless YouTube finance channel"],
        "disagreements": [
            {
                "topic": "time-to-revenue",
                "positions": {
                    "opportunity": "Stripe in week 2",
                    "skeptic": "6+ months trust building",
                    "execution": "MVP in 14 days",
                },
            }
        ],
        "recommended_primary_niche": primary,
        "recommended_venture_type": "MICRO_SAAS",
        "council_confidence": 0.71,
        "synthesis": "Council agrees on freelancer tax automation as primary wedge; media channel as secondary.",
        "evidence_gaps": ["live Tavily data not wired"],
    }
    debate_transcript = [
        {"scout": r["scout_role"], "report": r} for r in scout_reports
    ] + [{"phase": "synthesis", "summary": debate_summary}]

    dossier_body = {
        "scout_reports": scout_reports,
        "debate_summary": debate_summary,
        "recommended_primary_niche": primary,
        "recommended_venture_type": "MICRO_SAAS",
        "consensus_niches": debate_summary["consensus_niches"],
        "disagreements": debate_summary["disagreements"],
        "council_confidence": debate_summary["council_confidence"],
    }
    return dossier_body, debate_transcript
