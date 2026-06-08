"""
apps/orchestrator/product_graph.py
Product Department LangGraph pipeline — SaaS only.

Correct flow (per operator requirements):
  RESEARCH → CEO [go?] → PRODUCT_VP → PRODUCT_MANAGER → ENGINEERING ⟳
  → QA_TECHNICAL [pass?] → SECURITY [clear?] → LEGAL [cleared?]
  → DEPLOYMENT → MARKETING_SEO → PRODUCT_GROWTH → END

Retry/escalation rules:
  QA fail + retries < max  → back to ENGINEERING (with critique)
  QA fail + retries >= max → MANUAL_REVIEW
  Security critical findings + retries < max → back to ENGINEERING (with security report)
  Security critical findings + retries >= max → MANUAL_REVIEW
  Legal denied             → MANUAL_REVIEW (human must resolve)
  CEO go_decision=False    → END (no-go logged, niche remembered)

Media pipeline has been archived. This graph handles PRODUCT (MICRO_SAAS) only.
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
from packages.state.agent_state import AgentState

log = logging.getLogger(__name__)


async def manual_review_node(state: AgentState) -> AgentState:
    import uuid
    reason = state.get("manual_review_reason", "Unknown — check QA / Legal / Security report")
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
    from packages.db.client import log_agent_event
    log_agent_event(run_id, venture_id, "MANUAL_REVIEW", "FAILED",
                    error_detail=reason[:500])
    return {**state, "pipeline_stage": "MANUAL_REVIEW"}


# ---------------------------------------------------------------------------
# Conditional routing edges
# ---------------------------------------------------------------------------

def go_decision_edge(state: AgentState) -> Literal["PRODUCT_VP_NODE", "END"]:
    """CEO gate: only proceed to build if niche scored >= 70."""
    brief = state.get("venture_brief") or {}
    if brief.get("go_decision", False):
        return "PRODUCT_VP_NODE"
    niche = brief.get("niche", "unknown")
    score = brief.get("go_rationale", "")[:60]
    log.info("[go_decision_edge] NO-GO | niche=%s | %s", niche, score)
    return END


def qa_routing_edge(
    state: AgentState,
) -> Literal["SECURITY_NODE", "ENGINEERING_NODE", "MANUAL_REVIEW_NODE"]:
    """
    After QA: pass → Security. Fail → Engineering retry. Max retries → Manual Review.
    Security runs BEFORE Legal so the legal agent reviews a security-validated build.
    """
    qa = state.get("qa_report") or {}
    retries = state.get("qa_retry_count", 0)
    max_r = state.get("qa_max_retries", 3)
    if qa.get("is_passed"):
        return "SECURITY_NODE"
    if retries >= max_r:
        log.warning("[qa_routing] Max retries (%d) reached → MANUAL_REVIEW", max_r)
        return "MANUAL_REVIEW_NODE"
    log.info("[qa_routing] QA failed (retry %d/%d) → ENGINEERING", retries, max_r)
    return "ENGINEERING_NODE"


def security_routing_edge(
    state: AgentState,
) -> Literal["LEGAL_NODE", "ENGINEERING_NODE", "MANUAL_REVIEW_NODE"]:
    """
    After Security: no critical findings → Legal. Critical findings → Engineering retry.
    Allows the engineering team to fix OWASP issues before legal review.
    """
    sec_report = state.get("security_report") or {}
    retries = state.get("qa_retry_count", 0)
    max_r = state.get("qa_max_retries", 3)

    critical = sec_report.get("owasp_findings", [])
    if not critical:
        return "LEGAL_NODE"

    if retries >= max_r:
        log.warning("[security_routing] Critical findings after max retries → MANUAL_REVIEW: %s",
                    critical[:2])
        return "MANUAL_REVIEW_NODE"

    log.warning("[security_routing] %d critical security finding(s) → ENGINEERING retry: %s",
                len(critical), critical[:2])
    return "ENGINEERING_NODE"


def legal_routing_edge(
    state: AgentState,
) -> Literal["DEPLOYMENT_NODE", "MANUAL_REVIEW_NODE"]:
    """After Legal: cleared → Deploy directly. Denied → Manual Review."""
    clearance = state.get("legal_clearance") or {}
    if clearance.get("is_cleared", False):
        return "DEPLOYMENT_NODE"
    return "MANUAL_REVIEW_NODE"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_product_graph() -> StateGraph:
    """
    Assemble and compile the SaaS Product Department LangGraph.

    Node count: 12 (including MANUAL_REVIEW)
    Flow: Research → CEO → VP → PM → Engineering ⟳ → QA → Security → Legal → Deploy → Marketing → Growth → END
    """
    g: StateGraph = StateGraph(AgentState)

    g.add_node("RESEARCH_NODE",        research_council_node)
    g.add_node("CEO_NODE",             grand_ceo_node)
    g.add_node("PRODUCT_VP_NODE",      product_vp_node)
    g.add_node("PRODUCT_MANAGER_NODE", product_manager_node)
    g.add_node("ENGINEERING_NODE",     engineering_team_node)
    g.add_node("QA_TECHNICAL_NODE",    qa_technical_node)
    g.add_node("SECURITY_NODE",        security_agent_node)   # now runs BEFORE Legal
    g.add_node("LEGAL_NODE",           legal_agent_node)
    g.add_node("DEPLOYMENT_NODE",      deployment_agent_node)
    g.add_node("MARKETING_SEO_NODE",   marketing_seo_node)
    g.add_node("PRODUCT_GROWTH_NODE",  product_growth_node)
    g.add_node("MANUAL_REVIEW_NODE",   manual_review_node)

    g.set_entry_point("RESEARCH_NODE")
    g.add_edge("RESEARCH_NODE", "CEO_NODE")

    g.add_conditional_edges("CEO_NODE", go_decision_edge,
                            {"PRODUCT_VP_NODE": "PRODUCT_VP_NODE", END: END})

    g.add_edge("PRODUCT_VP_NODE",      "PRODUCT_MANAGER_NODE")
    g.add_edge("PRODUCT_MANAGER_NODE", "ENGINEERING_NODE")
    g.add_edge("ENGINEERING_NODE",     "QA_TECHNICAL_NODE")

    # QA → Security (on pass) OR Engineering retry OR Manual Review
    g.add_conditional_edges("QA_TECHNICAL_NODE", qa_routing_edge, {
        "SECURITY_NODE":      "SECURITY_NODE",
        "ENGINEERING_NODE":   "ENGINEERING_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    # Security → Legal (on clear) OR Engineering retry OR Manual Review
    g.add_conditional_edges("SECURITY_NODE", security_routing_edge, {
        "LEGAL_NODE":         "LEGAL_NODE",
        "ENGINEERING_NODE":   "ENGINEERING_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    # Legal → Deploy (on cleared) OR Manual Review
    g.add_conditional_edges("LEGAL_NODE", legal_routing_edge, {
        "DEPLOYMENT_NODE":    "DEPLOYMENT_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    g.add_edge("DEPLOYMENT_NODE",    "MARKETING_SEO_NODE")
    g.add_edge("MARKETING_SEO_NODE", "PRODUCT_GROWTH_NODE")
    g.add_edge("PRODUCT_GROWTH_NODE", END)
    g.add_edge("MANUAL_REVIEW_NODE",  END)

    compiled = g.compile()
    log.info("[product_graph] Compiled — 12 nodes | flow: Research→CEO→VP→PM→Eng⟳→QA→Sec→Legal→Deploy→Mktg→Growth")
    return compiled


product_graph = build_product_graph()
