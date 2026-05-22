# Day 3 Scaffold — Supabase Live + Trend Intelligence

You have Supabase and migrations applied. Stripe is not configured yet. Day 3 wires **live data in**, **persistence out**, and **manual revenue** until Stripe is ready.

## What Day 3 adds

| Component | Purpose |
|-----------|---------|
| `packages/tools/trends.py` | Google Trends (pytrends) + Tavily search |
| `packages/tools/tavily_client.py` | Tavily wrapper for niche queries |
| `packages/db/pipeline.py` | Pipeline runs, event log, research dossiers → Supabase |
| `003_day3_pipeline_artifacts.sql` | `research_dossiers` table |
| `scripts/day3_verify.py` | Pre-flight checks |
| `scripts/record_revenue.py` | Manual MRR/burn without Stripe |
| Orchestrator | `begin_pipeline_run` / `complete_pipeline_run` / persist events |
| API | Agent logs + portfolio from Supabase when connected |

## Migration (run once in Supabase SQL editor)

After `001_initial.sql` and `002_day2_revenue_confidence.sql`:

```sql
-- Paste contents of packages/db/migrations/003_day3_pipeline_artifacts.sql
```

## Environment

```bash
# Required (you have these)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# Live trends (Day 3)
TAVILY_API_KEY=tvly-...          # https://tavily.com
TRENDS_LIVE=true                 # false = mock trends only

# Still optional
STRIPE_SECRET_KEY=                # empty OK — use record_revenue.py
OPENROUTER_API_KEY=               # Kimi council live mode
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
```

## Day 3 exit checklist

```bash
pip install -e ".[dev]"

# 1. Verify Supabase + tables + trends
python scripts/day3_verify.py

# 2. Run one live pipeline (writes ventures, agent_logs, events, research_dossiers)
python -m apps.orchestrator.main --mode single

# 3. Record burn manually (Stripe not ready)
python scripts/record_revenue.py --venture-id ven_XXXXX --amount 0 --burn 47.20

# 4. Revenue confidence cycle (reads Supabase ledger)
python -m apps.revenue_engine.main --mode once

# 5. Dashboard
uvicorn apps.api.main:app --reload --port 8000
cd apps/command-center && npm run dev
```

Confirm in Supabase Table Editor:
- `pipeline_runs` — one row, status COMPLETED or MANUAL_REVIEW
- `research_dossiers` — JSON dossier from Kimi council
- `ventures` — niche from CEO
- `agent_logs` — rows per node
- `events` — bus audit trail

## Stripe (when ready — Day 3+ / Week 8)

1. Create Stripe product; add `metadata.venture_id=ven_xxx` on subscriptions.
2. Set `STRIPE_SECRET_KEY=sk_test_...` or live key.
3. `pip install -e ".[revenue]"` if not installed.
4. `python -m apps.revenue_engine.main --mode sync`

Until then:

```bash
python scripts/record_revenue.py --venture-id ven_wedge_001 --amount 29.00 --source STRIPE
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `research_dossiers` insert fails | Run migration `003` |
| pytrends rate limit | Retry later or `TRENDS_LIVE=false` |
| NullDB in logs | Check `SUPABASE_SERVICE_ROLE_KEY` (not anon for writes) |
| Empty agent_logs in UI | Run pipeline once; refresh API |

## Next: Day 4 preview

- Real `vite build` in QA for Engineering artifacts
- Engineering output template on disk under `builds/{venture_id}/`

See [ROADMAP.md](./ROADMAP.md) Week 4.
