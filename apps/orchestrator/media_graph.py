"""
apps/orchestrator/media_graph.py
Media Department LangGraph pipeline.

Happy path:
  RESEARCH → CEO → MEDIA_VP → SCRIPT ⟳ → VOICE → VIDEO → THUMBNAIL → SEO_METADATA
  → QA_COMPLIANCE ⟳ → LEGAL → SECURITY → ACCOUNT_DIST → PUBLISHING → ANALYTICS
  → ANTI_BAN → MEDIA_GROWTH → END

QA retry loop: max 3 attempts → MANUAL_REVIEW_NODE
Legal veto:    is_cleared=False → MANUAL_REVIEW_NODE
Anti-ban:      should_pause=True → MANUAL_REVIEW_NODE
"""
from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from packages.agents.governance.grand_ceo import grand_ceo_node
from packages.agents.governance.research_council import research_council_node
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
from packages.agents.shared.anti_ban_agent import anti_ban_agent_node
from packages.agents.shared.legal_agent import legal_agent_node
from packages.agents.shared.security_agent import security_agent_node
from packages.agents.shared.account_distribution import account_distribution_node
from packages.state.agent_state import AgentState

log = logging.getLogger(__name__)


async def manual_review_node(state: AgentState) -> AgentState:
    import uuid
    reason = state.get("manual_review_reason", "Unknown — check QA / Legal / Anti-Ban report")
    venture_id = state["venture_id"]
    run_id = state["run_id"]
    log.critical("[MANUAL_REVIEW] venture=%s reason=%s", venture_id, reason)
    try:
        from packages.revenue.store import enqueue_manual_review
        enqueue_manual_review({
            "id": str(uuid.uuid4()), "venture_id": venture_id, "run_id": run_id,
            "review_reason": reason, "artifact_type": "CONTENT", "priority": "CRITICAL",
        })
    except Exception:
        pass
    return {**state, "pipeline_stage": "MANUAL_REVIEW"}


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------

def go_decision_edge(state: AgentState) -> Literal["MEDIA_VP_NODE", "END"]:
    brief = state.get("venture_brief") or {}
    if brief.get("go_decision", False):
        return "MEDIA_VP_NODE"
    log.info("go_decision_edge → END | niche=%s", brief.get("niche", "unknown"))
    return END


def qa_routing_edge(
    state: AgentState,
) -> Literal["LEGAL_NODE", "SCRIPT_NODE", "MANUAL_REVIEW_NODE"]:
    qa = state.get("qa_report") or {}
    retries = state.get("qa_retry_count", 0)
    max_r = state.get("qa_max_retries", 3)
    if qa.get("is_passed"):
        return "LEGAL_NODE"
    if retries >= max_r:
        return "MANUAL_REVIEW_NODE"
    return "SCRIPT_NODE"


def legal_routing_edge(
    state: AgentState,
) -> Literal["SECURITY_NODE", "MANUAL_REVIEW_NODE"]:
    clearance = state.get("legal_clearance") or {}
    if clearance.get("is_cleared", False):
        return "SECURITY_NODE"
    return "MANUAL_REVIEW_NODE"


def anti_ban_routing_edge(
    state: AgentState,
) -> Literal["MEDIA_GROWTH_NODE", "MANUAL_REVIEW_NODE"]:
    stage = state.get("pipeline_stage", "")
    if stage == "MANUAL_REVIEW_NODE":
        return "MANUAL_REVIEW_NODE"
    return "MEDIA_GROWTH_NODE"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_media_graph() -> StateGraph:
    """
    Assemble and compile the Media Department LangGraph.

    Node count: 17 (including MANUAL_REVIEW)
    """
    g: StateGraph = StateGraph(AgentState)

    g.add_node("RESEARCH_NODE",             research_council_node)
    g.add_node("CEO_NODE",                  grand_ceo_node)
    g.add_node("MEDIA_VP_NODE",             media_vp_node)
    g.add_node("SCRIPT_NODE",               script_agent_node)
    g.add_node("VOICE_NODE",                voice_agent_node)
    g.add_node("VIDEO_NODE",                video_agent_node)
    g.add_node("THUMBNAIL_NODE",            thumbnail_agent_node)
    g.add_node("SEO_METADATA_NODE",         seo_metadata_node)
    g.add_node("QA_COMPLIANCE_NODE",        qa_compliance_node)
    g.add_node("LEGAL_NODE",                legal_agent_node)
    g.add_node("SECURITY_NODE",             security_agent_node)
    g.add_node("ACCOUNT_DISTRIBUTION_NODE", account_distribution_node)
    g.add_node("PUBLISHING_NODE",           publishing_agent_node)
    g.add_node("ANALYTICS_NODE",            analytics_agent_node)
    g.add_node("ANTI_BAN_NODE",             anti_ban_agent_node)
    g.add_node("MEDIA_GROWTH_NODE",         media_growth_node)
    g.add_node("MANUAL_REVIEW_NODE",        manual_review_node)

    g.set_entry_point("RESEARCH_NODE")
    g.add_edge("RESEARCH_NODE", "CEO_NODE")

    g.add_conditional_edges("CEO_NODE", go_decision_edge,
                            {"MEDIA_VP_NODE": "MEDIA_VP_NODE", END: END})

    # Content production pipeline
    g.add_edge("MEDIA_VP_NODE",  "SCRIPT_NODE")
    g.add_edge("SCRIPT_NODE",    "VOICE_NODE")
    g.add_edge("VOICE_NODE",     "VIDEO_NODE")
    g.add_edge("VIDEO_NODE",     "THUMBNAIL_NODE")
    g.add_edge("THUMBNAIL_NODE", "SEO_METADATA_NODE")
    g.add_edge("SEO_METADATA_NODE", "QA_COMPLIANCE_NODE")

    # QA → Legal gate
    g.add_conditional_edges("QA_COMPLIANCE_NODE", qa_routing_edge, {
        "LEGAL_NODE":         "LEGAL_NODE",
        "SCRIPT_NODE":        "SCRIPT_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    # Legal → Security
    g.add_conditional_edges("LEGAL_NODE", legal_routing_edge, {
        "SECURITY_NODE":      "SECURITY_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    # Distribution and publishing
    g.add_edge("SECURITY_NODE",             "ACCOUNT_DISTRIBUTION_NODE")
    g.add_edge("ACCOUNT_DISTRIBUTION_NODE", "PUBLISHING_NODE")
    g.add_edge("PUBLISHING_NODE",           "ANALYTICS_NODE")
    g.add_edge("ANALYTICS_NODE",            "ANTI_BAN_NODE")

    # Anti-ban → Growth or Manual Review
    g.add_conditional_edges("ANTI_BAN_NODE", anti_ban_routing_edge, {
        "MEDIA_GROWTH_NODE":  "MEDIA_GROWTH_NODE",
        "MANUAL_REVIEW_NODE": "MANUAL_REVIEW_NODE",
    })

    g.add_edge("MEDIA_GROWTH_NODE",  END)
    g.add_edge("MANUAL_REVIEW_NODE", END)

    compiled = g.compile()
    log.info("Media graph compiled — 17 nodes")
    return compiled


media_graph = build_media_graph()
