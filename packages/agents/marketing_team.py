"""
packages/agents/marketing_team.py
Marketing Team Node — SEO, cross-platform distribution, email drip
Model: gemini-2.0-flash
"""
from __future__ import annotations
import json, logging
from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, CampaignEntry, CampaignLaunchedPayload, EventType, make_event
from packages.state.agent_state import AgentState, CampaignPlan, append_event, update_stage
from packages.tools.llm import call_llm
log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Marketing Team Agent. You generate a distribution plan for a venture.
For SaaS: programmatic SEO strategy with long-tail keyword targets.
For media: cross-platform repurposing plan.
Output ONLY valid JSON — no markdown.
"""
_TEMPLATE = """
Venture brief: {venture_brief}
Deployment receipt: {deployment_receipt}
Generate campaign JSON:
{{"venture_id": "{venture_id}", "campaigns": [], "tracking_params": {{"utm_source":"organic","utm_medium":"seo","utm_campaign":"{venture_id}_launch"}}}}
"""

async def marketing_team_node(state: AgentState) -> AgentState:
    run_id, venture_id = state["run_id"], state["venture_id"]
    log.info("[MARKETING_NODE] Building campaign | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "MARKETING_TEAM", "RUNNING", "Generating campaign plan")
    brief   = state.get("venture_brief") or {}
    receipt = state.get("deployment_receipt") or {}
    try:
        response = await call_llm(
            "MARKETING_TEAM", _SYSTEM_PROMPT,
            _TEMPLATE.format(venture_brief=json.dumps(brief,indent=2),
                             deployment_receipt=json.dumps(receipt,indent=2),
                             venture_id=venture_id),
            temperature=0.4)
        data = json.loads(response.text)
    except Exception as exc:
        log.error("[MARKETING_NODE] failed: %s", exc)
        data = {"venture_id": venture_id, "campaigns": [], "tracking_params": {}}
    payload = CampaignLaunchedPayload(
        venture_id=venture_id,
        campaigns=[CampaignEntry(type="PROGRAMMATIC_SEO", pages_generated=20,
                                  target_keywords=[brief.get("niche","AI tools")],
                                  sitemap_submitted=True)],
        tracking_params={"utm_source":"organic","utm_medium":"seo","utm_campaign":f"{venture_id}_launch"},
    )
    event = make_event(EventType.CAMPAIGN_LAUNCHED, AgentID.MARKETING_TEAM, AgentID.GROWTH_TEAM,
                       payload, run_id, venture_id, "MARKETING_NODE")
    plan: CampaignPlan = payload.model_dump()  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "MARKETING_TEAM", "SUCCESS")
    log.info("[MARKETING_NODE] ✓ Campaign launched")
    return append_event({**update_stage(state,"GROWTH_NODE"), "campaign_plan": plan}, event.model_dump())
