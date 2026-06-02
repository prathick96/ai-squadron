-- AI Squadron — Migration 008: User authentication, subscriptions, and pricing
-- Uses the SAME Supabase project as the pipeline infrastructure.
-- Run this in the Supabase SQL editor (same project, same credentials).
--
-- After running:
--   1. Enable Email auth in Supabase Dashboard → Authentication → Providers
--   2. Set VITE_SUPABASE_URL = same value as SUPABASE_URL in Railway
--   3. Set VITE_SUPABASE_ANON_KEY = the anon key from Supabase Dashboard (safe for browser)
--   4. Set VITE_ADMIN_EMAIL = your email (redirects to Command Center after login)

-- ============================================================
-- USER PROFILES — links Supabase auth users to their plan
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
    id             UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email          TEXT NOT NULL,
    plan           TEXT NOT NULL DEFAULT 'starter'
                   CHECK (plan IN ('starter', 'builder', 'studio')),
    paddle_customer_id TEXT,
    is_admin       BOOLEAN DEFAULT FALSE,
    onboarding_done BOOLEAN DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);

-- Automatically create a user_profile row when someone signs up
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO user_profiles (id, email)
    VALUES (NEW.id, NEW.email)
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ============================================================
-- USER SUBSCRIPTIONS — synced from Paddle webhooks
-- ============================================================
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                 UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
    paddle_subscription_id  TEXT UNIQUE,
    paddle_customer_id      TEXT,
    plan                    TEXT NOT NULL DEFAULT 'starter',
    status                  TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'paused', 'cancelled', 'past_due', 'trialing')),
    price_id                TEXT,
    billing_interval        TEXT CHECK (billing_interval IN ('month', 'year')),
    current_period_start    TIMESTAMPTZ,
    current_period_end      TIMESTAMPTZ,
    cancel_at_period_end    BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user  ON user_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_paddle ON user_subscriptions(paddle_subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON user_subscriptions(status);

-- ============================================================
-- PRICING PLANS — editable without code changes
-- ============================================================
CREATE TABLE IF NOT EXISTS pricing_plans (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                   TEXT UNIQUE NOT NULL,   -- 'starter' | 'builder' | 'studio'
    display_name           TEXT NOT NULL,
    price_monthly_usd      NUMERIC(10,2) NOT NULL DEFAULT 0,
    price_annual_usd       NUMERIC(10,2) NOT NULL DEFAULT 0,
    paddle_monthly_price_id TEXT,
    paddle_annual_price_id  TEXT,
    pipeline_runs_per_month INTEGER DEFAULT 1,    -- -1 = unlimited
    max_ventures           INTEGER DEFAULT 1,      -- -1 = unlimited
    features               JSONB DEFAULT '[]',
    is_active              BOOLEAN DEFAULT TRUE,
    sort_order             INTEGER DEFAULT 0,
    created_at             TIMESTAMPTZ DEFAULT NOW()
);

-- Seed default plans
INSERT INTO pricing_plans (name, display_name, price_monthly_usd, price_annual_usd, pipeline_runs_per_month, max_ventures, features, sort_order)
VALUES
    ('starter', 'Starter', 0, 0, 1, 1,
     '["1 pipeline run/month","1 active venture","Product pipeline only","Community support","Build inspection & download"]',
     1),
    ('builder', 'Builder', 49, 39, 10, 5,
     '["10 pipeline runs/month","5 active ventures","Product + Media pipelines","Live niche research","ElevenLabs voice generation","Real Railway deployment","Priority email support","14-day money-back guarantee"]',
     2),
    ('studio', 'Studio', 149, 119, -1, -1,
     '["Unlimited pipeline runs","Unlimited ventures","Product + Media pipelines","YouTube + TikTok publishing","Stripe / Paddle revenue sync","PostHog analytics","Custom niche briefs","Dedicated Slack channel","14-day money-back guarantee"]',
     3)
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- ROW LEVEL SECURITY — users can only see their own data
-- ============================================================
ALTER TABLE user_profiles       ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_subscriptions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_plans       ENABLE ROW LEVEL SECURITY;

-- user_profiles: read/update own row only
CREATE POLICY "users_own_profile" ON user_profiles
    FOR ALL USING (auth.uid() = id);

-- user_subscriptions: read own subscriptions only
CREATE POLICY "users_own_subscriptions" ON user_subscriptions
    FOR SELECT USING (auth.uid() = user_id);

-- pricing_plans: public read (anyone can see plans)
CREATE POLICY "public_pricing" ON pricing_plans
    FOR SELECT USING (TRUE);

-- Updated_at trigger for user_profiles
CREATE TRIGGER user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER user_subscriptions_updated_at
    BEFORE UPDATE ON user_subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
