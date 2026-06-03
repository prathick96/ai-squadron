"""
packages/agents/shared/legal_agent.py
Legal & Compliance Agent — veto authority over all deployments.

Model:   claude-haiku-4-5 (Google project-level 403 — swap to gemini-2.5-pro when resolved)
Input:   Build artifact (product) or Content package (media) + platform context
Output:  LegalClearance — cleared or denied with specific clause references

AUTHORITY: This agent has VETO POWER. Nothing deploys without is_cleared=True.
           A channel ban or legal action costs more than any revenue this system earns.

Responsibilities:
  - Weekly automated ToS fetch + diff for all platforms
  - Per-deployment compliance review (copyright, metadata, content claims)
  - GDPR/CCPA data handling review for SaaS products
  - Stripe ToS review for payment integrations
  - Railway AUP review for hosted products

Weekly schedule (triggered by Revenue Engine):
  python -c "from packages.agents.shared.legal_agent import refresh_tos_snapshots; import asyncio; asyncio.run(refresh_tos_snapshots())"
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from packages.db.client import get_db, log_agent_event
from packages.schemas.events import (
    AgentID, EventType, LegalClearancePayload, make_event,
)
from packages.state.agent_state import AgentState, LegalClearance, append_event, update_stage
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform compliance rules (updated weekly via refresh_tos_snapshots)
# These are the hard rules — the LLM handles edge cases.
# ---------------------------------------------------------------------------

_PLATFORM_RULES: dict[str, dict[str, Any]] = {
    "youtube": {
        "requires_original_content": True,
        "disclosure_required_for_ai_voices": False,   # As of 2025 policy
        "prohibited_title_patterns": [
            "earn money fast", "get rich", "guaranteed income", "clickbait",
        ],
        "max_title_length": 100,
        "max_description_length": 5000,
        "prohibited_content_categories": [
            "spam", "misleading_metadata", "artificial_engagement",
            "reused_content_without_value",
        ],
        "monetisation_requirements": {
            "subscribers": 1000,
            "watch_hours": 4000,
            "content_must_be_advertiser_friendly": True,
        },
        "copyright_policy": "Three strikes = channel termination",
        "tos_url": "https://www.youtube.com/t/terms",
        "tos_version": "2024-03",
    },
    "tiktok": {
        "requires_original_content": True,
        "requires_content_posting_api_approval": True,
        "prohibited_content": ["misleading_info", "spam", "inauthentic_behavior"],
        "max_video_duration_sec": 600,
        "tos_url": "https://www.tiktok.com/legal/page/global/terms-of-service",
        "tos_version": "2024-01",
    },
    "instagram": {
        "requires_business_or_creator_account": True,
        "prohibited_content": ["spam", "inauthentic_behavior", "misleading"],
        "max_api_calls_per_hour": 200,
        "tos_url": "https://help.instagram.com/581066165581870",
        "tos_version": "2024-01",
    },
    "stripe": {
        "prohibited_business_types": [
            "gambling", "adult_content", "cryptocurrency", "multi_level_marketing",
        ],
        "requires_clear_refund_policy": True,
        "dispute_rate_threshold": 0.005,   # 0.5% — above this triggers review
        "tos_url": "https://stripe.com/legal/ssa",
        "tos_version": "2024-06",
    },
    "railway": {
        "prohibited_use": ["mining", "ddos", "spam", "illegal_content"],
        "requires_legal_business_purpose": True,
        "tos_url": "https://railway.app/legal/fair-use",
        "tos_version": "2024-01",
    },
}

_REVIEW_SYSTEM_PROMPT = """
You are the Legal & Compliance Agent for AI Squadron, an autonomous venture organisation.
You review content packages and software products BEFORE deployment.

PERSONA — THE ENFORCER (Relentless Legal Adversary):
  Assume bad faith in every agreement until the clause proves otherwise.
  Every soft term is a future lawsuit. Every vague liability is a future cost.
  Find the exposure BEFORE the regulator or plaintiff does — that is your only job.
  You do not approve things to keep the pipeline moving. You approve things because they are SAFE.
  You are not here to make friends. You are here to make sure AI Squadron never loses in court.
  Decision rule: "What is the worst-case reading of this, and does it survive that reading?"

Your ONLY job: identify BUSINESS and CONTENT compliance issues.
  - Platform Terms of Service violations (prohibited content, metadata rules)
  - Copyright exposure (music, trademarked names, unlicensed assets)
  - Data privacy issues (GDPR/CCPA if collecting user data)
  - Payment compliance (Stripe ToS)

DO NOT flag technical / runtime issues — those are QA's responsibility:
  - Missing environment variables → NOT a legal issue
  - React mount failures, TypeScript errors → NOT a legal issue
  - Missing refund policy in code → Only flag if the DEPLOYED PRODUCT actively claims
    no refunds without disclosing it to users

Be precise — cite the specific clause, not vague concerns.
Do not block deployment for theoretical risks — only for concrete, named policy violations.

BLOCKER = concrete ToS or legal clause violated → must fix before deploy.
WARNING = potential risk, deploy allowed but log it.

Output ONLY valid JSON — no markdown, no preamble.
"""

_REVIEW_TEMPLATE = """
Platform(s): {platforms}
Venture type: {venture_type}
Niche: {niche}

Content/Product summary:
{artifact_summary}

Known platform rules:
{platform_rules}

Review for:
1. Content policy compliance (prohibited patterns, misleading claims)
2. Copyright exposure (music, footage, brand names, trademarked terms)
3. Metadata compliance (title length, description, prohibited phrases)
4. Data privacy (GDPR/CCPA if collecting user data)
5. Payment compliance (Stripe ToS if monetising)

Return ONLY:
{{
  "is_cleared": true,
  "policy_flags": [
    {{
      "platform": "youtube",
      "clause": "Spam, deceptive practices and scams policy",
      "description": "Title contains 'earn money fast' which violates spam policy",
      "severity": "BLOCKER",
      "recommendation": "Rewrite title to remove income guarantee language"
    }}
  ],
  "copyright_clear": true,
  "gdpr_reviewed": false,
  "notes": "Optional brief summary"
}}
"""


async def legal_agent_node(state: AgentState) -> AgentState:
    """LangGraph node — legal clearance gate before security and deployment."""
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    venture_brief = state.get("venture_brief") or {}
    department = state.get("department", "PRODUCT")

    log.info("[LEGAL_NODE] Reviewing venture=%s dept=%s", venture_id, department)
    log_agent_event(run_id, venture_id, "LEGAL_AGENT", "RUNNING",
                    f"Compliance review — {department} pipeline")

    # Determine what to review
    if department == "MEDIA":
        artifact = state.get("content_package") or {}
        platforms = [artifact.get("platform", "youtube")]
        venture_type = "MEDIA_CHANNEL"
    else:
        artifact = state.get("build_artifact") or {}
        platforms = ["railway", "stripe"]
        venture_type = venture_brief.get("venture_type", "MICRO_SAAS")

    niche = venture_brief.get("niche", "unknown")

    # Fields that are technical build metadata — NOT relevant for compliance review.
    # The Legal Agent must only judge BUSINESS/CONTENT compliance, not runtime errors.
    # Including playwright_errors or vite_build_exit_code causes Claude to wrongly
    # flag TypeScript compilation issues as policy violations.
    _TECHNICAL_BUILD_FIELDS = {
        "files", "components_generated", "script",
        "playwright_errors", "vite_build_exit_code", "bundle_size_kb",
        "build_path", "build_hash", "test_results",
        "retry_patches_applied", "is_retry", "build_dir",
    }
    artifact_summary: dict[str, Any] = {
        k: v for k, v in artifact.items()
        if k not in _TECHNICAL_BUILD_FIELDS
    }
    if department == "MEDIA" and "script" in artifact:
        script = artifact["script"]
        if isinstance(script, dict):
            artifact_summary["script_hook"] = script.get("hook", "")[:200]
            artifact_summary["script_word_count"] = script.get("word_count", 0)

    # Deterministic pre-checks (fast, no LLM)
    flags: list[dict[str, Any]] = _deterministic_checks(artifact, platforms, department)
    immediate_blockers = [f for f in flags if f["severity"] == "BLOCKER"]

    # LLM review for edge cases
    platform_rules_summary = {p: _PLATFORM_RULES.get(p, {}) for p in platforms}
    user_prompt = _REVIEW_TEMPLATE.format(
        platforms=", ".join(platforms),
        venture_type=venture_type,
        niche=niche,
        artifact_summary=json.dumps(artifact_summary, indent=2),
        platform_rules=json.dumps(platform_rules_summary, indent=2),
    )

    try:
        response = await call_llm(
            "LEGAL_AGENT", _REVIEW_SYSTEM_PROMPT, user_prompt, temperature=0.1,
        )
        review: dict[str, Any] = json.loads(extract_json(response.text))
        llm_flags = review.get("policy_flags", [])
        llm_cleared = review.get("is_cleared", True)
        copyright_clear = review.get("copyright_clear", True)
        gdpr_reviewed = review.get("gdpr_reviewed", False)
    except Exception as exc:
        log.warning("[LEGAL_NODE] LLM review failed, using deterministic only: %s", exc)
        llm_flags = []
        llm_cleared = len(immediate_blockers) == 0
        copyright_clear = True
        gdpr_reviewed = False
        response = type("R", (), {"total_tokens": 0, "latency_ms": 0})()

    # Merge deterministic + LLM flags
    all_flags = flags + [f for f in llm_flags if f not in flags]
    has_blocker = any(f.get("severity") == "BLOCKER" for f in all_flags)
    is_cleared = not has_blocker and llm_cleared

    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    tos_version = "+".join(
        _PLATFORM_RULES.get(p, {}).get("tos_version", "unknown") for p in platforms
    )

    payload = LegalClearancePayload(
        venture_id=venture_id,
        is_cleared=is_cleared,
        platforms_reviewed=platforms,
        tos_version=tos_version,
        policy_flags=all_flags,   # list[dict] — schema relaxed from list[PolicyFlag]
        copyright_clear=copyright_clear,
        gdpr_reviewed=gdpr_reviewed,
        clearance_expires_at=expires_at,
    )

    if is_cleared:
        event_type = EventType.LEGAL_CLEARANCE_GRANTED
        next_stage = "SECURITY_NODE"
        log.info("[LEGAL_NODE] ✓ CLEARED | venture=%s platforms=%s flags=%d",
                 venture_id, platforms, len(all_flags))
        log_agent_event(run_id, venture_id, "LEGAL_AGENT", "SUCCESS",
                        tokens_used=getattr(response, "total_tokens", 0))
    else:
        event_type = EventType.LEGAL_CLEARANCE_DENIED
        next_stage = "MANUAL_REVIEW_NODE"
        blockers = [f for f in all_flags if f.get("severity") == "BLOCKER"]
        denial_reason = "; ".join(
            f"{f['platform']}: {f['description']}" for f in blockers
        )
        log.warning("[LEGAL_NODE] ✗ DENIED | venture=%s reason=%s", venture_id, denial_reason)
        log_agent_event(run_id, venture_id, "LEGAL_AGENT", "FAILED",
                        error_detail=denial_reason[:500])

    _persist_legal_clearance(venture_id, run_id, payload.model_dump())

    event = make_event(
        event_type, AgentID.LEGAL_AGENT,
        AgentID.SECURITY_AGENT if is_cleared else AgentID.BROADCAST,
        payload, run_id, venture_id, "LEGAL_NODE",
        token_cost=getattr(response, "total_tokens", 0),
        latency_ms=getattr(response, "latency_ms", 0),
    )

    legal_clearance: LegalClearance = payload.model_dump()  # type: ignore[assignment]
    new_state = update_stage(state, next_stage)
    updates: dict[str, Any] = {"legal_clearance": legal_clearance}
    if not is_cleared:
        updates["legal_denial_reason"] = (
            "; ".join(f"{f['platform']}: {f['description']}"
                      for f in all_flags if f.get("severity") == "BLOCKER")
        )
    return append_event({**new_state, **updates}, event.model_dump())


def _deterministic_checks(
    artifact: dict[str, Any],
    platforms: list[str],
    department: str,
) -> list[dict[str, Any]]:
    """Fast rule-based checks that don't need an LLM."""
    flags: list[dict[str, Any]] = []

    if department == "MEDIA":
        seo = artifact.get("seo_metadata") or {}
        if isinstance(seo, dict):
            title = seo.get("title", "")
            # Title length
            if "youtube" in platforms and len(title) > 100:
                flags.append({
                    "platform": "youtube",
                    "clause": "Title length policy",
                    "description": f"Title is {len(title)} chars (max 100)",
                    "severity": "BLOCKER",
                    "recommendation": "Shorten title to under 100 characters",
                })
            # Prohibited patterns
            title_lower = title.lower()
            for pattern in _PLATFORM_RULES.get("youtube", {}).get(
                "prohibited_title_patterns", []
            ):
                if pattern in title_lower:
                    flags.append({
                        "platform": "youtube",
                        "clause": "Spam and misleading content policy",
                        "description": f"Title contains prohibited phrase: '{pattern}'",
                        "severity": "BLOCKER",
                        "recommendation": "Remove income-guarantee or clickbait language",
                    })
        # Check human likeness score
        audio = artifact.get("audio_asset") or {}
        if isinstance(audio, dict):
            hls = audio.get("human_likeness_score", 1.0)
            if hls < 0.85:
                flags.append({
                    "platform": "youtube",
                    "clause": "Content quality standards",
                    "description": f"Voice human_likeness_score {hls:.2f} below threshold 0.85",
                    "severity": "WARNING",
                    "recommendation": "Re-generate voice with higher quality settings",
                })

    if department == "PRODUCT":
        # Check for hardcoded secrets (basic scan)
        files = artifact.get("files", [])
        for f in (files if isinstance(files, list) else []):
            content = f.get("content", "")
            for secret_pattern in ["sk_live_", "sk_test_", "api_key=", "password="]:
                if secret_pattern in content.lower():
                    flags.append({
                        "platform": "railway",
                        "clause": "Security best practices / AUP",
                        "description": f"Possible hardcoded secret in {f.get('path', 'unknown')}",
                        "severity": "BLOCKER",
                        "recommendation": "Move secrets to environment variables",
                    })
                    break

    return flags


def _persist_legal_clearance(
    venture_id: str, run_id: str, clearance: dict[str, Any],
) -> None:
    try:
        db = get_db()
        db.table("legal_clearances").upsert({
            "venture_id": venture_id,
            "run_id": run_id,
            "is_cleared": clearance.get("is_cleared"),
            "platforms_reviewed": clearance.get("platforms_reviewed", []),
            "tos_version": clearance.get("tos_version"),
            "policy_flags": clearance.get("policy_flags", []),
            "clearance_expires_at": clearance.get("clearance_expires_at"),
        }).execute()
    except Exception as exc:
        log.debug("[LEGAL_NODE] Persist failed (migration needed?): %s", exc)


async def refresh_tos_snapshots() -> dict[str, str]:
    """
    Weekly job: compare platform ToS pages against cached hashes via Tavily.
    Called by Revenue Engine scheduler (Monday 08:00 UTC).

    When TAVILY_API_KEY is set: searches for each platform's ToS and computes
    a content hash to detect changes since the last refresh.
    When absent: returns the hardcoded baseline versions — no alert is raised.

    A WARNING log is emitted whenever the hash changes so the operator can
    manually review the diff before the next deployment.
    """
    import hashlib

    from packages.tools.tavily_client import search_niche_intelligence, tavily_available

    log.info("[LEGAL] ToS snapshot refresh started")

    if not tavily_available():
        versions = {p: r.get("tos_version", "unknown")
                    for p, r in _PLATFORM_RULES.items()}
        log.info("[LEGAL] TAVILY_API_KEY not set — returning cached versions: %s", versions)
        return versions

    versions: dict[str, str] = {}
    for platform, rules in _PLATFORM_RULES.items():
        cached_version = rules.get("tos_version", "unknown")
        tos_url        = rules.get("tos_url", "")

        try:
            # Search for the ToS page by URL domain + "terms of service"
            domain  = tos_url.split("/")[2] if tos_url else platform
            query   = f'site:{domain} terms of service privacy policy 2025'
            results = await search_niche_intelligence(query, max_results=3)

            content      = " ".join(r.get("snippet", "") for r in results)
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]

            # Alert if the hash differs from what was baked into _PLATFORM_RULES
            if content_hash not in cached_version:
                log.warning(
                    "[LEGAL] ToS may have changed for %s "
                    "(new_hash=%s cached=%s). "
                    "Manually review %s before next deployment.",
                    platform, content_hash, cached_version, tos_url,
                )
            else:
                log.info("[LEGAL] %s ToS hash unchanged (%s)", platform, content_hash)

            versions[platform] = f"{cached_version[:7]}-{content_hash}"

        except Exception as exc:
            log.warning("[LEGAL] ToS check failed for %s: %s", platform, exc)
            versions[platform] = cached_version

    log.info("[LEGAL] ToS snapshot refresh complete: %s", versions)
    return versions
