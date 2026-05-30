"""
tests/test_schemas.py
Unit tests for all Pydantic event schema models.
Every payload model must parse without error — this is the JSON contract guard.
Run: pytest tests/test_schemas.py -v
"""
import pytest
from pydantic import ValidationError
from packages.schemas.events import (
    AgentID, CritiqueLog, EventEnvelope, EventMetadata,
    EventType, Priority, QACheckError, VentureBriefPayload, TechSpecPayload,
    StackSpec, Feature, BuildCompletePayload, TestResults,
    AudioAsset, VideoAsset, ThumbnailAsset, ScriptSpec, SeoMetadata,
    ContentPackagePayload, QAPassedPayload, QAFailedPayload,
    SecurityClearancePayload, TosStatus, PostingWindow,
    GrowthReportPayload, PortfolioSummary, VenturePerformance,
    make_event,
)


# ---------------------------------------------------------------------------
# EventEnvelope
# ---------------------------------------------------------------------------

def _make_metadata(venture_id="ven_test_001"):
    return EventMetadata(run_id="run-123", venture_id=venture_id, pipeline_stage="CEO_NODE")


def test_event_envelope_defaults():
    env = EventEnvelope(
        event_type=EventType.VENTURE_BRIEF_READY,
        source_agent=AgentID.CEO_NICHE_SCOUT,
        target_agent=AgentID.PRODUCT_TEAM,
        metadata=_make_metadata(),
    )
    assert env.priority == Priority.NORMAL
    assert env.schema_version == "1.0.0"
    assert env.retry_count == 0
    assert env.event_id is not None
    assert env.correlation_id is not None


def test_event_envelope_roundtrip():
    """Serialise to bus dict and deserialise back — must be lossless."""
    env = EventEnvelope(
        event_type=EventType.QA_PASSED,
        source_agent=AgentID.QA_AUDITOR,
        target_agent=AgentID.SECURITY_AGENT,
        payload={"is_passed": True, "checks_run": ["bundle_size", "test_pass_rate"]},
        metadata=_make_metadata(),
    )
    bus_dict = env.to_bus_dict()
    restored = EventEnvelope.from_bus_dict(bus_dict)
    assert restored.event_type == EventType.QA_PASSED
    assert restored.payload["is_passed"] is True
    assert restored.metadata.run_id == "run-123"


# ---------------------------------------------------------------------------
# VentureBriefPayload
# ---------------------------------------------------------------------------

def _venture_brief_data():
    return dict(
        venture_id="ven_finance_001",
        venture_type="MICRO_SAAS",
        niche="AI tax automation for freelancers",
        target_region=["US", "IN"],
        target_audience="Self-employed professionals",
        rpm_estimate_usd=18.5,
        competition_score=0.34,
        feasibility_score=0.81,
        tam_usd_millions=420.0,
        top_competitors=[{"name": "TurboTax", "weakness": "no AI layer", "moat_gap": "real-time alerts"}],
        recommended_monetization=["subscription_saas"],
        content_angles=["5 deductions freelancers miss"],
        go_decision=True,
        go_rationale="High RPM, clear competitor weakness",
    )


def test_venture_brief_valid():
    payload = VentureBriefPayload(**_venture_brief_data())
    assert payload.go_decision is True
    assert payload.feasibility_score == 0.81


def test_venture_brief_score_bounds():
    data = _venture_brief_data()
    data["competition_score"] = 1.5   # out of bounds
    with pytest.raises(ValidationError):
        VentureBriefPayload(**data)


def test_venture_brief_invalid_type():
    data = _venture_brief_data()
    data["venture_type"] = "INVALID_TYPE"
    with pytest.raises(ValidationError):
        VentureBriefPayload(**data)


# ---------------------------------------------------------------------------
# TechSpecPayload
# ---------------------------------------------------------------------------

def _tech_spec_data():
    return dict(
        venture_id="ven_finance_001",
        product_type="MICRO_SAAS",
        stack=StackSpec(),
        features=[Feature(
            feature_id="feat_001",
            name="Deduction Scanner",
            priority="P0",
            user_story="As a freelancer I upload my bank statement",
            acceptance_criteria=["Parses CSV", "Categorises expenses"],
            estimated_components=["FileUpload", "CSVParser"],
        )],
        data_models={"User": {"id": "uuid", "email": "string"}},
        api_routes=[{"method": "POST", "path": "/api/upload", "description": "Upload statement"}],
        estimated_build_tokens=180000,
        component_count=14,
        complexity="LOW",
    )


def test_tech_spec_valid():
    payload = TechSpecPayload(**_tech_spec_data())
    assert payload.complexity == "LOW"
    assert len(payload.features) == 1


def test_tech_spec_invalid_complexity():
    data = _tech_spec_data()
    data["complexity"] = "EXTREME"
    with pytest.raises(ValidationError):
        TechSpecPayload(**data)


# ---------------------------------------------------------------------------
# BuildCompletePayload
# ---------------------------------------------------------------------------

def test_build_complete_valid():
    payload = BuildCompletePayload(
        venture_id="ven_finance_001",
        build_path="/apps/ven_finance_001",
        build_hash="abc123def456",
        components_generated=["FileUpload.tsx", "Dashboard.tsx"],
        test_results=TestResults(total=10, passed=10, failed=0, coverage_pct=88.0),
        vite_build_exit_code=0,
        bundle_size_kb=280,
        dependencies=["react@19", "vite@6"],
    )
    assert payload.vite_build_exit_code == 0
    assert payload.is_retry is False


# ---------------------------------------------------------------------------
# ContentPackagePayload
# ---------------------------------------------------------------------------

def test_content_package_valid():
    payload = ContentPackagePayload(
        venture_id="ven_finance_001",
        platform="youtube",
        content_type="long_form",
        script=ScriptSpec(hook="You're leaving money on table", body_sections=["Problem", "Solution"], word_count=1800, estimated_duration_sec=480),
        audio_asset=AudioAsset(file_path="/assets/audio.mp3", duration_sec=480, voice_model="ElevenLabs:rachel_v3", human_likeness_score=0.91),
        video_asset=VideoAsset(file_path="/assets/video.mp4", resolution="1920x1080", duration_sec=480, has_captions=True),
        thumbnail_asset=ThumbnailAsset(file_path="/assets/thumb.png", resolution="1280x720"),
        seo_metadata=SeoMetadata(title="AI Tax Breakdown", description="How to find deductions", tags=["tax"], hashtags=["#taxes"]),
    )
    assert payload.platform == "youtube"
    assert payload.audio_asset.human_likeness_score >= 0.85


def test_content_package_invalid_platform():
    with pytest.raises(ValidationError):
        ContentPackagePayload(
            venture_id="ven_test",
            platform="snapchat",   # not in allowed platforms
            content_type="short_form",
            script=ScriptSpec(hook="hook", body_sections=[], word_count=100, estimated_duration_sec=60),
            audio_asset=AudioAsset(file_path="/a.mp3", duration_sec=60, voice_model="ElevenLabs:v1", human_likeness_score=0.9),
            video_asset=VideoAsset(file_path="/v.mp4", resolution="1080x1920", duration_sec=60, has_captions=True),
            thumbnail_asset=ThumbnailAsset(file_path="/t.png", resolution="1080x1080"),
            seo_metadata=SeoMetadata(title="Test", description="test desc", tags=[], hashtags=[]),
        )


# ---------------------------------------------------------------------------
# QA Payloads
# ---------------------------------------------------------------------------

def test_qa_passed_payload():
    payload = QAPassedPayload(
        venture_id="ven_001",
        artifact_type="BUILD",
        checks_run=["vite_build", "bundle_size", "test_pass_rate"],
        checks_passed=3,
        checks_failed=0,
        qa_report_path="/reports/ven_001_qa.json",
    )
    assert payload.is_passed is True


def test_qa_failed_payload():
    critique = CritiqueLog(
        failed_checks=["vite_build_exit_code"],
        errors=[QACheckError(
            check="vite_build_exit_code",
            severity="CRITICAL",
            component="CSVParser",
            error_type="RUNTIME_EXCEPTION",
            fix_directive="Add null guard before map call",
        )],
    )
    payload = QAFailedPayload(
        venture_id="ven_001",
        artifact_type="BUILD",
        retry_count=1,
        max_retries=3,
        qa_target="engineering",
        critique_log=critique,
    )
    assert payload.is_passed is False
    assert payload.qa_target == "engineering"
    assert len(payload.critique_log.errors) == 1


# ---------------------------------------------------------------------------
# SecurityClearancePayload
# ---------------------------------------------------------------------------

def test_security_clearance_valid():
    payload = SecurityClearancePayload(
        venture_id="ven_001",
        platform_accounts={"youtube": {"account_id": "acct_yt_001"}},
        tos_compliance_snapshot={"youtube": TosStatus(compliant=True, last_checked="2026-05-18T00:00:00Z")},
        posting_schedule={"youtube": PostingWindow(post_time_utc="14:00", jitter_minutes=18, frequency="daily")},
        clearance_valid_until="2026-05-25T00:00:00Z",
    )
    assert payload.tos_compliance_snapshot["youtube"].compliant is True


# ---------------------------------------------------------------------------
# make_event factory
# ---------------------------------------------------------------------------

def test_make_event_factory():
    brief = VentureBriefPayload(**_venture_brief_data())
    env = make_event(
        event_type=EventType.VENTURE_BRIEF_READY,
        source_agent=AgentID.CEO_NICHE_SCOUT,
        target_agent=AgentID.PRODUCT_TEAM,
        payload=brief,
        run_id="run-abc",
        venture_id="ven_finance_001",
        pipeline_stage="CEO_NODE",
    )
    assert env.event_type == EventType.VENTURE_BRIEF_READY
    assert env.payload["niche"] == "AI tax automation for freelancers"
    assert env.metadata.run_id == "run-abc"


# ---------------------------------------------------------------------------
# GrowthReportPayload
# ---------------------------------------------------------------------------

def test_growth_report_valid():
    payload = GrowthReportPayload(
        report_period="2026-05-01/2026-05-18",
        portfolio_summary=PortfolioSummary(
            total_ventures=5, live_ventures=3,
            total_mrr_usd=450.0, total_burn_usd=97.0, net_mrr_usd=353.0,
        ),
        top_performers=[VenturePerformance(
            venture_id="ven_finance_001", mrr_usd=280.0, growth_rate_mom=0.42,
            primary_channel="youtube", signal="SCALE",
        )],
        bottom_performers=[VenturePerformance(
            venture_id="ven_crypto_003", mrr_usd=8.0, growth_rate_mom=-0.1,
            primary_channel="youtube", signal="KILL", kill_rationale="TAM contraction",
        )],
        niche_recalibration={"boost_niches": ["freelancer_finance"], "blacklist_niches": ["crypto"]},
        winning_content_formats={"youtube": "8-12min explainer"},
    )
    assert payload.portfolio_summary.net_mrr_usd == 353.0
    assert payload.top_performers[0].signal == "SCALE"
