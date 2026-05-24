# Phase 1 Progress Tracker — First Live Wedge (SaaS + Media)

**Status:** IN PROGRESS  
**Timeline:** Week 3–8 (May 23, 2026 — projected completion ~July 8, 2026)  
**Target MRR:** $0 → $500–$3,000 (by Phase 2 end)

---

## Overview

Phase 1 operationalizes the Day 1 scaffold by wiring **9 critical API integrations** across the pipeline. Each integration unlocks one week's deliverable.

### Completion Status
- **Completed:** 3/9 (33%)
- **In Progress:** 2/9 (22%)
- **Not Started:** 4/9 (44%)

---

## Week-by-Week Checklist

### Week 3: CEO Trends Intelligence ✅ COMPLETED

**Goal:** CEO synthesizes real market trends using pytrends + Tavily → VentureBrief.go_decision

| Item | Status | Details |
|------|--------|---------|
| Wire pytrends (Google Trends) | ✅ | `packages/tools/trends.py` — live trending topics |
| Wire Tavily search API | ✅ | `packages/tools/tavily_client.py` — niche-specific research |
| CEO uses trend snapshot | ✅ | `ceo_niche_scout.py` reads dossier.trend_snapshot |
| Supabase ventures table | ✅ | Research dossiers persisted (migration 003) |
| Test: CEO outputs real niche | ✅ | `pytest tests/test_market_research.py -v` |

**Verification:**
```bash
python -m apps.orchestrator.main --mode single
# Check: ventures table → niche != "unknown" + feasibility_score ≠ 0
```

---

### Week 4: Engineering Build → Real Vite Compilation 🔄 IN PROGRESS

**Goal:** Engineering outputs React 19 repo → `vite build` succeeds in QA.

| Item | Status | Details |
|------|--------|---------|
| Claude Sonnet generates React 19 scaffold | 🔄 | `engineering_team.py` — writes to `/builds/{venture_id}/` |
| Vite template with component structure | 🔄 | Modular for 450+ product scale |
| QA runs `vite build` → exit code check | ⏳ | `qa_auditor.py` → compile, bundle size, test pass |
| QA retry loop for build failures | ⏳ | `qa_routing_edge` → ENGINEERING_NODE feedback |
| Test: green `vite build` exit code | ⏳ | `pytest tests/test_graph.py::test_qa_retry_loop` |

**Next Steps:**
1. Add `build_output_path` to `BuildArtifact` schema
2. Implement `await vite_build(venture_id)` in `qa_auditor.py`
3. Wire `claude_sonnet` for engineering code generation
4. Test with sample niche (e.g., "AI resume builder")

**Verification:**
```bash
python -m apps.orchestrator.main --mode single
# Check: build_artifact.vite_build_exit_code == 0
# Check: builds/{venture_id}/dist/ exists with bundle_size_kb
```

---

### Week 5: Content Audio & Video Rendering 📋 NOT STARTED

**Goal:** Content outputs ElevenLabs audio + Remotion video → real MP4 file.

| Item | Status | Details |
|------|--------|---------|
| ElevenLabs TTS integration | ⏳ | Replace audio stub: call ElevenLabs API → MP3 |
| Human-likeness quality gate | ⏳ | `human_likeness_score >= 0.85` → QA pass |
| Remotion video composition | ⏳ | Replace video stub: assemble script + audio → FFmpeg |
| FFmpeg command execution | ⏳ | Local or cloud render (Modal, Railway, etc.) |
| Caption generation | ⏳ | Auto-generate from script.body_sections |
| Test: MP4 plays without errors | ⏳ | `pytest tests/test_content_team.py::test_video_render` |

**Next Steps:**
1. Implement `call_elevenlabs_tts(script.hook + body, voice_id)` in content_team.py
2. Add quality classifier: `score_human_likeness(audio_path)` or use ElevenLabs built-in
3. Implement `render_with_remotion(script, audio_path, venture_id)` → FFmpeg subprocess
4. Wire caption API (or simple `script.word_list_to_vtt()`)

**Estimated Cost:** $2–5/venture (ElevenLabs free tier: 10k chars/mo; Remotion free)

**Verification:**
```bash
python -m apps.orchestrator.main --mode single --venture-id ven_media_test_001
# Check: content_package.audio_asset.file_path exists + plays
# Check: content_package.video_asset.file_path exists + MP4 valid
# Check: human_likeness_score in [0.85, 1.0]
```

---

### Week 6: SaaS Deployment to Railway 📋 NOT STARTED

**Goal:** Vite app deploys to Railway → live at `https://{venture_id}.up.railway.app`.

| Item | Status | Details |
|------|--------|---------|
| Railway Deploy API token auth | ⏳ | Store `RAILWAY_TOKEN` + `RAILWAY_PROJECT_ID` |
| Create Railway service + env vars | ⏳ | Automated service creation for each venture |
| Deploy `vite build` output | ⏳ | HTTP server for `/dist` folder |
| Smoke test URL | ⏳ | 200 OK + content-length > 0 |
| Test: deployment_receipt.url lives | ⏳ | `pytest tests/test_deployment.py::test_railway_smoke_test` |

**Next Steps:**
1. Implement `deploy_to_railway(venture_id, build_path, railway_token)` in deployment_team.py
2. Wire Railway Create Service API
3. Add health check: `await asyncio.sleep(10)` then `curl {url} → 200`
4. Update `deployment_receipt` with live URL + deployment_id

**Estimated Cost:** $0 (Railway Hobby tier free; $5/mo for Pro if scaling)

**Verification:**
```bash
python -m apps.orchestrator.main --mode single
curl https://ven_XXXX.up.railway.app/
# Should return 200 OK + React index.html
```

---

### Week 6 (Parallel): Media Publishing to YouTube 📋 NOT STARTED

**Goal:** Video uploads to YouTube (unlisted) → live with metadata.

| Item | Status | Details |
|------|--------|---------|
| YouTube Data API v3 OAuth setup | ⏳ | User consent flow (or test account service account) |
| Upload MP4 from Week 5 | ⏳ | youtube.videos().insert() |
| Set title, description, tags | ⏳ | From `seo_metadata` in content_package |
| Unlisted mode (no public listing yet) | ⏳ | visibility = "unlisted" for test runs |
| Get video_id + watchURL | ⏳ | Return in `deployment_receipt.url` |
| Test: YouTube returns 200 + video_id | ⏳ | `pytest tests/test_deployment.py::test_youtube_upload` |

**Next Steps:**
1. Create service account or wire OAuth2 flow
2. Implement `upload_to_youtube(mp4_path, title, description, tags)` in deployment_team.py
3. Handle quota limits: 10k requests/day free tier
4. Store refresh_token in Supabase Vault (for Phase 2 automation)

**Estimated Cost:** $0 (YouTube Data API free tier)

**Verification:**
```bash
python scripts/record_revenue.py --venture-id ven_media_001 --amount 0 --burn 47.20
# Check: YouTube Studio → unlisted video appears in uploads
```

---

### Week 7: Command Center Dashboard (Railway) ✅ MOSTLY COMPLETE

**Goal:** React 19 dashboard deployed to Railway → visualize agent health + revenue.

| Item | Status | Details |
|------|--------|---------|
| API endpoints for agent grid | ✅ | `/api/agent-grid` → recent executions |
| API endpoints for portfolio | ✅ | `/api/portfolio` → 450-slot grid |
| API endpoints for revenue | ✅ | `/api/revenue-summary` + `/api/confidence` |
| React components for dashboard | ✅ | `apps/command-center/src/App.tsx` + Recharts |
| WebSocket live updates | ⏳ | `/ws` → real-time agent status (optional for Phase 1) |
| Deploy to Railway | ⏳ | FastAPI + React served on same domain |

**Verification:**
```bash
uvicorn apps.api.main:app --reload --port 8000
cd apps/command-center && npm run dev
# Open http://localhost:5173 → see agent grid + portfolio + revenue
```

---

### Week 8: Revenue Engine — Stripe Integration ⏳ NOT STARTED

**Goal:** Revenue Engine reads Stripe subscriptions + manual ledger entries → MRR + Confidence.

| Item | Status | Details |
|------|--------|---------|
| Stripe API integration | ⏳ | `stripe_sync.py` reads subscriptions with `metadata.venture_id` |
| Subscription metadata mapping | ⏳ | Create sample Stripe product → map ventures |
| Revenue ledger table reads | ✅ | `revenue_ledger` schema ready (migration 002) |
| Manual entry via `record_revenue.py` | ✅ | Script for MRR/burn entry (until Stripe ready) |
| Confidence forecasts (p10/p50/p90) | ✅ | `confidence.py` generates bands |
| Scorecard signals (SCALE/KILL/HOLD) | ✅ | `scorecard.py` computes per-venture |
| Test: confidence report in API | ✅ | `pytest tests/test_revenue_day2.py -v` |

**Next Steps (Week 8):**
1. Create Stripe product with `metadata.venture_id=ven_wedge_001`
2. Implement `fetch_stripe_subscriptions(stripe_key)` in stripe_sync.py
3. Wire to `revenue_cycle.py` → daily sync at 00:00 UTC
4. Test: manual `record_revenue.py` entry + Stripe sync both feed scorecard

**Verification:**
```bash
python scripts/record_revenue.py --venture-id ven_wedge_001 --amount 29.00 --source STRIPE
python apps/revenue-engine/main.py --mode once
# Check: revenue_ledger table → new row
# Check: ventures_scorecards → signal in [SCALE, KILL, WATCH, HOLD]
```

---

## Integration Dependency Graph

```
Week 3: CEO Trends ✅
    ↓ (VentureBrief)
Week 4: Vite Build 🔄
    ↓ (BuildArtifact)
Week 5: Audio + Video ⏳
    ↓ (ContentPackage)
Week 6a: Railway Deploy ⏳ ← (Week 4 BuildArtifact)
Week 6b: YouTube Upload ⏳ ← (Week 5 ContentPackage)
Week 7: Dashboard ✅ ← (All prior)
Week 8: Revenue → Stripe ⏳ ← (Manual entry works, needs Stripe wire)
```

---

## Testing & Validation

### Pre-Phase-1-Go Criteria (Today)

```bash
# All scaffold tests must pass
pytest tests/ -v

# Dry-run validation
python -m apps.orchestrator.main --mode dry-run

# Day 2 revenue cycle (manual entry)
python apps/revenue-engine/main.py --mode once
```

### Phase 1 Weekly Checkpoints

**After Week 3:** 
```bash
pytest tests/test_market_research.py -v
python -m apps.orchestrator.main --mode single
# Verify: ventures table has real niches
```

**After Week 4:**
```bash
pytest tests/test_qa_auditor.py -v
# Verify: BuildArtifact.vite_build_exit_code == 0
```

**After Week 5:**
```bash
pytest tests/test_content_team.py -v
# Verify: content_package.audio_asset.file_path exists
```

**After Week 6:**
```bash
curl https://ven_wedge_001.up.railway.app/
# Verify: 200 OK + React app loads
```

**After Week 7:**
```bash
open http://localhost:5173
# Verify: agent grid shows recent runs, portfolio visible
```

**After Week 8:**
```bash
python apps/revenue-engine/main.py --mode once
# Verify: confidence report generated, SCALE/KILL signals computed
```

---

## Known Blockers & Mitigations

| Blocker | Impact | Mitigation |
|---------|--------|-----------|
| Vite build takes >2min locally | QA timeout | Cache node_modules, use Railway fast machines |
| ElevenLabs quality inconsistent | Audio gate fails | Manual quality audit in Phase 2; use best voice model |
| YouTube upload quota (10k/day) | Can't stress-test media | Use test channel + unlisted mode; quota resets daily |
| Stripe metadata mapping bugs | Revenue miscount | Manual ledger entry fallback; double-check with CSV export |
| Railway free tier CPU limits | Slow Vite compile + FFmpeg | Upgrade to Railway Pro ($5/mo) if compile >5min |
| Supabase RLS permission issues | Deployment fails | Pre-test RLS policies before production push |

---

## Budget (Phase 1 Total)

| Service | Free Tier | Cost/mo (Phase 1) | Notes |
|---------|-----------|-------------------|-------|
| Google AI Studio (Gemini) | 1500 Flash/day, 25 Pro/day | $0 | ✅ Covered |
| Anthropic (Claude) | 100k tokens/month | $0 | Generous free tier |
| Tavily API | 1000 requests/month | $0 | ✅ Covered |
| ElevenLabs TTS | 10k characters/month | $0–5 | ~50 char/sec → 200sec/venture → 5 ventures = $2–5 |
| fal.ai (Thumbnails) | 1000 requests/month | $0 | ✅ Covered |
| Railway (SaaS hosting) | Hobby tier $5 | $0 (hobby) → $5 (pro) | ✅ Free for Phase 1 |
| Supabase (PostgreSQL) | 500MB storage | $0 | ✅ Free tier covers Phase 1 |
| YouTube Data API | 10k requests/day | $0 | ✅ Free tier |
| Stripe (payments only) | No charge until revenue | 2.9% + $0.30 | Activated Week 8 |
| **Total Phase 1** | — | **$2–10** | Most costs deferred to Phase 2 |

---

## Post-Phase-1 Criteria (Go/No-Go)

### GO (SUCCESS)
- [ ] One MICRO_SAAS live on Railway with real URL
- [ ] One MEDIA_CHANNEL video unlisted on YouTube
- [ ] Command Center dashboard shows agent logs + portfolio
- [ ] Revenue Engine reads manual ledger entries
- [ ] All tests passing (`pytest tests/ -v`)
- [ ] Dry-run succeeds on WorkLaptop branch

### NO-GO (FAILURE)
- [ ] Vite build fails consistently (Week 4)
- [ ] ElevenLabs quality < 0.8 after 3 attempts (Week 5)
- [ ] Railway deployment times out (Week 6a)
- [ ] YouTube quota exceeded before Week 8 (Week 6b)
- [ ] Supabase migrations fail to run (ongoing)

---

## Handoff to Phase 2

When Phase 1 is complete:
1. **Merge WorkLaptop → main** with commit message "Phase 1 complete: live wedge deployed"
2. **Tag release:** `git tag phase-1-complete && git push origin phase-1-complete`
3. **Update ROADMAP.md:** Mark Phase 1 ✅, start Phase 2 dates
4. **Archive logs:** Save deployment receipts + revenue reports to `docs/phase-1-results/`
5. **Open Phase 2 issues:** QA browser testing, copyright validation, PostHog integration

---

## Links & References

- **README.md:** Phase 1 Stub → Live API Checklist
- **docs/DAY2.md:** Revenue confidence setup (already done)
- **docs/DAY3.md:** Supabase + trends setup (already done)
- **docs/AGENTS.md:** Full agent specs
- **docs/ROADMAP.md:** Phase overview + timelines
- **tests/:** Unit test suite (use as validation gates)

---

**Last Updated:** May 23, 2026  
**Next Review:** June 6, 2026 (end of Week 4)  
**Owner:** AI Squadron Team
