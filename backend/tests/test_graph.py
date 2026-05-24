"""
tests/test_graph.py
Integration tests for the AI Squadron two-department LangGraph architecture.
Tests graph compilation, edge logic, and pipeline dry-run.
NO real LLM calls — all agents mocked.

Run: pytest tests/test_graph.py -v
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langgraph.graph import END
from packages.state.agent_state import init_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockLLMResponse:
    def __init__(self, text: str):
        self.text = text
        self.total_tokens = 100
        self.latency_ms = 50
        self.input_tokens = 80
        self.output_tokens = 20


MOCK_RESEARCH_DOSSIER = {
    "recommended_primary_niche": "AI Productivity Tools",
    "research_mode": "mock",
    "scout_reports": [
        {"scout": "trend_hunter", "top_niches": ["AI tools"], "verdict": "strong"},
        {"scout": "competitor_analyst", "moat_gaps": ["no API"], "verdict": "viable"},
        {"scout": "skeptic", "risks": ["saturation"], "verdict": "proceed_with_caution"},
        {"scout": "audience_analyst", "persona": "solopreneur", "verdict": "validated"},
        {"scout": "execution_scout", "feasibility": "high", "verdict": "build"},
    ],
    "council_confidence": 0.78,
    "debate_summary": "Council agrees — build it.",
}

MOCK_VENTURE_BRIEF = {
    "venture_id": "ven_test_001",
    "venture_type": "MICRO_SAAS",
    "niche": "AI productivity tools",
    "department": "PRODUCT",
    "target_region": ["US"],
    "feasibility_score": 0.80,
    "competition_score": 0.30,
    "risk_score": 0.20,
    "go_decision": True,
    "go_rationale": "Strong feasibility, low competition",
    "time_to_first_revenue_days": 60,
}

MOCK_STRATEGY = {
    "venture_id": "ven_test_001",
    "product_name": "TaskFlow AI",
    "p0_features": [{"id": "feat_01", "name": "Dashboard"}],
    "monetisation": {"model": "freemium", "price_usd": 29.0, "trial_days": 14},
    "north_star_metric": "D7 retention",
    "go_live_target_days": 30,
}

MOCK_TECH_SPEC = {
    "venture_id": "ven_test_001",
    "product_type": "MICRO_SAAS",
    "stack": {"frontend": "React 19 + Vite", "backend": "FastAPI"},
    "features": [{"feature_id": "feat_001", "name": "Dashboard", "priority": "P0",
                  "user_story": "View metrics", "acceptance_criteria": ["Shows KPIs"],
                  "estimated_components": ["Dashboard"]}],
    "data_models": {},
    "api_routes": [],
    "estimated_build_tokens": 50000,
    "component_count": 3,
    "complexity": "LOW",
}

MOCK_LEGAL_CLEARANCE = {
    "venture_id": "ven_test_001",
    "is_cleared": True,
    "platforms_reviewed": ["stripe", "railway"],
    "tos_version": "2026-01",
    "policy_flags": [],
    "copyright_clear": True,
    "gdpr_reviewed": False,
    "clearance_expires_at": "2027-01-01T00:00:00Z",
}

MOCK_MARKETING_PLAN = {
    "venture_id": "ven_test_001",
    "landing_page": {"headline": "AI for solopreneurs"},
    "launch_channels": [{"channel": "product_hunt", "post_title": "Launch"}],
    "content_calendar": [],
}

MOCK_GROWTH_REPORT = {
    "venture_id": "ven_test_001",
    "signal": "MAINTAIN",
    "mrr_usd": 0.0,
    "days_live": 1,
    "signal_rationale": "Too early to judge.",
    "next_action": "Keep publishing.",
}


# ---------------------------------------------------------------------------
# Product graph — edge unit tests
# ---------------------------------------------------------------------------

def test_product_go_decision_true():
    from apps.orchestrator.product_graph import go_decision_edge
    state = {**init_state(), "venture_brief": {"go_decision": True}}
    assert go_decision_edge(state) == "PRODUCT_VP_NODE"


def test_product_go_decision_false():
    from apps.orchestrator.product_graph import go_decision_edge
    state = {**init_state(), "venture_brief": {"go_decision": False}}
    assert go_decision_edge(state) == END


def test_product_go_decision_no_brief():
    from apps.orchestrator.product_graph import go_decision_edge
    assert go_decision_edge(init_state()) == END


def test_product_qa_routing_passed():
    from apps.orchestrator.product_graph import qa_routing_edge
    state = {**init_state(), "qa_report": {"is_passed": True}}
    assert qa_routing_edge(state) == "LEGAL_NODE"


def test_product_qa_routing_retry():
    from apps.orchestrator.product_graph import qa_routing_edge
    state = {**init_state(), "qa_report": {"is_passed": False},
             "qa_retry_count": 1, "qa_max_retries": 3}
    assert qa_routing_edge(state) == "ENGINEERING_NODE"


def test_product_qa_routing_max_retries():
    from apps.orchestrator.product_graph import qa_routing_edge
    state = {**init_state(), "qa_report": {"is_passed": False},
             "qa_retry_count": 3, "qa_max_retries": 3}
    assert qa_routing_edge(state) == "MANUAL_REVIEW_NODE"


def test_product_qa_routing_boundary():
    from apps.orchestrator.product_graph import qa_routing_edge
    base = {**init_state(), "qa_report": {"is_passed": False}, "qa_max_retries": 3}
    assert qa_routing_edge({**base, "qa_retry_count": 2}) == "ENGINEERING_NODE"
    assert qa_routing_edge({**base, "qa_retry_count": 3}) == "MANUAL_REVIEW_NODE"


def test_legal_routing_cleared():
    from apps.orchestrator.product_graph import legal_routing_edge
    state = {**init_state(), "legal_clearance": {"is_cleared": True}}
    assert legal_routing_edge(state) == "SECURITY_NODE"


def test_legal_routing_denied():
    from apps.orchestrator.product_graph import legal_routing_edge
    state = {**init_state(), "legal_clearance": {"is_cleared": False}}
    assert legal_routing_edge(state) == "MANUAL_REVIEW_NODE"


def test_legal_routing_no_clearance():
    from apps.orchestrator.product_graph import legal_routing_edge
    assert legal_routing_edge(init_state()) == "MANUAL_REVIEW_NODE"


# ---------------------------------------------------------------------------
# Media graph — edge unit tests
# ---------------------------------------------------------------------------

def test_media_go_decision_true():
    from apps.orchestrator.media_graph import go_decision_edge
    state = {**init_state(), "venture_brief": {"go_decision": True}}
    assert go_decision_edge(state) == "MEDIA_VP_NODE"


def test_media_go_decision_false():
    from apps.orchestrator.media_graph import go_decision_edge
    state = {**init_state(), "venture_brief": {"go_decision": False}}
    assert go_decision_edge(state) == END


def test_media_qa_routing_passed():
    from apps.orchestrator.media_graph import qa_routing_edge
    state = {**init_state(), "qa_report": {"is_passed": True}}
    assert qa_routing_edge(state) == "LEGAL_NODE"


def test_media_qa_routing_retry():
    from apps.orchestrator.media_graph import qa_routing_edge
    state = {**init_state(), "qa_report": {"is_passed": False},
             "qa_retry_count": 1, "qa_max_retries": 3}
    assert qa_routing_edge(state) == "SCRIPT_NODE"


# ---------------------------------------------------------------------------
# Graph compilation tests
# ---------------------------------------------------------------------------

def test_product_graph_compiles():
    from apps.orchestrator.product_graph import build_product_graph
    graph = build_product_graph()
    assert graph is not None
    nodes = set(graph.get_graph().nodes.keys())
    expected = {
        "RESEARCH_NODE", "CEO_NODE", "PRODUCT_VP_NODE", "PRODUCT_MANAGER_NODE",
        "ENGINEERING_NODE", "QA_TECHNICAL_NODE", "LEGAL_NODE", "SECURITY_NODE",
        "ACCOUNT_DISTRIBUTION_NODE", "DEPLOYMENT_NODE", "MARKETING_SEO_NODE",
        "PRODUCT_GROWTH_NODE", "MANUAL_REVIEW_NODE",
    }
    assert expected.issubset(nodes), f"Missing nodes: {expected - nodes}"


def test_media_graph_compiles():
    from apps.orchestrator.media_graph import build_media_graph
    graph = build_media_graph()
    assert graph is not None
    nodes = set(graph.get_graph().nodes.keys())
    expected = {
        "RESEARCH_NODE", "CEO_NODE", "MEDIA_VP_NODE", "SCRIPT_NODE", "VOICE_NODE",
        "VIDEO_NODE", "THUMBNAIL_NODE", "SEO_METADATA_NODE", "QA_COMPLIANCE_NODE",
        "LEGAL_NODE", "SECURITY_NODE", "ACCOUNT_DISTRIBUTION_NODE", "PUBLISHING_NODE",
        "ANALYTICS_NODE", "ANTI_BAN_NODE", "MEDIA_GROWTH_NODE", "MANUAL_REVIEW_NODE",
    }
    assert expected.issubset(nodes), f"Missing nodes: {expected - nodes}"


def test_auto_graph_compiles():
    from apps.orchestrator.graph import build_squadron_graph
    graph = build_squadron_graph("AUTO")
    assert graph is not None


# ---------------------------------------------------------------------------
# Full product pipeline dry-run — mocks LLM and subprocess, no real API calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_dry_run_saas():
    """
    Run the full Product pipeline with LLM and subprocess mocked.
    Verifies state flows correctly from RESEARCH → PRODUCT_GROWTH.
    """
    mock_files = {
        "files": [
            {"path": "src/App.tsx",
             "content": "export default function App() { return <div>Test</div>; }"},
            {"path": "src/types.ts",
             "content": "export type User = { id: string; }"},
        ]
    }

    async def smart_llm(model_role: str, *args, **kwargs):
        role = model_role.upper()
        if "RESEARCH" in role or "KIMI" in role or "DEBATE" in role:
            return MockLLMResponse(json.dumps(MOCK_RESEARCH_DOSSIER))
        elif "CEO" in role or "GRAND" in role:
            return MockLLMResponse(json.dumps(MOCK_VENTURE_BRIEF))
        elif "PRODUCT_VP" in role:
            return MockLLMResponse(json.dumps(MOCK_STRATEGY))
        elif "PRODUCT_MANAGER" in role or "PM" in role:
            return MockLLMResponse(json.dumps(MOCK_TECH_SPEC))
        elif "ENGINEERING" in role:
            return MockLLMResponse(json.dumps(mock_files))
        elif "QA_TECHNICAL_CRITIQUE" in role:
            return MockLLMResponse(json.dumps({"failed_checks": [], "errors": []}))
        elif "LEGAL" in role:
            return MockLLMResponse(json.dumps(MOCK_LEGAL_CLEARANCE))
        elif "MARKETING" in role:
            return MockLLMResponse(json.dumps(MOCK_MARKETING_PLAN))
        elif "GROWTH" in role:
            return MockLLMResponse(json.dumps(MOCK_GROWTH_REPORT))
        else:
            return MockLLMResponse("{}")

    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute.return_value = None
    mock_db.table.return_value.upsert.return_value.execute.return_value = None
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    patches = [
        patch("packages.tools.llm.call_llm", side_effect=smart_llm),
        # Mock npm install and vite build — return success without hitting disk/Node
        patch("packages.agents.product.engineering_team._run_npm_install",
              new=AsyncMock(return_value=(0, ""))),
        patch("packages.agents.product.qa_technical._run_vite_build",
              new=AsyncMock(return_value=(0, "dist/ built", ""))),
        # Mock all DB calls
        patch("packages.db.client.get_db", return_value=mock_db),
        patch("packages.db.client.log_agent_event", return_value=None),
        patch("packages.db.client.save_qa_report", return_value=None),
        patch("packages.db.pipeline.begin_pipeline_run", return_value=None),
        patch("packages.db.pipeline.complete_pipeline_run", return_value=None),
        patch("packages.db.pipeline.persist_event_log", return_value=0),
        patch("packages.db.pipeline.save_research_dossier", return_value=None),
    ]

    for p in patches:
        p.start()
    try:
        from apps.orchestrator.product_graph import build_product_graph
        graph = build_product_graph()
        state = init_state()
        final = await graph.ainvoke(state)

        stage = final.get("pipeline_stage", "")
        assert stage not in ("", "FAILED"), \
            f"Pipeline stalled/failed at: {stage} | error: {final.get('last_error')}"
        assert len(final.get("event_log", [])) > 0, "No events logged"
    finally:
        for p in patches:
            p.stop()
