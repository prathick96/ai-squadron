-- AI Squadron — Initial Schema Migration
-- Run order: 001 (first migration, creates all base tables)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- VENTURES — one row per product/channel idea
-- ============================================================
CREATE TABLE IF NOT EXISTS ventures (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venture_id      VARCHAR(64) UNIQUE NOT NULL,
    venture_type    VARCHAR(32) NOT NULL CHECK (venture_type IN ('MICRO_SAAS', 'MEDIA_CHANNEL', 'AFFILIATE_SITE')),
    niche           TEXT NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'IDEATION'
                    CHECK (status IN ('IDEATION','DEVELOPMENT','QA','LIVE','SCALING','KILLED')),
    go_decision     BOOLEAN DEFAULT FALSE,
    feasibility_score NUMERIC(4,3),
    competition_score NUMERIC(4,3),
    target_regions  TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- PIPELINE RUNS — one row per graph execution
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id          UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    venture_id      VARCHAR(64) NOT NULL REFERENCES ventures(venture_id),
    pipeline_stage  VARCHAR(64) NOT NULL DEFAULT 'CEO_NODE',
    status          VARCHAR(32) NOT NULL DEFAULT 'RUNNING'
                    CHECK (status IN ('RUNNING','COMPLETED','FAILED','MANUAL_REVIEW')),
    qa_retry_count  INTEGER DEFAULT 0,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    error_message   TEXT
);

-- ============================================================
-- EVENTS — append-only audit trail of all JSON bus events
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    event_type      VARCHAR(64) NOT NULL,
    schema_version  VARCHAR(16) DEFAULT '1.0.0',
    source_agent    VARCHAR(64) NOT NULL,
    target_agent    VARCHAR(64) NOT NULL,
    correlation_id  UUID NOT NULL,
    priority        VARCHAR(16) DEFAULT 'NORMAL'
                    CHECK (priority IN ('LOW','NORMAL','HIGH','CRITICAL')),
    venture_id      VARCHAR(64),
    run_id          UUID,
    payload         JSONB NOT NULL DEFAULT '{}',
    token_cost      INTEGER DEFAULT 0,
    latency_ms      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_correlation   ON events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_venture        ON events(venture_id);
CREATE INDEX IF NOT EXISTS idx_events_type           ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created_at     ON events(created_at DESC);

-- ============================================================
-- AGENT LOGS — per-agent execution telemetry for dashboard
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_logs (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL,
    venture_id      VARCHAR(64),
    agent_name      VARCHAR(64) NOT NULL,
    status          VARCHAR(32) NOT NULL
                    CHECK (status IN ('IDLE','RUNNING','SUCCESS','FAILED','RETRYING')),
    current_task    TEXT,
    tokens_used     INTEGER DEFAULT 0,
    latency_ms      INTEGER DEFAULT 0,
    retry_count     INTEGER DEFAULT 0,
    error_detail    TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_agent ON agent_logs(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_logs_run   ON agent_logs(run_id);

-- ============================================================
-- REVENUE LEDGER — financial tracking per venture
-- ============================================================
CREATE TABLE IF NOT EXISTS revenue_ledger (
    id              BIGSERIAL PRIMARY KEY,
    venture_id      VARCHAR(64) NOT NULL REFERENCES ventures(venture_id),
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    revenue_source  VARCHAR(32) NOT NULL
                    CHECK (revenue_source IN ('ADSENSE','STRIPE','AFFILIATE','OTHER')),
    amount_usd      NUMERIC(12,2) NOT NULL DEFAULT 0,
    burn_usd        NUMERIC(12,2) NOT NULL DEFAULT 0,
    recorded_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(venture_id, period_start, revenue_source)
);

-- ============================================================
-- PLATFORM ACCOUNTS — OAuth tokens & account registry
-- ============================================================
CREATE TABLE IF NOT EXISTS platform_accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venture_id      VARCHAR(64) NOT NULL REFERENCES ventures(venture_id),
    platform        VARCHAR(32) NOT NULL
                    CHECK (platform IN ('YOUTUBE','TIKTOK','INSTAGRAM','X','RAILWAY')),
    account_handle  VARCHAR(128),
    oauth_token_ref VARCHAR(256),  -- Supabase Vault secret reference (never plain text)
    is_active       BOOLEAN DEFAULT TRUE,
    last_post_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(venture_id, platform)
);

-- ============================================================
-- QA REPORTS — per-artifact quality audit records
-- ============================================================
CREATE TABLE IF NOT EXISTS qa_reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id          UUID NOT NULL,
    venture_id      VARCHAR(64) NOT NULL,
    artifact_type   VARCHAR(32) NOT NULL CHECK (artifact_type IN ('BUILD','CONTENT')),
    is_passed       BOOLEAN NOT NULL,
    retry_count     INTEGER DEFAULT 0,
    checks_run      TEXT[] DEFAULT '{}',
    checks_failed   TEXT[] DEFAULT '{}',
    critique_log    JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- AUTO-UPDATE updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ventures_updated_at
    BEFORE UPDATE ON ventures
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
