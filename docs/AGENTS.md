# AI Squadron — Agent Catalog

Every agent is a LangGraph node (or standalone cron service) with a fixed input contract, output artifact, and bus events. The Revenue Engine sits outside the graph and governs portfolio-level SCALE/KILL decisions.

## Hierarchy Overview

```
Revenue Engine (cron) ──broadcasts──► ORCHESTRATOR / Command Center
         ▲                                    │
         │ GROWTH_REPORT, revenue metrics     │ MANUAL_REVIEW, KILL, SCALE
         │                                    ▼
RESEARCH (Kimi Council) → CEO → PRODUCT → [ENGINEERING | CONTENT] → QA ⟳ → SECURITY → ACCOUNT_DIST
    → DEPLOYMENT → MARKETING → GLOBAL → GROWTH → END
```

---

## 0. Market Research Council (`RESEARCH_NODE`)

**Models:** Kimi K2.x via OpenRouter (3 parallel scouts + 1 debate synthesizer)  
**Produces:** `ResearchDossier`, `RESEARCH_DOSSIER_READY` event  
**Does not:** Set `go_decision` or publish `VentureBrief`

See [RESEARCH_COUNCIL.md](./RESEARCH_COUNCIL.md).

| Scout | Role |
|-------|------|
| Opportunity | High RPM / growth niches |
| Skeptic | Risks, saturation, policy |
| Execution | Build feasibility, time-to-revenue |

---

## 1. AI CEO — Niche Scout (`CEO_NODE`)

**Model:** Gemini 2.5 Pro  
**Consumes:** `ResearchDossier` from Research Council, prior `GROWTH_REPORT` events  
**Produces:** `VentureBrief` artifact, `VENTURE_BRIEF_READY` event  

**Responsibilities**
- Ingest macro and micro trend signals; score niches on feasibility (0–1), competition (0–1), and RPM potential.
- Produce a Venture Brief: target audience, TAM estimate, top competitors with moat gaps, recommended monetization, content angles.
- Issue `go_decision`: only ventures above feasibility threshold (default 0.65) proceed to Product.
- Feed portfolio gaps back from Growth (channels/products with declining retention get deprioritized).

**Does not:** Write code, post to platforms, or override Security/QA failures.

---

## 2. AI Product Team (`PRODUCT_NODE`)

**Model:** Gemini 2.0 Flash  
**Consumes:** `VentureBrief`  
**Produces:** `TechSpec` artifact, `TECH_SPEC_READY` event  

**Responsibilities**
- Translate brief into a Technical Specification: user flows, P0/P1 features, data models, API routes, stack defaults (React 19 + Vite, FastAPI, Supabase, Vercel).
- Set `product_type`: `MICRO_SAAS` | `MEDIA_CHANNEL` | `AFFILIATE_SITE` (routes pipeline branch).
- Estimate build complexity and token budget for Engineering.

---

## 3. AI Engineering Team (`ENGINEERING_NODE`)

**Model:** Claude Sonnet 4.6  
**Consumes:** `TechSpec`, optional `QA_FAILED` with `qa_target=engineering` and `critique_log`  
**Produces:** `BuildArtifact`, `BUILD_COMPLETE` event  

**Responsibilities**
- Generate production-ready React 19 + Vite codebase (modular components for 450+ product scale).
- Run local Vite build; attach `vite_build_exit_code`, `bundle_size_kb`, `test_results`.
- On QA retry: apply `fix_directive` patches from Auditor without human input (max 3 attempts).

---

## 4. AI Content Team (`CONTENT_NODE`)

**Model:** Gemini 2.0 Flash + tool APIs (ElevenLabs, Remotion, fal.ai)  
**Consumes:** `VentureBrief` or content angles, optional `QA_FAILED` with `qa_target=content`  
**Produces:** `ContentPackage`, `CONTENT_PACKAGE_READY` event  

**Responsibilities**
- Script: hook, body sections, word count, duration target.
- Audio: ElevenLabs (or XTTS local) with `human_likeness_score` ≥ 0.85 gate.
- Video: Remotion + FFmpeg assembly; captions required.
- Thumbnail: Flux via fal.ai; original assets only (no stock watermarks).
- SEO metadata within platform title/description limits.

**Copyright stance:** Original scripts and generated assets; no copyrighted music; Security validates before publish.

---

## 5. AI QA Auditor (`QA_NODE`)

**Models:** Deterministic checks + Claude Haiku (critique)  
**Consumes:** `BuildArtifact` OR `ContentPackage`  
**Produces:** `QAReport`, `QA_PASSED` or `QA_FAILED` event  

**Two engines**

| Engine | Target | Checks |
|--------|--------|--------|
| Technical Validator | BUILD | Vite exit code, bundle size, test pass rate, component render |
| Compliance & Aesthetic Validator | CONTENT | Human-likeness ≥ 0.85, metadata length, duration bounds, copyright scan stub |

**Recursive loop**
- `is_passed=true` → Security Node  
- `is_passed=false` + `retry < max_retries` → Engineering or Content with `critique_log`  
- `retry >= max_retries` → `MANUAL_REVIEW_REQUIRED` broadcast  

---

## 6. AI Security Agent (`SECURITY_NODE`)

**Model:** Gemini 2.0 Flash (rule engine + LLM edge cases)  
**Consumes:** QA-passed artifact + platform ToS snapshot  
**Produces:** `SecurityClearance`, `SECURITY_CLEARANCE_GRANTED` or `SECURITY_VIOLATION_DETECTED`  

**Responsibilities**
- Enforce YouTube, TikTok, Instagram ToS: original content, upload rate limits, metadata honesty, no artificial engagement.
- Flag prohibited patterns (spam titles, misleading metadata, engagement pods).
- Generate jittered posting windows per region (never burst-post across accounts).
- **Does not** create accounts or bypass CAPTCHAs; only clears content that passed QA.

---

## 7. AI Account Distribution (`ACCOUNT_DISTRIBUTION_NODE`)

**Model:** None (deterministic policy engine)  
**Consumes:** `SecurityClearance`, venture `target_regions`  
**Produces:** `AccountDistributionPlan`, `ACCOUNTS_PROVISIONED` event  

**Responsibilities**
- Map ventures to **existing** platform accounts in `platform_accounts` table (one account per platform per venture at Phase 1).
- Enforce anti-ban policy: max posts/day per platform, minimum hours between posts, no duplicate content across accounts within 72h.
- Register OAuth token refs (Supabase Vault); never store plain tokens in state or logs.
- Phase 2+: suggest new account creation only via official APIs and human-verified OAuth flows (no automated mass signup).

**Legal boundary:** Autonomous operation uses official APIs with stored OAuth. Mass fake account creation violates platform ToS and is explicitly out of scope.

---

## 8. AI Deployment Team (`DEPLOYMENT_NODE`)

**Model:** None (tool execution)  
**Consumes:** Build and/or Content + clearance + account plan  
**Produces:** `DeploymentReceipt`, `DEPLOYMENT_COMPLETE` event  

**Responsibilities**
- SaaS: Vercel Deploy API, smoke test URL.
- Media: YouTube Data API v3 / TikTok Content Posting API (when approved) / Instagram Graph API.
- Respect Account Distribution rate limits from clearance.

---

## 9. AI Marketing Team (`MARKETING_NODE`)

**Model:** Gemini 2.0 Flash  
**Consumes:** Deployment URLs, TechSpec  
**Produces:** `CampaignPlan`, `CAMPAIGN_LAUNCHED` event  

**Responsibilities**
- Programmatic SEO pages for SaaS (sitemap, meta, internal links).
- Social distribution schedule aligned with Security posting windows.
- Affiliate link placement where `AFFILIATE_SITE` ventures apply.

---

## 10. AI Global / Regional Research (`GLOBAL_NODE`)

**Model:** Gemini 2.0 Flash  
**Consumes:** `ContentPackage`, `CampaignPlan`, region RPM table  
**Produces:** `LocalizationMap`, `LOCALIZATION_COMPLETE` event  

**Responsibilities**
- Rank countries by addressable RPM (US, UK, CA, AU, DE typically top for English AdSense).
- Localize titles, descriptions, hashtags; shift post times to local peak engagement.
- Output `TREND_ANALYSIS_READY` for Command Center heatmap.

---

## 11. AI Growth Team (`GROWTH_NODE`)

**Model:** Gemini 2.0 Flash + analytics APIs  
**Consumes:** All prior artifacts + analytics stubs  
**Produces:** `GrowthSignals`, `GROWTH_REPORT_READY` event  

**Responsibilities**
- Track retention, CTR, watch time, Stripe MRR per venture.
- Compare channel/product performance vs portfolio median.
- Recommend CEO niche pivots; close the feedback loop to Niche Scout.

---

## 12. Revenue Engine (standalone service)

**Model:** Gemini 2.5 Pro (portfolio reasoning) + SQL  
**Location:** `apps/revenue-engine/main.py`  
**Schedule:** Daily 00:00 UTC via APScheduler  

**Responsibilities**
- Aggregate `revenue_ledger`: AdSense, Stripe, affiliate.
- Emit `REVENUE_SCALE_SIGNAL` (MRR ≥ $200 default) or `REVENUE_KILL_SIGNAL` (MRR < $50 for 90+ days).
- Compute burn vs earn (API + hosting costs vs realized revenue).
- Feed Command Center revenue ticker and orchestrator plans.

**Kill/Scale defaults** (env-configurable): `KILL_THRESHOLD_MRR=50`, `KILL_THRESHOLD_DAYS=90`, `SCALE_THRESHOLD_MRR=200`.

---

## Agent → Event Matrix

| Agent | Publishes | Subscribes to |
|-------|-----------|---------------|
| CEO | VENTURE_BRIEF_READY | GROWTH_REPORT_READY |
| Product | TECH_SPEC_READY | VENTURE_BRIEF_READY |
| Engineering | BUILD_COMPLETE | TECH_SPEC_READY, QA_FAILED (engineering) |
| Content | CONTENT_PACKAGE_READY | VENTURE_BRIEF_READY, QA_FAILED (content) |
| QA Auditor | QA_PASSED, QA_FAILED, MANUAL_REVIEW_REQUIRED | BUILD_COMPLETE, CONTENT_PACKAGE_READY |
| Security | SECURITY_CLEARANCE_GRANTED | QA_PASSED |
| Account Distribution | ACCOUNTS_PROVISIONED | SECURITY_CLEARANCE_GRANTED |
| Deployment | DEPLOYMENT_COMPLETE | ACCOUNTS_PROVISIONED |
| Marketing | CAMPAIGN_LAUNCHED | DEPLOYMENT_COMPLETE |
| Global | LOCALIZATION_COMPLETE, TREND_ANALYSIS_READY | CAMPAIGN_LAUNCHED |
| Growth | GROWTH_REPORT_READY | LOCALIZATION_COMPLETE |
| Revenue Engine | SCALE/KILL signals | GROWTH_REPORT_READY, ledger cron |

See [COMMUNICATION_PROTOCOL.md](./COMMUNICATION_PROTOCOL.md) for envelope format and state store rules.
