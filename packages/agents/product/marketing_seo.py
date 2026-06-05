"""
packages/agents/product/marketing_seo.py
Marketing & SEO Agent (Product) — post-launch growth for SaaS products.

Model:   claude-haiku-4-5-20251001
Input:   deployment_receipt, venture_brief, tech_spec
Output:  marketing_plan with SEO targets, copy, and distribution channels

Scope:
  ✓ Landing page copy and SEO meta
  ✓ Product Hunt launch checklist
  ✓ Reddit / HN / IndieHackers distribution strategy
  ✓ Content calendar for first 30 days
  ✗ No paid ads (organic first until MRR > $5K per Zuckerberg rule)
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.state.agent_state import AgentState, append_event, update_stage
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Marketing & SEO Agent for AI Squadron's Product Department.
Your job: maximum organic reach for a newly deployed SaaS product.

Rules:
- No paid ads until MRR > $5,000/month
- SEO keywords: long-tail, low-competition, high-intent
- Distribution: Reddit, Hacker News, IndieHackers, Product Hunt, Twitter/X
- Copy must focus on outcome (what the user gains), not features
- Product Hunt launch: Tuesday–Thursday, 00:01 PST

Output ONLY valid JSON — no markdown.
"""

_TEMPLATE = """
Venture Brief:
{venture_brief}

Deployment:
{deployment_url}

Product type: {product_type}

Generate a 30-day marketing plan:
{{
  "venture_id": "{venture_id}",
  "landing_page": {{
    "headline": "...",
    "subheadline": "...",
    "cta_text": "...",
    "seo_title": "...",
    "seo_description": "...",
    "target_keywords": ["keyword1", "keyword2"]
  }},
  "launch_channels": [
    {{"channel": "product_hunt | reddit | hacker_news | indie_hackers",
      "post_title": "...", "post_body": "...", "best_time": "..."}}
  ],
  "content_calendar": [
    {{"day": 1, "channel": "...", "topic": "...", "format": "post|thread|article"}}
  ],
  "reddit_targets": ["r/subreddit"],
  "estimated_organic_traffic_month_1": 0
}}
"""


async def marketing_seo_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    brief = state.get("venture_brief") or {}
    receipt = state.get("deployment_receipt") or {}
    spec = state.get("tech_spec") or {}

    deployments = receipt.get("deployments", [])
    url = deployments[0].get("url", "") if deployments else ""

    log.info("[MARKETING_SEO_NODE] Building launch plan | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "MARKETING_SEO", "RUNNING", "30-day marketing plan")

    # Pass only the fields marketing SEO actually needs — not the full brief.
    # venture_brief can include niche_shortlist or other large fields that
    # bloat the prompt and cause truncation (ven_7c1a5960 failure pattern).
    brief_summary = {
        "niche":                  brief.get("niche", ""),
        "target_audience":        brief.get("target_audience", ""),
        "recommended_monetization": brief.get("recommended_monetization", []),
        "content_angles":         brief.get("content_angles", []),
        "go_rationale":           brief.get("go_rationale", "")[:200],
    }
    user_prompt = _TEMPLATE.format(
        venture_brief=json.dumps(brief_summary, indent=2),
        deployment_url=url,
        product_type=spec.get("product_type", "MICRO_SAAS"),
        venture_id=venture_id,
    )

    try:
        response = await call_llm("MARKETING_SEO", _SYSTEM_PROMPT, user_prompt, temperature=0.5)
        plan: dict = json.loads(extract_json(response.text))
    except Exception as exc:
        log.error("[MARKETING_SEO_NODE] failed: %s", exc)
        log_agent_event(run_id, venture_id, "MARKETING_SEO", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    log_agent_event(run_id, venture_id, "MARKETING_SEO", "SUCCESS", tokens_used=response.total_tokens)
    log.info("[MARKETING_SEO_NODE] ✓ Plan ready | channels=%d",
             len(plan.get("launch_channels", [])))

    new_state = update_stage(state, "PRODUCT_GROWTH_NODE")
    return append_event({**new_state, "marketing_plan": plan}, {
        "event_type": "MARKETING_PLAN_READY",
        "source": "MARKETING_SEO",
        "venture_id": venture_id,
    })
