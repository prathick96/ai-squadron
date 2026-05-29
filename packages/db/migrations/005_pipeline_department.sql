-- AI Squadron — Migration 005: Add department column to pipeline_runs
-- Required for Pipeline Control history to show PRODUCT vs MEDIA correctly.

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS department VARCHAR(32) DEFAULT 'PRODUCT'
        CHECK (department IN ('PRODUCT', 'MEDIA', 'AUTO'));

-- updated_at for accurate sort/merge with in-memory registry
ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
