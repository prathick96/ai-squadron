"""
packages/agents/product/engineering_team.py
Engineering Team — TechSpec → deployable React 19 + Vite codebase written to disk.

Model:   claude-sonnet-4-6
Input:   tech_spec (initial) | qa_report.critique_log (retry patch)
Output:  build_artifact with real build_path, files written to builds/{venture_id}/

Architecture (lessons learned from 30+ runs):
  SCAFFOLD owns all infrastructure — written deterministically, never by LLM:
    package.json, vite.config.ts, tsconfig.json, index.html, src/main.tsx
    src/App.tsx              ← routing + Supabase check (was biggest LLM failure)
    src/lib/supabase.ts      ← graceful degradation when env vars missing
    src/components/SetupRequired.tsx  ← shown when VITE_SUPABASE_* not set

  LLM generates ONLY feature-specific files (3 files max):
    src/pages/Home.tsx       ← main feature page
    src/types.ts             ← domain types
    src/hooks/useData.ts     ← TanStack Query hook

  This split guarantees React always mounts and the app always renders
  something meaningful — the only pending step for the user is Supabase keys.

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
    # ------------------------------------------------------------------
    # package.json — pinned deps, no LLM can change these
    # ------------------------------------------------------------------
    "package.json": json.dumps({
        "name": "ai-squadron-saas",
        "version": "0.1.0",
        "private": True,
        "type": "module",
        "scripts": {
            "dev":       "vite",
            "build":     "vite build",
            "preview":   "vite preview",
            "typecheck": "tsc --noEmit",
            "start":     "serve -s dist --listen $PORT",
        },
        "dependencies": {
            "@supabase/supabase-js": "^2.45.0",
            "@tanstack/react-query": "^5.59.0",
            "@paddle/paddle-js":     "^1.2.0",
            "posthog-js":            "^1.182.0",
            "react":                 "^19.0.0",
            "react-dom":             "^19.0.0",
            "react-router-dom":      "^6.28.0",
            "serve":                 "^14.2.0",
        },
        "devDependencies": {
            "@types/react":          "^19.0.0",
            "@types/react-dom":      "^19.0.0",
            "@vitejs/plugin-react":  "^4.3.3",
            "typescript":            "^5.6.0",
            "vite":                  "^6.0.0",
        },
    }, indent=2),

    # ------------------------------------------------------------------
    # vite.config.ts — deterministic, never changes
    # ------------------------------------------------------------------
    "vite.config.ts": """\
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: { output: { manualChunks: undefined } },
  },
})
""",

    # ------------------------------------------------------------------
    # tsconfig.json — lenient settings prevent LLM-generated code from
    # failing on unused vars, implicit any, etc.
    # ------------------------------------------------------------------
    "tsconfig.json": json.dumps({
        "compilerOptions": {
            "target":                     "ES2020",
            "useDefineForClassFields":    True,
            "lib":                        ["ES2020", "DOM", "DOM.Iterable"],
            "module":                     "ESNext",
            "skipLibCheck":               True,   # ignore type errors in node_modules
            "moduleResolution":           "bundler",
            "allowImportingTsExtensions": True,
            "isolatedModules":            True,
            "moduleDetection":            "force",
            "noEmit":                     True,
            "jsx":                        "react-jsx",
            "strict":                     False,  # off: LLM code has implicit any
            "noUnusedLocals":             False,
            "noUnusedParameters":         False,
            "noImplicitAny":              False,
            "noFallthroughCasesInSwitch": True,
        },
        "include": ["src"],
    }, indent=2),

    "tsconfig.node.json": json.dumps({
        "compilerOptions": {
            "target":                  "ES2022",
            "lib":                     ["ES2023"],
            "module":                  "ESNext",
            "moduleResolution":        "bundler",
            "allowSyntheticDefaultImports": True,
            "strict":                  False,
            "noEmit":                  True,
            "skipLibCheck":            True,
        },
        "include": ["vite.config.ts"],
    }, indent=2),

    # ------------------------------------------------------------------
    # index.html — inline reset + security meta tags
    # Primary security headers come from nginx (CSP, HSTS, etc.).
    # Meta tags here are a belt-and-suspenders fallback for local dev.
    # ------------------------------------------------------------------
    "index.html": """\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <!-- Security: prevent MIME sniffing -->
    <meta http-equiv="X-Content-Type-Options" content="nosniff" />
    <!-- Security: prevent clickjacking in browsers that don't honour the header -->
    <meta http-equiv="X-Frame-Options" content="SAMEORIGIN" />
    <!-- Security: CSP fallback for local dev (nginx provides the authoritative header) -->
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.paddle.com https://us.i.posthog.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://*.supabase.co https://us.i.posthog.com https://api.razorpay.com https://lumberjack.razorpay.com; frame-src https://api.razorpay.com; frame-ancestors 'none';" />
    <title>App</title>
    <style>
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: system-ui, -apple-system, sans-serif; background: #fff; color: #111; }
      #root { min-height: 100vh; }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",

    "src/vite-env.d.ts": '/// <reference types="vite/client" />\n',

    # ------------------------------------------------------------------
    # src/main.tsx — error boundary + React Query + PostHog
    # ------------------------------------------------------------------
    "src/main.tsx": """\
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import posthog from 'posthog-js'
import App from './App.tsx'

// PostHog — only fires when VITE_POSTHOG_KEY is set (free tier safe)
const posthogKey = import.meta.env.VITE_POSTHOG_KEY as string | undefined
if (posthogKey) {
  posthog.init(posthogKey, {
    api_host: (import.meta.env.VITE_POSTHOG_HOST as string | undefined) ?? 'https://us.i.posthog.com',
    capture_pageview: true,
    persistence: 'localStorage',
  })
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 60_000 } },
})

// Explicit null-check prevents confusing 'Cannot read properties of null' errors
const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('Root element not found — check index.html for <div id="root">')

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
""",

    # ------------------------------------------------------------------
    # src/lib/supabase.ts — graceful degradation when env vars missing.
    # isSupabaseConfigured is exported so App.tsx can show SetupRequired.
    # ------------------------------------------------------------------
    "src/lib/supabase.ts": """\
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL  as string | undefined
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

/** True when both VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are set */
export const isSupabaseConfigured = Boolean(
  url && url.startsWith('https://') && key && key.length > 20
)

/**
 * Supabase client — null when env vars are not configured.
 * Always guard with: if (!supabase) return []
 */
export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(url!, key!)
  : null
""",

    # ------------------------------------------------------------------
    # src/components/SetupRequired.tsx — rendered by App when Supabase
    # env vars are missing. Gives the user a clear next step.
    # ------------------------------------------------------------------
    "src/components/SetupRequired.tsx": """\
export default function SetupRequired() {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
      background: '#f8fafc',
    }}>
      <div style={{
        maxWidth: 480,
        width: '100%',
        background: '#fff',
        border: '1px solid #e2e8f0',
        borderRadius: 12,
        padding: 40,
        textAlign: 'center',
      }}>
        <div style={{ fontSize: 48, marginBottom: 20 }}>⚙️</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 10 }}>
          Connect Your Database
        </h1>
        <p style={{ color: '#64748b', lineHeight: 1.6, marginBottom: 28 }}>
          This app needs Supabase for authentication and data storage.
          Add these two environment variables to get started.
        </p>
        <div style={{
          background: '#f1f5f9',
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          padding: '14px 18px',
          fontFamily: 'monospace',
          fontSize: 13,
          textAlign: 'left',
          marginBottom: 24,
          lineHeight: 2,
        }}>
          <span style={{ color: '#94a3b8' }}># .env or Railway environment vars</span><br />
          <span style={{ color: '#0f172a' }}>VITE_SUPABASE_URL=https://xxx.supabase.co</span><br />
          <span style={{ color: '#0f172a' }}>VITE_SUPABASE_ANON_KEY=eyJ...</span>
        </div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          <a
            href="https://supabase.com/dashboard"
            target="_blank"
            rel="noreferrer"
            style={{
              padding: '10px 22px',
              background: '#3ecf8e',
              color: '#fff',
              borderRadius: 8,
              textDecoration: 'none',
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            Get Supabase Keys →
          </a>
          <a
            href="https://app.supabase.com/project/_/settings/api"
            target="_blank"
            rel="noreferrer"
            style={{
              padding: '10px 22px',
              background: '#f1f5f9',
              color: '#334155',
              borderRadius: 8,
              textDecoration: 'none',
              fontWeight: 600,
              fontSize: 14,
              border: '1px solid #e2e8f0',
            }}
          >
            Project Settings
          </a>
        </div>
      </div>
    </div>
  )
}
""",

    # ------------------------------------------------------------------
    # src/App.tsx — routing shell.  Moved from LLM → scaffold because LLM
    # was the #1 source of TypeScript errors and React mount failures.
    # Shows SetupRequired until VITE_SUPABASE_* are configured.
    # ------------------------------------------------------------------
    "src/App.tsx": """\
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { isSupabaseConfigured } from './lib/supabase'
import SetupRequired from './components/SetupRequired'
import Home from './pages/Home'

export default function App() {
  if (!isSupabaseConfigured) {
    return <SetupRequired />
  }

  return (
    <BrowserRouter>
      <nav style={{
        padding: '0 24px',
        height: 52,
        borderBottom: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        gap: 24,
        background: '#fff',
      }}>
        <Link to="/" style={{ fontWeight: 700, textDecoration: 'none', color: '#0f172a', fontSize: 16 }}>
          App
        </Link>
      </nav>
      <main style={{ padding: '32px 24px', maxWidth: 1100, margin: '0 auto' }}>
        <Routes>
          <Route path="/" element={<Home />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
""",
}

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Engineering Team Agent for AI Squadron.
You generate React 19 + TypeScript feature files for a SaaS MVP.

ALREADY PROVIDED BY SCAFFOLD (do NOT regenerate):
  package.json, vite.config.ts, tsconfig.json, index.html
  src/vite-env.d.ts
  src/main.tsx         — React root, QueryClient, PostHog
  src/App.tsx          — BrowserRouter, routes, nav, SetupRequired gate
  src/lib/supabase.ts  — exports: supabase (SupabaseClient | null), isSupabaseConfigured
  src/components/SetupRequired.tsx  — shown when Supabase env vars missing

GENERATE ONLY THESE 3 FILES (max 80 lines each):

1. src/types.ts
   — Domain types for this specific app (e.g. interface Invoice, type User)
   — No imports needed

2. src/hooks/useData.ts
   — ONE TanStack Query hook that fetches the core data from Supabase
   — Import pattern: import { supabase } from '../lib/supabase'
   — Guard: if (!supabase) return []
   — Return typed data from useQuery

3. src/pages/Home.tsx
   — The main feature page shown at route "/"
   — Import from '../lib/supabase', '../types', '../hooks/useData'
   — Simple, functional UI — no complex state management
   — Handle loading / error states

STRICT RULES:
  Only import from: react, react-router-dom, @tanstack/react-query, ../lib/supabase, ../types, ../hooks/useData
  NEVER import: axios, zod, lucide-react, shadcn, dayjs, lodash, or any other library
  NEVER import from @supabase/supabase-js directly (use ../lib/supabase instead)
  Keep each file under 80 lines
  Use plain inline styles — no CSS modules, no Tailwind, no styled-components

SECURITY RULES (enforced by QA and Security agents):
  NEVER hardcode secrets, API keys, tokens, or passwords in source — use import.meta.env.VITE_*
  NEVER use dangerouslySetInnerHTML — use React's text rendering instead
  NEVER store auth tokens in localStorage — Supabase handles session storage securely
  NEVER log sensitive fields: console.log(password), console.log(token), etc.
  NEVER use string interpolation in database queries — use Supabase typed selectors
  ALWAYS guard Supabase calls: if (!supabase) return (never assume it's configured)
  ALWAYS handle errors gracefully — never expose stack traces or internal paths to users

SUPABASE PATTERN (use exactly):
  import { supabase } from '../lib/supabase'
  const { data } = await supabase!.from('table_name').select('*')

OUTPUT RULE — CRITICAL:
  First character of response MUST be {
  Last character of response MUST be }
  No explanations, no markdown, no preamble.
  {"files": [{"path": "src/types.ts", "content": "..."}, ...]}
"""

_BUILD_TEMPLATE = """\
Build a SaaS app for this niche and tech spec.

Niche: {niche}
Venture type: {venture_type}

TechSpec:
{tech_spec}

The scaffold already provides: App.tsx, supabase.ts, SetupRequired.tsx, main.tsx.
Generate ONLY: src/types.ts, src/hooks/useData.ts, src/pages/Home.tsx
Output JSON only — first character must be {{
"""

_RETRY_TEMPLATE = """\
Previous vite build failed. Apply ONLY these targeted patches — do NOT regenerate unrelated files.

Fix directives:
{critique_log}

Output ONLY the corrected files as JSON:
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
    venture_brief = state.get("venture_brief") or {}
    niche = venture_brief.get("niche") or tech_spec.get("niche") or tech_spec.get("venture_id") or ""
    if not niche:
        log.error("[ENGINEERING_NODE] niche not found in venture_brief or tech_spec — pipeline state incomplete")

    venture_type  = tech_spec.get("product_type", "MICRO_SAAS")
    user_prompt = (
        _RETRY_TEMPLATE.format(
            critique_log=json.dumps(qa_report.get("critique_log", {}), indent=2),
        ) if is_retry else
        _BUILD_TEMPLATE.format(
            niche=niche,
            venture_type=venture_type,
            tech_spec=json.dumps(tech_spec, indent=2),
        )
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

    # Persist file contents to Supabase so they survive Railway redeploys.
    # /tmp/ is ephemeral; Supabase is permanent. Done before npm install
    # so a slow npm doesn't delay persistence.
    build_hash_early = hashlib.sha256(json.dumps(llm_files).encode()).hexdigest()[:16]
    try:
        from packages.db.pipeline import persist_build_artifact
        persist_build_artifact(venture_id, run_id, build_hash_early, llm_files)
    except Exception as exc:
        log.warning("[ENGINEERING_NODE] Supabase persist failed (non-blocking): %s", exc)

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
    # React ecosystem
    "react", "react-dom", "react-router-dom",
    # Data fetching
    "@tanstack/react-query",
    # Supabase (direct SDK + local wrapper)
    "@supabase/supabase-js",
    # Analytics (scaffold-injected)
    "posthog-js",
    # Relative imports — always fine
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
