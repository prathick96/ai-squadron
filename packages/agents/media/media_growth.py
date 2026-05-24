"""
packages/agents/media/media_growth.py
Media Growth Agent — channel analytics → SCALE/MAINTAIN/KILL signal.

Model:   gemini-2.0-flash
Input:   channel_analytics, channel_strategy, published_urls
Output:  growth_report with trajectory and next action

Decision thresholds:
  KILL    : days_live >= 60 AND views_last_28d < 1,000 AND revenue < $50
  SCALE   : subscribers >= 10,000 OR monthly_revenue >= $500
  MAINTAIN: all other cases
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, make_event
from packages.state.agent_state import AgentState, append_event, update_stage
from packages.tools.llm import call_llm

log = logging.getLogger(__name__)

_KILL_DAYS = 60
_KILL_MIN_VIEWS = 1000
_KILL_MIN_REVENUE = 50.0
_SCALE_SUBS = 10000
_SCALE_REVENUE = 500.0

_SYSTEM_PROMPT = """
You are the Media Growth Agent for AI Squadron's Media Department.
Analyse channel metrics and produce a growth assessment with SCALE/MAINTAIN/KILL signal.

Decision rules (non-negotiable):
- KILL if: days_live >= 60 AND views_last_28d < 1,000 AND revenue_usd < 50
- SCALE if: subscribers >= 10,000 OR monthly_revenue >= 500
- MAINTAIN: all other cases

Next actions for each signal:
- KILL:     Document lessons, terminate resources, flag niche as exhausted
- SCALE:    Increase upload cadence, expand to secondary platform, double content budget
- MAINTAIN: Optimise worst-performing video's title/thumbnail (A/B test), stay course

Output ONLY valid JSON — no markdown.
"""

_TEMPLATE = """
Channel Analytics:
{analytics}

Channel Strategy:
{strategy}

Published URLs: {urls}

Produce growth assessment:
{{
  "venture_id": "{venture_id}",
  "signal": "SCALE | MAINTAIN | KILL",
  "signal_rationale": "...",
  "views_last_28d": 0,
  "subscribers": 0,
  "monthly_revenue_usd": 0.0,
  "days_live": 0,
  "mrr_trajectory": "GROWING | FLAT | DECLINING",
  "next_action": "...",
  "content_optimisation": "Specific video to A/B test title or thumbnail"
}}
"""


async def media_growth_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    analytics = state.get("channel_analytics") or {}
    strategy = state.get("channel_strategy") or {}
    urls = state.get("published_urls") or {}

    log.info("[MEDIA_GROWTH_NODE] Growth assessment | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "MEDIA_GROWTH", "RUNNING", "Channel growth signal")

    user_prompt = _TEMPLATE.format(
        analytics=json.dumps(analytics, indent=2),
        strategy=json.dumps(strategy, indent=2),
        urls=json.dumps(urls, indent=2),
        venture_id=venture_id,
    )

    try:
        response = await call_llm("MEDIA_GROWTH", _SYSTEM_PROMPT, user_prompt, temperature=0.2)
        report: dict = json.loads(response.text)
    except Exception as exc:
        log.error("[MEDIA_GROWTH_NODE] failed: %s", exc)
        log_agent_event(run_id, venture_id, "MEDIA_GROWTH", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    signal = report.get("signal", "MAINTAIN")
    log.info("[MEDIA_GROWTH_NODE] ✓ Signal=%s | views=%d subs=%d | venture=%s",
             signal, report.get("views_last_28d", 0), report.get("subscribers", 0), venture_id)
    log_agent_event(run_id, venture_id, "MEDIA_GROWTH", "SUCCESS",
                    tokens_used=response.total_tokens,
                    current_task=f"Signal: {signal}")

    new_state = update_stage(state, "END")
    return append_event({**new_state, "growth_report": report}, {
        "event_type": "GROWTH_SIGNAL",
        "source": "MEDIA_GROWTH",
        "venture_id": venture_id,
        "signal": signal,
    })
