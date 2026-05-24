"""
tests/test_market_research.py
Research Council node tests (mock mode — no OpenRouter calls).
"""
from __future__ import annotations

import pytest

from packages.agents.market_research import market_research_node
from packages.state.agent_state import init_state
from packages.tools.llm import kimi_available


def test_kimi_not_required_in_tests(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert kimi_available() is False


@pytest.mark.asyncio
async def test_research_node_mock_dossier(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    state = init_state()
    final = await market_research_node(state)

    assert final.get("pipeline_stage") == "CEO_NODE"
    dossier = final.get("research_dossier") or {}
    assert dossier.get("recommended_primary_niche")
    assert dossier.get("research_mode") == "mock"
    assert len(dossier.get("scout_reports", [])) == 3
    assert dossier.get("council_confidence", 0) > 0
    assert len(final.get("event_log", [])) == 1
    assert final["event_log"][0].get("event_type") == "RESEARCH_DOSSIER_READY"


@pytest.mark.asyncio
async def test_research_debate_transcript(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    state = init_state()
    final = await market_research_node(state)
    transcript = final.get("debate_transcript") or []
    assert len(transcript) >= 4  # 3 scouts + synthesis
