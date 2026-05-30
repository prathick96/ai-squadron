"""
packages/agents/product/engineering_team.py
Engineering Team — TechSpec → deployable React 19 + Vite codebase written to disk.

Model:   claude-sonnet-4-6
Input:   tech_spec (initial) | qa_report.critique_log (retry patch)
Output:  build_artifact with real build_path, files written to builds/{venture_id}/

Disk layout:
  builds/{venture_id}/
    package.json          ← scaffold (deterministic, always written on first run)
    vite.config.ts        ← scaffold
    tsconfig.json         ← scaffold
    tsconfig.node.json    ← scaffold
    index.html            ← scaffold
    src/vite-env.d.ts     ← scaffold
    src/main.tsx          ← scaffold
    src/App.tsx           ← LLM-generated (and everything under src/ beyond main.tsx)

On retry: only patched files are overwritten; node_modules/ is reused.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

from packages.db.client import log_agent_event
from packages.schemas.events import (
    AgentID, BuildCompletePayload, EventType, TestResults, make_event,
)
from packages.state.agent_state import AgentState, BuildArtifact, append_event, update_stage
from packages.tools.llm import call_llm, extract_json

log = logging.getLogger(__name__)

# Builds go to /tmp so they're always writable regardless of where the app is deployed.
# /app/ on Railway is a read-optimised overlay; /tmp/ is a writable tmpfs.
# Use BUILDS_DIR env var to override (e.g. for local dev: BUILDS_DIR=./builds).
_BUILDS_ROOT = Path(os.getenv("BUILDS_DIR", "/tmp/squadron-builds"))

# ---------------------------------------------------------------------------
# Fixed scaffold — written on every initial build, never by the LLM
# ---------------------------------------------------------------------------

_SCAFFOLD: dict[str, str] = {
    "package.json": json.dumps({
        "name": "ai-squadron-app",
        "version": "0.1.0",
        "private": True,
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
            "typecheck": "tsc --noEmit",
            "start": "serve -s dist --listen $PORT",
        },
        "dependencies": {
            "@supabase/supabase-js": "^2.45.0",
            "@tanstack/react-query": "^5.59.0",
            "posthog-js": "^1.182.0",
            "react": "^19.0.0",
            "react-dom": "^19.0.0",
            "react-router-dom": "^6.28.0",
            "serve": "^14.2.0",
        },
        "devDependencies": {
            "@types/react": "^19.0.0",
            "@types/react-dom": "^19.0.0",
            "@vitejs/plugin-react": "^4.3.3",
            "typescript": "^5.6.0",
            "vite": "^6.0.0",
        },
    }, indent=2),

    "vite.config.ts": """\
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', sourcemap: false },
})
""",

    "tsconfig.json": json.dumps({
        "compilerOptions": {
            "target": "ES2020",
            "useDefineForClassFields": True,
            "lib": ["ES2020", "DOM", "DOM.Iterable"],
            "module": "ESNext",
            "skipLibCheck": True,
            "moduleResolution": "bundler",
            "allowImportingTsExtensions": True,
            "isolatedModules": True,
            "moduleDetection": "force",
            "noEmit": True,
            "jsx": "react-jsx",
            "strict": True,
            "noUnusedLocals": False,
            "noUnusedParameters": False,
            "noFallthroughCasesInSwitch": True,
        },
        "include": ["src"],
    }, indent=2),

    "tsconfig.node.json": json.dumps({
        "compilerOptions": {
            "target": "ES2022",
            "lib": ["ES2023"],
            "module": "ESNext",
            "moduleResolution": "bundler",
            "allowSyntheticDefaultImports": True,
            "strict": True,
            "noEmit": True,
            "skipLibCheck": True,
        },
        "include": ["vite.config.ts"],
    }, indent=2),

    "index.html": """\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",

    "src/vite-env.d.ts": '/// <reference types="vite/client" />\n',

    "src/main.tsx": """\
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import posthog from 'posthog-js'
import App from './App.tsx'

// PostHog analytics — only initialises when VITE_POSTHOG_KEY is set.
// Gives growth feedback (pageviews, signups, conversions) from day 1.
const posthogKey = import.meta.env.VITE_POSTHOG_KEY as string | undefined
if (posthogKey) {
  posthog.init(posthogKey, {
    api_host: (import.meta.env.VITE_POSTHOG_HOST as string | undefined)
      ?? 'https://us.i.posthog.com',
    capture_pageview: true,
    capture_pageleave: true,
    persistence: 'localStorage',
  })
}

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
""",
}

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Engineering Team Agent for AI Squadron.
You generate React 19 + TypeScript source files for a SaaS MVP.

The scaffold (package.json, vite.config.ts, tsconfig, index.html, src/main.tsx) \
is already written — do NOT regenerate those.

Generate ONLY these 5 source files (keep each SHORT — max 60 lines each):
  src/App.tsx           — routing shell with react-router-dom
  src/types.ts          — shared TypeScript interfaces only
  src/lib/supabase.ts   — Supabase client init only
  src/pages/Home.tsx    — one main page
  src/hooks/useData.ts  — one TanStack Query hook

ALLOWED IMPORTS (already in package.json — use ONLY these):
  react, react-dom, react-router-dom
  @tanstack/react-query
  @supabase/supabase-js
  posthog-js

NEVER import anything else. If you need a utility, write it inline.
Use import.meta.env.VITE_* for all config values.

CRITICAL OUTPUT RULE:
  Your ENTIRE response must be ONLY the JSON object below.
  Do NOT write any explanation, preamble, or text before or after the JSON.
  The VERY FIRST character of your response must be the opening brace {
  The VERY LAST character of your response must be the closing brace }

  {"files": [{"path": "src/...", "content": "..."}]}
"""

_BUILD_TEMPLATE = """\
TechSpec:
{tech_spec}

Generate the application source files listed above.
Output ONLY the JSON.
"""

_RETRY_TEMPLATE = """\
Previous vite build failed. Apply ONLY these targeted patches — do not regenerate \
unrelated files.

Fix directives:
{critique_log}

Output ONLY the corrected files:
{{"files": [{{"path": "src/...", "content": "..."}}]}}
"""


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def engineering_team_node(state: AgentState) -> AgentState:
    run_id     = state["run_id"]
    venture_id = state["venture_id"]
    tech_spec  = state.get("tech_spec") or {}
    qa_report  = state.get("qa_report") or {}
    retry_count = state.get("qa_retry_count", 0)
    is_retry   = retry_count > 0

    build_dir  = _BUILDS_ROOT / venture_id
    task = f"QA patch #{retry_count}" if is_retry else "Full build"

    log.info("[ENGINEERING_NODE] %s | venture=%s | dir=%s", task, venture_id, build_dir)
    log_agent_event(run_id, venture_id, "ENGINEERING_TEAM", "RUNNING", task,
                    retry_count=retry_count)

    # ---- Call LLM ----
    user_prompt = (
        _RETRY_TEMPLATE.format(
            critique_log=json.dumps(qa_report.get("critique_log", {}), indent=2),
        ) if is_retry else
        _BUILD_TEMPLATE.format(tech_spec=json.dumps(tech_spec, indent=2))
    )

    response = None
    try:
        response = await call_llm(
            "ENGINEERING_TEAM", _SYSTEM_PROMPT, user_prompt,
            temperature=0.1, max_tokens=8192,   # hard ceiling for claude-sonnet-4-6
        )
        # extract_json handles preamble text ("Here is the code: {...}") and
        # code fences (``` json {...} ```) — the "char 0" JSONDecodeError is
        # always caused by a non-JSON first character.
        json_text  = extract_json(response.text)
        build_data: dict = json.loads(json_text)
    except Exception as exc:
        tokens = response.total_tokens if response else 0
        log.error("[ENGINEERING_NODE] LLM call failed: %s | tokens=%d | raw_start=%r",
                  exc, tokens, (response.text[:120] if response else ""))
        log_agent_event(run_id, venture_id, "ENGINEERING_TEAM", "FAILED",
                        error_detail=str(exc), tokens_used=tokens)
        return {**state, "last_error": str(exc)}

    llm_files: list[dict] = build_data.get("files", [])

    # ---- Write files to disk ----
    try:
        _write_files(build_dir, llm_files, is_retry=is_retry)
    except Exception as exc:
        log.error("[ENGINEERING_NODE] Disk write failed: %s", exc)
        log_agent_event(run_id, venture_id, "ENGINEERING_TEAM", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    # ---- npm install (skip on retry if node_modules exists) ----
    node_modules = build_dir / "node_modules"
    if not is_retry or not node_modules.exists():
        npm_rc, npm_err = await _run_npm_install(build_dir)
        if npm_rc != 0:
            msg = f"npm install failed (exit {npm_rc}): {npm_err[:300]}"
            log.error("[ENGINEERING_NODE] %s", msg)
            log_agent_event(run_id, venture_id, "ENGINEERING_TEAM", "FAILED", error_detail=msg)
            return {**state, "last_error": msg}
        log.info("[ENGINEERING_NODE] npm install ✓")
    else:
        log.info("[ENGINEERING_NODE] node_modules exists — skipping npm install (retry)")

    # ---- Build artifact ----
    all_paths  = [f["path"] for f in llm_files]
    components = [p for p in all_paths if "/components/" in p or "/pages/" in p]
    build_hash = hashlib.sha256(json.dumps(llm_files).encode()).hexdigest()[:16]
    patches    = [
        e.get("component", "")
        for e in (qa_report.get("critique_log") or {}).get("errors", [])
    ] if is_retry else []

    payload = BuildCompletePayload(
        venture_id=venture_id,
        build_path=str(build_dir),
        build_hash=build_hash,
        components_generated=components,
        test_results=TestResults(
            total=len(components), passed=len(components), failed=0, coverage_pct=0.0,
        ),
        vite_build_exit_code=-1,        # QA will overwrite with the real value
        bundle_size_kb=0,               # QA will overwrite after vite build
        dependencies=list(_SCAFFOLD_DEPS),
        is_retry=is_retry,
        retry_patches_applied=patches,
    )

    event = make_event(
        EventType.BUILD_COMPLETE, AgentID.ENGINEERING_TEAM, AgentID.QA_TECHNICAL,
        payload, run_id, venture_id, "ENGINEERING_NODE",
        token_cost=response.total_tokens, latency_ms=response.latency_ms,
    )

    # Store files list for QA's secret scan
    build_artifact: BuildArtifact = {**payload.model_dump(), "files": llm_files}  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "ENGINEERING_TEAM", "SUCCESS",
                    tokens_used=response.total_tokens)
    log.info("[ENGINEERING_NODE] ✓ %d files written | hash=%s | dir=%s",
             len(llm_files) + len(_SCAFFOLD), build_hash, build_dir)

    new_state = update_stage(state, "QA_TECHNICAL_NODE")
    return append_event({**new_state, "build_artifact": build_artifact}, event.model_dump())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCAFFOLD_DEPS = [
    "react@19", "react-dom@19", "react-router-dom@6",
    "@tanstack/react-query@5", "@supabase/supabase-js@2",
    "posthog-js@1",
    "serve@14",
    "vite@6", "@vitejs/plugin-react", "typescript@5",
]


_ALLOWED_IMPORT_PREFIXES = (
    # React / routing
    "react", "react-dom", "react-router-dom",
    # Data fetching
    "@tanstack/react-query",
    # Supabase
    "@supabase/supabase-js",
    # Analytics (injected by scaffold)
    "posthog-js",
    # Built-in TypeScript/Node — always fine
    "node:", "./", "../", "/", "@/",
)


def _sanitise_llm_files(llm_files: list[dict]) -> list[dict]:
    """
    Strip files that import packages not in the scaffold's package.json.
    This prevents vite build failures caused by the LLM hallucinating
    library names (e.g. 'import { toast } from "sonner"').

    Files with unknown imports are replaced with a safe stub so the rest
    of the app can still compile and the QA retry can patch just that file.
    """
    import re
    import_re = re.compile(r"""(?:^|\n)\s*import\s+.*?\s+from\s+['"]([^'"]+)['"]""")

    sanitised = []
    for f in llm_files:
        path    = f.get("path", "")
        content = f.get("content", "")
        unknown = []
        for pkg in import_re.findall(content):
            if not any(pkg.startswith(p) for p in _ALLOWED_IMPORT_PREFIXES):
                unknown.append(pkg)
        if unknown:
            log.warning("[ENGINEERING_NODE] Stripping %s — unknown imports: %s", path, unknown)
            stub = f"// AUTO-STUB: unknown imports {unknown} removed\n"
            stub += "export default function Placeholder() { return null; }\n"
            sanitised.append({"path": path, "content": stub})
        else:
            sanitised.append(f)
    return sanitised


def _write_files(build_dir: Path, llm_files: list[dict], *, is_retry: bool) -> None:
    """Write scaffold + LLM files to build_dir."""
    build_dir.mkdir(parents=True, exist_ok=True)

    if not is_retry:
        for rel_path, content in _SCAFFOLD.items():
            dest = build_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        log.debug("[ENGINEERING_NODE] Scaffold written (%d files)", len(_SCAFFOLD))

    for f in _sanitise_llm_files(llm_files):
        rel = f.get("path", "").lstrip("/")
        if not rel:
            continue
        dest = build_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f.get("content", ""), encoding="utf-8")
    log.debug("[ENGINEERING_NODE] LLM files written (%d files)", len(llm_files))


def _npm_executable() -> str:
    """Return the correct npm executable name for this platform."""
    return "npm.cmd" if sys.platform == "win32" else "npm"


async def _run_npm_install(build_dir: Path, timeout: int = 300) -> tuple[int, str]:
    """
    Run `npm install` in build_dir.
    Returns (exit_code, stderr_tail).

    Notes:
      --no-audit / --no-fund   : skip network roundtrips for security audit + sponsor info
      --cache /tmp/.npm        : explicit writable cache dir (/app/.npm may be read-only)
      --legacy-peer-deps       : avoid peer-dep conflicts from auto-generated package.json
    """
    npm = _npm_executable()
    npm_cache = str(_BUILDS_ROOT.parent / ".npm-cache")
    try:
        proc = await asyncio.create_subprocess_exec(
            npm, "install",
            "--no-audit", "--no-fund",
            "--cache", npm_cache,
            "--legacy-peer-deps",
            cwd=str(build_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, stderr_bytes.decode(errors="replace")[-500:]
    except asyncio.TimeoutError:
        return 1, f"npm install timed out after {timeout}s"
    except FileNotFoundError:
        return 1, f"'{npm}' not found — ensure Node.js is installed and in PATH"
    except Exception as exc:
        return 1, str(exc)
