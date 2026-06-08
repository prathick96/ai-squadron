"""
packages/agents/governance/research_council.py
Global Research Council — 5 parallel Claude Sonnet scouts + structured debate.

Model:   Claude Sonnet 4.6 (deep reasoning for structured niche research + debate)
Input:   Live trend snapshot (pytrends + Tavily) — NO mock data, NO hardcoded niches
Output:  ResearchDossier handed to Grand CEO

Key design:
  - Each scout gets INDEPENDENT Tavily web search for its specific lens
    (competitor analyst searches reviews, skeptic searches failure cases, etc.)
  - Niche memory: exhausted/KILL'd niches fetched BEFORE scouts run and injected
    into every prompt — scouts never waste time on already-evaluated territory
  - Rotating exploration verticals via trends.py — different market categories
    explored each run to prevent repetitive recommendations
  - Date-aware prompts: scouts know today's date for recency judgement
  - Richer JSON schema: scouts must produce CITED evidence and specific moat gaps
  - Debate synthesiser cross-references scout evidence quality, not just picks

Scouts (run in parallel, Claude Sonnet):
  1. Trend Hunter     — rising search volume, viral signals, platform trends
  2. Competitor Analyst — reverse-engineers top performers, finds moat gaps
  3. Skeptic          — challenges every pitch: risk, saturation, policy, CAC
  4. Audience Analyst — target persona, pain severity, willingness to pay
  5. Execution Scout  — build feasibility for our specific agent stack

No mock fallback. Requires ANTHROPIC_API_KEY. If the API call fails, the error
propagates — pipelines run on real data or not at all.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any

from packages.db.client import log_agent_event
from packages.db.pipeline import save_research_dossier
from packages.schemas.events import (
    AgentID, EventType, ResearchDossierPayload, make_event,
)
from packages.state.agent_state import AgentState, ResearchDossier, append_event, update_stage
from packages.tools.llm import call_llm
from packages.tools.trends import fetch_trend_snapshot, fetch_tavily_for_scout

log = logging.getLogger(__name__)

_TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Scout definitions — (agent_role, display_name, system_prompt)
# Each scout has a distinct mandate and different Tavily search strategy.
# ---------------------------------------------------------------------------

_SCOUTS: list[tuple[str, str, str]] = [
    (
        "KIMI_SCOUT_TREND",
        "trend_hunter",
        f"""You are the Trend Hunter on AI Squadron's Research Council. Today is {_TODAY}.

YOUR MANDATE: Find 5 niches with RISING search interest and viral potential RIGHT NOW.
Not 6 months ago — TODAY. Rising = less saturated + more organic reach still available.

SEARCH STRATEGY: Analyse the trend snapshot AND the Tavily web results provided.
Look for: Google Trends rising queries, Product Hunt launches gaining traction,
Reddit discussions where people say "I wish there was a tool for X",
Indie Hackers posts where founders are making $500-5000 MRR in a new niche.

SCORING (include in every candidate):
  volume_index:      0-100 (how large is current search volume)
  growth_velocity:   "EXPLODING" | "RISING" | "STABLE" | "DECLINING"
  platform_fit:      "SaaS" | "YouTube" | "Affiliate" | "Multiple"
  evidence_quality:  "CITED" (you found specific data) | "INFERRED" (general reasoning)

RULES:
  - Never recommend niches in the EXHAUSTED_NICHES list
  - Each candidate must be a DIFFERENT vertical (no 5 variations on the same theme)
  - Prefer niches where bootstrappers are already making money (proof of willingness to pay)
  - Output ONLY valid JSON""",
    ),
    (
        "KIMI_SCOUT_COMPETITOR",
        "competitor_analyst",
        f"""You are the Competitor Analyst on AI Squadron's Research Council. Today is {_TODAY}.

YOUR MANDATE: Find the SPECIFIC MOAT GAP in each niche — the exact weakness of existing tools
that our AI-built SaaS can exploit. Vague gaps are worthless. Specific gaps win markets.

USE THE TAVILY RESULTS to find real competitor weaknesses:
  - Search for "1-star reviews" and "biggest complaints" about existing tools
  - Look for Hacker News "Ask HN: alternatives to X" threads
  - Find Reddit posts where users rage about specific missing features

MOAT GAP EXAMPLES (good vs bad):
  BAD:  "Competitors are expensive"
  GOOD: "FreshBooks doesn't auto-categorise UK VAT codes — freelancers spend 4h/month manually"
  BAD:  "Market is fragmented"
  GOOD: "No tool connects Shopify inventory data directly to TikTok Shop listings without CSV exports"

For each niche, output:
  top_competitors:     [{{name, monthly_searches, specific_weakness, 1star_complaint}}]
  moat_gap:            The specific gap, phrased as a user complaint
  keyword_gap:         A search term incumbents rank poorly for
  evidence_quality:    "CITED" | "INFERRED"

  - Never recommend niches in the EXHAUSTED_NICHES list
  - Output ONLY valid JSON""",
    ),
    (
        "KIMI_SCOUT_SKEPTIC",
        "skeptic",
        f"""You are the Adversarial Skeptic on AI Squadron's Research Council. Today is {_TODAY}.

YOUR SOLE JOB: Kill bad ideas before we waste $100 and 3 weeks building them.
You are NOT balanced. You are hostile. Every niche is guilty until proven innocent.

USE THE TAVILY RESULTS to find real failure cases:
  - Indie Hackers failure post-mortems for this niche
  - Hacker News threads about why this space is hard
  - Reddit posts from people who tried to build this and failed

For EVERY niche candidate produce ALL of these:
  1. KILL_REASON:         One specific, falsifiable reason this will fail
                          ("Existing tool X has 50k users at $19/mo" NOT "competitive market")
  2. REGULATORY_RISK:     Law, platform ToS, or compliance issue that could kill this
  3. CAC_ESTIMATE_USD:    Realistic cost to acquire first 10 paying customers
  4. MONTHS_TO_REVENUE:   At $100 venture budget, months to first $1 paid
  5. COPY_RISK:           How fast (days/weeks/months) can a funded competitor clone this?
  6. INDIA_FEASIBILITY:   Can a solo India-based developer sell this globally? (Yes/No/Limited)

risk_score rules (0.0–1.0, additive — REJECT if >= 0.60):
  +0.30 if no bootstrapper has made $500+ MRR in this niche in last 12 months
  +0.20 if requires B2B enterprise sales or institutional trust
  +0.20 if regulated (finance, health, legal) — not just adjacent, actually regulated
  +0.15 if dominant incumbent has >70% market share with no Reddit complaints
  +0.15 if CAC > $150 for a $29/mo product (payback period > 5 months)

  - Never recommend niches in the EXHAUSTED_NICHES list
  - Output ONLY valid JSON. No encouragement. Pure adversarial.""",
    ),
    (
        "KIMI_SCOUT_AUDIENCE",
        "audience_analyst",
        f"""You are the Audience Analyst on AI Squadron's Research Council. Today is {_TODAY}.

YOUR MANDATE: Build a detailed, realistic buyer persona for each niche.
NOT a marketing persona — a PURCHASING persona. Who actually takes out their credit card?

USE THE TAVILY RESULTS to find real audience language:
  - Reddit threads where this audience complains about their current tools
  - Quora questions this audience asks
  - Twitter/X threads where this pain is expressed

For each niche, output:
  buyer_persona:
    job_title:           Specific job title or role (not "small business owner")
    company_size:        Exact range ("1-person" | "2-10" | "10-50" | "enterprise")
    exact_pain:          One sentence using words THEY would use (not marketing language)
    current_workaround:  What they do today (spreadsheet, Zapier hack, manual, incumbent tool)
    trigger_event:       The moment they start searching for a solution
    wtp_monthly_usd:     Realistic monthly spend based on their role (not aspirational)
    search_queries:      3 exact Google queries this person types when looking for solutions
  pain_severity:         0.0–1.0 (0=minor annoyance, 1=stops them working)
  evidence_quality:      "CITED" (found real forum/Reddit post) | "INFERRED"

  - Never recommend niches in the EXHAUSTED_NICHES list
  - Output ONLY valid JSON""",
    ),
    (
        "KIMI_SCOUT_EXECUTION",
        "execution_scout",
        f"""You are the Execution Scout on AI Squadron's Research Council. Today is {_TODAY}.

YOUR MANDATE: Judge whether AI Squadron's specific stack can build and ship this niche
competitively in ONE engineering sprint (3 days LLM-generated code).

OUR STACK (cannot change):
  SaaS:   React 19 + Vite + Supabase + Railway + FastAPI
  Media:  FFmpeg + ElevenLabs TTS + YouTube Data API v3
  Budget: $100/venture for external APIs
  Builder: One solo developer in India — no hardware, no mobile apps

USE THE TAVILY RESULTS to verify:
  - What APIs are needed and their pricing/availability
  - Whether the core feature requires data we can realistically access
  - Whether comparable tools have been built by solo founders

For each niche, output:
  build_feasibility:
    weeks_to_first_deploy:  Realistic weeks from start to deployed URL
    weeks_to_first_revenue: Realistic weeks to first paid user (not trial)
    complexity:             "LOW" | "MEDIUM" | "HIGH"
    blocking_dependencies:  [APIs, datasets, or integrations that could block us]
    api_cost_per_month_usd: Estimated external API costs at 100 users
    core_feature_buildable: true/false — can the #1 feature be built in our stack?
  red_flags:    [Specific technical reasons this is hard for our stack]
  green_flags:  [Specific technical reasons this is easy for our stack]
  evidence_quality: "CITED" | "INFERRED"

  - REJECT if: requires hardware, mobile app, real-time financial data, HIPAA compliance,
    browser extension, >3 external paid APIs, or operator licence
  - Never recommend niches in the EXHAUSTED_NICHES list
  - Output ONLY valid JSON""",
    ),
]

_SCOUT_JSON_SCHEMA = """
{
  "scout_role": "<role_name>",
  "niche_candidates": [
    {
      "niche": "Specific niche name (not generic — e.g. 'AI receipt scanner for UK freelancers')",
      "venture_type": "MICRO_SAAS | MEDIA_CHANNEL | AFFILIATE_SITE",
      "score": 0.0,
      "evidence": ["Specific cited fact with source — e.g. 'Reddit r/freelance: 847 upvotes on post about X'"],
      "risks": ["Specific risk with evidence — not generic warnings"]
    }
  ],
  "top_pick": "The single best niche this scout recommends",
  "rationale": "2-3 sentences max — must reference specific evidence, not general claims",
  "evidence_quality": "HIGH | MEDIUM | LOW"
}
"""

_DEBATE_SYSTEM = f"""You are the Research Council Debate Synthesiser. Today is {_TODAY}.

You receive five scout memos from specialists with different lenses. Your job:
1. Cross-reference where scouts AGREE (consensus = higher confidence)
2. Surface where scouts DISAGREE and why (disagreement = evidence gap or genuine risk)
3. Weight evidence quality — CITED evidence beats INFERRED reasoning
4. Recommend the niche with the best combination of:
   - Trend signal (trend_hunter)
   - Exploitable moat gap (competitor_analyst)
   - Low risk score (skeptic)
   - Strong buyer persona with real pain (audience_analyst)
   - Buildable in our stack (execution_scout)

IMPORTANT: If the scouts are recommending similar niches across multiple runs, flag this in
evidence_gaps and push for a DIFFERENT recommendation — diversity of exploration matters.

Output ONLY valid JSON."""

_DEBATE_SCHEMA = """
{
  "consensus_niches": ["Niche with multi-scout support"],
  "disagreements": [
    {
      "topic": "Specific point of disagreement",
      "positions": {
        "trend_hunter": "Their specific view",
        "skeptic": "Their specific challenge",
        "execution_scout": "Their specific assessment"
      },
      "resolution": "How this disagreement should be resolved"
    }
  ],
  "recommended_primary_niche": "The single best niche for this run",
  "recommended_venture_type": "MICRO_SAAS | MEDIA_CHANNEL | AFFILIATE_SITE",
  "council_confidence": 0.0,
  "evidence_quality_summary": "HIGH | MEDIUM | LOW — overall evidence quality this run",
  "synthesis": "Executive summary for the Grand CEO (max 500 words). Must cite specific scout findings.",
  "evidence_gaps": ["Specific things the council could not verify — what data is missing"],
  "alternative_niches": ["Second choice", "Third choice — different vertical than primary"]
}
"""


async def research_council_node(state: AgentState) -> AgentState:
    """LangGraph node — 5-scout parallel research + debate synthesis."""
    run_id = state["run_id"]
    venture_id = state["venture_id"]

    log.info("[RESEARCH_NODE] Global Research Council starting | run=%s", run_id)
    log_agent_event(run_id, venture_id, "RESEARCH_COUNCIL", "RUNNING",
                    "5 scouts + debate synthesis")

    # Fetch niche memory BEFORE the council runs — scouts need to know what's already tried
    try:
        from packages.db.pipeline import get_exhausted_niches
        exhausted_niches = get_exhausted_niches()
        log.info("[RESEARCH_NODE] Niche memory: %d exhausted niches", len(exhausted_niches))
    except Exception as exc:
        log.warning("[RESEARCH_NODE] Could not load niche memory: %s", exc)
        exhausted_niches = []

    # Fetch trend snapshot WITH exhausted_niches so Tavily doesn't search for them
    trend_snapshot = await fetch_trend_snapshot(exhausted_niches=exhausted_niches)
    trend_json = json.dumps(trend_snapshot, indent=2)

    log.info("[RESEARCH_NODE] Trend snapshot ready | sources=%s verticals=%s",
             trend_snapshot.get("source", "none"),
             trend_snapshot.get("pytrends_keywords", []))

    # Always run live with Gemini 2.5 Pro. No mock fallback.
    log.info("[RESEARCH_NODE] Running live council with Gemini 2.5 Pro")
    dossier_body, debate_transcript, token_total, latency_total = (
        await _run_live_council(trend_json, exhausted_niches)
    )
    mode = "claude_live"

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
    log.info("[RESEARCH_NODE] ✓ Dossier | niche=%s confidence=%.2f sources=%s tokens=%d",
             payload.recommended_primary_niche, payload.council_confidence,
             trend_snapshot.get("source", "?"), token_total)

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
    exhausted_niches: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], int, int]:
    """
    Run all 5 scouts in parallel with independent Tavily enrichment, then synthesise.

    Each scout gets:
      - The shared trend snapshot (pytrends + Tavily global results)
      - Their own role-specific Tavily search results (competitor reviews, failure cases, etc.)
      - The exhausted_niches list so they never propose already-tried niches
      - Today's date for recency judgement
    """
    exhausted_str = (
        "EXHAUSTED NICHES — DO NOT recommend these (already evaluated or KILL'd):\n"
        + ", ".join(exhausted_niches[:30])
        if exhausted_niches else
        "EXHAUSTED NICHES: none yet — this is a fresh exploration"
    )

    # Kick off all 5 scouts in parallel — each also runs its own Tavily search
    scout_tasks = [
        _run_single_scout(role, name, system, trend_json, exhausted_str)
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

    # Debate synthesis — cross-references all scout memos
    debate_prompt = (
        f"Today's date: {_TODAY}\n\n"
        f"Trend snapshot (pytrends + Tavily):\n{trend_json[:3000]}\n\n"
        f"{exhausted_str}\n\n"
        f"Scout memos:\n{json.dumps(scout_reports, indent=2)}\n\n"
        f"Produce the debate summary. Return ONLY JSON matching:\n{_DEBATE_SCHEMA}"
    )
    debate_resp = await call_llm(
        "KIMI_DEBATE_SYNTHESIZER", _DEBATE_SYSTEM, debate_prompt,
        temperature=0.2, max_tokens=4096,
    )
    token_total += debate_resp.total_tokens
    latency_total = max(latency_total, debate_resp.latency_ms)

    try:
        debate_summary: dict[str, Any] = json.loads(debate_resp.text)
    except json.JSONDecodeError as exc:
        log.warning("[RESEARCH_NODE] Debate JSON parse failed: %s — using fallback", exc)
        debate_summary = _fallback_debate(scout_reports)

    debate_transcript.append({"phase": "synthesis", "summary": debate_summary})

    dossier_body = {
        "scout_reports": scout_reports,
        "debate_summary": debate_summary,
        "recommended_primary_niche": debate_summary.get(
            "recommended_primary_niche",
            _best_pick_from_scouts(scout_reports),
        ),
        "recommended_venture_type": debate_summary.get("recommended_venture_type", "MICRO_SAAS"),
        "consensus_niches": debate_summary.get("consensus_niches", []),
        "disagreements": debate_summary.get("disagreements", []),
        "council_confidence": float(debate_summary.get("council_confidence", 0.5)),
    }
    return dossier_body, debate_transcript, token_total, latency_total


async def _run_single_scout(
    agent_role: str,
    role_name: str,
    system_prompt: str,
    trend_json: str,
    exhausted_str: str,
) -> tuple[dict[str, Any], int, int]:
    """
    Run one scout with role-specific Tavily enrichment.
    The Tavily search runs in parallel with scout setup for efficiency.
    """
    # Each scout independently searches Tavily for evidence relevant to its lens
    # We kick off the Tavily search immediately and await it before building the prompt
    initial_candidates = _extract_candidate_topics(trend_json)
    tavily_results = await fetch_tavily_for_scout(role_name, initial_candidates)

    tavily_context = ""
    if tavily_results:
        tavily_context = (
            "\n\nTAVILY WEB SEARCH RESULTS (use as evidence):\n"
            + json.dumps([
                {"title": r.get("title", ""), "snippet": r.get("snippet", "")[:300]}
                for r in tavily_results[:5]
            ], indent=2)
        )

    user_prompt = (
        f"Today is {_TODAY}.\n\n"
        f"TREND SNAPSHOT (pytrends + Tavily global):\n{trend_json[:4000]}\n"
        f"{tavily_context}\n\n"
        f"{exhausted_str}\n\n"
        f"You are the {role_name}. Find 5 DIVERSE niche candidates from DIFFERENT verticals.\n"
        f"Each candidate must be from a different market segment — no variations on the same theme.\n"
        f"Use the Tavily results and trend data as evidence — cite specific findings.\n\n"
        f"Return ONLY JSON matching:\n{_SCOUT_JSON_SCHEMA}"
    )

    resp = await call_llm(agent_role, system_prompt, user_prompt,
                          temperature=0.5,   # higher temp for more diverse niche discovery
                          max_tokens=3072)
    try:
        raw_text = resp.text
        # Handle case where Gemini wraps in code fences despite instructions
        if "```" in raw_text:
            from packages.tools.llm import extract_json
            raw_text = extract_json(raw_text)
        data: dict[str, Any] = json.loads(raw_text)
        data["scout_role"] = role_name
        data["tavily_enriched"] = bool(tavily_results)
        return data, resp.total_tokens, resp.latency_ms
    except json.JSONDecodeError as exc:
        log.warning("[RESEARCH_NODE] Scout %s JSON parse failed: %s | raw=%r",
                    role_name, exc, resp.text[:120])
        return _fallback_scout(role_name, "json_parse_error"), resp.total_tokens, resp.latency_ms


def _extract_candidate_topics(trend_json: str) -> list[str]:
    """Extract top-level topics from trend snapshot for per-scout Tavily queries."""
    try:
        snap = json.loads(trend_json)
        topics = [t.get("topic", "") for t in snap.get("top_trending_topics", [])[:3]]
        emerging = snap.get("emerging_keywords", [])[:2]
        return [t for t in topics + emerging if t][:5]
    except Exception:
        return []


def _best_pick_from_scouts(scout_reports: list[dict[str, Any]]) -> str:
    """Derive the best niche from scout reports when debate JSON fails."""
    picks = [r.get("top_pick", "") for r in scout_reports if r.get("top_pick")]
    if not picks:
        return ""
    # Most common pick wins; in tie, prefer picks with higher evidence quality
    return max(set(picks), key=picks.count)


def _fallback_scout(role_name: str, reason: str) -> dict[str, Any]:
    """Minimal fallback when a single scout's JSON parse fails. No hardcoded niches."""
    log.error("[RESEARCH_NODE] Scout %s failed: %s", role_name, reason)
    return {
        "scout_role": role_name,
        "niche_candidates": [],
        "top_pick": "",
        "rationale": f"Scout failed — {reason}",
        "evidence_quality": "LOW",
        "error": reason,
    }


def _fallback_debate(scout_reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Fallback debate when synthesis JSON parse fails. Derives top pick from scout reports."""
    top = _best_pick_from_scouts(scout_reports)
    log.warning("[RESEARCH_NODE] Debate synthesis JSON failed — best scout pick: %s", top)
    return {
        "consensus_niches":          [top] if top else [],
        "disagreements":             [],
        "recommended_primary_niche": top,
        "recommended_venture_type":  "MICRO_SAAS",
        "council_confidence":        0.35,
        "evidence_quality_summary":  "LOW",
        "synthesis":                 "Debate synthesis failed — Grand CEO must weigh scout memos.",
        "evidence_gaps":             ["debate_json_parse_failed"],
        "alternative_niches":        [],
    }
