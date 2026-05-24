-- AI Squadron — Day 3: Pipeline artifacts + manual revenue entry support

-- ============================================================
-- RESEARCH DOSSIERS — persisted council output per run
-- ============================================================
CREATE TABLE IF NOT EXISTS research_dossiers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id          VARCHAR(64) NOT NULL,
    venture_id      VARCHAR(64) NOT NULL,
    dossier         JSONB NOT NULL,
    debate_transcript JSONB DEFAULT '[]',
    research_mode   VARCHAR(32) DEFAULT 'mock',
    council_confidence NUMERIC(4,3),
    recommended_primary_niche TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_dossiers_run ON research_dossiers(run_id);
CREATE INDEX IF NOT EXISTS idx_research_dossiers_venture ON research_dossiers(venture_id);

-- ============================================================
-- Allow pipeline_runs.run_id as VARCHAR (graph uses string UUIDs)
-- ============================================================
-- If your 001 migration used UUID type strictly, runs still work via string cast in app layer.

-- ============================================================
-- Manual revenue notes (Stripe not configured yet)
-- ============================================================
COMMENT ON TABLE revenue_ledger IS 'Stripe/AdSense sync + manual rows via scripts/record_revenue.py';
