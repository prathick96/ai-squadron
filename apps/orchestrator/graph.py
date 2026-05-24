"""
apps/orchestrator/graph.py
AI Squadron graph dispatcher — routes to Product or Media sub-graph.

Usage:
  from apps.orchestrator.graph import build_squadron_graph
  graph = build_squadron_graph(department="PRODUCT")   # or "MEDIA"

Callers pass department="PRODUCT", "MEDIA", or "AUTO" to main.py to select the pipeline.
"""
from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from packages.state.agent_state import AgentState

log = logging.getLogger(__name__)


def build_squadron_graph(
    department: Literal["PRODUCT", "MEDIA", "AUTO"] = "AUTO",
) -> StateGraph:
    """
    Return the compiled LangGraph for the requested department.

    department="AUTO"    → shared RESEARCH+CEO, then routes by CEO's department decision
    department="PRODUCT" → full Product pipeline
    department="MEDIA"   → full Media pipeline
    """
    if department == "PRODUCT":
        from apps.orchestrator.product_graph import build_product_graph
        return build_product_graph()

    if department == "MEDIA":
        from apps.orchestrator.media_graph import build_media_graph
        return build_media_graph()

    # AUTO: shared entry points → conditional split on CEO's department decision
    return _build_auto_graph()


def _build_auto_graph() -> StateGraph:
    """
    Unified graph: shared RESEARCH + CEO, then conditionally enters
    the Product or Media pipeline based on CEO's department assignment.
    This avoids duplicating research/CEO nodes in both sub-graphs.
    """
    from packages.agents.governance.research_council import research_council_node
    from packages.agents.governance.grand_ceo import grand_ceo_node

    # Import all department nodes
    from packages.agents.product.product_vp import product_vp_node
    from packages.agents.product.product_manager import product_manager_node
    from packages.agents.product.engineering_team import engineering_team_node
    from packages.agents.product.qa_technical import qa_technical_node
    from packages.agents.product.deployment_agent import deployment_agent_node
    from packages.agents.product.marketing_seo import marketing_seo_node
    from packages.agents.product.product_growth import product_growth_node

    from packages.agents.media.media_vp import media_vp_node
    from packages.agents.media.script_agent import script_agent_node
    from packages.agents.media.voice_agent import voice_agent_node
    from packages.agents.media.video_agent import video_agent_node
    from packages.agents.media.thumbnail_agent import thumbnail_agent_node
    from packages.agents.media.seo_metadata_agent import seo_metadata_node
    from packages.agents.media.qa_compliance import qa_compliance_node
    from packages.agents.media.publishing_agent import publishing_agent_node
    from packages.agents.media.analytics_agent import analytics_agent_node
    from packages.agents.media.media_growth import media_growth_node

    from packages.agents.shared.legal_agent import legal_agent_node
    from packages.agents.shared.security_agent import security_agent_node
    from packages.agents.shared.anti_ban_agent import anti_ban_agent_node
    from packages.agents.shared.account_distribution import account_distribution_node

    g: StateGraph = StateGraph(AgentState)

    # Governance (shared)
    g.add_node("RESEARCH_NODE", research_council_node)
    g.add_node("CEO_NODE",      grand_ceo_node)

    # Product nodes
    g.add_node("PRODUCT_VP_NODE",        product_vp_node)
    g.add_node("PRODUCT_MANAGER_NODE",   product_manager_node)
    g.add_node("ENGINEERING_NODE",       engineering_team_node)
    g.add_node("QA_TECHNICAL_NODE",      qa_technical_node)

    # Media nodes
    g.add_node("MEDIA_VP_NODE",          media_vp_node)
    g.add_node("SCRIPT_NODE",            script_agent_node)
    g.add_node("VOICE_NODE",             voice_agent_node)
    g.add_node("VIDEO_NODE",             video_agent_node)
    g.add_node("THUMBNAIL_NODE",         thumbnail_agent_node)
    g.add_node("SEO_METADATA_NODE",      seo_metadata_node)
    g.add_node("QA_COMPLIANCE_NODE",     qa_compliance_node)
    g.add_node("PUBLISHING_NODE",        publishing_agent_node)
    g.add_node("ANALYTICS_NODE",         analytics_agent_node)
    g.add_node("ANTI_BAN_NODE",          anti_ban_agent_node)
    g.add_node("MEDIA_GROWTH_NODE",      media_growth_node)

    # Shared post-QA
    g.add_node("LEGAL_NODE",                 legal_agent_node)
    g.add_node("SECURITY_NODE",              security_agent_node)
    g.add_node("ACCOUNT_DISTRIBUTION_NODE",  account_distribution_node)

    # Department-specific post-deploy
    g.add_node("DEPLOYMENT_NODE",        deployment_agent_node)
    g.add_node("MARKETING_SEO_NODE",     marketing_seo_node)
    g.add_node("PRODUCT_GROWTH_NODE",    product_growth_node)
    g.add_node("MANUAL_REVIEW_NODE",     _manual_review_node)

    # Entry
    g.set_entry_point("RESEARCH_NODE")
    g.add_edge("RESEARCH_NODE", "CEO_NODE")

    # CEO → department split
    g.add_conditional_edges("CEO_NODE", _ceo_routing_edge, {
        "PRODUCT_VP_NODE":    "PRODUCT_VP_NODE",
        "MEDIA_VP_NODE":      "MEDIA_VP_NODE",
        END:                  END,
    })

    # Product pipeline
    g.add_edge("PRODUCT_VP_NODE",      "PRODUCT_MANAGER_NODE")
    g.add_edge("PRODUCT_MANAGER_NODE", "ENGINEERING_NODE")
    g.add_edge("ENGINEERING_NODE",     "QA_TECHNICAL_NODE")
    g.add_conditional_edges("QA_TECHNICAL_NODE", _product_qa_edge, {
        "LEGAL_NODE":         "LEGAL_NODE",
        "ENGINEERING_NODE":   "ENGINEERING_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    # Media pipeline
    g.add_edge("MEDIA_VP_NODE",     "SCRIPT_NODE")
    g.add_edge("SCRIPT_NODE",       "VOICE_NODE")
    g.add_edge("VOICE_NODE",        "VIDEO_NODE")
    g.add_edge("VIDEO_NODE",        "THUMBNAIL_NODE")
    g.add_edge("THUMBNAIL_NODE",    "SEO_METADATA_NODE")
    g.add_edge("SEO_METADATA_NODE", "QA_COMPLIANCE_NODE")
    g.add_conditional_edges("QA_COMPLIANCE_NODE", _media_qa_edge, {
        "LEGAL_NODE":         "LEGAL_NODE",
        "SCRIPT_NODE":        "SCRIPT_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    # Shared compliance + distribution
    g.add_conditional_edges("LEGAL_NODE", _legal_edge, {
        "SECURITY_NODE":      "SECURITY_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })
    g.add_edge("SECURITY_NODE", "ACCOUNT_DISTRIBUTION_NODE")

    # Account dist → department-specific deploy
    g.add_conditional_edges("ACCOUNT_DISTRIBUTION_NODE", _dept_deploy_edge, {
        "DEPLOYMENT_NODE":  "DEPLOYMENT_NODE",
        "PUBLISHING_NODE":  "PUBLISHING_NODE",
    })

    # Product post-deploy
    g.add_edge("DEPLOYMENT_NODE",   "MARKETING_SEO_NODE")
    g.add_edge("MARKETING_SEO_NODE", "PRODUCT_GROWTH_NODE")
    g.add_edge("PRODUCT_GROWTH_NODE", END)

    # Media post-publish
    g.add_edge("PUBLISHING_NODE", "ANALYTICS_NODE")
    g.add_edge("ANALYTICS_NODE",  "ANTI_BAN_NODE")
    g.add_conditional_edges("ANTI_BAN_NODE", _anti_ban_edge, {
        "MEDIA_GROWTH_NODE":  "MEDIA_GROWTH_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })
    g.add_edge("MEDIA_GROWTH_NODE",  END)
    g.add_edge("MANUAL_REVIEW_NODE", END)

    compiled = g.compile()
    log.info("Auto-dispatch graph compiled")
    return compiled


# ---------------------------------------------------------------------------
# Edge functions for the auto graph
# ---------------------------------------------------------------------------

def _ceo_routing_edge(state: AgentState):
    brief = state.get("venture_brief") or {}
    if not brief.get("go_decision", False):
        return END
    dept = state.get("department", "PRODUCT")
    return "PRODUCT_VP_NODE" if dept == "PRODUCT" else "MEDIA_VP_NODE"


def _product_qa_edge(state: AgentState):
    qa = state.get("qa_report") or {}
    retries = state.get("qa_retry_count", 0)
    if qa.get("is_passed"):
        return "LEGAL_NODE"
    if retries >= state.get("qa_max_retries", 3):
        return "MANUAL_REVIEW_NODE"
    return "ENGINEERING_NODE"


def _media_qa_edge(state: AgentState):
    qa = state.get("qa_report") or {}
    retries = state.get("qa_retry_count", 0)
    if qa.get("is_passed"):
        return "LEGAL_NODE"
    if retries >= state.get("qa_max_retries", 3):
        return "MANUAL_REVIEW_NODE"
    return "SCRIPT_NODE"


def _legal_edge(state: AgentState):
    clearance = state.get("legal_clearance") or {}
    return "SECURITY_NODE" if clearance.get("is_cleared", False) else "MANUAL_REVIEW_NODE"


def _dept_deploy_edge(state: AgentState):
    return "DEPLOYMENT_NODE" if state.get("department") == "PRODUCT" else "PUBLISHING_NODE"


def _anti_ban_edge(state: AgentState):
    stage = state.get("pipeline_stage", "")
    return "MANUAL_REVIEW_NODE" if stage == "MANUAL_REVIEW_NODE" else "MEDIA_GROWTH_NODE"


async def _manual_review_node(state: AgentState) -> AgentState:
    import uuid
    reason = state.get("manual_review_reason", "Unknown")
    log.critical("[MANUAL_REVIEW] venture=%s reason=%s", state["venture_id"], reason)
    try:
        from packages.revenue.store import enqueue_manual_review
        enqueue_manual_review({
            "id": str(uuid.uuid4()), "venture_id": state["venture_id"],
            "run_id": state["run_id"], "review_reason": reason,
            "artifact_type": state.get("department", "PRODUCT"),
            "priority": "CRITICAL",
        })
    except Exception:
        pass
    return {**state, "pipeline_stage": "MANUAL_REVIEW"}

