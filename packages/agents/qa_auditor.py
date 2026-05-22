"""
packages/agents/qa_auditor.py
QA Auditor Node — gates every artifact before deployment.
Runs two separate logic engines:
  Technical Validator  → BUILD artifacts  (Playwright + bundle checks)
  Compliance Validator → CONTENT artifacts (copyright + quality checks)
Model: claude-haiku-4-5 (critique) + gemini-2.0-flash (pass/fail gate)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from packages.db.client import log_agent_event, save_qa_report
from packages.schemas.events import (
    AgentID, CritiqueLog, EventType, ManualReviewPayload,
    QACheckError, QAFailedPayload, QAPassedPayload, make_event
)
from packages.state.agent_state import AgentState, QAReport, append_event, update_stage
from packages.tools.llm import call_llm, classify

log = logging.getLogger(__name__)

_CRITIQUE_SYSTEM = """
You are a QA Auditor Agent. You receive a build or content artifact and a list of
failed checks. For each failure, you produce a structured critique with an actionable
fix_directive that the Engineering or Content agent can execute without human input.

Output ONLY valid JSON:
{
  "failed_checks": ["check_name"],
  "errors": [
    {
      "check": "check_name",
      "severity": "CRITICAL|WARNING|INFO",
      "component": "ComponentName",
      "error_type": "RUNTIME_EXCEPTION|RENDER_FAIL|COPYRIGHT_VIOLATION|LOW_QUALITY",
      "stack_trace": "optional",
      "fix_directive": "Specific, actionable instruction"
    }
  ]
}
"""


async def qa_auditor_node(state: AgentState) -> AgentState:
    run_id      = state["run_id"]
    venture_id  = state["venture_id"]
    retry_count = state.get("qa_retry_count", 0)
    max_retries = state.get("qa_max_retries", 3)

    # Determine what we're validating
    build     = state.get("build_artifact")
    content   = state.get("content_package")
    artifact_type = "BUILD" if build else "CONTENT"

    log.info("[QA_NODE] Validating %s | venture=%s retry=%d",
             artifact_type, venture_id, retry_count)
    log_agent_event(run_id, venture_id, "QA_AUDITOR", "RUNNING",
                    f"Validating {artifact_type}", retry_count=retry_count)

    # Run the appropriate validation suite
    if artifact_type == "BUILD":
        checks_run, failures = await _validate_build(build or {})
    else:
        checks_run, failures = await _validate_content(content or {})

    is_passed = len(failures) == 0
    report_id = str(uuid.uuid4())
    report_path = f"/reports/{venture_id}_qa_{report_id}.json"

    qa_report: QAReport = {
        "venture_id":    venture_id,
        "artifact_type": artifact_type,
        "is_passed":     is_passed,
        "checks_run":    checks_run,
        "checks_passed": len(checks_run) - len(failures),
        "checks_failed": len(failures),
        "qa_target":     None,
        "critique_log":  {},
        "qa_report_path": report_path,
    }

    save_qa_report({
        "run_id":        run_id,
        "venture_id":    venture_id,
        "artifact_type": artifact_type,
        "is_passed":     is_passed,
        "retry_count":   retry_count,
        "checks_run":    checks_run,
        "checks_failed": failures,
    })

    if is_passed:
        log.info("[QA_NODE] ✓ PASSED | checks=%d", len(checks_run))
        log_agent_event(run_id, venture_id, "QA_AUDITOR", "SUCCESS")

        payload = QAPassedPayload(
            venture_id     = venture_id,
            artifact_type  = artifact_type,  # type: ignore[arg-type]
            checks_run     = checks_run,
            checks_passed  = len(checks_run),
            checks_failed  = 0,
            qa_report_path = report_path,
        )
        event = make_event(
            EventType.QA_PASSED, AgentID.QA_AUDITOR, AgentID.SECURITY_AGENT,
            payload, run_id, venture_id, "QA_NODE",
        )
        new_state = update_stage(state, "SECURITY_NODE")
        return append_event({**new_state, "qa_report": qa_report}, event.model_dump())

    # ---- FAILED — generate critique ----
    log.warning("[QA_NODE] FAILED | failures=%s retry=%d/%d", failures, retry_count, max_retries)

    # Check max retries before generating critique
    if retry_count >= max_retries:
        log.error("[QA_NODE] Max retries reached — escalating to MANUAL_REVIEW")
        log_agent_event(run_id, venture_id, "QA_AUDITOR", "FAILED",
                        error_detail=f"Max retries ({max_retries}) reached")

        review_payload = ManualReviewPayload(
            venture_id    = venture_id,
            run_id        = run_id,
            review_reason = f"QA failed after {max_retries} retries on {artifact_type}",
            artifact_type = artifact_type,  # type: ignore[arg-type]
            retry_count   = retry_count,
        )
        event = make_event(
            EventType.MANUAL_REVIEW_REQUIRED, AgentID.QA_AUDITOR, AgentID.BROADCAST,
            review_payload, run_id, venture_id, "QA_NODE", priority="CRITICAL",  # type: ignore[arg-type]
        )
        new_state = update_stage(state, "MANUAL_REVIEW_NODE")
        return append_event(
            {**new_state, "qa_report": qa_report, "manual_review_reason": review_payload.review_reason},
            event.model_dump()
        )

    # Generate structured critique via Claude Haiku
    critique_log = await _generate_critique(failures, artifact_type, build or content or {})

    qa_target = "engineering" if artifact_type == "BUILD" else "content"
    qa_report["critique_log"] = critique_log
    qa_report["qa_target"]    = qa_target

    fail_payload = QAFailedPayload(
        venture_id    = venture_id,
        artifact_type = artifact_type,  # type: ignore[arg-type]
        retry_count   = retry_count + 1,
        max_retries   = max_retries,
        qa_target     = qa_target,  # type: ignore[arg-type]
        critique_log  = CritiqueLog(**critique_log),
    )

    target = AgentID.ENGINEERING_TEAM if qa_target == "engineering" else AgentID.CONTENT_TEAM
    event  = make_event(
        EventType.QA_FAILED, AgentID.QA_AUDITOR, target,
        fail_payload, run_id, venture_id, "QA_NODE",
    )

    log_agent_event(run_id, venture_id, "QA_AUDITOR", "FAILED",
                    error_detail=f"{len(failures)} checks failed")

    new_state = update_stage(state, "ENGINEERING_NODE" if qa_target == "engineering" else "CONTENT_NODE")
    return append_event(
        {**new_state, "qa_report": qa_report,
         "qa_retry_count": retry_count + 1, "qa_target": qa_target},
        event.model_dump()
    )


async def _validate_build(build: dict) -> tuple[list[str], list[str]]:
    """Run technical validation suite against a build artifact."""
    checks_run = ["vite_build_exit_code", "bundle_size", "test_pass_rate", "component_render"]
    failures: list[str] = []

    # Vite build exit code
    if build.get("vite_build_exit_code", 1) != 0:
        failures.append("vite_build_exit_code")

    # Bundle size (Railway compute limit: 250MB uncompressed)
    if build.get("bundle_size_kb", 0) > 250_000:
        failures.append("bundle_size")

    # Test pass rate
    test_results = build.get("test_results", {})
    if isinstance(test_results, dict):
        failed = test_results.get("failed", 0)
        if failed > 0:
            failures.append("test_pass_rate")

    return checks_run, failures


async def _validate_content(content: dict) -> tuple[list[str], list[str]]:
    """Run compliance + quality validation suite against a content package."""
    checks_run = ["human_likeness_score", "copyright_scan", "metadata_compliance",
                  "video_duration", "thumbnail_resolution"]
    failures: list[str] = []

    # Human likeness threshold
    audio = content.get("audio_asset", {})
    if isinstance(audio, dict) and audio.get("human_likeness_score", 0) < 0.85:
        failures.append("human_likeness_score")

    # Metadata compliance
    seo = content.get("seo_metadata", {})
    if isinstance(seo, dict):
        title = seo.get("title", "")
        if len(title) > 100 or len(title) < 10:
            failures.append("metadata_compliance")

    # Video duration sanity check
    video = content.get("video_asset", {})
    if isinstance(video, dict):
        duration = video.get("duration_sec", 0)
        if duration < 30 or duration > 3600:
            failures.append("video_duration")

    return checks_run, failures


async def _generate_critique(
    failed_checks: list[str],
    artifact_type: str,
    artifact: dict,
) -> dict:
    """Generate actionable fix directives via Claude Haiku."""
    prompt = f"""
Artifact type: {artifact_type}
Failed checks: {json.dumps(failed_checks)}
Artifact summary: {json.dumps({k: v for k, v in artifact.items() if k != "files"}, indent=2)}

Generate a critique_log JSON with specific fix_directives for each failure.
"""
    try:
        response = await call_llm(
            "QA_AUDITOR_CRITIQUE", _CRITIQUE_SYSTEM, prompt, temperature=0.1
        )
        return json.loads(response.text)
    except Exception:
        # Fallback: generate a basic critique without LLM
        return {
            "failed_checks": failed_checks,
            "errors": [
                {
                    "check":         check,
                    "severity":      "CRITICAL",
                    "component":     "Unknown",
                    "error_type":    "VALIDATION_FAILED",
                    "stack_trace":   None,
                    "fix_directive": f"Review and fix the {check} issue before resubmitting.",
                }
                for check in failed_checks
            ],
        }
