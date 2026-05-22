# AI Squadron — Day 1 Scaffold

Autonomous venture orchestration system. Builds SaaS products and media channels using
a 12-node LangGraph pipeline governed by a central Revenue Engine.

**Documentation:** [docs/AGENTS.md](docs/AGENTS.md) · [docs/RESEARCH_COUNCIL.md](docs/RESEARCH_COUNCIL.md) · [docs/DAY2.md](docs/DAY2.md) · [docs/ROADMAP.md](docs/ROADMAP.md)

## Architecture

```
RESEARCH_NODE (Kimi K2.x via OpenRouter — 3 scouts + debate)
    ↓
CEO_NODE (Gemini 2.5 Pro — final VentureBrief + go_decision)
    ↓ go_decision_edge
PRODUCT_NODE (Gemini 2.0 Flash)
    ↓ product_routing_edge
ENGINEERING_NODE (Claude Sonnet)  ─── CONTENT_NODE (Gemini 2.0 Flash)
    └──────────────┬───────────────────────────────┘
                QA_NODE  ◄──── retry loop (max 3)
                    ↓ qa_routing_edge
            SECURITY_NODE
                    ↓
        ACCOUNT_DISTRIBUTION_NODE
                    ↓
            DEPLOYMENT_NODE
              ↙         ↘
    MARKETING_NODE    GLOBAL_NODE
              ↘         ↙
             GROWTH_NODE → END
```

## Directory Structure

```
ai-squadron/
├── apps/
│   ├── orchestrator/
│   │   ├── graph.py        # LangGraph assembly — all nodes + conditional edges
│   │   └── main.py         # CLI entry point (dry-run / single / watch modes)
│   ├── revenue-engine/
│   │   └── main.py         # Daily cron: SCALE / KILL signal emitter
│   ├── api/
│   │   └── main.py         # Command Center REST + WebSocket API
│   └── command-center/     # React 19 war room dashboard
├── packages/
│   ├── agents/             # 11 agent node functions (one file per agent)
│   ├── schemas/events.py   # Pydantic models for every JSON event type
│   ├── state/agent_state.py # AgentState TypedDict + init_state() factory
│   ├── bus/event_bus.py    # Dual-mode: Redis Streams (prod) / asyncio.Queue (dev)
│   ├── db/
│   │   ├── client.py       # Supabase client with NullDB fallback
│   │   └── migrations/     # PostgreSQL schema (001_initial.sql)
│   └── tools/llm.py        # LLM router: Gemini + Anthropic with tenacity retry
├── tests/
│   ├── test_state.py       # AgentState unit tests
│   ├── test_schemas.py     # Pydantic schema validation tests
│   ├── test_event_bus.py   # EventBus publish/consume tests
│   └── test_graph.py       # Graph compilation + conditional edge tests
├── infra/
│   └── docker-compose.yml  # Local PostgreSQL + Redis + RedisInsight
├── .env.example            # All required API keys documented
└── pyproject.toml          # Project config + dependencies
```

## Quick Start (Day 2 — revenue confidence)

```bash
pip install -e ".[dev,api]"
python apps/revenue-engine/main.py --mode once
pytest tests/test_revenue_day2.py -v
uvicorn apps.api.main:app --reload --port 8000
```

See [docs/DAY2.md](docs/DAY2.md) for the full Day 2 checklist.

## Quick Start (Day 3 — Supabase + live trends)

```bash
# Run migration 003 in Supabase SQL editor, then:
python scripts/day3_verify.py
python -m apps.orchestrator.main --mode single
python scripts/record_revenue.py --venture-id ven_wedge_001 --amount 0 --burn 47.20
```

See [docs/DAY3.md](docs/DAY3.md).

## Quick Start (Day 1)

### 1. Clone and create virtualenv
```bash
git clone <your-repo>
cd ai-squadron
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in at minimum: GEMINI_API_KEY and ANTHROPIC_API_KEY
```

### 3. Start local infrastructure
```bash
docker compose -f infra/docker-compose.yml up -d
```

### 4. Validate the scaffold
```bash
# Verify graph compiles, all imports resolve, no LLM calls
python -m apps.orchestrator.main --mode dry-run
```

### 5. Run the test suite
```bash
pytest tests/ -v
```

### 6. Run a live pipeline
```bash
# Requires GEMINI_API_KEY and ANTHROPIC_API_KEY set in .env
python -m apps.orchestrator.main --mode single
```

### 7. Command Center (dashboard)
```bash
pip install -e ".[api]"
uvicorn apps.api.main:app --reload --port 8000

cd apps/command-center && npm install && npm run dev
# Open http://localhost:5173
```

## Agent → Model Assignments

| Agent | Model | Rationale |
|---|---|---|
| CEO Niche Scout | gemini-2.5-pro | Strategic synthesis over trend datasets |
| Revenue Engine | gemini-2.5-pro | Portfolio-level financial reasoning |
| Engineering Team | claude-sonnet-4-6 | Best code generation quality |
| QA Auditor (critique) | claude-haiku-4-5 | Precise structured fix directives |
| All others | gemini-2.0-flash | Cost-efficient, 1M context, fast |

## Phase 0 Exit Criteria

A dummy event flows from `CEO_NODE` → `PRODUCT_NODE` → `ENGINEERING_NODE` → `QA_NODE`
→ `SECURITY_NODE` → `DEPLOYMENT_NODE` → `MARKETING_NODE` + `GLOBAL_NODE` → `GROWTH_NODE`
and writes to Supabase without errors.

Run `pytest tests/ -v` — all tests must pass before moving to Phase 1.

## Phase 1 Stub → Live API Checklist

The following stubs in the Day 1 scaffold need live API integration in Phase 1:

- [ ] `packages/agents/ceo_niche_scout.py` → `_fetch_trend_snapshot()` → wire pytrends + Tavily
- [ ] `packages/agents/content_team.py` → audio stub → wire ElevenLabs API
- [ ] `packages/agents/content_team.py` → video stub → wire Remotion + FFmpeg
- [ ] `packages/agents/content_team.py` → thumbnail stub → wire fal.ai Flux
- [ ] `packages/agents/deployment_team.py` → Railway Deploy API (SaaS)
- [ ] `packages/agents/deployment_team.py` → YouTube Data API v3 (media)
- [ ] `packages/agents/growth_team.py` → YouTube Analytics API + PostHog
- [ ] `apps/revenue-engine/main.py` → `_fetch_portfolio()` → wire Supabase + Stripe
- [ ] `packages/db/client.py` → set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY

## Cost at Phase 0

**$0.00** — all agents run in stub/mock mode. Only LLM costs apply when live keys are set.
With Google AI Studio free tier (1,500 req/day Flash + 25 req/day Pro), Phase 1 runs
at approximately $2–5 total for the first 20 pipeline executions.
