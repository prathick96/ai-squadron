-- AI Squadron — Migration 011: Product waitlist / notify-me emails
-- Captures email addresses for upcoming products so we can notify
-- users when the product goes live.

CREATE TABLE IF NOT EXISTS product_waitlist (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id  TEXT NOT NULL,      -- e.g. 'freelancerflow', 'channelmind'
    email       TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    notified_at TIMESTAMPTZ,        -- set when the notification email is sent
    UNIQUE(product_id, email)       -- no duplicates
);

CREATE INDEX IF NOT EXISTS idx_waitlist_product ON product_waitlist(product_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_email   ON product_waitlist(email);

-- Public insert policy — anyone can join the waitlist
ALTER TABLE product_waitlist ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_waitlist_insert" ON product_waitlist
    FOR INSERT WITH CHECK (TRUE);

CREATE POLICY "admin_waitlist_read" ON product_waitlist
    FOR SELECT USING (auth.role() = 'service_role');
