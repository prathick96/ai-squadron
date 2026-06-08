"""
packages/agents/product/product_growth.py
Product Growth Agent — MRR tracking and scale/kill decisions.

Model:   claude-haiku-4-5-20251001
Input:   deployment_receipt, channel_analytics, venture_brief
Output:  growth_report with MRR trajectory and SCALE/MAINTAIN/KILL signal

Kill threshold: 60 days with MRR < $50 → KILL signal
Scale threshold: MRR > $500 → SCALE signal (triggers Revenue Engine attention)
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.state.agent_state import AgentState, append_event, update_stage
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

_KILL_THRESHOLD_MRR = 50.0
_KILL_THRESHOLD_DAYS = 60
_SCALE_THRESHOLD_MRR = 500.0

_SYSTEM_PROMPT = """
You are the Product Growth Agent for AI Squadron's Product Department.
Analyse deployment metrics and produce a growth assessment.

Decision rules (non-negotiable):
- KILL if: days_live >= 60 AND mrr_usd < 50
- SCALE if: mrr_usd >= 500
- MAINTAIN otherwise

Output ONLY valid JSON — no markdown.
"""

_TEMPLATE = """
Venture: {venture_id}
Days live: {days_live}
Current MRR: ${mrr_usd}
Trial signups: {trial_signups}
Paying customers: {paying_customers}
Churn rate: {churn_pct}%
Deployment URL: {deployment_url}
Marketing plan channels: {channels}

Produce growth assessment:
{{
  "venture_id": "{venture_id}",
  "mrr_usd": 0.0,
  "arr_usd": 0.0,
  "mrr_trajectory": "GROWING | FLAT | DECLINING",
  "days_live": 0,
  "trial_signups": 0,
  "paying_customers": 0,
  "activation_rate_pct": 0.0,
  "churn_rate_pct": 0.0,
  "signal": "SCALE | MAINTAIN | KILL",
  "signal_rationale": "...",
  "next_action": "..."
}}
"""


async def product_growth_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    analytics = state.get("channel_analytics") or {}
    receipt = state.get("deployment_receipt") or {}
    marketing = state.get("marketing_plan") or {}

    deployments = receipt.get("deployments", [])
    url = deployments[0].get("url", "") if deployments else ""
    days_live = analytics.get("days_live", 1)
    mrr = analytics.get("mrr_usd", 0.0)
    signups = analytics.get("trial_signups", 0)
    paying = analytics.get("paying_customers", 0)
    churn = analytics.get("churn_rate_pct", 0.0)
    channels = [c.get("channel") for c in marketing.get("launch_channels", [])]

    log.info("[PRODUCT_GROWTH_NODE] Growth assessment | venture=%s days=%d mrr=%.2f",
             venture_id, days_live, mrr)
    log_agent_event(run_id, venture_id, "PRODUCT_GROWTH", "RUNNING", "MRR assessment")

    user_prompt = _TEMPLATE.format(
        venture_id=venture_id, days_live=days_live, mrr_usd=mrr,
        trial_signups=signups, paying_customers=paying, churn_pct=churn,
        deployment_url=url, channels=json.dumps(channels),
    )

    try:
        response = await call_llm("PRODUCT_GROWTH", _SYSTEM_PROMPT, user_prompt, temperature=0.2)
        report: dict = json.loads(extract_json(response.text))
    except Exception as exc:
        log.error("[PRODUCT_GROWTH_NODE] failed: %s", exc)
        log_agent_event(run_id, venture_id, "PRODUCT_GROWTH", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    signal = report.get("signal", "MAINTAIN")
    log.info("[PRODUCT_GROWTH_NODE] ✓ Signal=%s MRR=%.2f | venture=%s",
             signal, report.get("mrr_usd", 0), venture_id)
    log_agent_event(run_id, venture_id, "PRODUCT_GROWTH", "SUCCESS",
                    tokens_used=response.total_tokens,
                    current_task=f"Signal: {signal} | MRR: ${report.get('mrr_usd', 0):.2f}")

    new_state = update_stage(state, "END")
    return append_event({**new_state, "growth_report": report}, {
        "event_type": "GROWTH_SIGNAL",
        "source": "PRODUCT_GROWTH",
        "venture_id": venture_id,
        "signal": signal,
    })
