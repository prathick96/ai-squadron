"""
tests/test_llm.py
Unit tests for the Claude-only LLM routing in packages/tools/llm.py.

Architecture (June 2026):
  - Claude Sonnet 4.6       : Research Council, CEO, Engineering, Legal, QA critique
  - Claude Haiku 4.5        : All operational agents (VP, PM, Marketing, Security, Infra)
  - Single provider — Anthropic only, no Gemini / OpenRouter / Kimi
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from packages.tools.llm import call_llm, LLMResponse


# ─── Research Council → Claude Sonnet ────────────────────────────────────────

@pytest.mark.asyncio
async def test_research_scouts_route_to_claude_sonnet(monkeypatch):
    """KIMI_SCOUT_* roles route to Claude Sonnet for deep reasoning."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse("Scout output", 10, 20, 100, "claude-sonnet-4-6")

    with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = response_mock

        resp = await call_llm("KIMI_SCOUT_TREND", "System prompt", "User prompt")

        assert resp.text == "Scout output"
        mock_claude.assert_called_once()
        assert mock_claude.call_args[0][0] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_debate_synthesizer_routes_to_claude_sonnet(monkeypatch):
    """Debate synthesiser uses Claude Sonnet for complex multi-scout reasoning."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse("Synthesis output", 50, 200, 3000, "claude-sonnet-4-6")

    with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = response_mock

        resp = await call_llm("KIMI_DEBATE_SYNTHESIZER", "System prompt", "User prompt")

        assert resp.text == "Synthesis output"
        assert mock_claude.call_args[0][0] == "claude-sonnet-4-6"


# ─── CEO + QA Critique → Claude Sonnet ───────────────────────────────────────

@pytest.mark.asyncio
async def test_grand_ceo_routes_to_claude_sonnet(monkeypatch):
    """Grand CEO uses Claude Sonnet — go/no-go decisions must use best model."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse('{"go_decision": true}', 30, 100, 800, "claude-sonnet-4-6")

    with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = response_mock

        resp = await call_llm("GRAND_CEO", "System prompt", "User prompt")

        assert resp.text == '{"go_decision": true}'
        assert mock_claude.call_args[0][0] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_qa_critique_routes_to_claude_sonnet(monkeypatch):
    """QA critique agents use Claude Sonnet for code analysis quality."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse('{"failed_checks": []}', 20, 60, 600, "claude-sonnet-4-6")

    for role in ["QA_TECHNICAL_CRITIQUE", "QA_COMPLIANCE_CRITIQUE", "QA_AUDITOR_CRITIQUE"]:
        with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = response_mock

            resp = await call_llm(role, "System prompt", "User prompt")

            assert resp.text == '{"failed_checks": []}'
            assert mock_claude.call_args[0][0] == "claude-sonnet-4-6", \
                f"{role} should use claude-sonnet-4-6"


# ─── Engineering + Legal → Claude Sonnet ─────────────────────────────────────

@pytest.mark.asyncio
async def test_engineering_team_routes_to_claude_sonnet(monkeypatch):
    """Engineering Team uses Claude Sonnet — best code generation."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse('{"files": []}', 100, 500, 4000, "claude-sonnet-4-6")

    with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = response_mock

        resp = await call_llm("ENGINEERING_TEAM", "System prompt", "User prompt")

        assert resp.text == '{"files": []}'
        assert mock_claude.call_args[0][0] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_legal_agent_routes_to_claude_sonnet(monkeypatch):
    """Legal Agent uses Claude Sonnet for compliance reasoning."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse('{"is_cleared": true}', 20, 100, 2000, "claude-sonnet-4-6")

    with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = response_mock

        resp = await call_llm("LEGAL_AGENT", "System prompt", "User prompt")

        assert resp.text == '{"is_cleared": true}'
        assert mock_claude.call_args[0][0] == "claude-sonnet-4-6"


# ─── Operational agents → Claude Haiku ───────────────────────────────────────

@pytest.mark.asyncio
async def test_operational_agents_route_to_claude_haiku(monkeypatch):
    """Product VP, PM, Marketing, Growth use Claude Haiku — fast structured ops."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse('{"plan": "ok"}', 10, 50, 300, "claude-haiku-4-5-20251001")

    for role in ["PRODUCT_VP", "PRODUCT_MANAGER", "MARKETING_SEO", "PRODUCT_GROWTH"]:
        with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = response_mock

            resp = await call_llm(role, "System prompt", "User prompt")

            assert resp.text == '{"plan": "ok"}', f"Wrong response for {role}"
            assert mock_claude.call_args[0][0] == "claude-haiku-4-5-20251001", \
                f"{role} should use claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_security_agents_route_to_claude_haiku(monkeypatch):
    """Security, Anti-ban, Deployment agents use Claude Haiku."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse('{"score": 85}', 10, 30, 400, "claude-haiku-4-5-20251001")

    for role in ["SECURITY_AGENT", "ANTI_BAN_AGENT", "DEPLOYMENT_AGENT"]:
        with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = response_mock

            resp = await call_llm(role, "System prompt", "User prompt")

            assert resp.text == '{"score": 85}'
            assert mock_claude.call_args[0][0] == "claude-haiku-4-5-20251001", \
                f"{role} should use claude-haiku-4-5-20251001"


# ─── Unknown role → Haiku fallback ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_role_falls_back_to_haiku(monkeypatch):
    """Roles not in MODEL_REGISTRY default to Haiku (cheap, safe fallback)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse('{}', 5, 10, 200, "claude-haiku-4-5-20251001")

    with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = response_mock

        resp = await call_llm("UNKNOWN_AGENT_ROLE_XYZ", "System prompt", "User prompt")

        assert mock_claude.call_args[0][0] == "claude-haiku-4-5-20251001"


# ─── response_schema ignored ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_response_schema_param_is_accepted_but_ignored(monkeypatch):
    """response_schema is accepted for call-site compat but not passed to Anthropic."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    response_mock = LLMResponse('{"ok": true}', 5, 10, 200, "claude-haiku-4-5-20251001")

    with patch("packages.tools.llm._call_anthropic", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = response_mock

        # Should not raise even with a schema passed
        resp = await call_llm(
            "SECURITY_AGENT", "System", "User",
            response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        )
        assert resp.text == '{"ok": true}'
