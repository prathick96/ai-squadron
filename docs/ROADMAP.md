# AI Squadron — Build Roadmap

## Tech stack (locked)

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Orchestration | LangGraph 0.2+ | Conditional QA loops, stateful pipelines |
| Agent runtime | Python 3.11+ | Existing agent modules |
| LLM routing | Gemini 2.5 Pro / 2.0 Flash, Claude Sonnet/Haiku | Cost vs quality per role |
| Event bus | Redis Streams (prod), asyncio.Queue (dev) | Horizontal scale |
| Database | Supabase (Postgres) | Auth, RLS, Vault for OAuth refs |
| SaaS frontend | React 19 + Vite + TypeScript | Engineering agent output |
| Command Center | React 19 + Vite + Recharts | War room dashboard |
| Dashboard API | FastAPI + Uvicorn | Thin read layer over Supabase |
| SaaS hosting | Vercel Hobby → Pro | Free start, scale on revenue |
| Media APIs | YouTube Data API v3, TikTok Content Posting, Instagram Graph | Official only |
| Voice | ElevenLabs (free tier 10k chars/mo) → paid | Human-likeness |
| Video | Remotion + FFmpeg (local/cloud render) | Programmatic video |
| Thumbnails | fal.ai Flux | Fast gen |
| Trends | pytrends, Tavily, Reddit API (optional) | CEO inputs |
| Analytics | PostHog (free tier), YouTube Analytics API | Growth feedback |
| Payments | Stripe | SaaS MRR |
| Cron | APScheduler → Railway free / GitHub Actions | Revenue Engine |
| CI | GitHub Actions | Test + lint on PR |

## Phase 0 — Scaffold (complete)

**Duration:** Week 1–2  
**Cost:** $0  

- [x] LangGraph 12-node pipeline with QA retry
- [x] Pydantic event schemas + AgentState
- [x] Event bus dual mode
- [x] Supabase schema migration
- [x] pytest suite

**Exit:** `python -m apps.orchestrator.main --mode dry-run` and `pytest tests/ -v` green.

## Phase 1 — First live wedge (Week 3–8)

**Goal:** 1 MICRO_SAAS + 1 MEDIA_CHANNEL through full pipeline with real APIs.

| Week | Deliverable |
|------|-------------|
| 3 | Wire CEO: pytrends + Tavily; Supabase ventures write |
| 4 | Wire Engineering: Claude → Vite repo template; real `vite build` in QA |
| 5 | Wire Content: ElevenLabs + Remotion stub → real audio file |
| 6 | Wire Deployment: Vercel token deploy; YouTube OAuth upload (unlisted tests) |
| 7 | Command Center v1 on Vercel; connect Supabase read |
| 8 | Revenue Engine reads `revenue_ledger`; manual Stripe + AdSense entry |

**Exit criteria:** One SaaS URL live, one unlisted video uploaded, dashboard shows agent logs from real run.

**Budget:** $2–$20/mo APIs.

## Phase 2 — Quality & compliance (Week 9–14)

- Playwright headless in QA Technical Validator
- Copyright audio fingerprint stub (e.g. ACRCloud free tier or skip music entirely)
- Security ToS snapshot weekly refresh job
- Account Distribution: platform_accounts CRUD + rate limits
- PostHog on SaaS product

**Exit:** QA pass rate > 50% first attempt; zero policy strikes on test accounts.

## Phase 3 — Portfolio loop (Month 4–6)

- Parallel ENGINEERING + CONTENT (LangGraph `Annotated` reducers on `event_log`)
- CEO watches Growth reports automatically
- Kill 10 ventures, scale 2
- 5 live products max concurrent

**Target MRR:** $500–$3,000 (conservative).

## Phase 4 — Media network (Month 7–12)

- 5–8 monetized-bound channels (original series format)
- Global Agent: 3 locales (EN, DE, ES)
- Affiliate_SITE template for high-RPM niches
- Remotion cloud render (Modal or Railway) if local CPU bottleneck

**Target MRR:** $3,000–$12,000.

## Phase 5 — Scale organization (Month 13–24)

- Hire or contract: editor, devops, compliance reviewer
- Vercel Pro, Supabase Pro, paid ElevenLabs
- Sales outbound for top SaaS SKU only
- 30–50 active ventures, 450-slot grid as funnel history

**Target MRR:** $12,000–$40,000 (still conservative for solo; team unlocks $100k+).

## Phase 6 — Enterprise path (Year 3+)

- SOC2-minded logging, contracts, SLAs on winner product
- API productization of Squadron orchestration (meta play)
- M&A or PE on cash-flowing SKU

**Target:** $200k+ MRR only with proven SKU + team (see REVENUE_REALITY.md).

## Command Center build order

1. `apps/api` — REST + WebSocket (mock data fallback)
2. `apps/command-center` — Agent grid, revenue ticker, portfolio 450 grid, trend heatmap, risk panel
3. Deploy API to Railway; UI to Vercel
4. Wire Supabase realtime (optional) for agent_logs

## Commands reference

```bash
# Infrastructure
docker compose -f infra/docker-compose.yml up -d

# Pipeline
python -m apps.orchestrator.main --mode single

# Revenue cycle
python -m apps.revenue-engine.main --mode once

# Dashboard API
uvicorn apps.api.main:app --reload --port 8000

# Command Center
cd apps/command-center && npm install && npm run dev
```

## Risk register

| Risk | Mitigation |
|------|------------|
| Platform ban | Official APIs only; Account Distribution rate limits |
| Demonetization | QA aesthetic + original scripts |
| 450-product spam | Revenue Engine KILL; max concurrent cap |
| API cost overrun | Token budgets per agent in metadata |
| Legal (copyright) | No third-party music; document asset provenance |

## Documentation index

- [AGENTS.md](./AGENTS.md) — roles and responsibilities
- [COMMUNICATION_PROTOCOL.md](./COMMUNICATION_PROTOCOL.md) — bus and graph protocol
- [REVENUE_REALITY.md](./REVENUE_REALITY.md) — conservative financial model
