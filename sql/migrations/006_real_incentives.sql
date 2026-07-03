-- Real incentive data readiness: credits, status, capture metadata, incentive_sources.

ALTER TABLE incentives
    ADD COLUMN IF NOT EXISTS custom_credit_amount INTEGER NOT NULL DEFAULT 0;

ALTER TABLE incentives
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

ALTER TABLE incentives
    ADD COLUMN IF NOT EXISTS capture_method TEXT;

CREATE INDEX IF NOT EXISTS idx_incentives_status ON incentives(status);
CREATE INDEX IF NOT EXISTS idx_incentives_capture ON incentives(capture_method);

COMMENT ON COLUMN incentives.free_months IS 'Fractional months supported (e.g. 1.5, 2.77 from weeks/4.333)';
COMMENT ON COLUMN incentives.status IS 'active | pending_review | expired | rejected';
COMMENT ON COLUMN incentives.capture_method IS 'crawler | manual_admin | user_submission | partner_csv | leasing_office_verified | screenshot_review';

CREATE TABLE IF NOT EXISTS incentive_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    building_id     UUID REFERENCES buildings(id) ON DELETE SET NULL,
    source_url      TEXT,
    source_type     TEXT,
    capture_method  TEXT NOT NULL DEFAULT 'crawler',
    active          BOOLEAN NOT NULL DEFAULT true,
    last_checked_at TIMESTAMPTZ,
    last_status     TEXT,
    last_error      TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incentive_sources_building ON incentive_sources(building_id);
CREATE INDEX IF NOT EXISTS idx_incentive_sources_active ON incentive_sources(active);
