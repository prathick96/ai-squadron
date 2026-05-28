-- 004_revenue_ledger_notes.sql
-- Adds optional free-text notes column to revenue_ledger for manual entries.
ALTER TABLE revenue_ledger
  ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT '';
