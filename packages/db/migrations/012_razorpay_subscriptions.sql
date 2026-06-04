-- 012_razorpay_subscriptions.sql
-- Replace Paddle/Stripe subscription columns with Razorpay equivalents.
-- Run in Supabase SQL Editor.

-- 1. Add razorpay_subscription_id column (unique, used as upsert key)
ALTER TABLE user_subscriptions
  ADD COLUMN IF NOT EXISTS razorpay_subscription_id TEXT UNIQUE;

-- 2. Drop Paddle-specific columns that are no longer used
ALTER TABLE user_subscriptions
  DROP COLUMN IF EXISTS paddle_subscription_id,
  DROP COLUMN IF EXISTS paddle_customer_id;

-- 3. Update revenue_ledger CHECK constraint if it exists
-- (Supabase may enforce the revenue_source enum via a check constraint)
DO $$
BEGIN
  -- Allow RAZORPAY in addition to existing values
  -- If the constraint doesn't exist, this is a no-op
  ALTER TABLE revenue_ledger DROP CONSTRAINT IF EXISTS revenue_ledger_revenue_source_check;
  ALTER TABLE revenue_ledger
    ADD CONSTRAINT revenue_ledger_revenue_source_check
    CHECK (revenue_source IN ('RAZORPAY', 'ADSENSE', 'MANUAL'));
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'revenue_source constraint update skipped: %', SQLERRM;
END;
$$;

-- 4. RLS — razorpay webhook needs service_role to write
-- (existing RLS on user_subscriptions already covers this via service_role)
