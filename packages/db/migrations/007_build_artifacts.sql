-- AI Squadron — Migration 007: build_artifacts
-- Persists LLM-generated SaaS source files so they survive Railway redeploys.
-- /tmp/squadron-builds/ is wiped on every container restart; this is the
-- permanent store that the build inspection API reads from.

CREATE TABLE IF NOT EXISTS build_artifacts (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venture_id  VARCHAR(64)  NOT NULL UNIQUE,  -- one row per venture (upsert on retry)
    run_id      VARCHAR(64),
    build_hash  VARCHAR(32),
    files       JSONB        NOT NULL DEFAULT '[]',   -- [{path, content, size_bytes}]
    file_count  INTEGER      DEFAULT 0,
    total_kb    NUMERIC(10,1) DEFAULT 0,
    created_at  TIMESTAMPTZ  DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_build_artifacts_venture ON build_artifacts(venture_id);

CREATE TRIGGER build_artifacts_updated_at
    BEFORE UPDATE ON build_artifacts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
