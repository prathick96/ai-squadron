-- AI Squadron — Migration 006: legal_clearances table
-- Fixes the silent failure in legal_agent._persist_legal_clearance().
-- The function was catching "relation does not exist" and logging
-- "migration needed?" — this migration resolves that.

CREATE TABLE IF NOT EXISTS legal_clearances (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venture_id           VARCHAR(64)  NOT NULL,
    run_id               VARCHAR(64)  NOT NULL,
    is_cleared           BOOLEAN      NOT NULL,
    platforms_reviewed   TEXT[]       DEFAULT '{}',
    tos_version          VARCHAR(256),
    policy_flags         JSONB        DEFAULT '[]',
    copyright_clear      BOOLEAN      DEFAULT TRUE,
    gdpr_reviewed        BOOLEAN      DEFAULT FALSE,
    clearance_expires_at TIMESTAMPTZ,
    created_at           TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (venture_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_legal_clearances_venture ON legal_clearances(venture_id);
CREATE INDEX IF NOT EXISTS idx_legal_clearances_cleared ON legal_clearances(is_cleared);

-- Convenience view: most recent clearance per venture
CREATE OR REPLACE VIEW latest_legal_clearances AS
SELECT DISTINCT ON (venture_id)
    venture_id,
    is_cleared,
    platforms_reviewed,
    tos_version,
    policy_flags,
    clearance_expires_at,
    created_at
FROM legal_clearances
ORDER BY venture_id, created_at DESC;
