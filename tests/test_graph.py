"""
tests/test_graph.py
Integration tests for the LangGraph graph assembly.
Tests graph compilation, conditional edge logic, and QA retry loop.
NO LLM calls — all agent nodes are mocked.
Run: pytest tests/test_graph.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch
from packages.state.agent_state import init_state
from apps.orchestrator.graph import (
    go_decision_edge, product_routing_edge, qa_routing_edge, build_squadron_graph
)


# ---------------------------------------------------------------------------
# Conditional edge unit tests — no graph execution needed
# ---------------------------------------------------------------------------

def test_go_decision_edge_true():
    state = {**init_state(), "venture_brief": {"go_decision": True, "niche": "AI tools", "feasibility_score": 0.8}}
    assert go_decision_edge(state) == "PRODUCT_NODE"


def test_go_decision_edge_false():
    from langgraph.graph import END
    state = {**init_state(), "venture_brief": {"go_decision": False, "niche": "test", "feasibility_score": 0.3}}
    assert go_decision_edge(state) == END


def test_go_decision_edge_no_brief():
    from langgraph.graph import END
    state = init_state()
    assert go_decision_edge(state) == END


def test_product_routing_saas():
    state = {**init_state(), "tech_spec": {"product_type": "MICRO_SAAS"}}
    assert product_routing_edge(state) == "ENGINEERING_NODE"


def test_product_routing_media():
    state = {**init_state(), "tech_spec": {"product_type": "MEDIA_CHANNEL"}}
    assert product_routing_edge(state) == "CONTENT_NODE"


def test_product_routing_affiliate():
    state = {**init_state(), "tech_spec": {"product_type": "AFFILIATE_SITE"}}
    assert product_routing_edge(state) == "CONTENT_NODE"


def test_product_routing_default():
    state = {**init_state(), "tech_spec": {}}
    assert product_routing_edge(state) == "ENGINEERING_NODE"


def test_qa_routing_passed():
    state = {**init_state(), "qa_report": {"is_passed": True}}
    assert qa_routing_edge(state) == "SECURITY_NODE"


def test_qa_routing_failed_engineering():
    state = {
        **init_state(),
        "qa_report": {"is_passed": False, "qa_target": "engineering"},
        "qa_retry_count": 1,
        "qa_max_retries": 3,
    }
    assert qa_routing_edge(state) == "ENGINEERING_NODE"


def test_qa_routing_failed_content():
    state = {
        **init_state(),
        "qa_report": {"is_passed": False, "qa_target": "content"},
        "qa_retry_count": 1,
        "qa_max_retries": 3,
    }
    assert qa_routing_edge(state) == "CONTENT_NODE"


def test_qa_routing_max_retries_exceeded():
    state = {
        **init_state(),
        "qa_report": {"is_passed": False, "qa_target": "engineering"},
        "qa_retry_count": 3,
        "qa_max_retries": 3,
    }
    assert qa_routing_edge(state) == "MANUAL_REVIEW_NODE"


def test_qa_routing_retry_boundary():
    """Verify retry=2 still routes to agent, retry=3 routes to manual review."""
    base = {**init_state(), "qa_report": {"is_passed": False, "qa_target": "engineering"}, "qa_max_retries": 3}
    assert qa_routing_edge({**base, "qa_retry_count": 2}) == "ENGINEERING_NODE"
    assert qa_routing_edge({**base, "qa_retry_count": 3}) == "MANUAL_REVIEW_NODE"


# ---------------------------------------------------------------------------
# Graph compilation test
# ---------------------------------------------------------------------------

def test_graph_compiles():
    """Verify the full graph compiles without errors."""
    graph = build_squadron_graph()
    assert graph is not None


def test_graph_has_correct_nodes():
    """Verify all 13 nodes are registered."""
    graph = build_squadron_graph()
    # LangGraph compiled graph exposes the graph attribute
    node_names = set(graph.get_graph().nodes.keys())
    expected = {
        "RESEARCH_NODE", "CEO_NODE", "PRODUCT_NODE", "ENGINEERING_NODE", "CONTENT_NODE",
        "QA_NODE", "SECURITY_NODE", "ACCOUNT_DISTRIBUTION_NODE", "DEPLOYMENT_NODE",
        "MARKETING_NODE",
        "GLOBAL_NODE", "GROWTH_NODE", "MANUAL_REVIEW_NODE", "__start__",
    }
    assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


# ---------------------------------------------------------------------------
# Dry-run pipeline test — mocks all LLM calls and DB writes
# ---------------------------------------------------------------------------

MOCK_VENTURE_BRIEF = {
    "venture_id": "ven_test_001",
    "venture_type": "MICRO_SAAS",
    "niche": "AI productivity tools",
    "target_region": ["US"],
    "target_audience": "Solopreneurs",
    "rpm_estimate_usd": 12.0,
    "competition_score": 0.3,
    "feasibility_score": 0.75,
    "tam_usd_millions": 200.0,
    "top_competitors": [{"name": "Notion", "weakness": "no AI", "moat_gap": "AI-native workflow"}],
    "recommended_monetization": ["subscription"],
    "content_angles": ["5 productivity hacks"],
    "go_decision": True,
    "go_rationale": "Strong feasibility",
}

MOCK_TECH_SPEC = {
    "venture_id": "ven_test_001",
    "product_type": "MICRO_SAAS",
    "stack": {"frontend": "React 19 + Vite", "backend": "Python FastAPI",
              "database": "PostgreSQL", "auth": "Supabase Auth", "hosting": "Vercel"},
    "features": [{"feature_id": "feat_001", "name": "Dashboard", "priority": "P0",
                  "user_story": "View metrics", "acceptance_criteria": ["Shows KPIs"],
                  "estimated_components": ["Dashboard"]}],
    "data_models": {},
    "api_routes": [],
    "estimated_build_tokens": 50000,
    "component_count": 3,
    "complexity": "LOW",
}


class MockLLMResponse:
    def __init__(self, text: str):
        self.text = text
        self.total_tokens = 100
        self.latency_ms = 50
        self.input_tokens = 80
        self.output_tokens = 20


@pytest.mark.asyncio
async def test_pipeline_dry_run_saas():
    """
    Run the full pipeline with all LLM calls mocked.
    Patches call_llm at each agent module's import path.
    """
    import json

    mock_build = {
        "files": [{"path": "src/components/Dashboard.tsx",
                   "content": "export default function Dashboard() { return <div/> }"}]
    }

    call_count = [0]
    responses = [
        json.dumps(MOCK_VENTURE_BRIEF),   # CEO
        json.dumps(MOCK_TECH_SPEC),       # Product
        json.dumps(mock_build),            # Engineering
        "{}",                              # Marketing (graceful fallback)
        "Translated title",                # Global (per region x2)
        "Translated title",
    ]

    async def mock_call_llm(*args, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return MockLLMResponse(responses[idx])

    # Patch call_llm at every agent module that imports it
    agent_modules = [
        "packages.agents.ceo_niche_scout.call_llm",
        "packages.agents.product_team.call_llm",
        "packages.agents.engineering_team.call_llm",
        "packages.agents.qa_auditor.call_llm",
        "packages.agents.marketing_team.call_llm",
        "packages.agents.global_approach.call_llm",
    ]

    from unittest.mock import AsyncMock, patch, MagicMock
    # Stack all patches
    patches = [patch(m, side_effect=mock_call_llm) for m in agent_modules]
    db_patch = patch("packages.db.client.get_db", return_value=MagicMock(
        table=lambda _: MagicMock(
            insert=lambda d: MagicMock(execute=lambda: None),
            upsert=lambda d: MagicMock(execute=lambda: None),
        )
    ))

    for p in patches:
        p.start()
    db_patch.start()
    try:
        graph = build_squadron_graph()
        state = init_state()
        final = await graph.ainvoke(state)

        assert final.get("pipeline_stage") in ("COMPLETE", "MANUAL_REVIEW", "GROWTH_NODE"), \
            f"Pipeline stalled at: {final.get('pipeline_stage')} | error: {final.get('last_error')}"
        assert len(final.get("event_log", [])) > 0
    finally:
        for p in patches:
            p.stop()
        db_patch.stop()
