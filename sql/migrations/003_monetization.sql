-- Monetization: users, plans, entitlements, checkout, deal unlocks, concierge.
-- Run: psql "$DATABASE_URL" -f sql/migrations/003_monetization.sql

CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT NOT NULL UNIQUE,
    name        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plans (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    price_cents     INTEGER NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'USD',
    duration_days   INTEGER,
    plan_type       TEXT NOT NULL DEFAULT 'subscription',
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customer_entitlements (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                 UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    plan_code               TEXT NOT NULL REFERENCES plans (code) ON DELETE RESTRICT,
    starts_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at              TIMESTAMPTZ,
    status                  TEXT NOT NULL DEFAULT 'active',
    source                  TEXT NOT NULL DEFAULT 'mock',
    stripe_customer_id      TEXT,
    stripe_subscription_id  TEXT,
    stripe_payment_intent_id TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_entitlements_user_status ON customer_entitlements (user_id, status);
CREATE INDEX IF NOT EXISTS idx_entitlements_expires ON customer_entitlements (expires_at);

CREATE TABLE IF NOT EXISTS checkout_sessions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    plan_code           TEXT NOT NULL REFERENCES plans (code) ON DELETE RESTRICT,
    stripe_session_id   TEXT,
    amount_cents        INTEGER NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'USD',
    status              TEXT NOT NULL DEFAULT 'created',
    checkout_url        TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_checkout_user ON checkout_sessions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS deal_report_unlocks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    unit_id         UUID REFERENCES units (id) ON DELETE SET NULL,
    floorplan_id    UUID REFERENCES floorplans (id) ON DELETE SET NULL,
    unlocked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    source            TEXT NOT NULL DEFAULT 'entitlement',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deal_unlocks_user_building ON deal_report_unlocks (user_id, building_id);

CREATE TABLE IF NOT EXISTS concierge_requests (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'submitted',
    target_city     TEXT,
    budget_min      NUMERIC(12, 2),
    budget_max      NUMERIC(12, 2),
    bedrooms        NUMERIC(4, 1),
    commute_target  TEXT,
    notes             TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_concierge_user ON concierge_requests (user_id, created_at DESC);

INSERT INTO plans (code, name, price_cents, currency, duration_days, plan_type, description, is_active)
VALUES
    ('free', 'Free', 0, 'USD', NULL, 'free',
     'Browse listings, basic signals, and Deal Report previews.', true),
    ('hunt_pass_30', 'Premium Hunt Pass (30 days)', 1900, 'USD', 30, 'subscription',
     'Unlimited Deal Reports, full rent history, fee breakdown, negotiation tools, alerts, compare.', true),
    ('premium_plus_30', 'Premium Plus (30 days)', 3900, 'USD', 30, 'subscription',
     'Everything in Hunt Pass plus enhanced report export and decision-support placeholders.', true),
    ('concierge_one_time', 'Concierge (one-time)', 14900, 'USD', NULL, 'one_time',
     'Human-assisted shortlist and negotiation help — fulfillment is manual (placeholder).', true)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    price_cents = EXCLUDED.price_cents,
    duration_days = EXCLUDED.duration_days,
    plan_type = EXCLUDED.plan_type,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active;
