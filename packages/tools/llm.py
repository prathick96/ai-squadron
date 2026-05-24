"""
packages/tools/llm.py
LLM client factory with proper rate-limit handling.

Retry strategy:
  - Transient errors (5xx, network)  : retry up to 3x, exponential backoff (4s→60s)
  - 429 / quota exhausted on Pro      : immediate fallback to Flash (no retry)
  - 429 on Flash                      : wait 61 seconds, retry Flash once
  - All other errors                  : raise immediately
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import anthropic
from google import genai
from google.genai import types as genai_types
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

_FLASH  = "gemini-2.0-flash"
_FLASH_LITE = "gemini-2.0-flash-lite"   # absolute last resort

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_gemini_client: genai.Client | None = None
_anthropic_client: anthropic.AsyncAnthropic | None = None


def _get_gemini() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY not set")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set")
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic_client


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
_KIMI_MODEL = os.getenv("KIMI_MODEL", "moonshotai/kimi-k2.6")

MODEL_REGISTRY: dict[str, tuple[str, str]] = {
    # ── Research Council (Kimi — 1M context for deep niche research) ──────
    "KIMI_SCOUT_TREND":        ("kimi", _KIMI_MODEL),
    "KIMI_SCOUT_COMPETITOR":   ("kimi", _KIMI_MODEL),
    "KIMI_SCOUT_SKEPTIC":      ("kimi", _KIMI_MODEL),
    "KIMI_SCOUT_AUDIENCE":     ("kimi", _KIMI_MODEL),
    "KIMI_SCOUT_EXECUTION":    ("kimi", _KIMI_MODEL),
    "KIMI_DEBATE_SYNTHESIZER": ("kimi", _KIMI_MODEL),
    # Legacy scout names (backward compat)
    "KIMI_SCOUT_OPPORTUNITY":  ("kimi", _KIMI_MODEL),

    # ── Governance (Gemini Pro — strategic reasoning) ─────────────────────
    "GRAND_CEO":           ("gemini",    "gemini-2.5-pro"),
    "LEGAL_AGENT":         ("gemini",    "gemini-2.5-pro"),
    "REVENUE_ENGINE":      ("gemini",    "gemini-2.5-pro"),
    # Legacy
    "CEO_NICHE_SCOUT":     ("gemini",    "gemini-2.5-pro"),

    # ── Engineering (Claude Sonnet — best code gen) ───────────────────────
    "ENGINEERING_TEAM":    ("anthropic", "claude-sonnet-4-6"),

    # ── QA critique (Claude Haiku — precise structured directives) ────────
    "QA_TECHNICAL_CRITIQUE":   ("anthropic", "claude-haiku-4-5-20251001"),
    "QA_COMPLIANCE_CRITIQUE":  ("anthropic", "claude-haiku-4-5-20251001"),
    # Legacy
    "QA_AUDITOR_CRITIQUE": ("anthropic", "claude-haiku-4-5-20251001"),

    # ── All other agents (Gemini Flash — cost-efficient) ──────────────────
    "PRODUCT_VP":          ("gemini", _FLASH),
    "PRODUCT_MANAGER":     ("gemini", _FLASH),
    "MEDIA_VP":            ("gemini", _FLASH),
    "SCRIPT_AGENT":        ("gemini", _FLASH),
    "VOICE_AGENT":         ("gemini", _FLASH),
    "VIDEO_AGENT":         ("gemini", _FLASH),
    "THUMBNAIL_AGENT":     ("gemini", _FLASH),
    "SEO_METADATA_AGENT":  ("gemini", _FLASH),
    "QA_TECHNICAL_GATE":   ("gemini", _FLASH),
    "QA_COMPLIANCE_GATE":  ("gemini", _FLASH),
    "SECURITY_AGENT":      ("gemini", _FLASH),
    "ANTI_BAN_AGENT":      ("gemini", _FLASH),
    "DEPLOYMENT_AGENT":    ("gemini", _FLASH),
    "MARKETING_SEO":       ("gemini", _FLASH),
    "PUBLISHING_AGENT":    ("gemini", _FLASH),
    "ANALYTICS_AGENT":     ("gemini", _FLASH),
    "PRODUCT_GROWTH":      ("gemini", _FLASH),
    "MEDIA_GROWTH":        ("gemini", _FLASH),
    # Legacy
    "PRODUCT_TEAM":        ("gemini", _FLASH),
    "CONTENT_TEAM":        ("gemini", _FLASH),
    "MARKETING_TEAM":      ("gemini", _FLASH),
    "GLOBAL_TEAM":         ("gemini", _FLASH),
    "GROWTH_TEAM":         ("gemini", _FLASH),
    "DEPLOYMENT_TEAM":     ("gemini", _FLASH),
    "QA_AUDITOR_GATE":     ("gemini", _FLASH),
}

# ---------------------------------------------------------------------------
# Response wrapper
# ---------------------------------------------------------------------------
class LLMResponse:
    def __init__(self, text: str, input_tokens: int, output_tokens: int,
                 latency_ms: int, model_used: str = ""):
        self.text          = text
        self.input_tokens  = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens  = input_tokens + output_tokens
        self.latency_ms    = latency_ms
        self.model_used    = model_used

    def __repr__(self) -> str:
        return (f"LLMResponse(model={self.model_used}, tokens={self.total_tokens}, "
                f"latency={self.latency_ms}ms)")


# ---------------------------------------------------------------------------
# Error classification helpers
# ---------------------------------------------------------------------------
def _is_rate_limit(exc: Exception) -> bool:
    """
    Detect 429 / quota errors from google-genai.
    Checks the exception itself AND its cause chain (tenacity wraps in RetryError).
    """
    def _check(e: BaseException) -> bool:
        s = str(e).lower()
        return any(k in s for k in (
            "429", "quota", "rate_limit", "resource_exhausted",
            "too many requests", "rate exceeded",
        ))

    if _check(exc):
        return True
    # Unwrap tenacity RetryError → check the last underlying exception
    cause = getattr(exc, "__cause__", None) or getattr(exc, "last_attempt", None)
    if cause is not None:
        inner = getattr(cause, "exception", lambda: None)()
        if inner is not None and _check(inner):
            return True
    return False


def _is_transient(exc: Exception) -> bool:
    """Only retry on transient errors — never on 429 (handled separately)."""
    if _is_rate_limit(exc):
        return False
    s = str(exc).lower()
    return any(k in s for k in ("500", "503", "502", "network", "timeout",
                                  "connection", "connect error"))


# ---------------------------------------------------------------------------
# Core Gemini raw call — retries ONLY on transient errors, never on 429
# ---------------------------------------------------------------------------
@retry(
    retry=retry_if_exception(_is_transient),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    reraise=True,
)
async def _gemini_raw(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    response_schema: Any | None,
) -> LLMResponse:
    client = _get_gemini()
    t0     = time.monotonic()

    extra: dict[str, Any] = {}
    if response_schema:
        extra["response_mime_type"] = "application/json"
        extra["response_schema"]    = response_schema

    config = genai_types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
        **extra,
    )
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=user_prompt,
        config=config,
    )

    latency_ms    = int((time.monotonic() - t0) * 1000)
    text          = response.text or ""
    usage         = getattr(response, "usage_metadata", None)
    input_tokens  = getattr(usage, "prompt_token_count",     0) if usage else 0
    output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

    log.debug("Gemini %s → %d tokens %dms", model_name, input_tokens + output_tokens, latency_ms)
    return LLMResponse(text, input_tokens, output_tokens, latency_ms, model_used=model_name)


# ---------------------------------------------------------------------------
# Public Gemini call — full fallback + rate-limit wait logic
# ---------------------------------------------------------------------------
async def _call_gemini(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    response_schema: Any | None = None,
) -> LLMResponse:
    """
    Call hierarchy on rate limits:
      gemini-2.5-pro  → (429) → gemini-2.0-flash  → (429) → wait 61s → retry flash
    """
    try:
        return await _gemini_raw(model_name, system_prompt, user_prompt,
                                  temperature, response_schema)
    except Exception as exc:
        if not _is_rate_limit(exc):
            raise

        # Step 1: If Pro was rate-limited, try Flash immediately
        if model_name != _FLASH:
            log.warning("Gemini %s rate-limited — trying %s", model_name, _FLASH)
            try:
                return await _gemini_raw(_FLASH, system_prompt, user_prompt,
                                          temperature, response_schema)
            except Exception as flash_exc:
                if not _is_rate_limit(flash_exc):
                    raise

        # Step 2: Flash also rate-limited — wait out the 60s RPM window
        wait_sec = 61
        log.warning(
            "Gemini %s also rate-limited (15 RPM exceeded). "
            "Waiting %ds for rate limit window to reset...",
            _FLASH, wait_sec,
        )
        await asyncio.sleep(wait_sec)

        # Step 3: Retry Flash after the wait
        log.info("Retrying %s after rate-limit wait", _FLASH)
        return await _gemini_raw(_FLASH, system_prompt, user_prompt,
                                  temperature, response_schema)


# ---------------------------------------------------------------------------
# Anthropic call — unchanged
# ---------------------------------------------------------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=60))
async def _call_anthropic(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 8192,
) -> LLMResponse:
    client = _get_anthropic()
    t0     = time.monotonic()

    response = await client.messages.create(
        model=model_name,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    latency_ms    = int((time.monotonic() - t0) * 1000)
    text          = response.content[0].text if response.content else ""
    input_tokens  = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    log.debug("Anthropic %s → %d tokens %dms", model_name, input_tokens + output_tokens, latency_ms)
    return LLMResponse(text, input_tokens, output_tokens, latency_ms, model_used=model_name)


# ---------------------------------------------------------------------------
# OpenRouter / Kimi (OpenAI-compatible)
# ---------------------------------------------------------------------------
def _is_valid_key(env_name: str) -> bool:
    val = os.getenv(env_name, "")
    return bool(val) and len(val) > 10 and "your_" not in val.lower()


def kimi_available() -> bool:
    return (
        _is_valid_key("DEEPINFRA_API_KEY")
        or _is_valid_key("OPENROUTER_API_KEY")
        or _is_valid_key("MOONSHOT_API_KEY")
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=60))
async def _call_openai_compatible(
    provider_name: str,
    api_key: str,
    base_url: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
    max_tokens: int = 4096,
    extra_headers: dict[str, str] | None = None,
) -> LLMResponse:
    import httpx

    t0 = time.monotonic()
    headers = {"Authorization": f"Bearer {api_key}"}
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    text = data["choices"][0]["message"]["content"] or ""
    usage = data.get("usage", {})
    latency_ms = int((time.monotonic() - t0) * 1000)
    inp = usage.get("prompt_tokens", 0)
    out = usage.get("completion_tokens", 0)
    log.debug("%s %s → %d tokens %dms", provider_name, model_name, inp + out, latency_ms)
    return LLMResponse(text, inp, out, latency_ms, model_used=f"{provider_name.lower()}:{model_name}")


async def _call_openrouter(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
    max_tokens: int = 4096,
) -> LLMResponse:
    api_key = os.environ["OPENROUTER_API_KEY"]
    base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    extra_headers = {
        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://ai-squadron.local"),
        "X-Title": "AI Squadron",
    }
    return await _call_openai_compatible(
        "OpenRouter", api_key, base, model_name, system_prompt, user_prompt,
        temperature, max_tokens, extra_headers
    )


async def _call_deepinfra(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
    max_tokens: int = 4096,
) -> LLMResponse:
    api_key = os.environ["DEEPINFRA_API_KEY"]
    base = os.getenv("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai")
    return await _call_openai_compatible(
        "DeepInfra", api_key, base, model_name, system_prompt, user_prompt,
        temperature, max_tokens
    )


async def _call_moonshot(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
    max_tokens: int = 4096,
) -> LLMResponse:
    api_key = os.environ["MOONSHOT_API_KEY"]
    base = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    return await _call_openai_compatible(
        "Moonshot", api_key, base, model_name, system_prompt, user_prompt,
        temperature, max_tokens
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
async def call_llm(
    agent_role: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 8192,
    response_schema: Any | None = None,
) -> LLMResponse:
    provider, model_name = MODEL_REGISTRY.get(agent_role, ("gemini", _FLASH))

    # Resolve adaptive 'kimi' provider
    if provider == "kimi":
        if not kimi_available():
            raise EnvironmentError(
                "No API key configured for Kimi (requires DEEPINFRA_API_KEY, OPENROUTER_API_KEY, or MOONSHOT_API_KEY)"
            )
        if _is_valid_key("DEEPINFRA_API_KEY"):
            provider = "deepinfra"
            model_name = os.getenv("KIMI_MODEL") or "moonshotai/Kimi-K2.6"
        elif _is_valid_key("OPENROUTER_API_KEY"):
            provider = "openrouter"
            model_name = os.getenv("KIMI_MODEL") or "moonshotai/kimi-k2.6"
        else:
            provider = "moonshot"
            model_name = os.getenv("KIMI_MODEL") or "kimi-k2.6"

    if provider == "openrouter":
        if not _is_valid_key("OPENROUTER_API_KEY"):
            raise EnvironmentError("OPENROUTER_API_KEY not set")
        return await _call_openrouter(
            model_name, system_prompt, user_prompt, temperature, min(max_tokens, 4096)
        )
    if provider == "deepinfra":
        if not _is_valid_key("DEEPINFRA_API_KEY"):
            raise EnvironmentError("DEEPINFRA_API_KEY not set")
        return await _call_deepinfra(
            model_name, system_prompt, user_prompt, temperature, min(max_tokens, 4096)
        )
    if provider == "moonshot":
        if not _is_valid_key("MOONSHOT_API_KEY"):
            raise EnvironmentError("MOONSHOT_API_KEY not set")
        return await _call_moonshot(
            model_name, system_prompt, user_prompt, temperature, min(max_tokens, 4096)
        )
    if provider == "anthropic":
        return await _call_anthropic(model_name, system_prompt, user_prompt,
                                      temperature, max_tokens)
    return await _call_gemini(model_name, system_prompt, user_prompt,
                               temperature, response_schema)


async def classify(prompt: str, choices: list[str]) -> str:
    client = _get_gemini()
    full_prompt = f"Respond ONLY with one of: {', '.join(choices)}.\n\n{prompt}"
    try:
        response = await client.aio.models.generate_content(
            model=_FLASH, contents=full_prompt,
        )
        result = (response.text or "").strip()
        for c in choices:
            if c.lower() in result.lower():
                return c
    except Exception:
        pass
    return choices[0]
