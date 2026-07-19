-- Kayak v1 baseline schema (empty database bootstrap only).
-- Production: ALLOW_PROD_BOOTSTRAP=yes ./scripts/bootstrap_prod_db.sh
--   (applies this file once, then sql/migrations/*.sql, then seed_plans.sql — never demo seeds)
-- Dev: ./scripts/bootstrap_db.sh
-- Incremental changes belong in sql/migrations/*.sql (source of truth). See docs/DATABASE.md.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE dmv_area AS ENUM (
    'DC',
    'ARLINGTON',
    'ALEXANDRIA',
    'TYSONS',
    'RESTON',
    'ASHBURN',
    'SILVER_SPRING',
    'BETHESDA'
);

CREATE TYPE fetch_mode AS ENUM ('http', 'playwright');
CREATE TYPE capture_format AS ENUM ('html', 'json');

CREATE TABLE buildings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    slug            TEXT UNIQUE NOT NULL,
    address_line1   TEXT,
    city            TEXT NOT NULL,
    state           CHAR(2) NOT NULL DEFAULT 'VA',
    postal_code     TEXT,
    neighborhood    TEXT,
    dmv_area        dmv_area NOT NULL,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    property_url    TEXT NOT NULL,
    portal_urls     JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_buildings_dmv_area ON buildings (dmv_area);
CREATE INDEX idx_buildings_city ON buildings (city);

CREATE TABLE crawl_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',
    stats           JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message   TEXT
);

CREATE TABLE sources (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id         UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    url                 TEXT NOT NULL,
    source_type         TEXT NOT NULL DEFAULT 'direct_site',
    crawl_strategy      fetch_mode NOT NULL DEFAULT 'http',
    wait_selector       TEXT,
    active              BOOLEAN NOT NULL DEFAULT true,
    -- Route this source through the configured proxy (requires PROXY_ENABLED=true).
    use_proxy           BOOLEAN NOT NULL DEFAULT false,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_crawl_at       TIMESTAMPTZ,
    last_crawl_status   TEXT,
    last_error          TEXT,
    last_listings_count INTEGER,
    last_parser_used    TEXT,
    UNIQUE (building_id, url)
);

CREATE INDEX idx_sources_building ON sources (building_id);

CREATE TABLE raw_documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id       UUID REFERENCES sources (id) ON DELETE SET NULL,
    building_id     UUID REFERENCES buildings (id) ON DELETE SET NULL,
    crawl_run_id    UUID,
    source_url      TEXT NOT NULL,
    fetch_mode      fetch_mode NOT NULL,
    format          capture_format NOT NULL,
    body            TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    http_status     INTEGER,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_raw_documents_building_time ON raw_documents (building_id, captured_at DESC);

CREATE TABLE floorplans (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    external_key    TEXT NOT NULL,
    name            TEXT,
    bedrooms        NUMERIC (4, 1),
    bathrooms       NUMERIC (4, 1),
    sqft            INTEGER,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (building_id, external_key)
);

CREATE INDEX idx_floorplans_building ON floorplans (building_id);

CREATE TABLE units (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    floorplan_id    UUID REFERENCES floorplans (id) ON DELETE SET NULL,
    external_key    TEXT NOT NULL,
    unit_label      TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (building_id, external_key)
);

CREATE INDEX idx_units_building ON units (building_id);

CREATE TABLE listings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    external_key    TEXT,
    unit_label      TEXT,
    floorplan_name  TEXT,
    bedrooms        NUMERIC (3, 1),
    bathrooms       NUMERIC (3, 1),
    sqft            INTEGER,
    floorplan_id    UUID REFERENCES floorplans (id) ON DELETE SET NULL,
    unit_id         UUID REFERENCES units (id) ON DELETE SET NULL,
    UNIQUE (building_id, external_key)
);

CREATE INDEX idx_listings_building ON listings (building_id);

CREATE TABLE listing_snapshots (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_id              UUID NOT NULL REFERENCES listings (id) ON DELETE CASCADE,
    captured_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    base_rent_monthly       NUMERIC (12, 2),
    lease_term_months       INTEGER,
    move_in_date            DATE,
    availability_status     TEXT,
    concessions             JSONB NOT NULL DEFAULT '{}'::jsonb,
    fees                    JSONB NOT NULL DEFAULT '{}'::jsonb,
    utilities_estimate      NUMERIC (12, 2),
    effective_rent_monthly  NUMERIC (12, 2),
    all_in_monthly          NUMERIC (12, 2),
    leasing_pressure_score  SMALLINT,
    negotiation_score       SMALLINT,
    parser_name             TEXT,
    parser_version          TEXT,
    notes                   TEXT,
    raw_document_id         UUID REFERENCES raw_documents (id) ON DELETE SET NULL,
    parser_confidence       NUMERIC (8, 5),
    raw_fragment            JSONB,
    field_confidences       JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_snapshots_listing_time ON listing_snapshots (listing_id, captured_at DESC);

CREATE TABLE snapshot_concessions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_snapshot_id UUID NOT NULL REFERENCES listing_snapshots (id) ON DELETE CASCADE,
    raw_text            TEXT NOT NULL,
    parser_confidence   NUMERIC (8, 5),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE snapshot_fees (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_snapshot_id UUID NOT NULL REFERENCES listing_snapshots (id) ON DELETE CASCADE,
    raw_text            TEXT NOT NULL,
    parser_confidence   NUMERIC (8, 5),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE raw_captures (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id     UUID REFERENCES buildings (id) ON DELETE SET NULL,
    listing_id      UUID REFERENCES listings (id) ON DELETE SET NULL,
    source_url      TEXT NOT NULL,
    fetch_mode      fetch_mode NOT NULL,
    format          capture_format NOT NULL,
    body            TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    http_status     INTEGER,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_raw_building_time ON raw_captures (building_id, captured_at DESC);

-- --- Monetization (plans, users, checkout, deal unlocks, concierge) ---

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT NOT NULL UNIQUE,
    name            TEXT,
    password_hash   TEXT,
    email_verified  BOOLEAN NOT NULL DEFAULT false,
    is_admin        BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_refresh_user ON refresh_tokens (user_id);
CREATE INDEX idx_refresh_hash ON refresh_tokens (token_hash);

CREATE TABLE alerts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID REFERENCES users (id) ON DELETE CASCADE,
    email               TEXT,
    label               TEXT,
    name                TEXT,
    criteria            JSONB NOT NULL,
    alert_type          TEXT NOT NULL DEFAULT 'general',
    active              BOOLEAN NOT NULL DEFAULT true,
    last_triggered_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_alerts_user ON alerts (user_id);

CREATE TABLE saved_buildings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, building_id)
);

CREATE INDEX idx_saved_buildings_user ON saved_buildings (user_id);

CREATE TABLE plans (
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

CREATE TABLE customer_entitlements (
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

CREATE INDEX idx_entitlements_user_status ON customer_entitlements (user_id, status);
CREATE INDEX idx_entitlements_expires ON customer_entitlements (expires_at);

CREATE TABLE checkout_sessions (
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

CREATE INDEX idx_checkout_user ON checkout_sessions (user_id, created_at DESC);

CREATE TABLE deal_report_unlocks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    unit_id         UUID REFERENCES units (id) ON DELETE SET NULL,
    floorplan_id    UUID REFERENCES floorplans (id) ON DELETE SET NULL,
    unlocked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    source            TEXT NOT NULL DEFAULT 'entitlement',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_deal_unlocks_user_building ON deal_report_unlocks (user_id, building_id);

CREATE TABLE concierge_requests (
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

CREATE INDEX idx_concierge_user ON concierge_requests (user_id, created_at DESC);

CREATE TABLE stripe_webhook_events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stripe_event_id     TEXT NOT NULL UNIQUE,
    event_type          TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'received',
    processed_at        TIMESTAMPTZ,
    raw_payload         JSONB,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
ON CONFLICT (code) DO NOTHING;
