"""
tests/test_market_research.py
Research Council node tests — Claude live mode with mocked LLM calls.

The research council always runs live (no mock dossier fallback).
Tests use patched call_llm and fetch_trend_snapshot so no real API calls are made.
Run: pytest tests/test_market_research.py -v
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch

from packages.agents.governance.research_council import research_council_node
from packages.state.agent_state import init_state
from packages.tools.llm import LLMResponse


_MOCK_TREND_SNAPSHOT = {
    "topics": [
        {"topic": "AI receipt scanner", "score": 88, "region": "US"},
        {"topic": "freelancer invoicing tool", "score": 72, "region": "US"},
    ],
    "rising": ["AI expense tracking", "solo contractor tools"],
    "fetched_at": "2026-06-05T00:00:00Z",
}

_MOCK_SCOUT_REPORT = {
    "scout_role": "trend_hunter",
    "niche_candidates": [
        {
            "niche": "AI receipt scanner for freelancers",
            "venture_type": "MICRO_SAAS",
            "score": 0.84,
            "evidence": ["Google Trends +38% 90-day", "Active subreddits r/freelance"],
            "risks": ["Competitive market"],
        }
    ],
    "top_pick": "AI receipt scanner for freelancers",
    "rationale": "Strong trend signal with clear underserved segment.",
}

_MOCK_DEBATE = {
    "consensus_niches": ["AI receipt scanner for freelancers"],
    "disagreements": [],
    "recommended_primary_niche": "AI receipt scanner for freelancers",
    "recommended_venture_type": "MICRO_SAAS",
    "council_confidence": 0.78,
    "synthesis": "Council consensus: AI receipt scanner is the strongest candidate this cycle.",
    "evidence_gaps": [],
}


async def _smart_scout_llm(agent_role: str, *args, **kwargs) -> LLMResponse:
    role = agent_role.upper()
    if "DEBATE" in role or "SYNTHESIZER" in role:
        return LLMResponse(json.dumps(_MOCK_DEBATE), 50, 200, 3000, "claude-sonnet-4-6")
    report = {**_MOCK_SCOUT_REPORT, "scout_role": agent_role.lower()}
    return LLMResponse(json.dumps(report), 20, 80, 1500, "claude-sonnet-4-6")


@pytest.mark.asyncio
async def test_research_node_runs_live_with_claude(monkeypatch):
    """Research council uses Claude Sonnet and returns a real dossier."""
    state = init_state()

    with (
        patch("packages.agents.governance.research_council.call_llm",
              side_effect=_smart_scout_llm),
        patch("packages.agents.governance.research_council.fetch_trend_snapshot",
              new=AsyncMock(return_value=_MOCK_TREND_SNAPSHOT)),
        patch("packages.db.client.log_agent_event", return_value=None),
        patch("packages.db.pipeline.save_research_dossier", return_value=None),
    ):
        final = await research_council_node(state)

    assert final.get("pipeline_stage") == "CEO_NODE"
    dossier = final.get("research_dossier") or {}
    assert dossier.get("recommended_primary_niche") == "AI receipt scanner for freelancers"
    assert dossier.get("research_mode") == "claude_live"
    assert len(dossier.get("scout_reports", [])) == 5   # 5 scouts
    assert dossier.get("council_confidence", 0) > 0
    event_log = final.get("event_log", [])
    assert len(event_log) == 1
    assert event_log[0].get("event_type") == "RESEARCH_DOSSIER_READY"


@pytest.mark.asyncio
async def test_research_debate_transcript_has_5_scouts_and_synthesis():
    """Transcript must contain entries for all 5 scouts plus the synthesis phase."""
    state = init_state()

    with (
        patch("packages.agents.governance.research_council.call_llm",
              side_effect=_smart_scout_llm),
        patch("packages.agents.governance.research_council.fetch_trend_snapshot",
              new=AsyncMock(return_value=_MOCK_TREND_SNAPSHOT)),
        patch("packages.db.client.log_agent_event", return_value=None),
        patch("packages.db.pipeline.save_research_dossier", return_value=None),
    ):
        final = await research_council_node(state)

    transcript = final.get("debate_transcript") or []
    assert len(transcript) >= 6  # 5 scouts + 1 synthesis


@pytest.mark.asyncio
async def test_research_council_handles_scout_failure_gracefully():
    """If one scout's LLM call fails, the council continues with remaining scouts."""
    state = init_state()
    call_count = 0

    async def flaky_llm(agent_role: str, *args, **kwargs) -> LLMResponse:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated API timeout")
        return await _smart_scout_llm(agent_role, *args, **kwargs)

    with (
        patch("packages.agents.governance.research_council.call_llm",
              side_effect=flaky_llm),
        patch("packages.agents.governance.research_council.fetch_trend_snapshot",
              new=AsyncMock(return_value=_MOCK_TREND_SNAPSHOT)),
        patch("packages.db.client.log_agent_event", return_value=None),
        patch("packages.db.pipeline.save_research_dossier", return_value=None),
    ):
        final = await research_council_node(state)

    # Pipeline should still progress — 4 scouts succeeded
    assert final.get("pipeline_stage") == "CEO_NODE"
    dossier = final.get("research_dossier") or {}
    assert dossier.get("research_mode") == "claude_live"
