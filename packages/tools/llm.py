"""
packages/tools/llm.py
LLM client — Anthropic Claude only.

Model assignment (June 2026):
  - Claude Sonnet 4.6       : Research Council, CEO, Engineering, Legal, QA critique
                              Anything that needs deep reasoning, code gen, or compliance analysis.
  - Claude Haiku 4.5        : All operational agents — VP, PM, Marketing, Growth, Security, Infra.
                              Fast structured output for pipeline throughput.

Retry strategy (Anthropic):
  - Transient errors (5xx, network) : retry up to 3×, exponential backoff 4 s → 60 s
  - 429 / quota                     : retry up to 3× with backoff (Anthropic limits are per-minute)
  - Empty response                  : raise ValueError

Credentials: set ANTHROPIC_API_KEY in Railway env vars.
  Get from: console.anthropic.com → API Keys
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

# ── Claude models ──────────────────────────────────────────────────────────────
_SONNET = "claude-sonnet-4-6"          # Deep reasoning, code gen, compliance
_HAIKU  = "claude-haiku-4-5-20251001"  # Fast structured ops


# ---------------------------------------------------------------------------
# Markdown code-fence stripper — applied to ALL LLM responses
# ---------------------------------------------------------------------------
_CODE_FENCE_RE = re.compile(
    r'^```(?:json|python|javascript|typescript|text|xml|yaml|markdown)?\s*\n?',
    re.MULTILINE,
)

def _strip_code_fences(text: str) -> str:
    """
    Remove markdown code fences LLMs add despite instructions.

      ```json\\n{...}\\n```  → {...}
      {... no fences ...}    → unchanged
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = _CODE_FENCE_RE.sub("", stripped, count=1)
    if stripped.endswith("```"):
        stripped = stripped[: stripped.rfind("```")].rstrip()
    return stripped.strip()


def extract_json(text: str) -> str:
    """
    Robustly extract a JSON object or array from LLM output.

    Handles:
      1. Clean JSON                    → returned as-is
      2. JSON inside ```json ... ```   → fences stripped
      3. Preamble text before JSON     → 'Here is the output: {...}' → '{...}'
      4. Preamble + fences             → both stripped
    """
    cleaned = _strip_code_fences(text.strip())
    if cleaned.startswith(("{", "[")):
        return cleaned
    first_brace   = cleaned.find("{")
    first_bracket = cleaned.find("[")
    candidates = [i for i in (first_brace, first_bracket) if i != -1]
    if not candidates:
        return cleaned
    return cleaned[min(candidates):]


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
# Lazy singleton
# ---------------------------------------------------------------------------
_anthropic_client: anthropic.AsyncAnthropic | None = None


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set")
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic_client


# ---------------------------------------------------------------------------
# Model registry — maps agent role → Claude model
# ---------------------------------------------------------------------------
MODEL_REGISTRY: dict[str, str] = {
    # ── Research Council — Sonnet ────────────────────────────────────────────
    # 5-scout parallel debate + synthesis; needs best multi-step reasoning.
    "KIMI_SCOUT_TREND":        _SONNET,
    "KIMI_SCOUT_COMPETITOR":   _SONNET,
    "KIMI_SCOUT_SKEPTIC":      _SONNET,
    "KIMI_SCOUT_AUDIENCE":     _SONNET,
    "KIMI_SCOUT_EXECUTION":    _SONNET,
    "KIMI_DEBATE_SYNTHESIZER": _SONNET,
    "KIMI_SCOUT_OPPORTUNITY":  _SONNET,  # legacy name compat

    # ── Governance — Sonnet ──────────────────────────────────────────────────
    # CEO makes the go/no-go venture decision — never downgrade this.
    # Legal requires strict instruction-following for compliance reasoning.
    "GRAND_CEO":       _SONNET,
    "LEGAL_AGENT":     _SONNET,
    "REVENUE_ENGINE":  _HAIKU,
    "CEO_NICHE_SCOUT": _HAIKU,

    # ── Engineering — Sonnet ─────────────────────────────────────────────────
    # Best React/TypeScript code generation.  Single most important quality gate.
    "ENGINEERING_TEAM": _SONNET,

    # ── QA critique — Sonnet ─────────────────────────────────────────────────
    # Code analysis and compliance critique need quality reasoning.
    "QA_TECHNICAL_CRITIQUE":  _SONNET,
    "QA_COMPLIANCE_CRITIQUE": _SONNET,
    "QA_AUDITOR_CRITIQUE":    _SONNET,  # legacy name compat

    # ── Product operational agents — Haiku ───────────────────────────────────
    # Fast structured output for planning artifacts.
    "PRODUCT_VP":      _HAIKU,
    "PRODUCT_MANAGER": _HAIKU,
    "PRODUCT_GROWTH":  _HAIKU,
    "MARKETING_SEO":   _HAIKU,

    # ── Media agents — Haiku (archived, kept for backward compat) ────────────
    "MEDIA_VP":           _HAIKU,
    "SCRIPT_AGENT":       _HAIKU,
    "SEO_METADATA_AGENT": _HAIKU,
    "THUMBNAIL_AGENT":    _HAIKU,
    "PUBLISHING_AGENT":   _HAIKU,
    "ANALYTICS_AGENT":    _HAIKU,
    "MEDIA_GROWTH":       _HAIKU,
    "VOICE_AGENT":        _HAIKU,
    "VIDEO_AGENT":        _HAIKU,

    # ── Security / Infra — Haiku ─────────────────────────────────────────────
    # Pattern matching and structured security ops; speed over reasoning depth.
    "SECURITY_AGENT":     _HAIKU,
    "ANTI_BAN_AGENT":     _HAIKU,
    "DEPLOYMENT_AGENT":   _HAIKU,
    "QA_TECHNICAL_GATE":  _HAIKU,
    "QA_COMPLIANCE_GATE": _HAIKU,
    "QA_AUDITOR_GATE":    _HAIKU,  # legacy name compat

    # ── Legacy backward compat ───────────────────────────────────────────────
    "PRODUCT_TEAM":    _HAIKU,
    "CONTENT_TEAM":    _HAIKU,
    "MARKETING_TEAM":  _HAIKU,
    "GLOBAL_TEAM":     _HAIKU,
    "GROWTH_TEAM":     _HAIKU,
    "DEPLOYMENT_TEAM": _HAIKU,
}


# ---------------------------------------------------------------------------
# Anthropic call with retry
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
# Public interface
# ---------------------------------------------------------------------------
async def call_llm(
    agent_role: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 8192,
    response_schema: Any | None = None,  # kept for call-site compat — ignored (use text prompts)
) -> LLMResponse:
    """
    Call the Claude model assigned to `agent_role`.
    Unknown roles fall back to Haiku (fast + cheap).
    `response_schema` is accepted but unused — all JSON extraction uses text prompts.
    """
    model_name = MODEL_REGISTRY.get(agent_role, _HAIKU)
    return await _call_anthropic(model_name, system_prompt, user_prompt,
                                  temperature, max_tokens)


async def classify(prompt: str, choices: list[str]) -> str:
    """
    Classify `prompt` into one of `choices` using Claude Haiku.
    Returns the first matching choice, or choices[0] on failure.
    """
    system = f"Respond ONLY with one of these exact options (no other text): {', '.join(choices)}"
    try:
        resp = await _call_anthropic(_HAIKU, system, prompt, temperature=0.0, max_tokens=32)
        result = resp.text.strip()
        for c in choices:
            if c.lower() in result.lower():
                return c
    except Exception:
        pass
    return choices[0]
