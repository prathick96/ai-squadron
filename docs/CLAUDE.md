# AI Squadron — Project Guide for Claude Code

## What This Project Is
Autonomous venture orchestration system. Two parallel departments (Product + Media) governed by a Grand CEO agent. Builds SaaS products and media channels using LangGraph pipelines.

## Running the Project

```bash
# Install dependencies (from backend/)
cd backend && pip install -e ".[dev,api]"

# Dry-run (validates all imports, no LLM calls) — run from backend/
cd backend
python -m apps.orchestrator.main --mode dry-run

# Run product pipeline (SaaS builds)
python -m apps.orchestrator.main --mode single --department product

# Run media pipeline (YouTube/TikTok content)
python -m apps.orchestrator.main --mode single --department media

# Revenue Engine
python apps/revenue-engine/main.py --mode once

# Command Center API
uvicorn apps.api.main:app --reload --port 8000

# Command Center UI (from frontend/)
cd frontend && npm install && npm run dev

# Tests (from backend/)
cd backend && pytest tests/ -v
```

## Directory Structure

```
backend/
  packages/
    agents/
      governance/   — Grand CEO + Global Research Council (5 scouts + debate)
      product/      — Product VP, Manager, Engineering, QA, Deploy, Marketing, Growth
      media/        — Media VP, Script, Voice, Video, Thumbnail, SEO, QA, Publish, Analytics
      shared/       — Legal Agent, Security, Anti-Ban, Credential Guardian, Account Distribution
    schemas/        — Pydantic event models (EventEnvelope + all payload types)
    state/          — AgentState TypedDict (shared across all nodes)
    tools/          — LLM router, pytrends, Tavily
    db/             — Supabase client + migrations
    revenue/        — Revenue Engine: Stripe sync, AdSense sync, confidence, scorecards
    bus/            — Event bus (Redis Streams prod / asyncio.Queue dev)
    config/         — Settings
  apps/
    orchestrator/
      product_graph.py   — Product department LangGraph pipeline
      media_graph.py     — Media department LangGraph pipeline
      graph.py           — Dispatcher (imports both sub-graphs)
      main.py            — CLI entry: --mode, --department flags
    api/            — FastAPI dashboard API
    revenue-engine/ — Daily cron service
  tests/            — Pytest suite
  pyproject.toml    — Python package definition

frontend/           — React 19 war room dashboard (Vite)

infra/              — Docker Compose files for local dev
builds/             — Generated SaaS code (gitignored, written by Engineering agent)
```

## Agent Model Assignments

| Agent | Model |
|---|---|
| Grand CEO | gemini-2.5-pro |
| Research Council (5 scouts + debate) | Kimi K2.x via OpenRouter/DeepInfra |
| Legal Agent | gemini-2.5-pro |
| Revenue Engine | gemini-2.5-pro |
| Engineering Team | claude-sonnet-4-6 |
| QA Critique | claude-haiku-4-5-20251001 |
| All others | gemini-2.0-flash |

## Critical Rules

1. **Engineering writes to disk** — `builds/{venture_id}/` — never discard LLM file output
2. **Legal Agent has veto power** — nothing deploys without `LegalClearance.is_cleared = True`
3. **Official platform APIs only** — no browser automation, no scraping
4. **venture_id FK order** — upsert the venture row BEFORE inserting pipeline_run
5. **Kill threshold: 60 days** — ventures with MRR < $50 after 60 days get KILL signal

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```
GEMINI_API_KEY=          # Required — Gemini 2.5 Pro + 2.0 Flash
ANTHROPIC_API_KEY=       # Required — Claude Sonnet (engineering) + Haiku (QA)
OPENROUTER_API_KEY=      # Optional — Kimi K2.x for Research Council
DEEPINFRA_API_KEY=       # Optional — alternative Kimi provider
SUPABASE_URL=            # Optional — falls back to local JSON store
SUPABASE_SERVICE_ROLE_KEY=
TAVILY_API_KEY=          # Optional — live niche intelligence
ELEVENLABS_API_KEY=      # Optional — voice generation
FAL_KEY=                 # Optional — thumbnail generation
RAILWAY_API_TOKEN=       # Required for real deployment
STRIPE_SECRET_KEY=       # Required for Stripe revenue sync
TRENDS_LIVE=true         # Set false to use mock trend data in tests
```

## Testing

```bash
cd backend
pytest tests/ -v                         # All tests
pytest tests/test_graph.py -v            # Graph compilation tests
pytest tests/test_schemas.py -v          # Schema validation
TRENDS_LIVE=false pytest tests/ -v       # No external API calls
```

## Adding a New Agent

1. Create file in the correct department subpackage under `backend/packages/agents/`
2. Implement `async def {name}_node(state: AgentState) -> AgentState`
3. Add agent role to `MODEL_REGISTRY` in `backend/packages/tools/llm.py`
4. Add `AgentID.{NAME}` to `backend/packages/schemas/events.py`
5. Register node in the appropriate graph (`backend/apps/orchestrator/product_graph.py` or `media_graph.py`)
6. Add test in `backend/tests/`
