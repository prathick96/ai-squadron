-- AI Squadron — Day 2: Revenue truth, scorecards, confidence reports, human review queue

-- ============================================================
-- VENTURE SCORECARDS — leading indicators per venture (weekly refresh)
-- ============================================================
CREATE TABLE IF NOT EXISTS venture_scorecards (
    id                      BIGSERIAL PRIMARY KEY,
    venture_id              VARCHAR(64) NOT NULL REFERENCES ventures(venture_id),
    period_start            DATE NOT NULL,
    period_end              DATE NOT NULL,
    mrr_usd                 NUMERIC(12,2) DEFAULT 0,
    burn_usd                NUMERIC(12,2) DEFAULT 0,
    gross_margin_pct        NUMERIC(5,2) DEFAULT 0,
    organic_visits_monthly  INTEGER DEFAULT 0,
    retention_30d_pct       NUMERIC(5,2),
    qa_first_pass_rate_pct  NUMERIC(5,2) DEFAULT 0,
    days_live               INTEGER DEFAULT 0,
    platform_monetization   VARCHAR(32) DEFAULT 'NONE'
        CHECK (platform_monetization IN ('NONE','PENDING','YPP','MONETIZED','REJECTED')),
    ltv_usd                 NUMERIC(12,2),
    cac_usd                 NUMERIC(12,2),
    signal                  VARCHAR(16) DEFAULT 'HOLD'
        CHECK (signal IN ('SCALE','HOLD','KILL','WATCH')),
    signal_reason           TEXT,
    recorded_at             TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(venture_id, period_start)
);

CREATE INDEX IF NOT EXISTS idx_scorecards_venture ON venture_scorecards(venture_id);
CREATE INDEX IF NOT EXISTS idx_scorecards_signal ON venture_scorecards(signal);

-- ============================================================
-- CONFIDENCE REPORTS — portfolio-level forecast bands (weekly)
-- ============================================================
CREATE TABLE IF NOT EXISTS confidence_reports (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_week             DATE NOT NULL UNIQUE,
    confidence_score        INTEGER NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
    confidence_tier         VARCHAR(16) NOT NULL
        CHECK (confidence_tier IN ('LOW','MEDIUM','HIGH')),
    mrr_current_usd         NUMERIC(12,2) DEFAULT 0,
    burn_current_usd        NUMERIC(12,2) DEFAULT 0,
    burn_earn_ratio           NUMERIC(8,4) DEFAULT 0,
    forecast_p10_mrr_12mo   NUMERIC(12,2) NOT NULL,
    forecast_p50_mrr_12mo   NUMERIC(12,2) NOT NULL,
    forecast_p90_mrr_12mo   NUMERIC(12,2) NOT NULL,
    leading_indicators      JSONB NOT NULL DEFAULT '{}',
    recommended_actions     JSONB NOT NULL DEFAULT '[]',
    scale_ventures          TEXT[] DEFAULT '{}',
    kill_ventures           TEXT[] DEFAULT '{}',
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- MANUAL REVIEW QUEUE — human gate for QA exhaustion / compliance
-- ============================================================
CREATE TABLE IF NOT EXISTS manual_review_queue (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venture_id              VARCHAR(64) NOT NULL,
    run_id                  UUID NOT NULL,
    review_reason           TEXT NOT NULL,
    artifact_type           VARCHAR(32) CHECK (artifact_type IN ('BUILD','CONTENT')),
    status                  VARCHAR(32) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','APPROVED','REJECTED','DEFERRED')),
    priority                VARCHAR(16) DEFAULT 'HIGH'
        CHECK (priority IN ('LOW','NORMAL','HIGH','CRITICAL')),
    assigned_to             VARCHAR(128),
    notes                   TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    resolved_at             TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_manual_review_status ON manual_review_queue(status);
CREATE INDEX IF NOT EXISTS idx_manual_review_venture ON manual_review_queue(venture_id);

-- ============================================================
-- REVENUE SYNC RUNS — audit trail for Stripe / AdSense ingestion
-- ============================================================
CREATE TABLE IF NOT EXISTS revenue_sync_runs (
    id                      BIGSERIAL PRIMARY KEY,
    source                  VARCHAR(32) NOT NULL CHECK (source IN ('STRIPE','ADSENSE','MANUAL')),
    status                  VARCHAR(32) NOT NULL CHECK (status IN ('SUCCESS','PARTIAL','FAILED')),
    rows_upserted           INTEGER DEFAULT 0,
    error_message           TEXT,
    started_at              TIMESTAMPTZ DEFAULT NOW(),
    completed_at            TIMESTAMPTZ
);

-- Link ventures to Stripe for MRR attribution
ALTER TABLE ventures
    ADD COLUMN IF NOT EXISTS stripe_product_id VARCHAR(128),
    ADD COLUMN IF NOT EXISTS stripe_price_id VARCHAR(128),
    ADD COLUMN IF NOT EXISTS live_url TEXT,
    ADD COLUMN IF NOT EXISTS first_revenue_at TIMESTAMPTZ;
