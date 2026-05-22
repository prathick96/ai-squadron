"""
apps/orchestrator/graph.py
LangGraph graph assembly — wires all agent nodes with correct edges.
This is the structural core of the entire system.
"""
from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from packages.agents.account_distribution import account_distribution_node
from packages.agents.ceo_niche_scout import ceo_niche_scout_node
from packages.agents.market_research import market_research_node
from packages.agents.content_team import content_team_node
from packages.agents.deployment_team import deployment_team_node
from packages.agents.engineering_team import engineering_team_node
from packages.agents.global_approach import global_approach_node
from packages.agents.growth_team import growth_team_node
from packages.agents.marketing_team import marketing_team_node
from packages.agents.product_team import product_team_node
from packages.agents.qa_auditor import qa_auditor_node
from packages.agents.security_agent import security_agent_node
from packages.state.agent_state import AgentState

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Manual review stub node — fires when QA max_retries is exhausted
# ---------------------------------------------------------------------------

async def manual_review_node(state: AgentState) -> AgentState:
    import uuid

    from packages.revenue.store import enqueue_manual_review

    reason = state.get("manual_review_reason", "Unknown — check QA report")
    venture_id = state["venture_id"]
    run_id = state["run_id"]
    qa_report = state.get("qa_report") or {}

    enqueue_manual_review({
        "id": str(uuid.uuid4()),
        "venture_id": venture_id,
        "run_id": run_id,
        "review_reason": reason,
        "artifact_type": qa_report.get("artifact_type", "BUILD"),
        "priority": "CRITICAL",
    })

    log.critical(
        "[MANUAL_REVIEW] venture=%s | reason=%s | retries=%d | queued for human",
        venture_id, reason, state.get("qa_retry_count", 0),
    )
    return {**state, "pipeline_stage": "MANUAL_REVIEW"}


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def product_routing_edge(
    state: AgentState,
) -> Literal["ENGINEERING_NODE", "CONTENT_NODE"]:
    """
    After Product Node: route to Engineering for MICRO_SAAS,
    to Content for MEDIA_CHANNEL or AFFILIATE_SITE.
    """
    spec = state.get("tech_spec") or {}
    product_type = spec.get("product_type", "MICRO_SAAS")
    route = "ENGINEERING_NODE" if product_type == "MICRO_SAAS" else "CONTENT_NODE"
    log.debug("product_routing_edge → %s (product_type=%s)", route, product_type)
    return route


def qa_routing_edge(
    state: AgentState,
) -> Literal["SECURITY_NODE", "ENGINEERING_NODE", "CONTENT_NODE", "MANUAL_REVIEW_NODE"]:
    """
    The critical gate of the entire pipeline.
    Determines what happens after every QA audit.

    Decision tree:
      is_passed=True                          → SECURITY_NODE
      is_passed=False + retry < max_retries   → ENGINEERING_NODE or CONTENT_NODE
      is_passed=False + retry >= max_retries  → MANUAL_REVIEW_NODE
    """
    qa_report   = state.get("qa_report") or {}
    retry_count = state.get("qa_retry_count", 0)
    max_retries = state.get("qa_max_retries", 3)

    if qa_report.get("is_passed"):
        log.debug("qa_routing_edge → SECURITY_NODE (passed)")
        return "SECURITY_NODE"

    if retry_count >= max_retries:
        log.warning(
            "qa_routing_edge → MANUAL_REVIEW_NODE (retries exhausted: %d/%d)",
            retry_count, max_retries,
        )
        return "MANUAL_REVIEW_NODE"

    qa_target = state.get("qa_target") or qa_report.get("qa_target", "engineering")
    if qa_target == "engineering":
        log.debug("qa_routing_edge → ENGINEERING_NODE (retry %d)", retry_count)
        return "ENGINEERING_NODE"

    log.debug("qa_routing_edge → CONTENT_NODE (retry %d)", retry_count)
    return "CONTENT_NODE"


def go_decision_edge(
    state: AgentState,
) -> Literal["PRODUCT_NODE", END]:
    """
    After CEO Node: only proceed to Product if go_decision is True.
    Prevents low-feasibility ventures from consuming downstream resources.
    """
    brief = state.get("venture_brief") or {}
    if brief.get("go_decision", False):
        return "PRODUCT_NODE"
    log.info(
        "go_decision_edge → END (go=False | niche=%s feasibility=%.2f)",
        brief.get("niche", "unknown"),
        brief.get("feasibility_score", 0.0),
    )
    return END


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_squadron_graph() -> StateGraph:
    """
    Assembles and compiles the full AI Squadron LangGraph.
    Returns a compiled graph ready for .invoke() or .ainvoke().

    Node execution order (happy path):
    RESEARCH → CEO → PRODUCT → [ENGINEERING|CONTENT] → QA ⟳ → SECURITY → ACCOUNT_DIST → DEPLOYMENT
                                                              ↓
                                               MARKETING ← ← ← →  GLOBAL
                                                          ↘  ↗
                                                          GROWTH → END
    """
    graph: StateGraph = StateGraph(AgentState)

    # ---- Register all nodes ----
    graph.add_node("RESEARCH_NODE",         market_research_node)
    graph.add_node("CEO_NODE",            ceo_niche_scout_node)
    graph.add_node("PRODUCT_NODE",        product_team_node)
    graph.add_node("ENGINEERING_NODE",    engineering_team_node)
    graph.add_node("CONTENT_NODE",        content_team_node)
    graph.add_node("QA_NODE",             qa_auditor_node)
    graph.add_node("SECURITY_NODE",              security_agent_node)
    graph.add_node("ACCOUNT_DISTRIBUTION_NODE", account_distribution_node)
    graph.add_node("DEPLOYMENT_NODE",            deployment_team_node)
    graph.add_node("MARKETING_NODE",      marketing_team_node)
    graph.add_node("GLOBAL_NODE",         global_approach_node)
    graph.add_node("GROWTH_NODE",         growth_team_node)
    graph.add_node("MANUAL_REVIEW_NODE",  manual_review_node)

    # ---- Set entry point ----
    graph.set_entry_point("RESEARCH_NODE")
    graph.add_edge("RESEARCH_NODE", "CEO_NODE")

    # ---- CEO → conditional on go_decision ----
    graph.add_conditional_edges(
        "CEO_NODE",
        go_decision_edge,
        {"PRODUCT_NODE": "PRODUCT_NODE", END: END},
    )

    # ---- PRODUCT → branch on venture type ----
    graph.add_conditional_edges(
        "PRODUCT_NODE",
        product_routing_edge,
        {
            "ENGINEERING_NODE": "ENGINEERING_NODE",
            "CONTENT_NODE":     "CONTENT_NODE",
        },
    )

    # ---- Both engineering and content paths converge on QA ----
    graph.add_edge("ENGINEERING_NODE", "QA_NODE")
    graph.add_edge("CONTENT_NODE",     "QA_NODE")

    # ---- QA → conditional routing (retry loop or proceed) ----
    graph.add_conditional_edges(
        "QA_NODE",
        qa_routing_edge,
        {
            "SECURITY_NODE":      "SECURITY_NODE",
            "ENGINEERING_NODE":   "ENGINEERING_NODE",
            "CONTENT_NODE":       "CONTENT_NODE",
            "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
        },
    )

    # ---- Security → Account Distribution → Deployment ----
    graph.add_edge("SECURITY_NODE", "ACCOUNT_DISTRIBUTION_NODE")
    graph.add_edge("ACCOUNT_DISTRIBUTION_NODE", "DEPLOYMENT_NODE")

    # ---- Sequential post-deploy: DEPLOYMENT → MARKETING → GLOBAL → GROWTH ----
    # Phase 0: sequential to avoid LangGraph concurrent state-update constraints.
    # Phase 3: convert to parallel using Annotated[list, operator.add] on event_log.
    graph.add_edge("DEPLOYMENT_NODE", "MARKETING_NODE")
    graph.add_edge("MARKETING_NODE",  "GLOBAL_NODE")
    graph.add_edge("GLOBAL_NODE",     "GROWTH_NODE")

    # ---- Growth and Manual Review terminate ----
    graph.add_edge("GROWTH_NODE",         END)
    graph.add_edge("MANUAL_REVIEW_NODE",  END)

    compiled = graph.compile()
    log.info("Squadron graph compiled successfully — %d nodes registered", 13)
    return compiled


# Module-level compiled graph — import and use directly
squadron_graph = build_squadron_graph()
