# AI Squadron — Complete Project Review

**Last Updated:** May 23, 2026  
**Status:** Phase 0 Scaffold (Complete) → Phase 1 Wedge (In Progress)  
**Current Version:** 0.1.0

---

## Executive Summary

**AI Squadron** is an autonomous venture orchestration system that uses LangGraph and multi-agent LLMs (Gemini 2.5 Pro, Claude Sonnet, etc.) to build SaaS products and media channels end-to-end. A 12-node pipeline transforms a market niche into:

1. **MICRO_SAAS** → Fully deployed React 19 + Vite app on Railway
2. **MEDIA_CHANNEL** → YouTube/TikTok-ready video with ElevenLabs audio & Remotion rendering
3. **AFFILIATE_SITE** → SEO-optimized content site

The **Revenue Engine** (external cron) reads portfolio metrics and emits **SCALE** or **KILL** signals based on confidence scoring. A **Command Center** dashboard (React 19 + Recharts) visualizes agent health and revenue truth in real time.

---

## Architecture Overview

### The 12-Node Pipeline

```
RESEARCH_NODE (Kimi K2.x via OpenRouter — 3 scouts + debate)
    ↓
CEO_NODE (Gemini 2.5 Pro — final VentureBrief + go_decision)
    ↓ go_decision_edge
PRODUCT_NODE (Gemini 2.0 Flash)
    ↓ product_routing_edge (MICRO_SAAS vs MEDIA_CHANNEL)
[ENGINEERING_NODE] ──────── [CONTENT_NODE]
(Claude Sonnet)           (Gemini 2.0 Flash)
    ↓                            ↓
    └─────────────────────────────┘
                    ↓
            QA_NODE (QA Auditor)
                    ↓ qa_routing_edge
    ┌─────────────────┬──────────────────┐
    ↓                 ↓                  ↓
[FIX LOOP]      SECURITY_NODE      MANUAL_REVIEW_NODE
(max 3 retries) (rule engine)       (human gate)
                    ↓
        ACCOUNT_DISTRIBUTION_NODE
                    ↓
            DEPLOYMENT_NODE
                    ↓
        MARKETING_NODE (sequential)
                    ↓
            GLOBAL_NODE (i18n)
                    ↓
            GROWTH_NODE
                    ↓
                  END
```

### Model Assignments

| Agent | Model | Rationale |
|-------|-------|-----------|
| Market Research | Kimi K2.x (OpenRouter) | 3 parallel scouts + debate for trend analysis |
| CEO | Gemini 2.5 Pro | Strategic synthesis over trend datasets |
| Product | Gemini 2.0 Flash | TechSpec generation (cost-efficient) |
| Engineering | Claude Sonnet 4.6 | Best code generation quality |
| Content | Gemini 2.0 Flash | Script, audio, video, thumbnail orchestration |
| QA Auditor | Claude Haiku 4.5 (critique) | Precise fix directives |
| All Others | Gemini 2.0 Flash | Cost-efficient, 1M context, fast |

### Event Bus (Dual Mode)

- **Production:** Redis Streams (`REDIS_URL` set) — horizontal scale, persistent log
- **Development:** asyncio.Queue (no Redis required) — perfect for local testing

Every agent publishes `EventEnvelope` (Pydantic) with:
- `event_type` (e.g., `VENTURE_BRIEF_READY`, `QA_FAILED`)
- `source_agent`, `target_agent`
- `payload` (JSON artifact)
- `metadata` (run_id, venture_id, token_cost, latency_ms)

### State Flow (AgentState TypedDict)

Every node reads and mutates a single immutable `AgentState` dictionary:

```python
class AgentState(TypedDict):
    run_id: str                    # UUID — immutable
    venture_id: str                # ven_XXXXX — immutable
    pipeline_stage: str            # Current node name
    research_dossier: ResearchDossier | None
    venture_brief: VentureBrief | None
    tech_spec: TechSpec | None
    build_artifact: BuildArtifact | None  # Engineering output
    content_package: ContentPackage | None  # Content output
    qa_report: QAReport | None
    qa_retry_count: int            # For retry loop
    qa_max_retries: int            # Default: 3
    qa_target: str | None          # engineering | content
    security_clearance: SecurityClearance | None
    account_distribution_plan: AccountDistributionPlan | None
    deployment_receipt: DeploymentReceipt | None
    # ... plus 20+ other fields for each agent's outputs
```

---

## Technology Stack

| Layer | Tech | Why |
|-------|------|-----|
| **Orchestration** | LangGraph 0.2+ | Conditional QA loops, stateful retries, native graph DSL |
| **Agent Runtime** | Python 3.11+ | Existing modules, rich async/await support |
| **LLM Routing** | Anthropic SDK, google-genai, OpenRouter | Multi-vendor support, cost optimization |
| **Event Bus** | Redis Streams (prod), asyncio.Queue (dev) | Append-only audit trail, horizontal scale |
| **Database** | Supabase (PostgreSQL) | Auth, RLS, Vault for OAuth tokens, real-time subs |
| **SaaS Frontend** | React 19 + Vite + TypeScript | Fast dev + build, tree-shaking |
| **Command Center** | React 19 + Vite + Recharts | Live charts, agent grid, manual review queue |
| **API** | FastAPI + Uvicorn | Thin read layer, WebSocket for live events |
| **Local Infra** | Docker Compose (PostgreSQL + Redis + RedisInsight) | Full dev parity with prod |
| **Deployment** | Railway Hobby → Pro | Free tier $5, scale on revenue, automatic SSL |
| **Media APIs** | YouTube Data v3, TikTok Official, Instagram Graph | Approved channels only |
| **Audio** | ElevenLabs (free 10k chars/mo → paid) | Human-likeness ≥ 0.85 required |
| **Video** | Remotion + FFmpeg | Programmatic video generation on Railway |
| **Thumbnails** | fal.ai Flux | Fast gen images, no watermarks |
| **Trends** | pytrends (Google Trends), Tavily API | CEO input for niche selection |
| **Analytics** | PostHog (free tier) | Growth feedback loop |
| **Payments** | Stripe | SaaS MRR tracking |

---

## Directory Structure

```
ai-squadron/
├── apps/
│   ├── orchestrator/
│   │   ├── graph.py               # LangGraph assembly (13 nodes + edges)
│   │   └── main.py                # CLI: dry-run, single, watch modes
│   ├── revenue-engine/
│   │   └── main.py                # Daily cron: SCALE/KILL emitter
│   ├── api/
│   │   ├── main.py                # FastAPI: REST + WebSocket
│   │   └── data/
│   │       ├── mock_dashboard.py  # Fake data for Phase 0
│   │       └── revenue_dashboard.py  # Supabase live data (Day 2+)
│   └── command-center/            # React 19 dashboard (Vite)
│       ├── src/
│       │   ├── App.tsx
│       │   ├── api.ts             # Fetch from /api/*
│       │   ├── main.tsx
│       │   └── styles.css
│       ├── package.json
│       ├── tsconfig.json
│       └── vite.config.ts
│
├── packages/
│   ├── agents/                    # 12 agent node files
│   │   ├── market_research.py     # Kimi scout orchestration
│   │   ├── ceo_niche_scout.py
│   │   ├── product_team.py
│   │   ├── engineering_team.py    # Vite React output
│   │   ├── content_team.py        # ElevenLabs + Remotion
│   │   ├── qa_auditor.py          # Retry loop orchestrator
│   │   ├── security_agent.py      # ToS validation
│   │   ├── account_distribution.py
│   │   ├── deployment_team.py     # Railway + YouTube upload
│   │   ├── marketing_team.py
│   │   ├── global_approach.py     # i18n, localization
│   │   └── growth_team.py         # Growth signal & reporting
│   │
│   ├── schemas/
│   │   └── events.py              # Pydantic EventEnvelope + all payloads (522 lines)
│   │
│   ├── state/
│   │   └── agent_state.py         # AgentState TypedDict + init_state() factory
│   │
│   ├── bus/
│   │   └── event_bus.py           # Dual-mode (Redis / asyncio.Queue)
│   │
│   ├── db/
│   │   ├── client.py              # Supabase client + NullDB fallback
│   │   ├── pipeline.py            # DB helpers (begin/complete run, persist events)
│   │   └── migrations/
│   │       ├── 001_initial.sql    # Ventures, pipeline_runs, events, agent_logs
│   │       ├── 002_day2_revenue_confidence.sql  # Scorecard, confidence, ledger
│   │       └── 003_day3_pipeline_artifacts.sql  # Research dossiers (Supabase Live)
│   │
│   ├── revenue/
│   │   ├── adsense_sync.py        # Import AdSense CSV
│   │   ├── stripe_sync.py         # Sync Stripe subscriptions
│   │   ├── confidence.py          # Forecast MRR bands (p10/p50/p90)
│   │   ├── cycle.py               # Daily revenue cycle runner
│   │   ├── scorecard.py           # Per-venture signals (SCALE/KILL/HOLD)
│   │   └── store.py               # JSON local store (day2_store.json)
│   │
│   ├── tools/
│   │   ├── llm.py                 # Multi-vendor LLM router (with tenacity)
│   │   ├── tavily_client.py       # Tavily search wrapper
│   │   └── trends.py              # pytrends + live search integration
│   │
│   ├── config/
│   │   └── settings.py            # Centralized env vars
│   │
│   └── __init__.py
│
├── data/
│   ├── adsense_demo.csv           # Sample AdSense export
│   └── day2_store.json            # Local ledger (auto-created if no Supabase)
│
├── docs/
│   ├── AGENTS.md                  # Full agent spec (229 lines)
│   ├── RESEARCH_COUNCIL.md        # Kimi 3-scout architecture
│   ├── COMMUNICATION_PROTOCOL.md  # Event bus contract
│   ├── DAY2.md                    # Revenue Day 2 checklist
│   ├── DAY3.md                    # Supabase + Trends checklist
│   ├── REVENUE_REALITY.md         # MRR roadmap (Phase 0→6)
│   └── ROADMAP.md                 # 6-phase delivery (142 lines)
│
├── scripts/
│   ├── day3_verify.py             # Pre-flight checks
│   └── record_revenue.py          # Manual MRR/burn entry
│
├── tests/
│   ├── test_state.py              # AgentState unit tests
│   ├── test_schemas.py            # Pydantic validation
│   ├── test_event_bus.py          # EventBus pub/sub
│   ├── test_graph.py              # Graph compilation + edges
│   ├── test_llm.py                # LLM router tests
│   ├── test_market_research.py
│   ├── test_revenue_day2.py       # Revenue cycle + scorecard
│   └── test_trends.py
│
├── infra/
│   └── docker-compose.yml         # Local PostgreSQL + Redis + RedisInsight
│
├── docker-compose.yml             # Root compose (same as infra/)
├── pyproject.toml                 # Dependencies + extras (dev, api, revenue)
├── .env.example                   # All required API keys documented
└── README.md
```

---

## Key Modules Deep Dive

### 1. **AgentState** (`packages/state/agent_state.py`)

The central immutable dictionary flowing through all 12 nodes. Contains:

- **Immutable:** `run_id`, `venture_id`, `created_at` (set once, never changed)
- **Mutable:** Each node appends to `research_dossier`, `venture_brief`, `build_artifact`, etc.
- **Retry tracking:** `qa_retry_count`, `qa_max_retries`, `qa_target`
- **Error tracking:** `last_error`, `manual_review_reason`

Factory function: `init_state(venture_id: str | None = None)` generates UUID and sensible defaults.

### 2. **LangGraph Assembly** (`apps/orchestrator/graph.py`)

**Nodes:**
1. RESEARCH_NODE → ResearchDossier
2. CEO_NODE → VentureBrief + go_decision
3. PRODUCT_NODE → TechSpec
4. ENGINEERING_NODE ← (if MICRO_SAAS)
5. CONTENT_NODE ← (if MEDIA_CHANNEL/AFFILIATE_SITE)
6. QA_NODE → QA retry orchestration
7. SECURITY_NODE → SecurityClearance or SECURITY_VIOLATION_DETECTED
8. ACCOUNT_DISTRIBUTION_NODE
9. DEPLOYMENT_NODE
10. MARKETING_NODE
11. GLOBAL_NODE
12. GROWTH_NODE
13. MANUAL_REVIEW_NODE (fallback when QA maxes out)

**Conditional Edges:**
- `go_decision_edge`: CEO's `go_decision=true/false` → PRODUCT_NODE or END
- `product_routing_edge`: TechSpec.product_type → ENGINEERING_NODE or CONTENT_NODE
- `qa_routing_edge`: QA result + retry count → SECURITY_NODE | ENGINEERING_NODE | CONTENT_NODE | MANUAL_REVIEW_NODE

### 3. **Event Bus** (`packages/bus/event_bus.py`)

Dual-mode async pub/sub:

```python
bus = EventBus()  # Auto-detects Redis or falls back to asyncio.Queue

# Publish
await bus.publish(envelope)

# Consume
async for envelope in bus.consume("consumer-name", filter_types=["QA_PASSED"]):
    handle(envelope)
```

**Production Mode (Redis Streams):**
- Consumer groups for exactly-once semantics
- Persistent audit trail
- Horizontal scale (multiple workers)

**Dev Mode (asyncio.Queue):**
- No external dependency
- Ephemeral (lost on restart)
- Perfect for testing

### 4. **Event Schemas** (`packages/schemas/events.py`)

Pydantic v2 models enforce strict contracts:

```python
class EventEnvelope(BaseModel):
    event_id: str                    # UUID
    event_type: EventType            # Enum: VENTURE_BRIEF_READY, etc.
    source_agent: AgentID
    target_agent: AgentID
    payload: dict[str, Any]          # Variant per event_type
    metadata: EventMetadata
    timestamp: datetime
```

All payloads are type-checked before bus publish.

### 5. **Revenue Engine** (`packages/revenue/`)

Tracks portfolio metrics and emits SCALE/KILL signals:

**scorecard.py:**
- Per-venture leading indicators (QA first-pass rate, MRR, burn, visits, retention)
- Decision logic:
  - `MRR ≥ $200` → SCALE
  - `MRR < $50` for 90 days → KILL
  - `MRR ≤ 0` + `< 100 visits` for 60 days → KILL
  - `MRR > 0` + `QA pass rate ≥ 60%` → WATCH (validate before scale)
  - Otherwise → HOLD

**confidence.py:**
- Bayesian forecasts: p10, p50, p90 MRR bands over 12 months
- Confidence tiers: LOW (0–39), MEDIUM (40–69), HIGH (70+)
- Determines portfolio capacity (max 5 parallel at MEDIUM, unlimited at HIGH)

**cycle.py / store.py:**
- Daily cycle reads ventures table + revenue_ledger
- Sync with Stripe subscriptions (when STRIPE_SECRET_KEY set)
- Fall back to JSON store (data/day2_store.json) if no Supabase
- AdSense integration via CSV export (ADSENSE_REPORT_CSV_PATH)

### 6. **Database** (`packages/db/`)

**001_initial.sql:**
- `ventures` (venture_id, venture_type, niche, status, feasibility, competition)
- `pipeline_runs` (run_id, venture_id, stage, status, qa_retry_count)
- `events` (audit trail: event_id, event_type, source, target, correlation_id, payload JSONB)
- `agent_logs` (agent_name, status, tokens_used, latency, retry_count, error_detail)

**002_day2_revenue_confidence.sql:**
- `ventures_scorecards` (venture_id, period, mrr, burn, qa_rate, signal)
- `revenue_ledger` (venture_id, source [STRIPE|ADSENSE|MANUAL], amount_usd, period)
- `confidence_reports` (run_date, forecast_mode, ventures_in_portfolio, p10/p50/p90)
- `manual_review_queue` (id, venture_id, review_reason, artifact_type, priority)

**003_day3_pipeline_artifacts.sql:**
- `research_dossiers` (venture_id, council_confidence, scout_reports JSONB, debate_transcript)

### 7. **API & Dashboard** (`apps/api/`, `apps/command-center/`)

**FastAPI (apps/api/main.py):**
- GET `/api/agent-grid` — Recent agent executions + health
- GET `/api/portfolio` — 450-slot grid with live ventures
- GET `/api/revenue-summary` — MRR, confidence, trend
- GET `/api/confidence` — p10/p50/p90 forecast
- GET `/api/manual-review` — Unresolved QA failures
- POST `/api/review/{id}` — Approve/reject/defer manual review
- WebSocket `/ws` — Live event stream for agent updates

**React Command Center (apps/command-center/):**
- Agent grid (executing tasks in real-time)
- Portfolio heat map (450 slots, color-coded by status)
- Revenue dashboard (MRR ticker, confidence gauge)
- Trends heatmap (hot niches from research)
- Manual review queue with action buttons

---

## Execution Modes

### Mode 1: Dry-Run (Validation Only)

```bash
python -m apps.orchestrator.main --mode dry-run
```

- Compiles graph, imports all agents
- **Does NOT** make LLM calls
- Validates Supabase connection (if SUPABASE_* set)
- Perfect for CI/CD and quick sanity checks

### Mode 2: Single Pipeline Run

```bash
python -m apps.orchestrator.main --mode single [--venture-id ven_custom_001]
```

- Generates a random `ven_XXXXX` if none provided
- Runs graph from RESEARCH → GROWTH end-to-end
- Logs to console + stores in DB (if connected)
- Returns final state as JSON on stdout

### Mode 3: Watch Mode (Listener)

```bash
python -m apps.orchestrator.main --mode watch
```

- Continuously polls event bus (Redis Streams)
- Spawns a new pipeline for each inbound request
- Horizontal scale: run multiple watchers on different machines
- Not yet fully wired in Phase 0 (scaffold)

---

## Phase Roadmap

### Phase 0 ✅ (Complete — Scaffold)

**Goal:** Validate architecture — dummy event flows through all 12 nodes without real APIs.

**Deliverables:**
- [x] LangGraph + 12 nodes + conditional edges
- [x] Pydantic schemas + EventBus (dual-mode)
- [x] AgentState TypedDict + init_state()
- [x] pytest suite (test_graph.py passes)
- [x] Supabase schema (migrations 001, 002, 003)
- [x] Docker Compose (local PostgreSQL + Redis)

**Exit Criteria:** `pytest tests/ -v` green + `dry-run` succeeds

---

### Phase 1 🔄 (In Progress — First Live Wedge)

**Goal:** 1 MICRO_SAAS + 1 MEDIA_CHANNEL through full pipeline with real APIs.

**Timeline:** Week 3–8

| Week | Deliverable |
|------|-------------|
| 3 | CEO wired to pytrends + Tavily; Supabase ventures write ✅ |
| 4 | Engineering: Claude → Vite repo template; real `vite build` in QA |
| 5 | Content: ElevenLabs + Remotion stub → real audio file |
| 6 | Deployment: Railway token deploy; YouTube OAuth upload (unlisted tests) |
| 7 | Command Center v1 on Railway; Supabase portfolio read |
| 8 | Revenue Engine reads `revenue_ledger`; manual Stripe + AdSense entry |

**Budget:** $2–20/mo APIs

---

### Phase 2 (Planned — Quality & Compliance)

**Weeks 9–14**

- Playwright headless in QA (real browser tests)
- Copyright audio fingerprint stub
- Security ToS snapshot weekly job
- Account Distribution CRUD + rate limits
- PostHog analytics on SaaS product
- **Exit:** QA pass rate > 50% first attempt

---

### Phase 3 (Planned — Portfolio Loop)

**Months 4–6**

- Parallel ENGINEERING + CONTENT (LangGraph `Annotated` reducers)
- CEO watches Growth auto-reports
- KILL 10 ventures, SCALE 2
- 5 live products max concurrent
- **Target MRR:** $500–$3,000

---

### Phase 4 (Planned — Media Network)

**Months 7–12**

- 5–8 monetized channels
- Global Agent (EN, DE, ES localization)
- Affiliate_SITE template
- Remotion cloud render (Modal or Railway)
- **Target MRR:** $3,000–$12,000

---

### Phase 5–6 (Long-Term)

**Hire, scale, M&A path**

- Revenue Operator + DevOps + Compliance
- 30–50 concurrent ventures
- **Target MRR:** $12k–$40k (solo), $100k+ (with team)

---

## Environment Variables (.env)

**Required (Phase 0+):**
```bash
# LLM APIs
GEMINI_API_KEY=aiz...                # Google AI
ANTHROPIC_API_KEY=sk-ant-...         # Claude
OPENROUTER_API_KEY=sk-or-...         # Kimi K2.x via OpenRouter
TAVILY_API_KEY=tvly-...              # Market search
```

**Required (Day 2 onwards):**
```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...     # For writes

STRIPE_SECRET_KEY=sk_test_...        # Or live key (optional until Week 8)
```

**Optional:**
```bash
ELEVENLABS_API_KEY=...               # Audio generation
FAL_KEY=...                          # Thumbnail generation
RAILWAY_TOKEN=...                    # Deploy API
POSTHOG_API_KEY=...                  # Analytics
ADSENSE_REPORT_CSV_PATH=/path/to/report.csv

REDIS_URL=redis://localhost:6379     # Auto-detected; falls back to asyncio.Queue
LOG_LEVEL=INFO
MAX_PARALLEL_PIPELINES=5
QA_MAX_RETRIES=3
MONTHLY_BURN_USD=47.20               # For scorecard KILL threshold
```

---

## Quick Start

### 1. Clone & Setup

```bash
git clone <repo>
cd ai-squadron
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
# Fill in GEMINI_API_KEY and ANTHROPIC_API_KEY at minimum
```

### 2. Local Infrastructure

```bash
docker compose -f infra/docker-compose.yml up -d
# Waits for PostgreSQL, Redis, RedisInsight to be healthy
```

### 3. Validate

```bash
pytest tests/ -v
python -m apps.orchestrator.main --mode dry-run
```

### 4. Run Single Pipeline

```bash
python -m apps.orchestrator.main --mode single
# Outputs JSON with venture_id and final pipeline_stage
```

### 5. Command Center (Dashboard)

```bash
# Terminal 1: API server
pip install -e ".[api]"
uvicorn apps.api.main:app --reload --port 8000

# Terminal 2: React dev server
cd apps/command-center
npm install
npm run dev
# Open http://localhost:5173
```

---

## Testing

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_graph.py -v

# With coverage
pytest tests/ --cov=packages --cov=apps --cov-report=html

# Watch mode (auto-rerun on file change)
pytest-watch tests/ -- -v
```

---

## Known Limitations & TODO

1. **Manual Review Node** — Currently logs to store; no full UI workflow (Phase 2)
2. **Parallel Orchestration** — ENGINEERING + CONTENT run sequentially; LangGraph Annotated reducers for Phase 3
3. **No API Key Rotation** — Vault integration stub only (Phase 2)
4. **Engineering Output** — Builds to memory; needs disk persistence under `builds/{venture_id}/` (Phase 1 Week 4)
5. **Content Assets** — Thumbnails + audio output paths not yet persisted to S3 (Phase 1 Week 5)
6. **QA Browser Tests** — Playwright headless support planned (Phase 2)
7. **Account Mass Creation** — Intentionally blocked; only OAuth official APIs (compliance + ToS)

---

## Key Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **LangGraph over Airflow** | Native graph DSL, conditional edges, state persistence out-of-box |
| **Pydantic for events** | Runtime validation, self-documenting contracts, IDE autocomplete |
| **Dual-mode event bus** | Dev without Redis, prod with horizontal scale |
| **Supabase over custom Postgres** | Auth, RLS, Vault for secrets, real-time subscriptions, free tier $0 |
| **Railway for deployment** | 5-min setup, automatic SSL, pay-on-revenue model fits early stage |
| **Agent per file** | Modularity, testability, no circular imports |
| **Gemini 2.0 Flash for volume** | 1M context, $0.075/M input, 50k RPM — cost-optimal for commodity agents |
| **Claude Sonnet for engineering** | Best code quality; fewer iterations = lower cost overall |
| **Kimi K2.x for research** | Superior long-context reasoning for multi-scout debate; OpenRouter access |

---

## Architecture Strengths

1. **Resilience:** QA retry loop (max 3) before manual escalation — no hanging pipelines
2. **Observability:** Every event logged; correlation_id traces flow end-to-end
3. **Cost Control:** Model routing by agent role; cheaper models for volume
4. **Scalability:** Redis Streams + PostgreSQL support 100s of concurrent ventures
5. **Testability:** Event schemas force contract adherence; mock event bus for unit tests
6. **Auditability:** Immutable event log in Supabase; full workflow reconstruction from run_id

---

## Common Workflows

### Scenario: Run one SaaS idea end-to-end

```bash
python -m apps.orchestrator.main --mode single --venture-id ven_ai_copilot_001
```

Check Supabase `ventures` table → see final niche, feasibility, go_decision.

### Scenario: Inspect QA failure and retry

1. Find failing run in `pipeline_runs` table (status = `MANUAL_REVIEW`)
2. View `qa_report` in state or final event log
3. Fix in Engineering or Content agent code
4. Re-run same `venture_id` (creates new run_id)

### Scenario: Check portfolio health

```bash
python apps/revenue-engine/main.py --mode once
# Reads all ventures + revenue_ledger
# Outputs scorecards + confidence report
# Emits SCALE/KILL signals
```

View Command Center `/api/portfolio` endpoint for live grid.

### Scenario: Add AdSense revenue

1. Export monthly CSV from AdSense (columns: venture_id, period_start, period_end, amount_usd)
2. Set `ADSENSE_REPORT_CSV_PATH=/path/to/report.csv`
3. Run revenue cycle:
   ```bash
   python apps/revenue-engine/main.py --mode once
   ```
4. Check `revenue_ledger` table for imported rows

---

## Deployment (Future)

### Railway (Phase 1 Week 7)

1. Connect Git repo to Railway
2. Set environment variables (GEMINI_API_KEY, SUPABASE_URL, etc.)
3. Railway auto-detects Python → runs `pip install -e .` + `uvicorn apps.api.main:app`
4. Custom commands for cron:
   - `python apps/revenue-engine/main.py --mode once` (via GitHub Actions / Railway cron)
   - `python -m apps.orchestrator.main --mode watch` (long-running service)

### Supabase (Day 3)

- PostgreSQL already cloud-hosted at supabase.co
- Migrations auto-applied via SQL editor
- No additional setup beyond API key env vars

---

## Contributing

1. **New Agent?** → Create `packages/agents/my_agent.py`, define node function, register in `graph.py`
2. **New Event Type?** → Add to `EventType` enum in `packages/schemas/events.py`
3. **New Schema Field?** → Extend TypedDict in `packages/state/agent_state.py` or payload model
4. **Test:** Always run `pytest tests/ -v` before push
5. **Format:** `ruff check packages/ apps/` + `mypy packages/ --strict`

---

## Contact & Resources

- **Docs:** See `docs/` folder (AGENTS.md, RESEARCH_COUNCIL.md, REVENUE_REALITY.md, ROADMAP.md)
- **Examples:** Check `tests/test_graph.py` for end-to-end mock run
- **Dashboard:** http://localhost:5173 (after `npm run dev`)
- **API Docs:** http://localhost:8000/docs (FastAPI Swagger)
- **Database:** Supabase Console (https://app.supabase.io)

---

**Last Updated:** May 23, 2026  
**Maintainer:** AI Squadron Team  
**License:** TBD
