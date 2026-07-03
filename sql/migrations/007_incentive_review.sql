-- Incentive review workflow: submission + admin audit fields.

ALTER TABLE incentives
    ADD COLUMN IF NOT EXISTS submitted_by_user_id UUID REFERENCES users (id) ON DELETE SET NULL;

ALTER TABLE incentives
    ADD COLUMN IF NOT EXISTS reviewed_by_user_id UUID REFERENCES users (id) ON DELETE SET NULL;

ALTER TABLE incentives
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_incentives_status_created ON incentives (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incentives_submitted_by ON incentives (submitted_by_user_id);

COMMENT ON COLUMN incentives.status IS 'pending_review | verified | active (legacy verified) | rejected | expired';
COMMENT ON COLUMN incentives.submitted_by_user_id IS 'User who submitted via POST /incentives/submit';
COMMENT ON COLUMN incentives.reviewed_by_user_id IS 'Admin who verified or rejected';
COMMENT ON COLUMN incentives.reviewed_at IS 'When admin completed review';
