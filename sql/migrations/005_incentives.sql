-- Incentive-focused product layer (move-in specials, effective rent, savings).

CREATE TABLE IF NOT EXISTS incentives (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    building_id             UUID REFERENCES buildings(id) ON DELETE SET NULL,
    submitted_listing_id    UUID REFERENCES listings(id) ON DELETE SET NULL,
    source_url              TEXT,
    incentive_type          TEXT NOT NULL,
    free_months             NUMERIC(6, 3),
    lease_term_months       INTEGER,
    listed_rent             INTEGER,
    recurring_fee_monthly   INTEGER DEFAULT 0,
    one_time_fee            INTEGER DEFAULT 0,
    waived_fee_amount       INTEGER DEFAULT 0,
    gift_card_amount        INTEGER DEFAULT 0,
    parking_discount_monthly INTEGER DEFAULT 0,
    raw_text                TEXT,
    applies_to              TEXT,
    expires_at              TIMESTAMPTZ,
    verified_at             TIMESTAMPTZ,
    verification_method     TEXT,
    confidence_score        NUMERIC(4, 3) DEFAULT 0.5,
    is_demo                 BOOLEAN NOT NULL DEFAULT false,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incentives_building ON incentives(building_id);
CREATE INDEX IF NOT EXISTS idx_incentives_type ON incentives(incentive_type);
CREATE INDEX IF NOT EXISTS idx_incentives_demo ON incentives(is_demo);

CREATE TABLE IF NOT EXISTS incentive_snapshots (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incentive_id            UUID NOT NULL REFERENCES incentives(id) ON DELETE CASCADE,
    captured_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_text                TEXT,
    free_months             NUMERIC(6, 3),
    lease_term_months       INTEGER,
    listed_rent             INTEGER,
    estimated_savings       INTEGER,
    effective_rent          INTEGER,
    all_in_effective_rent   INTEGER,
    confidence_score        NUMERIC(4, 3)
);

CREATE INDEX IF NOT EXISTS idx_incentive_snapshots_incentive ON incentive_snapshots(incentive_id, captured_at DESC);
