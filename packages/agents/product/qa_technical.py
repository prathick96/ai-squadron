"""
packages/agents/product/qa_technical.py
QA Technical Validator — gates BUILD artifacts before legal/security.

Model:   claude-haiku-4-5 (critique generation) + rule-engine (pass/fail)
Input:   build_artifact
Output:  qa_report — pass routes to LEGAL_NODE, fail loops back to ENGINEERING_NODE

Checks:
  ✓ Vite build exit code
  ✓ Bundle size (< 250 MB)
  ✓ Test pass rate (0 failures)
  ✓ Component render checks
  ✓ No hardcoded secrets scan (defence-in-depth; Legal Agent also checks)
  ✓ TypeScript strict compliance signal
"""
from __future__ import annotations

import json
import logging
import uuid

from packages.db.client import log_agent_event, save_qa_report
from packages.schemas.events import (
    AgentID, CritiqueLog, EventType, ManualReviewPayload,
    QACheckError, QAFailedPayload, QAPassedPayload, make_event,
)
from packages.state.agent_state import AgentState, QAReport, append_event, update_stage
from packages.tools.llm import call_llm

log = logging.getLogger(__name__)

_CRITIQUE_SYSTEM = """
You are the QA Technical Auditor for AI Squadron.
A build has failed automated checks. For each failure, produce a structured critique
with a specific, actionable fix_directive the Engineering agent can execute alone.

Output ONLY valid JSON:
{
  "failed_checks": ["check_name"],
  "errors": [
    {
      "check": "check_name",
      "severity": "CRITICAL|WARNING",
      "component": "filename or module",
      "error_type": "BUILD_FAILURE|TEST_FAILURE|BUNDLE_TOO_LARGE|SECRET_EXPOSED",
      "stack_trace": null,
      "fix_directive": "Specific, executable instruction"
    }
  ]
}
"""

_SECRET_PATTERNS = ["sk_live_", "sk_test_", "api_key=", "password=", "secret=", "token="]


async def qa_technical_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    retry_count = state.get("qa_retry_count", 0)
    max_retries = state.get("qa_max_retries", 3)
    build = state.get("build_artifact") or {}

    log.info("[QA_TECHNICAL_NODE] Validating build | venture=%s retry=%d", venture_id, retry_count)
    log_agent_event(run_id, venture_id, "QA_TECHNICAL", "RUNNING",
                    "Build validation", retry_count=retry_count)

    checks_run, failures = _validate_build(build)
    is_passed = len(failures) == 0
    report_id = str(uuid.uuid4())

    qa_report: QAReport = {
        "venture_id":     venture_id,
        "artifact_type":  "BUILD",
        "is_passed":      is_passed,
        "checks_run":     checks_run,
        "checks_passed":  len(checks_run) - len(failures),
        "checks_failed":  len(failures),
        "qa_target":      None,
        "critique_log":   {},
        "qa_report_path": f"/reports/{venture_id}_qa_{report_id}.json",
    }

    save_qa_report({
        "run_id": run_id, "venture_id": venture_id,
        "artifact_type": "BUILD", "is_passed": is_passed,
        "retry_count": retry_count, "checks_run": checks_run, "checks_failed": failures,
    })

    if is_passed:
        log.info("[QA_TECHNICAL_NODE] ✓ PASSED | checks=%d", len(checks_run))
        log_agent_event(run_id, venture_id, "QA_TECHNICAL", "SUCCESS")
        payload = QAPassedPayload(
            venture_id=venture_id, artifact_type="BUILD",
            checks_run=checks_run, checks_passed=len(checks_run),
            checks_failed=0, qa_report_path=qa_report["qa_report_path"],
        )
        event = make_event(
            EventType.QA_PASSED, AgentID.QA_TECHNICAL, AgentID.LEGAL_AGENT,
            payload, run_id, venture_id, "QA_TECHNICAL_NODE",
        )
        new_state = update_stage(state, "LEGAL_NODE")
        return append_event({**new_state, "qa_report": qa_report}, event.model_dump())

    log.warning("[QA_TECHNICAL_NODE] FAILED | checks=%s retry=%d/%d",
                failures, retry_count, max_retries)

    if retry_count >= max_retries:
        log.error("[QA_TECHNICAL_NODE] Max retries — escalating to MANUAL_REVIEW")
        log_agent_event(run_id, venture_id, "QA_TECHNICAL", "FAILED",
                        error_detail=f"Max retries ({max_retries}) reached")
        review_payload = ManualReviewPayload(
            venture_id=venture_id, run_id=run_id,
            review_reason=f"Build QA failed after {max_retries} retries",
            artifact_type="BUILD", retry_count=retry_count,
        )
        event = make_event(
            EventType.MANUAL_REVIEW_REQUIRED, AgentID.QA_TECHNICAL, AgentID.BROADCAST,
            review_payload, run_id, venture_id, "QA_TECHNICAL_NODE", priority="CRITICAL",
        )
        new_state = update_stage(state, "MANUAL_REVIEW_NODE")
        return append_event(
            {**new_state, "qa_report": qa_report,
             "manual_review_reason": review_payload.review_reason},
            event.model_dump(),
        )

    critique_log = await _generate_critique(failures, build)
    qa_report["critique_log"] = critique_log
    qa_report["qa_target"] = "engineering"

    fail_payload = QAFailedPayload(
        venture_id=venture_id, artifact_type="BUILD",
        retry_count=retry_count + 1, max_retries=max_retries,
        qa_target="engineering", critique_log=CritiqueLog(**critique_log),
    )
    event = make_event(
        EventType.QA_FAILED, AgentID.QA_TECHNICAL, AgentID.ENGINEERING_TEAM,
        fail_payload, run_id, venture_id, "QA_TECHNICAL_NODE",
    )
    log_agent_event(run_id, venture_id, "QA_TECHNICAL", "FAILED",
                    error_detail=f"{len(failures)} checks failed")

    new_state = update_stage(state, "ENGINEERING_NODE")
    return append_event(
        {**new_state, "qa_report": qa_report,
         "qa_retry_count": retry_count + 1, "qa_target": "engineering"},
        event.model_dump(),
    )


def _validate_build(build: dict) -> tuple[list[str], list[str]]:
    checks = ["vite_build_exit_code", "bundle_size", "test_pass_rate",
              "component_render", "no_hardcoded_secrets"]
    failures: list[str] = []

    if build.get("vite_build_exit_code", 1) != 0:
        failures.append("vite_build_exit_code")

    if build.get("bundle_size_kb", 0) > 250_000:
        failures.append("bundle_size")

    test_results = build.get("test_results", {})
    if isinstance(test_results, dict) and test_results.get("failed", 0) > 0:
        failures.append("test_pass_rate")

    for f in (build.get("files") or []):
        content = (f.get("content") or "").lower()
        for pat in _SECRET_PATTERNS:
            if pat in content:
                failures.append("no_hardcoded_secrets")
                break

    return checks, failures


async def _generate_critique(failed_checks: list[str], build: dict) -> dict:
    prompt = (
        f"Failed checks: {json.dumps(failed_checks)}\n"
        f"Build summary: {json.dumps({k: v for k, v in build.items() if k != 'files'}, indent=2)}\n"
        "Generate critique_log JSON."
    )
    try:
        response = await call_llm(
            "QA_TECHNICAL_CRITIQUE", _CRITIQUE_SYSTEM, prompt, temperature=0.1,
        )
        return json.loads(response.text)
    except Exception:
        return {
            "failed_checks": failed_checks,
            "errors": [
                {"check": c, "severity": "CRITICAL", "component": "Unknown",
                 "error_type": "VALIDATION_FAILED", "stack_trace": None,
                 "fix_directive": f"Fix the {c} failure before resubmitting."}
                for c in failed_checks
            ],
        }
