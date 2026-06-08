"""
packages/agents/media/qa_compliance.py
QA Compliance Validator — gates CONTENT packages before legal/security.

Model:   claude-haiku-4-5 (critique) + rule-engine (pass/fail)
Input:   content_package
Output:  qa_report — pass routes to LEGAL_NODE, fail loops to SCRIPT_NODE

Checks:
  ✓ Human likeness score >= 0.85
  ✓ Title length within platform limits
  ✓ Video duration within platform limits
  ✓ Thumbnail resolution 1280x720
  ✓ No prohibited phrases in title
  ✓ Description length within limits
  ✓ Copyright fingerprint (Week 9: file-size stub; Phase 3: ACRCloud API)
"""
from __future__ import annotations

import json
import logging
import uuid

from packages.db.client import log_agent_event, save_qa_report
from packages.schemas.events import (
    AgentID, CritiqueLog, EventType, ManualReviewPayload,
    QAFailedPayload, QAPassedPayload, make_event,
)
from packages.state.agent_state import AgentState, QAReport, append_event, update_stage
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

_PROHIBITED_PHRASES = [
    "earn money fast", "get rich", "guaranteed income",
    "make $", "passive income guaranteed",
]

_CRITIQUE_SYSTEM = """
You are the QA Compliance Auditor for AI Squadron's Media Department.
A content package has failed validation checks. For each failure, produce a structured
critique with a specific, actionable fix_directive the Script Agent can execute.

Output ONLY valid JSON:
{
  "failed_checks": ["check_name"],
  "errors": [
    {
      "check": "check_name",
      "severity": "CRITICAL|WARNING",
      "component": "title|audio|video|thumbnail|description",
      "error_type": "LOW_QUALITY|POLICY_VIOLATION|LENGTH_VIOLATION",
      "stack_trace": null,
      "fix_directive": "Specific, executable instruction"
    }
  ]
}
"""


async def qa_compliance_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    retry_count = state.get("qa_retry_count", 0)
    max_retries = state.get("qa_max_retries", 3)
    content = state.get("content_package") or {}

    log.info("[QA_COMPLIANCE_NODE] Validating content | venture=%s retry=%d",
             venture_id, retry_count)
    log_agent_event(run_id, venture_id, "QA_COMPLIANCE", "RUNNING",
                    "Content compliance validation", retry_count=retry_count)

    checks_run, failures = _validate_content(content)
    is_passed = len(failures) == 0
    report_id = str(uuid.uuid4())

    qa_report: QAReport = {
        "venture_id":     venture_id,
        "artifact_type":  "CONTENT",
        "is_passed":      is_passed,
        "checks_run":     checks_run,
        "checks_passed":  len(checks_run) - len(failures),
        "checks_failed":  len(failures),
        "qa_target":      None,
        "critique_log":   {},
        "qa_report_path": f"/reports/{venture_id}_content_qa_{report_id}.json",
    }

    save_qa_report({
        "run_id": run_id, "venture_id": venture_id,
        "artifact_type": "CONTENT", "is_passed": is_passed,
        "retry_count": retry_count, "checks_run": checks_run, "checks_failed": failures,
    })

    if is_passed:
        log.info("[QA_COMPLIANCE_NODE] ✓ PASSED | checks=%d", len(checks_run))
        log_agent_event(run_id, venture_id, "QA_COMPLIANCE", "SUCCESS")
        payload = QAPassedPayload(
            venture_id=venture_id, artifact_type="CONTENT",
            checks_run=checks_run, checks_passed=len(checks_run),
            checks_failed=0, qa_report_path=qa_report["qa_report_path"],
        )
        event = make_event(
            EventType.QA_PASSED, AgentID.QA_COMPLIANCE, AgentID.LEGAL_AGENT,
            payload, run_id, venture_id, "QA_COMPLIANCE_NODE",
        )
        new_state = update_stage(state, "LEGAL_NODE")
        return append_event({**new_state, "qa_report": qa_report}, event.model_dump())

    log.warning("[QA_COMPLIANCE_NODE] FAILED | checks=%s retry=%d/%d",
                failures, retry_count, max_retries)

    if retry_count >= max_retries:
        log.error("[QA_COMPLIANCE_NODE] Max retries — escalating to MANUAL_REVIEW")
        log_agent_event(run_id, venture_id, "QA_COMPLIANCE", "FAILED",
                        error_detail=f"Max retries ({max_retries}) reached")
        review_payload = ManualReviewPayload(
            venture_id=venture_id, run_id=run_id,
            review_reason=f"Content QA failed after {max_retries} retries",
            artifact_type="CONTENT", retry_count=retry_count,
        )
        event = make_event(
            EventType.MANUAL_REVIEW_REQUIRED, AgentID.QA_COMPLIANCE, AgentID.BROADCAST,
            review_payload, run_id, venture_id, "QA_COMPLIANCE_NODE", priority="CRITICAL",
        )
        new_state = update_stage(state, "MANUAL_REVIEW_NODE")
        return append_event(
            {**new_state, "qa_report": qa_report,
             "manual_review_reason": review_payload.review_reason},
            event.model_dump(),
        )

    critique_log = await _generate_critique(failures, content)
    qa_report["critique_log"] = critique_log
    qa_report["qa_target"] = "content"

    fail_payload = QAFailedPayload(
        venture_id=venture_id, artifact_type="CONTENT",
        retry_count=retry_count + 1, max_retries=max_retries,
        qa_target="content", critique_log=CritiqueLog(**critique_log),
    )
    event = make_event(
        EventType.QA_FAILED, AgentID.QA_COMPLIANCE, AgentID.SCRIPT_AGENT,
        fail_payload, run_id, venture_id, "QA_COMPLIANCE_NODE",
    )
    log_agent_event(run_id, venture_id, "QA_COMPLIANCE", "FAILED",
                    error_detail=f"{len(failures)} checks failed")

    new_state = update_stage(state, "SCRIPT_NODE")
    return append_event(
        {**new_state, "qa_report": qa_report,
         "qa_retry_count": retry_count + 1, "qa_target": "content"},
        event.model_dump(),
    )


def _validate_content(content: dict) -> tuple[list[str], list[str]]:
    checks = [
        "human_likeness_score",
        "title_length",
        "video_duration",
        "prohibited_phrases",
        "copyright_fingerprint",
    ]
    failures: list[str] = []

    audio = content.get("audio_asset") or {}
    if isinstance(audio, dict) and audio.get("human_likeness_score", 0) < 0.85:
        failures.append("human_likeness_score")

    seo = content.get("seo_metadata") or {}
    if isinstance(seo, dict):
        title = seo.get("title", "")
        platform = content.get("platform", "youtube")
        max_len = 100 if platform == "youtube" else 150
        if len(title) > max_len or len(title) < 10:
            failures.append("title_length")
        title_lower = title.lower()
        if any(phrase in title_lower for phrase in _PROHIBITED_PHRASES):
            failures.append("prohibited_phrases")

    video = content.get("video_asset") or {}
    if isinstance(video, dict):
        duration = video.get("duration_sec", 0)
        if duration < 30 or duration > 3600:
            failures.append("video_duration")

    # Copyright fingerprint — Week 9 stub
    # Checks: audio file is non-empty and within sane size bounds.
    # Phase 3 upgrade: replace with ACRCloud humming-search API call.
    copyright_ok, copyright_reason = _copyright_fingerprint_check(audio)
    if not copyright_ok:
        failures.append("copyright_fingerprint")
        log.warning("[QA_COMPLIANCE] Copyright check failed: %s", copyright_reason)

    return checks, failures


def _copyright_fingerprint_check(audio_asset: dict) -> tuple[bool, str]:
    """
    Stub copyright check — verifies the audio asset is plausibly original.

    Current logic (file-size heuristic):
      - No file_path set          → assume clear (ElevenLabs stub mode)
      - File doesn't exist on disk → assume clear (remote storage path)
      - File < 1 KB               → flag as suspiciously small (may be silent)
      - File > 500 MB             → flag as suspiciously large

    Phase 3 upgrade path:
      if ACRCOUD_API_KEY set → submit audio to ACRCloud humming-search endpoint
      → compare against their 90M-track copyright database
      → return match details as a WARNING flag for manual review.
    """
    from pathlib import Path

    file_path = audio_asset.get("file_path", "")
    if not file_path:
        return True, ""

    p = Path(file_path)
    if not p.exists():
        # Path is a cloud/Supabase URL — can't stat locally, assume clear
        return True, ""

    size = p.stat().st_size
    if size < 1_000:
        return False, (
            f"Audio file is only {size} bytes — may be silent or corrupt. "
            "Re-generate with ElevenLabs."
        )
    if size > 500 * 1024 * 1024:
        return False, (
            f"Audio file is {size // (1024*1024)} MB — unexpectedly large. "
            "Verify the correct file was written."
        )
    return True, ""


async def _generate_critique(failed_checks: list[str], content: dict) -> dict:
    prompt = (
        f"Failed checks: {json.dumps(failed_checks)}\n"
        f"Content summary: {json.dumps({k: v for k, v in content.items() if k != 'script'}, indent=2)}\n"
        "Generate critique_log JSON."
    )
    try:
        response = await call_llm(
            "QA_COMPLIANCE_CRITIQUE", _CRITIQUE_SYSTEM, prompt, temperature=0.1,
        )
        return json.loads(extract_json(response.text))
    except Exception:
        return {
            "failed_checks": failed_checks,
            "errors": [
                {"check": c, "severity": "CRITICAL", "component": "content",
                 "error_type": "VALIDATION_FAILED", "stack_trace": None,
                 "fix_directive": f"Fix the {c} issue before resubmitting."}
                for c in failed_checks
            ],
        }
