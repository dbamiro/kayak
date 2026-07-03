-- Demo move-in specials for seed buildings only (is_demo=true).
-- Run after schema + seed + migrations 005 and 006:
--   psql "$DATABASE_URL" -f sql/migrations/005_incentives.sql
--   psql "$DATABASE_URL" -f sql/migrations/006_real_incentives.sql
--   psql "$DATABASE_URL" -f sql/seed_incentives.sql

DELETE FROM incentive_snapshots WHERE incentive_id IN (SELECT id FROM incentives WHERE is_demo = true);
DELETE FROM incentives WHERE is_demo = true;

-- 1 month free
INSERT INTO incentives (
    building_id, incentive_type, free_months, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'free_months', 1, 14, 2450,
    'DEMO: 1 month free on select 1BR homes — illustrative seed only',
    'select units', 0.95, true, 'partner_csv', 'active', '{"demo": true, "bedrooms": 1}'::jsonb
FROM buildings b WHERE b.slug = 'the-hepburn-dc';

-- 2 months free
INSERT INTO incentives (
    building_id, incentive_type, free_months, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'free_months', 2, 15, 2680,
    'DEMO: 2 months free when you sign a 15-month lease',
    'new leases 15+ months', 0.95, true, 'partner_csv', 'active', '{"demo": true, "bedrooms": 2}'::jsonb
FROM buildings b WHERE b.slug = 'the-bartlett-arlington';

-- 3 months free
INSERT INTO incentives (
    building_id, incentive_type, free_months, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'free_months', 3, 16, 2100,
    'DEMO: 3 months free on studio homes — seed data',
    'studios only', 0.92, true, 'partner_csv', 'active', '{"demo": true, "bedrooms": 0}'::jsonb
FROM buildings b WHERE b.slug = 'the-muse-alexandria';

-- 4 months free (example only — not a product limit)
INSERT INTO incentives (
    building_id, incentive_type, free_months, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'free_months', 4, 16, 2400,
    'DEMO: 4 months free on 16-month lease — example from product spec',
    '16-month lease required', 0.95, true, 'partner_csv', 'active', '{"demo": true, "bedrooms": 1}'::jsonb
FROM buildings b WHERE b.slug = 'verse-tysons';

-- 5 months free
INSERT INTO incentives (
    building_id, incentive_type, free_months, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'free_months', 5, 18, 2750,
    'DEMO: 5 months free on 18-month lease',
    '18-month lease', 0.93, true, 'partner_csv', 'active', '{"demo": true}'::jsonb
FROM buildings b WHERE b.slug = 'reston-gateway-example';

-- 6 weeks free (~1.385 months)
INSERT INTO incentives (
    building_id, incentive_type, free_months, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'free_weeks', 1.385, 14, 2320,
    'DEMO: 6 weeks free on select floorplans',
    'select units', 0.9, true, 'partner_csv', 'active', '{"demo": true, "weeks_free": 6}'::jsonb
FROM buildings b WHERE b.slug = 'the-hepburn-dc'
AND NOT EXISTS (
    SELECT 1 FROM incentives i WHERE i.building_id = b.id AND i.is_demo AND i.raw_text LIKE '%6 weeks%'
);

-- 8 weeks free (~1.846 months) — second listing at Bartlett
INSERT INTO incentives (
    building_id, incentive_type, free_months, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'free_weeks', 1.846, 15, 2550,
    'DEMO: 8 weeks free when you lease this month',
    'limited time', 0.9, true, 'partner_csv', 'active', '{"demo": true, "weeks_free": 8}'::jsonb
FROM buildings b WHERE b.slug = 'the-bartlett-arlington';

-- Waived admin fee
INSERT INTO incentives (
    building_id, incentive_type, free_months, lease_term_months, listed_rent,
    waived_fee_amount, raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'waived_admin_fee', 0, 12, 2295,
    500, 'DEMO: Waived admin fee ($500 value)',
    'all homes this month', 0.9, true, 'partner_csv', 'active', '{"demo": true}'::jsonb
FROM buildings b WHERE b.slug = 'the-harrison-silver-spring';

-- Gift card
INSERT INTO incentives (
    building_id, incentive_type, gift_card_amount, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'gift_card', 1000, 13, 2550,
    'DEMO: $1,000 gift card when you apply within 72 hours',
    '72-hour look special', 0.88, true, 'partner_csv', 'active', '{"demo": true}'::jsonb
FROM buildings b WHERE b.slug = 'reston-gateway-example'
AND NOT EXISTS (
    SELECT 1 FROM incentives i WHERE i.building_id = b.id AND i.is_demo AND i.incentive_type = 'gift_card'
);

-- $1,500 rent credit
INSERT INTO incentives (
    building_id, incentive_type, custom_credit_amount, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'rent_credit', 1500, 14, 2425,
    'DEMO: $1,500 move-in credit on 14-month leases',
    '14-month lease', 0.9, true, 'partner_csv', 'active', '{"demo": true}'::jsonb
FROM buildings b WHERE b.slug = 'the-muse-alexandria';

-- Free parking 12 months ($150/mo value)
INSERT INTO incentives (
    building_id, incentive_type, parking_discount_monthly, lease_term_months, listed_rent,
    raw_text, applies_to, confidence_score, is_demo, capture_method, status, metadata
)
SELECT b.id, 'free_parking', 150, 12, 2380,
    'DEMO: Free parking for 12 months',
    'garage included', 0.88, true, 'partner_csv', 'active', '{"demo": true}'::jsonb
FROM buildings b WHERE b.slug = 'verse-tysons';

-- Snapshots (uses calculator-aligned formula)
INSERT INTO incentive_snapshots (
    incentive_id, raw_text, free_months, lease_term_months, listed_rent,
    estimated_savings, effective_rent, all_in_effective_rent, confidence_score
)
SELECT
    i.id,
    i.raw_text,
    i.free_months,
    i.lease_term_months,
    i.listed_rent,
    (
        (COALESCE(i.listed_rent, 0) * COALESCE(i.free_months, 0))::int
        + COALESCE(i.waived_fee_amount, 0)
        + COALESCE(i.gift_card_amount, 0)
        + COALESCE(i.custom_credit_amount, 0)
        + COALESCE(i.parking_discount_monthly, 0) * COALESCE(i.lease_term_months, 0)
    ),
    GREATEST(
        0,
        (
            (i.listed_rent * i.lease_term_months)
            - (i.listed_rent * COALESCE(i.free_months, 0))
            - COALESCE(i.waived_fee_amount, 0)
            - COALESCE(i.gift_card_amount, 0)
            - COALESCE(i.custom_credit_amount, 0)
            - COALESCE(i.parking_discount_monthly, 0) * i.lease_term_months
        ) / NULLIF(i.lease_term_months, 0)
    )::int,
    GREATEST(
        0,
        (
            (i.listed_rent * i.lease_term_months)
            - (i.listed_rent * COALESCE(i.free_months, 0))
            - COALESCE(i.waived_fee_amount, 0)
            - COALESCE(i.gift_card_amount, 0)
            - COALESCE(i.custom_credit_amount, 0)
            - COALESCE(i.parking_discount_monthly, 0) * i.lease_term_months
        ) / NULLIF(i.lease_term_months, 0)
    )::int,
    i.confidence_score
FROM incentives i
WHERE i.is_demo = true
  AND i.listed_rent IS NOT NULL
  AND i.lease_term_months IS NOT NULL;
