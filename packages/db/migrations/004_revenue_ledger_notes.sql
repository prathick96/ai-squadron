-- 004_revenue_ledger_notes.sql
-- Adds notes column and fixes revenue_source constraint to include MANUAL.

ALTER TABLE revenue_ledger
  ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT '';

-- Drop and recreate the check constraint to add MANUAL source.
-- Safe to run multiple times: DROP IF EXISTS is idempotent.
ALTER TABLE revenue_ledger
  DROP CONSTRAINT IF EXISTS revenue_ledger_revenue_source_check;

ALTER TABLE revenue_ledger
  ADD CONSTRAINT revenue_ledger_revenue_source_check
  CHECK (revenue_source IN ('ADSENSE', 'STRIPE', 'AFFILIATE', 'OTHER', 'MANUAL'));
