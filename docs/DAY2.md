# Day 2 Scaffold — Revenue Truth & Confidence

Day 2 operationalizes the direct answers from the revenue strategy: measure leading indicators, sync real revenue, and forecast conservatively before scaling.

## What Day 2 adds

| Component | Path | Purpose |
|-----------|------|---------|
| DB migration | `packages/db/migrations/002_day2_revenue_confidence.sql` | scorecards, confidence reports, manual review queue |
| Revenue package | `packages/revenue/` | Stripe/AdSense sync, scorecards, confidence, cycle |
| Local store | `data/day2_store.json` | Works without Supabase (auto-created) |
| Revenue Engine | `python -m apps.revenue_engine.main` | Daily sync + weekly confidence |
| API | `/api/confidence`, `/api/scorecards`, `/api/manual-review` | Command Center data |
| Manual review | `manual_review_queue` + graph node | Human gate when QA exhausts retries |

## Day 2 exit criteria

```bash
# 1. Run revenue cycle (creates data/day2_store.json)
python -m apps.revenue_engine.main --mode once

# 2. Tests
pytest tests/test_revenue_day2.py -v

# 3. API + dashboard
pip install -e ".[api]"
uvicorn apps.api.main:app --reload --port 8000
cd apps/command-center && npm run dev
```

You should see:
- Confidence score and p10/p50/p90 12-month MRR bands on the dashboard
- Revenue ticker fed from `revenue_ledger` (demo burn row until Stripe is wired)
- Recommended actions from the confidence engine

## Weekly operating rhythm

| Day | Action |
|-----|--------|
| Daily | `python -m apps.revenue_engine.main --mode once` (or scheduler) |
| Monday | Review confidence report in Command Center |
| On QA fail x3 | Resolve item in manual review queue |
| On SCALE signal | Double distribution on that venture only |
| On KILL signal | Decommission and blacklist niche |

## Wire Stripe (first real revenue)

1. Create Stripe product with metadata `venture_id=ven_wedge_001`
2. Set `STRIPE_SECRET_KEY=sk_live_...` or test key
3. `pip install stripe` and re-run revenue cycle
4. MRR appears in ledger and confidence score increases

## Wire AdSense

Export monthly CSV with columns `venture_id`, `period_start`, `period_end`, `amount_usd`
Set `ADSENSE_REPORT_CSV_PATH=/path/to/report.csv`

## Supabase production

Run migration `002_day2_revenue_confidence.sql` in SQL editor.
Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
Local JSON store is bypassed automatically.

## Confidence score meaning

| Score | Tier | Meaning |
|-------|------|---------|
| 0–39 | LOW | Do not add ventures; fix QA and ship wedge |
| 40–69 | MEDIUM | Hold parallel pipeline cap at 5 |
| 70+ | HIGH | Eligible to scale spend on SCALE ventures |

Forecasts are **planning bands**, not promises. Update only when leading indicators improve for 60+ days.

## Next: Day 3 (Phase 1 wedge)

See `docs/ROADMAP.md` Week 3–8: live CEO trends, Engineering deploy, Content ElevenLabs, first Stripe customer.
