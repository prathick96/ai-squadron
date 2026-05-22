"""
packages/state/agent_state.py
Central state object that flows through every LangGraph node.
Every node reads and writes to this TypedDict. Immutable fields
are only written once (run_id, venture_id, created_at).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict


# ---------------------------------------------------------------------------
# Sub-schemas embedded inside AgentState
# ---------------------------------------------------------------------------

class ResearchDossier(TypedDict, total=False):
    venture_id: str
    trend_snapshot: dict[str, Any]
    scout_reports: list[dict[str, Any]]
    debate_summary: dict[str, Any]
    debate_transcript: list[dict[str, Any]]
    recommended_primary_niche: str
    recommended_venture_type: str
    consensus_niches: list[str]
    disagreements: list[dict[str, Any]]
    council_confidence: float
    research_mode: str


class VentureBrief(TypedDict, total=False):
    venture_id: str
    venture_type: Literal["MICRO_SAAS", "MEDIA_CHANNEL", "AFFILIATE_SITE"]
    niche: str
    target_region: list[str]
    target_audience: str
    rpm_estimate_usd: float
    competition_score: float
    feasibility_score: float
    tam_usd_millions: float
    top_competitors: list[dict[str, str]]
    recommended_monetization: list[str]
    content_angles: list[str]
    go_decision: bool
    go_rationale: str


class TechSpec(TypedDict, total=False):
    venture_id: str
    product_type: Literal["MICRO_SAAS", "MEDIA_CHANNEL", "AFFILIATE_SITE"]
    stack: dict[str, str]
    features: list[dict[str, Any]]
    data_models: dict[str, Any]
    api_routes: list[dict[str, str]]
    estimated_build_tokens: int
    component_count: int
    complexity: Literal["LOW", "MEDIUM", "HIGH"]


class BuildArtifact(TypedDict, total=False):
    venture_id: str
    build_path: str
    build_hash: str
    components_generated: list[str]
    test_results: dict[str, Any]
    vite_build_exit_code: int
    bundle_size_kb: int
    dependencies: list[str]
    is_retry: bool
    retry_patches_applied: list[str]


class ContentPackage(TypedDict, total=False):
    venture_id: str
    platform: str
    content_type: Literal["short_form", "long_form"]
    script: dict[str, Any]
    audio_asset: dict[str, Any]
    video_asset: dict[str, Any]
    thumbnail_asset: dict[str, Any]
    seo_metadata: dict[str, Any]
    is_retry: bool


class QAReport(TypedDict, total=False):
    venture_id: str
    artifact_type: Literal["BUILD", "CONTENT"]
    is_passed: bool
    checks_run: list[str]
    checks_passed: int
    checks_failed: int
    qa_target: Literal["engineering", "content"] | None
    critique_log: dict[str, Any]
    qa_report_path: str


class SecurityClearance(TypedDict, total=False):
    venture_id: str
    platform_accounts: dict[str, dict[str, str]]
    tos_compliance_snapshot: dict[str, dict[str, Any]]
    posting_schedule: dict[str, dict[str, Any]]
    clearance_valid_until: str
    is_compliant: bool


class AccountDistributionPlan(TypedDict, total=False):
    venture_id: str
    accounts: list[dict[str, Any]]
    duplicate_content_window_hours: int
    provisioned_at: str


class DeploymentReceipt(TypedDict, total=False):
    venture_id: str
    deployments: list[dict[str, Any]]
    post_deployment_status: Literal["LIVE", "FAILED", "PARTIAL"]


class CampaignPlan(TypedDict, total=False):
    venture_id: str
    campaigns: list[dict[str, Any]]
    tracking_params: dict[str, str]


class LocalizationMap(TypedDict, total=False):
    venture_id: str
    localizations: list[dict[str, Any]]
    regions_covered: list[str]
    estimated_incremental_reach: int


class GrowthSignals(TypedDict, total=False):
    report_period: str
    portfolio_summary: dict[str, Any]
    top_performers: list[dict[str, Any]]
    bottom_performers: list[dict[str, Any]]
    niche_recalibration: dict[str, list[str]]
    winning_content_formats: dict[str, str]


# ---------------------------------------------------------------------------
# Root AgentState — the shared state object across ALL nodes
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    # ------------------------------------------------------------------
    # Pipeline identity (set once at graph entry, never mutated)
    # ------------------------------------------------------------------
    run_id: str                        # UUID4 string
    venture_id: str                    # Stable venture identifier
    pipeline_stage: str                # Current node name
    created_at: str                    # ISO 8601

    # ------------------------------------------------------------------
    # Artifacts produced per stage (None until that node completes)
    # ------------------------------------------------------------------
    research_dossier: ResearchDossier | None
    venture_brief: VentureBrief | None
    tech_spec: TechSpec | None
    build_artifact: BuildArtifact | None
    content_package: ContentPackage | None
    qa_report: QAReport | None
    security_clearance: SecurityClearance | None
    account_distribution_plan: AccountDistributionPlan | None
    deployment_receipt: DeploymentReceipt | None
    campaign_plan: CampaignPlan | None
    localization_map: LocalizationMap | None
    growth_signals: GrowthSignals | None

    # ------------------------------------------------------------------
    # QA retry loop control
    # ------------------------------------------------------------------
    qa_target: Literal["engineering", "content"] | None
    qa_retry_count: int
    qa_max_retries: int                # Hard cap — default 3

    # ------------------------------------------------------------------
    # Revenue & lifecycle
    # ------------------------------------------------------------------
    revenue_status: Literal["pending", "active", "scaling", "kill"]
    mrr_current: float
    burn_current: float

    # ------------------------------------------------------------------
    # Event log — append-only list of all events in this run
    # ------------------------------------------------------------------
    event_log: list[dict[str, Any]]

    # ------------------------------------------------------------------
    # Error tracking
    # ------------------------------------------------------------------
    last_error: str | None
    manual_review_reason: str | None


# ---------------------------------------------------------------------------
# State factory — always initialise via this function
# ---------------------------------------------------------------------------

def init_state(venture_id: str | None = None) -> AgentState:
    """
    Returns a fully initialised AgentState with safe defaults.
    Use this as the graph's entry-point input.
    """
    return AgentState(
        run_id=str(uuid.uuid4()),
        venture_id=venture_id or f"ven_{uuid.uuid4().hex[:8]}",
        pipeline_stage="CEO_NODE",
        created_at=datetime.now(timezone.utc).isoformat(),

        # Artifacts — all None until produced
        research_dossier=None,
        venture_brief=None,
        tech_spec=None,
        build_artifact=None,
        content_package=None,
        qa_report=None,
        security_clearance=None,
        account_distribution_plan=None,
        deployment_receipt=None,
        campaign_plan=None,
        localization_map=None,
        growth_signals=None,

        # QA loop
        qa_target=None,
        qa_retry_count=0,
        qa_max_retries=3,

        # Revenue
        revenue_status="pending",
        mrr_current=0.0,
        burn_current=0.0,

        # Audit trail
        event_log=[],
        last_error=None,
        manual_review_reason=None,
    )


def append_event(state: AgentState, event: dict[str, Any]) -> AgentState:
    """
    Appends an event to the state's event_log.
    Returns a new state dict — does NOT mutate in place.
    """
    updated_log = list(state.get("event_log", []))
    updated_log.append({**event, "logged_at": datetime.now(timezone.utc).isoformat()})
    return {**state, "event_log": updated_log}


def update_stage(state: AgentState, stage: str) -> AgentState:
    """Convenience: update pipeline_stage and return new state."""
    return {**state, "pipeline_stage": stage}
