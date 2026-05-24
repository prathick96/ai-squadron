"""
apps/orchestrator/product_graph.py
Product Department LangGraph pipeline.

Happy path:
  RESEARCH → CEO → PRODUCT_VP → PRODUCT_MANAGER → ENGINEERING ⟳ → QA_TECHNICAL ⟳
  → LEGAL → SECURITY → ACCOUNT_DIST → DEPLOYMENT → MARKETING_SEO → PRODUCT_GROWTH → END

QA retry loop: max 3 attempts → MANUAL_REVIEW_NODE
Legal veto:    is_cleared=False → MANUAL_REVIEW_NODE
"""
from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from packages.agents.governance.grand_ceo import grand_ceo_node
from packages.agents.governance.research_council import research_council_node
from packages.agents.product.product_vp import product_vp_node
from packages.agents.product.product_manager import product_manager_node
from packages.agents.product.engineering_team import engineering_team_node
from packages.agents.product.qa_technical import qa_technical_node
from packages.agents.product.deployment_agent import deployment_agent_node
from packages.agents.product.marketing_seo import marketing_seo_node
from packages.agents.product.product_growth import product_growth_node
from packages.agents.shared.legal_agent import legal_agent_node
from packages.agents.shared.security_agent import security_agent_node
from packages.agents.shared.account_distribution import account_distribution_node
from packages.state.agent_state import AgentState

log = logging.getLogger(__name__)


async def manual_review_node(state: AgentState) -> AgentState:
    import uuid
    reason = state.get("manual_review_reason", "Unknown — check QA / Legal report")
    venture_id = state["venture_id"]
    run_id = state["run_id"]
    log.critical("[MANUAL_REVIEW] venture=%s reason=%s", venture_id, reason)
    try:
        from packages.revenue.store import enqueue_manual_review
        enqueue_manual_review({
            "id": str(uuid.uuid4()), "venture_id": venture_id, "run_id": run_id,
            "review_reason": reason, "artifact_type": "BUILD", "priority": "CRITICAL",
        })
    except Exception:
        pass
    return {**state, "pipeline_stage": "MANUAL_REVIEW"}


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------

def go_decision_edge(state: AgentState) -> Literal["PRODUCT_VP_NODE", "END"]:
    brief = state.get("venture_brief") or {}
    if brief.get("go_decision", False):
        return "PRODUCT_VP_NODE"
    log.info("go_decision_edge → END | niche=%s", brief.get("niche", "unknown"))
    return END


def qa_routing_edge(
    state: AgentState,
) -> Literal["LEGAL_NODE", "ENGINEERING_NODE", "MANUAL_REVIEW_NODE"]:
    qa = state.get("qa_report") or {}
    retries = state.get("qa_retry_count", 0)
    max_r = state.get("qa_max_retries", 3)
    if qa.get("is_passed"):
        return "LEGAL_NODE"
    if retries >= max_r:
        return "MANUAL_REVIEW_NODE"
    return "ENGINEERING_NODE"


def legal_routing_edge(
    state: AgentState,
) -> Literal["SECURITY_NODE", "MANUAL_REVIEW_NODE"]:
    clearance = state.get("legal_clearance") or {}
    if clearance.get("is_cleared", False):
        return "SECURITY_NODE"
    return "MANUAL_REVIEW_NODE"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_product_graph() -> StateGraph:
    """
    Assemble and compile the Product Department LangGraph.

    Node count: 13 (including MANUAL_REVIEW)
    """
    g: StateGraph = StateGraph(AgentState)

    g.add_node("RESEARCH_NODE",          research_council_node)
    g.add_node("CEO_NODE",               grand_ceo_node)
    g.add_node("PRODUCT_VP_NODE",        product_vp_node)
    g.add_node("PRODUCT_MANAGER_NODE",   product_manager_node)
    g.add_node("ENGINEERING_NODE",       engineering_team_node)
    g.add_node("QA_TECHNICAL_NODE",      qa_technical_node)
    g.add_node("LEGAL_NODE",             legal_agent_node)
    g.add_node("SECURITY_NODE",          security_agent_node)
    g.add_node("ACCOUNT_DISTRIBUTION_NODE", account_distribution_node)
    g.add_node("DEPLOYMENT_NODE",        deployment_agent_node)
    g.add_node("MARKETING_SEO_NODE",     marketing_seo_node)
    g.add_node("PRODUCT_GROWTH_NODE",    product_growth_node)
    g.add_node("MANUAL_REVIEW_NODE",     manual_review_node)

    g.set_entry_point("RESEARCH_NODE")
    g.add_edge("RESEARCH_NODE", "CEO_NODE")

    g.add_conditional_edges("CEO_NODE", go_decision_edge,
                            {"PRODUCT_VP_NODE": "PRODUCT_VP_NODE", END: END})

    g.add_edge("PRODUCT_VP_NODE",      "PRODUCT_MANAGER_NODE")
    g.add_edge("PRODUCT_MANAGER_NODE", "ENGINEERING_NODE")
    g.add_edge("ENGINEERING_NODE",     "QA_TECHNICAL_NODE")

    g.add_conditional_edges("QA_TECHNICAL_NODE", qa_routing_edge, {
        "LEGAL_NODE":         "LEGAL_NODE",
        "ENGINEERING_NODE":   "ENGINEERING_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    g.add_conditional_edges("LEGAL_NODE", legal_routing_edge, {
        "SECURITY_NODE":      "SECURITY_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    g.add_edge("SECURITY_NODE",             "ACCOUNT_DISTRIBUTION_NODE")
    g.add_edge("ACCOUNT_DISTRIBUTION_NODE", "DEPLOYMENT_NODE")
    g.add_edge("DEPLOYMENT_NODE",           "MARKETING_SEO_NODE")
    g.add_edge("MARKETING_SEO_NODE",        "PRODUCT_GROWTH_NODE")
    g.add_edge("PRODUCT_GROWTH_NODE",       END)
    g.add_edge("MANUAL_REVIEW_NODE",        END)

    compiled = g.compile()
    log.info("Product graph compiled — 13 nodes")
    return compiled


product_graph = build_product_graph()
