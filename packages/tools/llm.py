"""
packages/tools/llm.py
LLM client factory — Claude + Gemini dual-provider architecture.

Model assignment philosophy (June 2026):
  - Gemini 2.5 Pro  : Research Council — 1M context for deep niche research with trend data
  - Gemini 2.5 Flash: All creative/SEO/ops agents — fast, excellent at content & analysis
  - Claude Sonnet   : Engineering Team + Legal Agent — best code gen + compliance reasoning
  - Claude Haiku    : Security, Anti-ban, Deployment, Credential Guardian — fast structured ops

Retry strategy:
  - Transient errors (5xx, network)  : retry up to 3x, exponential backoff (4s→60s)
  - 429 / quota exhausted            : immediate fallback to Gemini Flash (no retry)
  - 403 / permission denied          : treated as rate-limit → fallback to Flash
  - 404 / model not found            : treated as unavailable → fallback to Flash
  - 429 / 403 on Flash               : wait 61 seconds, retry Flash once
  - Empty response (safety filter)   : raise ValueError so fallback fires

Gemini credentials: Set GEMINI_API_KEY in Railway env vars.
  Get from: aistudio.google.com → Get API Key
Anthropic credentials: ANTHROPIC_API_KEY
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
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

# ── Gemini models ─────────────────────────────────────────────────────────────
# 2.5-pro:   1M context, best reasoning — Research Council scouts
# 2.5-flash: Fast + cheap, excellent creative/SEO — operational agents
# 1.5-flash: Stable fallback if 2.5 quota is exhausted or unavailable
_GEMINI_PRO   = "gemini-2.5-pro"
_GEMINI_FLASH = "gemini-2.5-flash"
_FLASH        = "gemini-1.5-flash"        # stable fallback
_FLASH_LITE   = "gemini-1.5-flash-8b"    # absolute last resort

# ── Anthropic models ───────────────────────────────────────────────────────────
_HAIKU      = "claude-haiku-4-5-20251001"  # fast structured ops (security, infra)
_SONNET     = "claude-sonnet-4-6"          # code gen + legal reasoning


# ---------------------------------------------------------------------------
# Markdown code-fence stripper — applied to ALL LLM responses
# ---------------------------------------------------------------------------
_CODE_FENCE_RE = re.compile(
    r'^```(?:json|python|javascript|typescript|text|xml|yaml|markdown)?\s*\n?',
    re.MULTILINE,
)

def _strip_code_fences(text: str) -> str:
    """
    Remove markdown code fences that LLMs sometimes add despite instructions.

    Handles:
      ```json\\n{...}\\n```      → {...}
      ```\\n{...}\\n```          → {...}
      {... no fences ...}        → unchanged

    Applied to every provider response so all agents can safely call
    json.loads(response.text) without worrying about fence wrapping.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    # Remove opening fence line
    stripped = _CODE_FENCE_RE.sub("", stripped, count=1)
    # Remove closing fence
    if stripped.endswith("```"):
        stripped = stripped[: stripped.rfind("```")].rstrip()
    return stripped.strip()


def extract_json(text: str) -> str:
    """
    Robustly extract a JSON object or array from LLM output.

    Handles all the ways LLMs deviate from 'output ONLY valid JSON':
      1. Clean JSON                     → returned as-is
      2. JSON inside ```json ... ```    → fences stripped first
      3. Preamble text before JSON      → 'Here is the code: {...}' → '{...}'
      4. Preamble + fences              → both stripped

    The 'char 0' JSONDecodeError ('Expecting value: line 1 col 1') is always
    caused by a non-JSON first character, i.e. case 3.  This function fixes it.
    """
    # Step 1: strip code fences
    cleaned = _strip_code_fences(text.strip())

    # Step 2: if it already starts with a JSON opener, we're done
    if cleaned.startswith(("{", "[")):
        return cleaned

    # Step 3: find the first JSON opener buried in preamble text
    first_brace  = cleaned.find("{")
    first_bracket = cleaned.find("[")

    candidates = [i for i in (first_brace, first_bracket) if i != -1]
    if not candidates:
        return cleaned  # nothing found — let json.loads give the real error

    start = min(candidates)
    return cleaned[start:]

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
# Kimi kept as optional override — if KIMI_MODEL env var is set alongside
# an OpenRouter/DeepInfra key, it will be used for any agent that explicitly
# requests "kimi" provider. Otherwise all research routes to Gemini 2.5 Pro.
_KIMI_MODEL = os.getenv("KIMI_MODEL", "moonshotai/kimi-k2.6")

MODEL_REGISTRY: dict[str, tuple[str, str]] = {
    # ── Research Council — Gemini 2.5 Pro ────────────────────────────────────
    # 1M context window + best multi-step reasoning for structured 5-scout debate.
    # Gemini 2.5 Pro outperforms Kimi on structured JSON output and debate synthesis.
    # Falls back to gemini-1.5-flash if 2.5-pro quota is hit or unavailable (404).
    "KIMI_SCOUT_TREND":        ("gemini", _GEMINI_PRO),
    "KIMI_SCOUT_COMPETITOR":   ("gemini", _GEMINI_PRO),
    "KIMI_SCOUT_SKEPTIC":      ("gemini", _GEMINI_PRO),
    "KIMI_SCOUT_AUDIENCE":     ("gemini", _GEMINI_PRO),
    "KIMI_SCOUT_EXECUTION":    ("gemini", _GEMINI_PRO),
    "KIMI_DEBATE_SYNTHESIZER": ("gemini", _GEMINI_PRO),
    "KIMI_SCOUT_OPPORTUNITY":  ("gemini", _GEMINI_PRO),  # legacy name compat

    # ── Governance ────────────────────────────────────────────────────────────
    # CEO: Gemini 2.5 Flash — fast strategic decisions with rich market context
    # Legal: Claude Sonnet — best compliance reasoning, strict instruction following
    # Revenue: Gemini 2.5 Flash — financial pattern analysis and portfolio signals
    "GRAND_CEO":           ("gemini",    _GEMINI_FLASH),
    "LEGAL_AGENT":         ("anthropic", _SONNET),
    "REVENUE_ENGINE":      ("gemini",    _GEMINI_FLASH),
    "CEO_NICHE_SCOUT":     ("gemini",    _GEMINI_FLASH),  # legacy

    # ── Engineering — Claude Sonnet ───────────────────────────────────────────
    # Claude Sonnet 4.6 produces the most correct TypeScript/React/Python code.
    # This is the single most important agent quality gate — never downgrade it.
    "ENGINEERING_TEAM":    ("anthropic", _SONNET),

    # ── QA critique — Gemini 2.5 Flash ───────────────────────────────────────
    # Fast, precise structured JSON critique directives for build failures.
    "QA_TECHNICAL_CRITIQUE":   ("gemini", _GEMINI_FLASH),
    "QA_COMPLIANCE_CRITIQUE":  ("gemini", _GEMINI_FLASH),
    "QA_AUDITOR_CRITIQUE":     ("gemini", _GEMINI_FLASH),  # legacy

    # ── Product agents — Gemini 2.5 Flash ────────────────────────────────────
    # Gemini excels at business analysis, market positioning, and product strategy.
    "PRODUCT_VP":          ("gemini", _GEMINI_FLASH),
    "PRODUCT_MANAGER":     ("gemini", _GEMINI_FLASH),
    "PRODUCT_GROWTH":      ("gemini", _GEMINI_FLASH),
    "MARKETING_SEO":       ("gemini", _GEMINI_FLASH),

    # ── Media agents — Gemini 2.5 Flash ──────────────────────────────────────
    # Creative scriptwriting, SEO metadata, and thumbnail prompts are Gemini strengths.
    # Gemini has seen more YouTube/TikTok content and produces better hooks + titles.
    "MEDIA_VP":            ("gemini", _GEMINI_FLASH),
    "SCRIPT_AGENT":        ("gemini", _GEMINI_FLASH),
    "SEO_METADATA_AGENT":  ("gemini", _GEMINI_FLASH),
    "THUMBNAIL_AGENT":     ("gemini", _GEMINI_FLASH),
    "PUBLISHING_AGENT":    ("gemini", _GEMINI_FLASH),
    "ANALYTICS_AGENT":     ("gemini", _GEMINI_FLASH),
    "MEDIA_GROWTH":        ("gemini", _GEMINI_FLASH),
    "VOICE_AGENT":         ("gemini", _GEMINI_FLASH),
    "VIDEO_AGENT":         ("gemini", _GEMINI_FLASH),

    # ── Security / Infra — Claude Haiku ──────────────────────────────────────
    # Security and anti-ban agents need conservative, precise pattern matching.
    # Claude Haiku's training makes it more reliable for security-sensitive ops.
    "SECURITY_AGENT":      ("anthropic", _HAIKU),
    "ANTI_BAN_AGENT":      ("anthropic", _HAIKU),
    "DEPLOYMENT_AGENT":    ("anthropic", _HAIKU),
    "QA_TECHNICAL_GATE":   ("anthropic", _HAIKU),
    "QA_COMPLIANCE_GATE":  ("anthropic", _HAIKU),
    "QA_AUDITOR_GATE":     ("anthropic", _HAIKU),  # legacy

    # Legacy agent names — backward compat with old pipeline runs
    "PRODUCT_TEAM":        ("gemini",    _GEMINI_FLASH),
    "CONTENT_TEAM":        ("gemini",    _GEMINI_FLASH),
    "MARKETING_TEAM":      ("gemini",    _GEMINI_FLASH),
    "GLOBAL_TEAM":         ("gemini",    _GEMINI_FLASH),
    "GROWTH_TEAM":         ("gemini",    _GEMINI_FLASH),
    "DEPLOYMENT_TEAM":     ("anthropic", _HAIKU),
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
    Detect errors that should trigger a fallback to a lower/stable model.
    Checks the exception itself AND its cause chain (tenacity wraps in RetryError).

    Triggers fallback:
      - 429 / quota exhausted     → rate limited
      - 403 / permission denied   → no access to this model tier
      - 404 / not found           → model deprecated or not yet available in your region
    """
    def _check(e: BaseException) -> bool:
        s = str(e).lower()
        return any(k in s for k in (
            "429", "quota", "rate_limit", "resource_exhausted",
            "too many requests", "rate exceeded",
            "403", "permission_denied", "denied access",
            "404", "not found", "model not found",  # model unavailable → fallback to 1.5-flash
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
    text          = _strip_code_fences(response.text or "")
    usage         = getattr(response, "usage_metadata", None)
    input_tokens  = getattr(usage, "prompt_token_count",     0) if usage else 0
    output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

    if not text:
        # Empty text means quota exhaustion (billing not active), a safety filter
        # block, or a model error.  Raise so _call_gemini's fallback chain fires.
        try:
            candidates = getattr(response, "candidates", None) or []
            finish_reason = str(getattr(candidates[0], "finish_reason", "UNKNOWN")) if candidates else "UNKNOWN"
        except Exception:
            finish_reason = "UNKNOWN"
        raise ValueError(
            f"Gemini {model_name} returned empty response "
            f"(finish_reason={finish_reason}). Check billing/quota and safety filters."
        )

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
    raw_text      = response.content[0].text if response.content else ""
    text          = _strip_code_fences(raw_text)
    input_tokens  = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    if not text:
        stop_reason = getattr(response, "stop_reason", "unknown")
        raise ValueError(
            f"Anthropic {model_name} returned empty response "
            f"(stop_reason={stop_reason}). Check API key credits and prompt safety."
        )

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

    text = _strip_code_fences(data["choices"][0]["message"]["content"] or "")
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
