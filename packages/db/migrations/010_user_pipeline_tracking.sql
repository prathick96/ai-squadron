-- AI Squadron — Migration 010: Associate pipeline runs with users
-- Enables per-user run counting, plan enforcement, and customer dashboards.
-- Run in Supabase SQL editor after migration 009.

-- ── 1. Add user_id to pipeline_runs ────────────────────────────────────────
ALTER TABLE pipeline_runs
  ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_user ON pipeline_runs(user_id);

-- ── 2. Monthly run counter view ─────────────────────────────────────────────
-- Used by the API to enforce free-tier limit (1 run/month) without a
-- separate table — just aggregates pipeline_runs for the current month.
CREATE OR REPLACE VIEW user_monthly_runs AS
SELECT
    user_id,
    COUNT(*)                                    AS runs_this_month,
    DATE_TRUNC('month', NOW())::date            AS month_start,
    (DATE_TRUNC('month', NOW()) + INTERVAL '1 month')::date AS month_end
FROM pipeline_runs
WHERE user_id IS NOT NULL
  AND started_at >= DATE_TRUNC('month', NOW())
  AND status     NOT IN ('FAILED')             -- only count meaningful attempts
GROUP BY user_id;

-- ── 3. Plan limits lookup ───────────────────────────────────────────────────
-- Mirrors the pricing_plans table — used by API for enforcement.
-- update pricing_plans SET run_limit = -1 for unlimited (builder/studio).
ALTER TABLE pricing_plans
  ADD COLUMN IF NOT EXISTS run_limit INTEGER DEFAULT 1;  -- -1 = unlimited

UPDATE pricing_plans SET run_limit = 1   WHERE name = 'starter';
UPDATE pricing_plans SET run_limit = 10  WHERE name = 'builder';
UPDATE pricing_plans SET run_limit = -1  WHERE name = 'studio';

-- ── 4. RLS: users can only read their own pipeline_runs ────────────────────
ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_own_runs" ON pipeline_runs;
CREATE POLICY "users_own_runs" ON pipeline_runs
    FOR SELECT USING (
        auth.uid() = user_id
        OR auth.uid() IN (                       -- admin bypass
            SELECT id FROM auth.users
            WHERE email = current_setting('app.admin_email', true)
        )
    );

-- Service role can still insert/update for the pipeline background task.
DROP POLICY IF EXISTS "service_role_all" ON pipeline_runs;
CREATE POLICY "service_role_all" ON pipeline_runs
    FOR ALL USING (auth.role() = 'service_role');
