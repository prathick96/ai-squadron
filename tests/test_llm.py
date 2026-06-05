"""
tests/test_llm.py
Unit tests for the Claude + Gemini dual-provider routing in packages/tools/llm.py.

Architecture (June 2026):
  - Gemini 2.5 Pro   : Research Council scouts
  - Gemini 2.5 Flash : Operational / creative agents
  - Claude Sonnet    : Engineering Team + Legal Agent
  - Claude Haiku     : Security / infra agents
  - Kimi (optional)  : Available if OpenRouter/DeepInfra/Moonshot key is set
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from packages.tools.llm import kimi_available, call_llm, LLMResponse


# ─── Kimi availability (kept as optional provider) ────────────────────────────

def test_kimi_availability(monkeypatch):
    # Case 1: No keys set
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    assert not kimi_available()

    # Case 2: Placeholder key
    monkeypatch.setenv("DEEPINFRA_API_KEY", "your_deepinfra_key")
    assert not kimi_available()

    # Case 3: Valid DeepInfra key
    monkeypatch.setenv("DEEPINFRA_API_KEY", "valid_deepinfra_key_here")
    assert kimi_available()

    # Case 4: Valid OpenRouter key
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "valid_openrouter_key_here")
    assert kimi_available()

    # Case 5: Valid Moonshot key
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("MOONSHOT_API_KEY", "valid_moonshot_key_here")
    assert kimi_available()


# ─── Gemini routing — Research Council (now Gemini 2.5 Pro) ──────────────────

@pytest.mark.asyncio
async def test_research_scouts_route_to_gemini_pro(monkeypatch):
    """KIMI_SCOUT_* roles now route to Gemini 2.5 Pro, not Kimi."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")

    response_mock = LLMResponse("Scout output", 10, 20, 100, "gemini-2.5-pro")

    with patch("packages.tools.llm._call_gemini", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = response_mock

        resp = await call_llm("KIMI_SCOUT_TREND", "System prompt", "User prompt")

        assert resp.text == "Scout output"
        mock_gemini.assert_called_once()
        # First arg to _call_gemini is the model name
        assert mock_gemini.call_args[0][0] == "gemini-2.5-pro"


@pytest.mark.asyncio
async def test_debate_synthesizer_routes_to_gemini_pro(monkeypatch):
    """Debate synthesiser also uses Gemini 2.5 Pro for complex reasoning."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")

    response_mock = LLMResponse("Synthesis output", 50, 200, 3000, "gemini-2.5-pro")

    with patch("packages.tools.llm._call_gemini", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = response_mock

        resp = await call_llm("KIMI_DEBATE_SYNTHESIZER", "System prompt", "User prompt")

        assert resp.text == "Synthesis output"
        assert mock_gemini.call_args[0][0] == "gemini-2.5-pro"


# ─── Gemini routing — operational agents (Gemini 2.5 Flash) ──────────────────

@pytest.mark.asyncio
async def test_operational_agents_route_to_gemini_flash(monkeypatch):
    """Product VP, Media VP, Script Agent etc. use Gemini 2.5 Flash."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")

    response_mock = LLMResponse("Flash output", 10, 50, 500, "gemini-2.5-flash")

    for agent_role in ["PRODUCT_VP", "SCRIPT_AGENT", "SEO_METADATA_AGENT", "MARKETING_SEO"]:
        with patch("packages.tools.llm._call_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_gemini.return_value = response_mock

            resp = await call_llm(agent_role, "System prompt", "User prompt")

            assert resp.text == "Flash output", f"Wrong response for {agent_role}"
            assert mock_gemini.call_args[0][0] == "gemini-2.5-flash", \
                f"{agent_role} should use gemini-2.5-flash"


# ─── Claude routing — Engineering Team + Legal ────────────────────────────────

@pytest.mark.asyncio
async def test_engineering_team_routes_to_claude_sonnet(monkeypatch):
    """Engineering Team must always use Claude Sonnet — best code gen."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")

    response_mock = LLMResponse('{"files": []}', 100, 500, 4000, "claude-sonnet-4-6")

    with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = response_mock

        resp = await call_llm("ENGINEERING_TEAM", "System prompt", "User prompt")

        assert resp.text == '{"files": []}'
        mock_claude.assert_called_once()
        assert mock_claude.call_args[0][0] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_legal_agent_routes_to_claude_sonnet(monkeypatch):
    """Legal Agent uses Claude Sonnet for compliance reasoning."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")

    response_mock = LLMResponse('{"is_cleared": true}', 20, 100, 2000, "claude-sonnet-4-6")

    with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = response_mock

        resp = await call_llm("LEGAL_AGENT", "System prompt", "User prompt")

        assert resp.text == '{"is_cleared": true}'
        assert mock_claude.call_args[0][0] == "claude-sonnet-4-6"


# ─── Claude Haiku routing — security agents ───────────────────────────────────

@pytest.mark.asyncio
async def test_security_agents_route_to_claude_haiku(monkeypatch):
    """Security, Anti-ban, Deployment agents use Claude Haiku."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")

    response_mock = LLMResponse('{"score": 85}', 10, 30, 400, "claude-haiku-4-5-20251001")

    for agent_role in ["SECURITY_AGENT", "ANTI_BAN_AGENT", "DEPLOYMENT_AGENT"]:
        with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = response_mock

            resp = await call_llm(agent_role, "System prompt", "User prompt")

            assert resp.text == '{"score": 85}'
            assert mock_claude.call_args[0][0] == "claude-haiku-4-5-20251001", \
                f"{agent_role} should use claude-haiku"


# ─── Kimi optional provider (still works if keys are set) ─────────────────────

@pytest.mark.asyncio
async def test_kimi_provider_still_works_for_explicit_kimi_calls(monkeypatch):
    """
    Kimi is available as an optional provider. Any agent configured with
    provider='kimi' in the registry will still route correctly if keys are set.
    This test validates the Kimi routing machinery still works end-to-end,
    even though no standard agent uses it by default anymore.
    """
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test_deepinfra_key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_MODEL", raising=False)

    response_mock = LLMResponse("Kimi output", 10, 20, 100, "deepinfra:moonshotai/Kimi-K2.6")

    # Temporarily override one agent's registry entry to 'kimi' provider
    from packages.tools import llm as llm_module
    original = llm_module.MODEL_REGISTRY.get("KIMI_SCOUT_OPPORTUNITY")
    llm_module.MODEL_REGISTRY["KIMI_SCOUT_OPPORTUNITY"] = ("kimi", "moonshotai/Kimi-K2.6")

    try:
        with patch("packages.tools.llm._call_deepinfra", new_callable=AsyncMock) as mock_deepinfra:
            mock_deepinfra.return_value = response_mock

            resp = await call_llm("KIMI_SCOUT_OPPORTUNITY", "System instructions", "User prompt")

            assert resp.text == "Kimi output"
            mock_deepinfra.assert_called_once_with(
                "moonshotai/Kimi-K2.6", "System instructions", "User prompt", 0.3, 4096
            )
    finally:
        if original:
            llm_module.MODEL_REGISTRY["KIMI_SCOUT_OPPORTUNITY"] = original
