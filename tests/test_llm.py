"""
tests/test_llm.py
Unit tests for adaptive Kimi K2.6 routing and OpenAI-compatible provider wrappers.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch

from packages.tools.llm import kimi_available, call_llm, LLMResponse


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


@pytest.mark.asyncio
async def test_adaptive_routing_deepinfra(monkeypatch):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test_deepinfra_key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_MODEL", raising=False)

    response_mock = LLMResponse("Scout output", 10, 20, 100, "deepinfra:moonshotai/Kimi-K2.6")

    with patch("packages.tools.llm._call_deepinfra", new_callable=AsyncMock) as mock_deepinfra:
        mock_deepinfra.return_value = response_mock

        resp = await call_llm("KIMI_SCOUT_OPPORTUNITY", "System instructions", "User prompt")

        assert resp.text == "Scout output"
        mock_deepinfra.assert_called_once_with(
            "moonshotai/Kimi-K2.6", "System instructions", "User prompt", 0.3, 4096
        )


@pytest.mark.asyncio
async def test_adaptive_routing_openrouter(monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_openrouter_key")
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_MODEL", raising=False)

    response_mock = LLMResponse("Scout output OpenRouter", 15, 25, 120, "openrouter:moonshotai/kimi-k2.6")

    with patch("packages.tools.llm._call_openrouter", new_callable=AsyncMock) as mock_openrouter:
        mock_openrouter.return_value = response_mock

        resp = await call_llm("KIMI_SCOUT_OPPORTUNITY", "System instructions", "User prompt")

        assert resp.text == "Scout output OpenRouter"
        mock_openrouter.assert_called_once_with(
            "moonshotai/kimi-k2.6", "System instructions", "User prompt", 0.3, 4096
        )


@pytest.mark.asyncio
async def test_adaptive_routing_moonshot(monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("MOONSHOT_API_KEY", "test_moonshot_key")
    monkeypatch.delenv("KIMI_MODEL", raising=False)

    response_mock = LLMResponse("Scout output Moonshot", 8, 12, 80, "moonshot:kimi-k2.6")

    with patch("packages.tools.llm._call_moonshot", new_callable=AsyncMock) as mock_moonshot:
        mock_moonshot.return_value = response_mock

        resp = await call_llm("KIMI_SCOUT_OPPORTUNITY", "System instructions", "User prompt")

        assert resp.text == "Scout output Moonshot"
        mock_moonshot.assert_called_once_with(
            "kimi-k2.6", "System instructions", "User prompt", 0.3, 4096
        )


@pytest.mark.asyncio
async def test_adaptive_routing_model_env_override(monkeypatch):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test_deepinfra_key")
    monkeypatch.setenv("KIMI_MODEL", "custom-model-id")

    response_mock = LLMResponse("Custom output", 5, 5, 50, "deepinfra:custom-model-id")

    with patch("packages.tools.llm._call_deepinfra", new_callable=AsyncMock) as mock_deepinfra:
        mock_deepinfra.return_value = response_mock

        resp = await call_llm("KIMI_SCOUT_OPPORTUNITY", "System instructions", "User prompt")

        assert resp.text == "Custom output"
        mock_deepinfra.assert_called_once_with(
            "custom-model-id", "System instructions", "User prompt", 0.3, 4096
        )
