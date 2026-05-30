"""
packages/schemas/events.py
Pydantic v2 models for every JSON event on the bus.
All inter-agent messages must conform to EventEnvelope.
Payload models enforce the contract defined in the Agent Spec.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Event Type Registry
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    # ── Research & CEO ──────────────────────────────────────────
    RESEARCH_DOSSIER_READY       = "RESEARCH_DOSSIER_READY"
    VENTURE_BRIEF_READY          = "VENTURE_BRIEF_READY"
    # ── Department routing ──────────────────────────────────────
    PRODUCT_VP_BRIEFED           = "PRODUCT_VP_BRIEFED"
    MEDIA_VP_BRIEFED             = "MEDIA_VP_BRIEFED"
    # ── Product pipeline ────────────────────────────────────────
    TECH_SPEC_READY              = "TECH_SPEC_READY"
    BUILD_COMPLETE               = "BUILD_COMPLETE"
    # ── Media pipeline ──────────────────────────────────────────
    SCRIPT_READY                 = "SCRIPT_READY"
    VOICE_READY                  = "VOICE_READY"
    VIDEO_READY                  = "VIDEO_READY"
    THUMBNAIL_READY              = "THUMBNAIL_READY"
    CONTENT_PACKAGE_READY        = "CONTENT_PACKAGE_READY"
    CONTENT_PUBLISHED            = "CONTENT_PUBLISHED"
    ANALYTICS_UPDATED            = "ANALYTICS_UPDATED"
    # ── Shared QA ───────────────────────────────────────────────
    QA_PASSED                    = "QA_PASSED"
    QA_FAILED                    = "QA_FAILED"
    # ── Legal (new — veto authority) ────────────────────────────
    LEGAL_CLEARANCE_GRANTED      = "LEGAL_CLEARANCE_GRANTED"
    LEGAL_CLEARANCE_DENIED       = "LEGAL_CLEARANCE_DENIED"
    # ── Security ────────────────────────────────────────────────
    SECURITY_CLEARANCE_GRANTED   = "SECURITY_CLEARANCE_GRANTED"
    SECURITY_VIOLATION_DETECTED  = "SECURITY_VIOLATION_DETECTED"
    ACCOUNTS_PROVISIONED         = "ACCOUNTS_PROVISIONED"
    # ── Deployment & growth ─────────────────────────────────────
    DEPLOYMENT_COMPLETE          = "DEPLOYMENT_COMPLETE"
    CAMPAIGN_LAUNCHED            = "CAMPAIGN_LAUNCHED"
    LOCALIZATION_COMPLETE        = "LOCALIZATION_COMPLETE"
    GROWTH_REPORT_READY          = "GROWTH_REPORT_READY"
    TREND_ANALYSIS_READY         = "TREND_ANALYSIS_READY"
    # ── Revenue engine ──────────────────────────────────────────
    REVENUE_SCALE_SIGNAL         = "REVENUE_SCALE_SIGNAL"
    REVENUE_KILL_SIGNAL          = "REVENUE_KILL_SIGNAL"
    # ── Manual escalation ───────────────────────────────────────
    MANUAL_REVIEW_REQUIRED       = "MANUAL_REVIEW_REQUIRED"


class Priority(str, Enum):
    LOW      = "LOW"
    NORMAL   = "NORMAL"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class AgentID(str, Enum):
    # ── Governance ──────────────────────────────────────────────
    GRAND_CEO              = "GRAND_CEO"
    RESEARCH_COUNCIL       = "RESEARCH_COUNCIL"
    # ── Product department ──────────────────────────────────────
    PRODUCT_VP             = "PRODUCT_VP"
    PRODUCT_MANAGER        = "PRODUCT_MANAGER"
    ENGINEERING_TEAM       = "ENGINEERING_TEAM"
    QA_TECHNICAL           = "QA_TECHNICAL"
    DEPLOYMENT_AGENT       = "DEPLOYMENT_AGENT"
    MARKETING_SEO          = "MARKETING_SEO"
    PRODUCT_GROWTH         = "PRODUCT_GROWTH"
    # ── Media department ────────────────────────────────────────
    MEDIA_VP               = "MEDIA_VP"
    SCRIPT_AGENT           = "SCRIPT_AGENT"
    VOICE_AGENT            = "VOICE_AGENT"
    VIDEO_AGENT            = "VIDEO_AGENT"
    THUMBNAIL_AGENT        = "THUMBNAIL_AGENT"
    SEO_METADATA_AGENT     = "SEO_METADATA_AGENT"
    QA_COMPLIANCE          = "QA_COMPLIANCE"
    PUBLISHING_AGENT       = "PUBLISHING_AGENT"
    ANALYTICS_AGENT        = "ANALYTICS_AGENT"
    MEDIA_GROWTH           = "MEDIA_GROWTH"
    # ── Shared / Legal / Security ────────────────────────────────
    LEGAL_AGENT            = "LEGAL_AGENT"
    SECURITY_AGENT         = "SECURITY_AGENT"
    ANTI_BAN_AGENT         = "ANTI_BAN_AGENT"
    CREDENTIAL_GUARDIAN    = "CREDENTIAL_GUARDIAN"
    ACCOUNT_DISTRIBUTION   = "ACCOUNT_DISTRIBUTION"
    # ── System ──────────────────────────────────────────────────
    REVENUE_ENGINE         = "REVENUE_ENGINE"
    BROADCAST              = "BROADCAST"
    ORCHESTRATOR           = "ORCHESTRATOR"
    # ── Legacy aliases (kept for backward compatibility) ─────────
    MARKET_RESEARCH_TEAM   = "MARKET_RESEARCH_TEAM"
    CEO_NICHE_SCOUT        = "CEO_NICHE_SCOUT"
    PRODUCT_TEAM           = "PRODUCT_TEAM"
    CONTENT_TEAM           = "CONTENT_TEAM"
    QA_AUDITOR             = "QA_AUDITOR"
    DEPLOYMENT_TEAM        = "DEPLOYMENT_TEAM"
    MARKETING_TEAM         = "MARKETING_TEAM"
    GLOBAL_TEAM            = "GLOBAL_TEAM"
    GROWTH_TEAM            = "GROWTH_TEAM"


# ---------------------------------------------------------------------------
# Event Metadata
# ---------------------------------------------------------------------------

class EventMetadata(BaseModel):
    run_id: str
    venture_id: str
    pipeline_stage: str
    token_cost: int = 0
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# Master Envelope — every bus message conforms to this
# ---------------------------------------------------------------------------

class EventEnvelope(BaseModel):
    event_id: str             = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    schema_version: str       = "1.0.0"
    source_agent: AgentID
    target_agent: AgentID
    correlation_id: str       = Field(default_factory=lambda: str(uuid.uuid4()))
    priority: Priority        = Priority.NORMAL
    timestamp: str            = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    retry_count: int          = 0
    payload: dict[str, Any]   = Field(default_factory=dict)
    metadata: EventMetadata

    def to_bus_dict(self) -> dict[str, Any]:
        """
        Serialise for the event bus (Redis XADD or asyncio.Queue).
        Enums are serialised to their .value string. Dicts/lists go through
        json.dumps so they survive the string-only Redis Streams wire format.
        """
        import json

        # model_dump(mode="json") converts enums → their values automatically
        d = self.model_dump(mode="json")
        return {
            k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            for k, v in d.items()
        }

    @classmethod
    def from_bus_dict(cls, raw: dict[str, Any]) -> "EventEnvelope":
        """
        Deserialise from bus dict (Redis XREAD fields or local queue item).
        Handles both already-parsed dicts and JSON-string values.
        """
        import json

        parsed: dict[str, Any] = {}
        for k, v in raw.items():
            if isinstance(v, (dict, list)):
                # Already a Python object (local queue path)
                parsed[k] = v
            else:
                try:
                    parsed[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    parsed[k] = v
        return cls.model_validate(parsed)


# ---------------------------------------------------------------------------
# Payload Models — one per EventType
# ---------------------------------------------------------------------------

class Competitor(BaseModel):
    name: str
    weakness: str
    moat_gap: str


class NicheCandidate(BaseModel):
    niche: str
    venture_type: Literal["MICRO_SAAS", "MEDIA_CHANNEL", "AFFILIATE_SITE"]
    score: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = []
    risks: list[str] = []


class ScoutReport(BaseModel):
    scout_role: Literal["opportunity", "skeptic", "execution"]
    niche_candidates: list[NicheCandidate] = []
    top_pick: str
    rationale: str
    error: str | None = None


class DebateDisagreement(BaseModel):
    topic: str
    positions: dict[str, str] = Field(default_factory=dict)


class DebateSummary(BaseModel):
    consensus_niches: list[str] = []
    disagreements: list[DebateDisagreement | dict[str, Any]] = []
    recommended_primary_niche: str
    recommended_venture_type: Literal["MICRO_SAAS", "MEDIA_CHANNEL", "AFFILIATE_SITE"]
    council_confidence: float = Field(ge=0.0, le=1.0)
    synthesis: str
    evidence_gaps: list[str] = []


class ResearchDossierPayload(BaseModel):
    venture_id: str
    trend_snapshot: dict[str, Any] = Field(default_factory=dict)
    scout_reports: list[dict[str, Any]] = []
    debate_summary: dict[str, Any] = Field(default_factory=dict)
    recommended_primary_niche: str
    recommended_venture_type: Literal["MICRO_SAAS", "MEDIA_CHANNEL", "AFFILIATE_SITE"]
    consensus_niches: list[str] = []
    disagreements: list[dict[str, Any]] = []
    council_confidence: float = Field(ge=0.0, le=1.0)
    research_mode: Literal["kimi_live", "kimi_openrouter", "mock"] = "mock"


class VentureBriefPayload(BaseModel):
    venture_id: str
    venture_type: Literal["MICRO_SAAS", "MEDIA_CHANNEL", "AFFILIATE_SITE"] = "MICRO_SAAS"
    niche: str = ""
    target_region: list[str] = []
    target_audience: str = ""
    rpm_estimate_usd: float = 0.0
    competition_score: float = Field(default=0.5, ge=0.0, le=1.0)
    feasibility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    tam_usd_millions: float = 0.0
    top_competitors: list[dict[str, Any]] = []  # was list[Competitor] — too strict for LLM
    recommended_monetization: list[str] = []
    content_angles: list[str] = []
    go_decision: bool = False
    go_rationale: str = ""
    department: str = "PRODUCT"  # added by CEO; optional for backward compat


class StackSpec(BaseModel):
    frontend: str  = "React 19 + Vite"
    backend: str   = "Python FastAPI"
    database: str  = "PostgreSQL"
    auth: str      = "Supabase Auth"
    hosting: str   = "Railway"


class Feature(BaseModel):
    feature_id: str
    name: str
    priority: Literal["P0", "P1", "P2"]
    user_story: str
    acceptance_criteria: list[str]
    estimated_components: list[str]


class TechSpecPayload(BaseModel):
    venture_id: str
    product_type: Literal["MICRO_SAAS", "MEDIA_CHANNEL", "AFFILIATE_SITE"] = "MICRO_SAAS"
    stack: StackSpec = Field(default_factory=StackSpec)
    # list[dict[str, Any]] — LLMs return booleans/objects inside routes (auth_required, request_body)
    features: list[dict[str, Any]] = []
    data_models: dict[str, Any] = {}
    api_routes: list[dict[str, Any]] = []
    environment_variables: list[str] = []
    estimated_build_tokens: int = 0
    component_count: int = 0
    complexity: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class TestResults(BaseModel):
    total: int
    passed: int
    failed: int
    coverage_pct: float


class BuildCompletePayload(BaseModel):
    venture_id: str
    build_path: str
    build_hash: str
    components_generated: list[str]
    test_results: TestResults
    vite_build_exit_code: int
    bundle_size_kb: int
    dependencies: list[str]
    is_retry: bool = False
    retry_patches_applied: list[str] = []


class VoiceReadyPayload(BaseModel):
    venture_id: str = ""
    duration_sec: float = 0.0
    voice_model: str = ""
    human_likeness_score: float = 0.0
    provider: str = "ElevenLabs"


class VideoReadyPayload(BaseModel):
    venture_id: str = ""
    duration_sec: float = 0.0
    resolution: str = "1920x1080"
    size_mb: float = 0.0
    provider: str = "FFmpeg"


class AudioAsset(BaseModel):
    file_path: str
    duration_sec: float
    voice_model: str
    human_likeness_score: float = Field(ge=0.0, le=1.0)


class VideoAsset(BaseModel):
    file_path: str
    resolution: str
    duration_sec: float
    has_captions: bool


class ThumbnailAsset(BaseModel):
    file_path: str
    resolution: str


class ScriptSpec(BaseModel):
    hook: str
    body_sections: list[str]
    word_count: int
    estimated_duration_sec: int


class SeoMetadata(BaseModel):
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]


class ContentPackagePayload(BaseModel):
    venture_id: str
    platform: Literal["youtube", "tiktok", "instagram", "x"]
    content_type: Literal["short_form", "long_form"]
    script: ScriptSpec
    audio_asset: AudioAsset
    video_asset: VideoAsset
    thumbnail_asset: ThumbnailAsset
    seo_metadata: SeoMetadata
    is_retry: bool = False


class QACheckError(BaseModel):
    check: str = ""
    severity: str = "CRITICAL"   # was Literal — LLM may use non-standard values
    component: str = "Unknown"
    error_type: str = "VALIDATION_FAILED"
    stack_trace: str | None = None
    fix_directive: str = ""


class CritiqueLog(BaseModel):
    failed_checks: list[str] = []
    errors: list[dict[str, Any]] = []   # was list[QACheckError] — accept raw LLM dicts


class QAPassedPayload(BaseModel):
    venture_id: str
    artifact_type: Literal["BUILD", "CONTENT"]
    is_passed: bool = True
    checks_run: list[str]
    checks_passed: int
    checks_failed: int
    qa_report_path: str


class QAFailedPayload(BaseModel):
    venture_id: str
    artifact_type: Literal["BUILD", "CONTENT"]
    is_passed: bool = False
    retry_count: int
    max_retries: int
    qa_target: Literal["engineering", "content"]
    critique_log: CritiqueLog


class TosStatus(BaseModel):
    compliant: bool
    last_checked: str
    flagged_items: list[str] = []


class PostingWindow(BaseModel):
    post_time_utc: str
    jitter_minutes: int
    frequency: str


class SecurityClearancePayload(BaseModel):
    venture_id: str
    platform_accounts: dict[str, dict[str, str]] = {}
    tos_compliance_snapshot: dict[str, TosStatus] = {}
    posting_schedule: dict[str, PostingWindow] = {}
    clearance_valid_until: str
    is_compliant: bool = True


class PlatformAccountEntry(BaseModel):
    platform: str
    account_handle: str
    oauth_token_ref: str
    max_posts_today: int
    min_hours_between_posts: int
    target_regions: list[str] = []


class AccountProvisionedPayload(BaseModel):
    venture_id: str
    accounts: list[PlatformAccountEntry]
    policy_version: str = "1.0.0"


class SecurityViolationPayload(BaseModel):
    venture_id: str
    platform: str
    violation_type: Literal[
        "SHADOWBAN_DETECTED", "TOS_UPDATED", "RATE_LIMIT_HIT", "ACCOUNT_FLAGGED"
    ]
    evidence: dict[str, Any]
    recommended_action: str
    auto_action_taken: str
    resume_at: str


class DeploymentEntry(BaseModel):
    type: Literal["SAAS", "MEDIA"]
    platform: str
    url: str
    deployment_id: str | None = None
    video_id: str | None = None
    deployed_at: str
    smoke_test_passed: bool = False


class DeploymentCompletePayload(BaseModel):
    venture_id: str
    deployments: list[DeploymentEntry]
    post_deployment_status: Literal["LIVE", "FAILED", "PARTIAL"]


class CampaignEntry(BaseModel):
    type: str
    pages_generated: int | None = None
    target_keywords: list[str] = []
    sitemap_submitted: bool | None = None
    source: str | None = None
    distributed_to: list[str] = []
    posts_created: int | None = None
    sequence_id: str | None = None
    trigger: str | None = None
    emails_in_sequence: int | None = None


class CampaignLaunchedPayload(BaseModel):
    venture_id: str
    campaigns: list[CampaignEntry]
    tracking_params: dict[str, str]


class LocalizationEntry(BaseModel):
    region: str
    language: str
    platform: str
    adapted_title: str
    adapted_description: str | None = None
    post_time_local: str
    thumbnail_variant: str | None = None
    deployment_status: Literal["LIVE", "SCHEDULED", "FAILED"]
    video_id: str | None = None


class LocalizationCompletePayload(BaseModel):
    venture_id: str
    localizations: list[LocalizationEntry]
    regions_covered: list[str]
    estimated_incremental_reach: int


class VenturePerformance(BaseModel):
    venture_id: str
    mrr_usd: float
    growth_rate_mom: float
    primary_channel: str
    winning_content_angle: str | None = None
    signal: Literal["SCALE", "HOLD", "KILL"]
    kill_rationale: str | None = None


class PortfolioSummary(BaseModel):
    total_ventures: int
    live_ventures: int
    total_mrr_usd: float
    total_burn_usd: float
    net_mrr_usd: float


class GrowthReportPayload(BaseModel):
    report_period: str
    portfolio_summary: PortfolioSummary
    top_performers: list[VenturePerformance]
    bottom_performers: list[VenturePerformance]
    niche_recalibration: dict[str, list[str]]
    winning_content_formats: dict[str, str]


class RevenueScalePayload(BaseModel):
    trigger_venture_id: str
    trigger_mrr_usd: float
    scale_directive: str
    budget_allocated_usd: float = 0.0
    target_mrr_per_variant_usd: float
    deadline_days: int


class RevenueKillPayload(BaseModel):
    venture_id: str
    kill_reason: str
    mrr_at_kill_usd: float
    threshold_usd: float
    days_live: int
    decommission_actions: list[str]
    niche_blacklisted: bool = True


class ManualReviewPayload(BaseModel):
    venture_id: str
    run_id: str
    review_reason: str
    artifact_type: Literal["BUILD", "CONTENT"]
    retry_count: int
    critique_log: CritiqueLog | None = None


# ---------------------------------------------------------------------------
# Two-department routing payloads (new)
# ---------------------------------------------------------------------------

class ProductVPBriefPayload(BaseModel):
    venture_id: str
    department: str = "PRODUCT"
    strategy_memo: dict = {}
    approved_budget_usd: float = 500.0


class MediaVPBriefPayload(BaseModel):
    venture_id: str
    department: str = "MEDIA"
    strategy_memo: dict = {}
    approved_budget_usd: float = 200.0


# ---------------------------------------------------------------------------
# Media pipeline stage payloads (new)
# ---------------------------------------------------------------------------

class ScriptPayload(BaseModel):
    venture_id: str
    platform: Literal["youtube", "tiktok", "instagram", "x"]
    content_angle: str
    hook: str
    body_sections: list[str]
    cta: str
    word_count: int
    estimated_duration_sec: int
    hook_variants: list[str] = []


class VoicePayload(BaseModel):
    venture_id: str
    audio_file_path: str
    duration_sec: float
    voice_id: str
    human_likeness_score: float
    provider: Literal["elevenlabs", "xtts", "mock"] = "mock"


class VideoPayload(BaseModel):
    venture_id: str
    video_file_path: str
    resolution: str
    duration_sec: float
    has_captions: bool
    caption_file_path: str | None = None
    provider: Literal["remotion", "ffmpeg", "mock"] = "mock"


class ThumbnailPayload(BaseModel):
    venture_id: str
    variants: list[str]          # list of file paths (A/B/C variants)
    selected_variant: str | None = None
    provider: Literal["flux", "sdxl", "mock"] = "mock"


class PublishingResultPayload(BaseModel):
    venture_id: str
    platform: str
    published_url: str
    video_id: str | None = None
    scheduled_at: str | None = None
    status: Literal["LIVE", "SCHEDULED", "FAILED"]


class AnalyticsPayload(BaseModel):
    venture_id: str
    platform: str
    period: str
    views: int = 0
    watch_time_hours: float = 0.0
    ctr_pct: float = 0.0
    subscribers_gained: int = 0
    revenue_usd: float = 0.0
    top_content_angle: str | None = None


# ---------------------------------------------------------------------------
# Legal clearance payload (new — veto authority)
# ---------------------------------------------------------------------------

class PolicyFlag(BaseModel):
    platform: str = ""
    clause: str = ""
    description: str = ""
    severity: str = "INFO"        # was Literal — Legal Agent LLM may use other values
    recommendation: str = ""


class LegalClearancePayload(BaseModel):
    venture_id: str
    is_cleared: bool = True
    platforms_reviewed: list[str] = []
    tos_version: str = "unknown"
    policy_flags: list[dict[str, Any]] = []   # was list[PolicyFlag] — accept raw LLM dicts
    copyright_clear: bool = True
    gdpr_reviewed: bool = False
    clearance_expires_at: str = ""  # ISO 8601 — set by agent; empty = not set yet


# ---------------------------------------------------------------------------
# Factory functions — construct typed envelopes without boilerplate
# ---------------------------------------------------------------------------

def make_event(
    event_type: EventType,
    source_agent: AgentID,
    target_agent: AgentID,
    payload: BaseModel,
    run_id: str,
    venture_id: str,
    pipeline_stage: str,
    priority: Priority = Priority.NORMAL,
    correlation_id: str | None = None,
    token_cost: int = 0,
    latency_ms: int = 0,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        source_agent=source_agent,
        target_agent=target_agent,
        priority=priority,
        correlation_id=correlation_id or str(uuid.uuid4()),
        payload=payload.model_dump(),
        metadata=EventMetadata(
            run_id=run_id,
            venture_id=venture_id,
            pipeline_stage=pipeline_stage,
            token_cost=token_cost,
            latency_ms=latency_ms,
        ),
    )
