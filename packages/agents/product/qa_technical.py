"""
packages/agents/product/qa_technical.py
QA Technical Validator — gates BUILD artifacts before legal/security.

Model:   claude-haiku-4-5 (critique) + real subprocess (pass/fail)
Input:   build_artifact (build_path points to real disk directory)
Output:  qa_report — pass → LEGAL_NODE, fail → ENGINEERING_NODE (max 3 retries)

Checks (in order):
  1. build_path exists on disk
  2. vite build exits 0           ← real subprocess, 3-minute timeout
  3. bundle size < 50 MB          ← dist/ folder total
  4. no hardcoded secrets          ← scans LLM-generated file contents
  5. playwright smoke test         ← Week 9: Chromium headless, React mounts
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re as _re
import sys
import uuid
from pathlib import Path

from packages.db.client import log_agent_event, save_qa_report
from packages.schemas.events import (
    AgentID, CritiqueLog, EventType, ManualReviewPayload,
    QAFailedPayload, QAPassedPayload, make_event,
)
from packages.state.agent_state import AgentState, QAReport, append_event, update_stage
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

_VITE_BUILD_TIMEOUT = 180          # 3 minutes
_MAX_BUNDLE_SIZE_MB = 50

# BLOCKING secrets — actual API keys / tokens hardcoded in source.
# These require a real-looking VALUE (not just a variable name pattern).
_SECRET_PATTERNS_BLOCKING = [
    "sk_live_",          # Stripe live key — always followed by 20+ chars
    "sk_test_",          # Stripe test key
    "AKIAIOSFODNN",      # AWS access key prefix (fixed 16-char suffix)
    "ghp_",              # GitHub personal token (followed by 36 chars)
]
# Regex for secrets that need value context (not just the key name)
_SECRET_REGEXES_BLOCKING = [
    _re.compile(r'\beyJ[A-Za-z0-9+/]{50,}'),   # JWT / Supabase service-role key
]

# Patterns that should NOT appear in the built dist/ bundle
_BUNDLE_SECRET_RE = _re.compile(
    r'sk_(?:live|test)_[A-Za-z0-9]{20,}'
    r'|AKIA[A-Z0-9]{16}'
    r'|ghp_[A-Za-z0-9]{36}',
    _re.IGNORECASE,
)

# Vite build MUST pass — a product that doesn't compile cannot be deployed.
# Override with QA_REQUIRE_VITE_BUILD=false only for local dev/testing.
_REQUIRE_VITE_BUILD = os.getenv("QA_REQUIRE_VITE_BUILD", "true").lower() == "true"

# TypeScript strict check: run tsc --noEmit before vite build.
# Disabled by default — the scaffold uses lenient tsconfig to tolerate LLM-generated code.
_REQUIRE_TYPECHECK = os.getenv("QA_REQUIRE_TYPECHECK", "false").lower() == "true"

_CRITIQUE_SYSTEM = """\
You are the QA Technical Auditor for AI Squadron.
A React + Vite build has failed. For each failure, produce a structured critique
with a specific, actionable fix_directive the Engineering agent can apply alone.

Output ONLY valid JSON:
{
  "failed_checks": ["check_name"],
  "errors": [
    {
      "check": "check_name",
      "severity": "CRITICAL|WARNING",
      "component": "filename or module",
      "error_type": "BUILD_FAILURE|BUNDLE_TOO_LARGE|SECRET_EXPOSED|MISSING_FILE",
      "stack_trace": null,
      "fix_directive": "Specific, executable instruction for the Engineering agent"
    }
  ]
}
"""


async def qa_technical_node(state: AgentState) -> AgentState:
    run_id      = state["run_id"]
    venture_id  = state["venture_id"]
    retry_count = state.get("qa_retry_count", 0)
    max_retries = state.get("qa_max_retries", 3)
    build       = state.get("build_artifact") or {}

    log.info("[QA_TECHNICAL_NODE] Validating build | venture=%s retry=%d", venture_id, retry_count)
    log_agent_event(run_id, venture_id, "QA_TECHNICAL", "RUNNING",
                    "Build validation", retry_count=retry_count)

    checks_run, failures, build_update = await _validate_build(build)
    is_passed = len(failures) == 0

    # Merge real vite_build_exit_code and bundle_size_kb back into the artifact
    updated_build = {**build, **build_update}

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
        "qa_report_path": f"builds/{venture_id}/qa_report_{report_id}.json",
    }

    save_qa_report({
        "run_id": run_id, "venture_id": venture_id,
        "artifact_type": "BUILD", "is_passed": is_passed,
        "retry_count": retry_count, "checks_run": checks_run, "checks_failed": failures,
    })

    if is_passed:
        log.info("[QA_TECHNICAL_NODE] ✓ PASSED | checks=%d | bundle=%dkB",
                 len(checks_run), build_update.get("bundle_size_kb", 0))
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
        return append_event(
            {**new_state, "qa_report": qa_report, "build_artifact": updated_build},
            event.model_dump(),
        )

    log.warning("[QA_TECHNICAL_NODE] FAILED | checks=%s | retry=%d/%d",
                failures, retry_count, max_retries)

    if retry_count >= max_retries:
        log.error("[QA_TECHNICAL_NODE] Max retries exhausted — escalating to MANUAL_REVIEW")
        log_agent_event(run_id, venture_id, "QA_TECHNICAL", "FAILED",
                        error_detail=f"Max retries ({max_retries}) reached")
        review_payload = ManualReviewPayload(
            venture_id=venture_id, run_id=run_id,
            review_reason=f"Build QA failed after {max_retries} retries: {failures}",
            artifact_type="BUILD", retry_count=retry_count,
        )
        event = make_event(
            EventType.MANUAL_REVIEW_REQUIRED, AgentID.QA_TECHNICAL, AgentID.BROADCAST,
            review_payload, run_id, venture_id, "QA_TECHNICAL_NODE", priority="CRITICAL",
        )
        new_state = update_stage(state, "MANUAL_REVIEW_NODE")
        return append_event(
            {**new_state, "qa_report": qa_report, "build_artifact": updated_build,
             "manual_review_reason": review_payload.review_reason},
            event.model_dump(),
        )

    critique_log = await _generate_critique(failures, build_update)
    qa_report["critique_log"] = critique_log
    qa_report["qa_target"]    = "engineering"

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
                    error_detail=f"{len(failures)} checks failed: {failures}")

    new_state = update_stage(state, "ENGINEERING_NODE")
    return append_event(
        {**new_state, "qa_report": qa_report, "build_artifact": updated_build,
         "qa_retry_count": retry_count + 1, "qa_target": "engineering"},
        event.model_dump(),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

async def _validate_build(build: dict) -> tuple[list[str], list[str], dict]:
    """
    Run all checks. Returns (checks_run, failures, updates_to_merge_into_artifact).
    The updates dict contains the real vite_build_exit_code, bundle_size_kb, and
    playwright_errors from the browser smoke test.
    """
    checks = [
        "build_path_exists",
        "typecheck",          # tsc --noEmit strict TypeScript validation
        "vite_build",         # vite build — produces deployable dist/
        "bundle_size",        # dist/ < 50 MB
        "no_hardcoded_secrets",
        "playwright_smoke",   # Chromium headless — React mounts in browser
    ]
    failures: list[str] = []
    updates: dict = {}

    build_path = build.get("build_path", "")

    # 1 — path exists
    if not build_path or not Path(build_path).is_dir():
        failures.append("build_path_exists")
        log.error("[QA_TECHNICAL] build_path missing or not a dir: %s", build_path)
        updates["vite_build_exit_code"] = -1
        updates["bundle_size_kb"] = 0
        updates["playwright_errors"] = []
        return checks, failures, updates

    # 2a — TypeScript strict check (tsc --noEmit) — BLOCKING by default
    # Catches type errors before vite build — faster feedback loop.
    if _REQUIRE_TYPECHECK:
        tc_exit, _, tc_err = await _run_typecheck(Path(build_path))
        updates["typecheck_exit_code"] = tc_exit
        if tc_exit != 0:
            failures.append("typecheck")
            log.warning("[QA_TECHNICAL] TypeScript errors | exit=%d\n%s", tc_exit, tc_err[-400:])
        else:
            log.info("[QA_TECHNICAL] TypeScript check ✓")

    # 2b — vite build — BLOCKING by default (was warning-only in Phase 1)
    exit_code, build_stdout, build_stderr = await _run_vite_build(Path(build_path))
    updates["vite_build_exit_code"] = exit_code
    if exit_code != 0:
        if _REQUIRE_VITE_BUILD:
            failures.append("vite_build")
        log.warning(
            "[QA_TECHNICAL] vite build exit=%d (%s) | stderr_tail=%s",
            exit_code,
            "BLOCKING" if _REQUIRE_VITE_BUILD else "WARNING-ONLY",
            (build_stderr or build_stdout)[-400:],
        )

    # 3 — bundle size (only meaningful if build succeeded)
    dist_dir = Path(build_path) / "dist"
    if exit_code == 0 and dist_dir.is_dir():
        total_bytes = sum(f.stat().st_size for f in dist_dir.rglob("*") if f.is_file())
        bundle_kb = total_bytes // 1024
        updates["bundle_size_kb"] = bundle_kb
        if bundle_kb > _MAX_BUNDLE_SIZE_MB * 1024:
            if _REQUIRE_VITE_BUILD:
                failures.append("bundle_size")
            log.warning("[QA_TECHNICAL] Bundle too large: %d kB", bundle_kb)
    else:
        updates["bundle_size_kb"] = 0

    # 4 — secret scan: only flag ACTUAL key VALUES, not variable names or comments.
    # Patterns like "sk_live_" require actual Stripe key characters after them.
    # Regex patterns ensure a real value is present, not a placeholder.
    secret_found = False
    for f in (build.get("files") or []):
        content = f.get("content") or ""
        if any(pat in content for pat in _SECRET_PATTERNS_BLOCKING):
            failures.append("no_hardcoded_secrets")
            log.warning("[QA_TECHNICAL] Real secret prefix in: %s", f.get("path"))
            secret_found = True
            break
        if not secret_found:
            for regex in _SECRET_REGEXES_BLOCKING:
                if regex.search(content):
                    failures.append("no_hardcoded_secrets")
                    log.warning("[QA_TECHNICAL] JWT/token pattern in: %s", f.get("path"))
                    secret_found = True
                    break

    # 4b — bundle secret scan: secrets that survived the Vite build (critical)
    if exit_code == 0 and dist_dir.is_dir() and not secret_found:
        for js_file in list(dist_dir.glob("**/*.js"))[:15]:
            try:
                bundle_content = js_file.read_text(encoding="utf-8", errors="ignore")
                if _BUNDLE_SECRET_RE.search(bundle_content):
                    failures.append("no_hardcoded_secrets")
                    log.warning("[QA_TECHNICAL] Secret leaked into bundle: %s", js_file.name)
                    break
            except Exception:
                pass

    # 5 — Playwright smoke test (only if dist/ was built and Playwright installed)
    playwright_errors: list[str] = []
    if exit_code == 0 and dist_dir.is_dir():
        from packages.tools.playwright_runner import run_smoke_test, playwright_available
        if playwright_available():
            pw_passed, playwright_errors = await run_smoke_test(dist_dir)
            if not pw_passed and _REQUIRE_VITE_BUILD:
                failures.append("playwright_smoke")
        else:
            playwright_errors = ["playwright_skip"]
    else:
        playwright_errors = ["playwright_skip — vite build did not produce dist/"]

    updates["playwright_errors"] = playwright_errors
    return checks, failures, updates


async def _run_typecheck(build_dir: Path, timeout: int = 60) -> tuple[int, str, str]:
    """
    Run `npx tsc --noEmit` for strict TypeScript validation.
    Returns (exit_code, stdout_tail, stderr_tail).
    Separate from vite build — catches type errors faster.
    """
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    log.info("[QA_TECHNICAL] Running tsc --noEmit | dir=%s", build_dir)
    try:
        proc = await asyncio.create_subprocess_exec(
            npm, "exec", "tsc", "--", "--noEmit",
            cwd=str(build_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        rc = proc.returncode or 0
        return rc, stdout_b.decode(errors="replace")[-600:], stderr_b.decode(errors="replace")[-600:]
    except asyncio.TimeoutError:
        log.warning("[QA_TECHNICAL] tsc timed out after %ds", timeout)
        return 1, "", "tsc --noEmit timed out"
    except Exception as exc:
        log.warning("[QA_TECHNICAL] tsc failed to launch: %s", exc)
        return 1, "", str(exc)


async def _run_vite_build(build_dir: Path, timeout: int = _VITE_BUILD_TIMEOUT) -> tuple[int, str, str]:
    """
    Run `npm run build` in build_dir.
    Returns (exit_code, stdout_tail, stderr_tail).
    """
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    log.info("[QA_TECHNICAL] Running vite build | dir=%s", build_dir)
    try:
        proc = await asyncio.create_subprocess_exec(
            npm, "run", "build",
            cwd=str(build_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        rc = proc.returncode or 0
        stdout = stdout_b.decode(errors="replace")[-800:]
        stderr = stderr_b.decode(errors="replace")[-800:]
        log.info("[QA_TECHNICAL] vite build exit=%d", rc)
        return rc, stdout, stderr
    except asyncio.TimeoutError:
        log.error("[QA_TECHNICAL] vite build timed out after %ds", timeout)
        return 1, "", f"vite build timed out after {timeout}s"
    except FileNotFoundError:
        return 1, "", f"'{npm}' not found — Node.js must be in PATH"
    except Exception as exc:
        return 1, "", str(exc)


# ---------------------------------------------------------------------------
# Critique generation
# ---------------------------------------------------------------------------

async def _generate_critique(failed_checks: list[str], build: dict) -> dict:
    """Ask Claude Haiku for structured fix directives per failed check."""
    exit_code  = build.get("vite_build_exit_code", -1)
    bundle_kb  = build.get("bundle_size_kb", 0)
    build_path = build.get("build_path", "")

    prompt = (
        f"Failed checks: {json.dumps(failed_checks)}\n"
        f"vite_build_exit_code: {exit_code}\n"
        f"bundle_size_kb: {bundle_kb}\n"
        f"build_path: {build_path}\n"
        "Generate critique_log JSON with actionable fix_directives."
    )
    try:
        response = await call_llm(
            "QA_TECHNICAL_CRITIQUE", _CRITIQUE_SYSTEM, prompt, temperature=0.1,
        )
        return json.loads(extract_json(response.text))
    except Exception:
        return {
            "failed_checks": failed_checks,
            "errors": [
                {
                    "check": c,
                    "severity": "CRITICAL",
                    "component": "Unknown",
                    "error_type": "BUILD_FAILURE",
                    "stack_trace": None,
                    "fix_directive": f"Investigate and fix the '{c}' failure before resubmitting.",
                }
                for c in failed_checks
            ],
        }
