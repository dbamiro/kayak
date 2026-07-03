-- Production: auth fields, refresh tokens, webhook idempotency, alerts ownership,
-- saved buildings, source crawl health.
-- psql "$DATABASE_URL" -f sql/migrations/004_production.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_hash ON refresh_tokens (token_hash);

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stripe_event_id     TEXT NOT NULL UNIQUE,
    event_type          TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'received',
    processed_at        TIMESTAMPTZ,
    raw_payload         JSONB,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE alerts ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users (id) ON DELETE CASCADE;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_type TEXT NOT NULL DEFAULT 'general';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS last_triggered_at TIMESTAMPTZ;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts (user_id);

CREATE TABLE IF NOT EXISTS saved_buildings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, building_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_buildings_user ON saved_buildings (user_id);

ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_crawl_at TIMESTAMPTZ;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_crawl_status TEXT;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_error TEXT;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_listings_count INTEGER;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_parser_used TEXT;
