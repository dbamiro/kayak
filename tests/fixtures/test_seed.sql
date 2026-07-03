-- Deterministic pytest seed (no production data). Reloaded before each @pytest.mark.db test.
-- Fixed UUIDs for stable references across test runs.

INSERT INTO plans (code, name, price_cents, currency, duration_days, plan_type, description, is_active)
VALUES
    ('free', 'Free', 0, 'USD', NULL, 'free', 'Browse listings and Deal Report previews.', true),
    ('hunt_pass_30', 'Premium Hunt Pass (30 days)', 1900, 'USD', 30, 'subscription', 'Full Deal Reports.', true),
    ('premium_plus_30', 'Premium Plus (30 days)', 3900, 'USD', 30, 'subscription', 'Premium Plus.', true),
    ('concierge_one_time', 'Concierge (one-time)', 14900, 'USD', NULL, 'one_time', 'Concierge.', true)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    price_cents = EXCLUDED.price_cents,
    is_active = EXCLUDED.is_active;

INSERT INTO buildings (
    id, name, slug, address_line1, city, state, postal_code, neighborhood, dmv_area,
    property_url, metadata
) VALUES
(
    'b0000000-0000-4000-8000-000000000001',
    'Kayak Test Alpha',
    'kayak-test-alpha',
    '100 Test St NW',
    'Washington',
    'DC',
    '20001',
    'Test Ward',
    'DC',
    'https://example.com/kayak-test-alpha',
    '{"test": true}'::jsonb
),
(
    'b0000000-0000-4000-8000-000000000002',
    'Kayak Test Beta',
    'kayak-test-beta',
    '200 Test Ave',
    'Arlington',
    'VA',
    '22202',
    'Test Corridor',
    'ARLINGTON',
    'https://example.com/kayak-test-beta',
    '{"test": true}'::jsonb
);

INSERT INTO sources (building_id, url, source_type, crawl_strategy, active, notes)
VALUES
(
    'b0000000-0000-4000-8000-000000000001',
    'https://www.rentcafe.com/kayak-test-alpha-floorplans',
    'rentcafe',
    'playwright',
    true,
    'pytest rentcafe fixture'
);

INSERT INTO listings (id, building_id, external_key, unit_label, floorplan_name, bedrooms, bathrooms, sqft)
VALUES
(
    'c0000000-0000-4000-8000-000000000001',
    'b0000000-0000-4000-8000-000000000001',
    'test-a1',
    'A1',
    '1BR Test',
    1,
    1,
    700
),
(
    'c0000000-0000-4000-8000-000000000002',
    'b0000000-0000-4000-8000-000000000002',
    'test-b1',
    'B1',
    '2BR Test',
    2,
    2,
    950
);

INSERT INTO listing_snapshots (
    listing_id, captured_at, base_rent_monthly, lease_term_months,
    concessions, fees, effective_rent_monthly, all_in_monthly,
    leasing_pressure_score, negotiation_score, parser_name
) VALUES
(
    'c0000000-0000-4000-8000-000000000001',
    now() - interval '1 day',
    2400.00,
    16,
    '{"raw_text": "look and lease credit"}'::jsonb,
    '{"admin": 50}'::jsonb,
    2300.00,
    2350.00,
    55,
    50,
    'test_seed'
),
(
    'c0000000-0000-4000-8000-000000000002',
    now() - interval '1 day',
    2680.00,
    15,
    '{}'::jsonb,
    '{}'::jsonb,
    2680.00,
    2680.00,
    48,
    45,
    'test_seed'
);

-- Demo incentives for search/specials API tests (clearly demo)
INSERT INTO incentives (
    id, building_id, incentive_type, free_months, lease_term_months, listed_rent,
    raw_text, confidence_score, is_demo, capture_method, status
) VALUES
(
    'd0000000-0000-4000-8000-000000000001',
    'b0000000-0000-4000-8000-000000000001',
    'free_months',
    4,
    16,
    2400,
    'TEST: 4 months free on 16-month lease',
    0.95,
    true,
    'partner_csv',
    'active'
),
(
    'd0000000-0000-4000-8000-000000000002',
    'b0000000-0000-4000-8000-000000000002',
    'free_months',
    2,
    15,
    2680,
    'TEST: 2 months free',
    0.95,
    true,
    'partner_csv',
    'active'
);

INSERT INTO incentive_snapshots (
    incentive_id, raw_text, free_months, lease_term_months, listed_rent,
    estimated_savings, effective_rent, all_in_effective_rent, confidence_score
) VALUES
(
    'd0000000-0000-4000-8000-000000000001',
    'TEST: 4 months free on 16-month lease',
    4,
    16,
    2400,
    9600,
    1800,
    1800,
    0.95
),
(
    'd0000000-0000-4000-8000-000000000002',
    'TEST: 2 months free',
    2,
    15,
    2680,
    5360,
    2144,
    2144,
    0.95
);
