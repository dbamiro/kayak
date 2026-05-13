-- Seed: DMV buildings + demo snapshots + crawl sources (TEMPLATE URLs — replace manually).
-- Run after schema: psql $DATABASE_URL -f sql/seed.sql
--
-- IMPORTANT (legal / ops): Replace example.com URLs with the building's real floorplans /
-- availability pages only when you have permission and robots/terms allow automated access.
-- These URLs are intentionally generic templates — they do NOT imply verified scraping targets.

INSERT INTO buildings (
    name, slug, address_line1, city, state, postal_code, neighborhood, dmv_area,
    latitude, longitude, property_url, portal_urls, metadata
) VALUES
(
    'The Hepburn',
    'the-hepburn-dc',
    '1901 Connecticut Ave NW',
    'Washington',
    'DC',
    '20009',
    'Kalorama',
    'DC',
    38.9167,
    -77.0456,
    'https://example.com/replace-with-hepburn-floorplans-url',
    '[]'::jsonb,
    '{"seed": true, "submarket": "Kalorama / Dupont-adjacent", "notes": "TEMPLATE — Replace property_url + sources.url with actual availability URL."}'::jsonb
),
(
    'The Bartlett',
    'the-bartlett-arlington',
    '520 12th St S',
    'Arlington',
    'VA',
    '22202',
    'Crystal City',
    'ARLINGTON',
    38.8576,
    -77.0508,
    'https://example.com/replace-with-bartlett-floorplans-url',
    '[]'::jsonb,
    '{"seed": true, "submarket": "Crystal City / National Landing"}'::jsonb
),
(
    'The Muse',
    'the-muse-alexandria',
    '1800 Belle View Blvd',
    'Alexandria',
    'VA',
    '22307',
    'Belle Haven',
    'ALEXANDRIA',
    38.7794,
    -77.0536,
    'https://example.com/replace-with-muse-floorplans-url',
    '[]'::jsonb,
    '{"seed": true, "submarket": "Belle Haven"}'::jsonb
),
(
    'Verse',
    'verse-tysons',
    '8250 Greensboro Dr',
    'Tysons',
    'VA',
    '22102',
    'Tysons',
    'TYSONS',
    38.9187,
    -77.2318,
    'https://example.com/replace-with-verse-tysons-floorplans-url',
    '[]'::jsonb,
    '{"seed": true, "submarket": "Tysons CBD"}'::jsonb
),
(
    'The Harrison',
    'the-harrison-silver-spring',
    '811 4th St',
    'Silver Spring',
    'MD',
    '20910',
    'Downtown Silver Spring',
    'SILVER_SPRING',
    38.9965,
    -77.0276,
    'https://example.com/replace-with-harrison-silver-spring-floorplans-url',
    '[]'::jsonb,
    '{"seed": true, "submarket": "Downtown Silver Spring"}'::jsonb
),
(
    'Reston Gateway (example)',
    'reston-gateway-example',
    '1900 Reston Metro Plaza',
    'Reston',
    'VA',
    '20190',
    'Reston Town Center',
    'RESTON',
    38.9525,
    -77.3570,
    'https://example.com/replace-with-reston-gateway-floorplans-url',
    '[]'::jsonb,
    '{"seed": true, "submarket": "Reston Town Center / Metro"}'::jsonb
),
(
    'Ashburn Tech Corridor (example)',
    'ashburn-tech-corridor-example',
    '44505 Pecan Terrace Plaza',
    'Ashburn',
    'VA',
    '20147',
    'Ashburn Village',
    'ASHBURN',
    39.0438,
    -77.4875,
    'https://example.com/replace-with-ashburn-floorplans-url',
    '[]'::jsonb,
    '{"seed": true, "submarket": "Route 28 / Loudoun"}'::jsonb
),
(
    'Bethesda Row (example)',
    'bethesda-row-example',
    '7700 Woodmont Ave',
    'Bethesda',
    'MD',
    '20814',
    'Woodmont Triangle',
    'BETHESDA',
    38.9877,
    -77.0965,
    'https://example.com/replace-with-bethesda-row-floorplans-url',
    '[]'::jsonb,
    '{"seed": true, "submarket": "Woodmont Triangle"}'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

-- Crawl sources: one primary URL per building (strategy hints only — tune per site).
INSERT INTO sources (building_id, url, source_type, crawl_strategy, notes, metadata)
SELECT b.id,
       b.property_url,
       'direct_site',
       -- Prefer playwright when JS hydration is typical; switch per building once tested.
       CASE b.slug
           WHEN 'the-hepburn-dc' THEN 'playwright'::fetch_mode
           WHEN 'the-bartlett-arlington' THEN 'playwright'::fetch_mode
           WHEN 'the-muse-alexandria' THEN 'http'::fetch_mode
           WHEN 'verse-tysons' THEN 'playwright'::fetch_mode
           WHEN 'the-harrison-silver-spring' THEN 'playwright'::fetch_mode
           WHEN 'reston-gateway-example' THEN 'playwright'::fetch_mode
           WHEN 'ashburn-tech-corridor-example' THEN 'http'::fetch_mode
           WHEN 'bethesda-row-example' THEN 'playwright'::fetch_mode
           ELSE 'http'::fetch_mode
       END,
       'TEMPLATE: Replace url with real floorplans / availability page after verifying terms & robots.',
       jsonb_build_object('seed', true, 'wait_selector', null)
FROM buildings b
WHERE (b.metadata->>'seed')::boolean IS TRUE
ON CONFLICT (building_id, url) DO NOTHING;

COMMENT ON TABLE sources IS 'Per-building crawl entrypoints; urls must be replaced with real availability pages.';

-- Demo listings + two snapshots each for GET /buildings/{id}/history
INSERT INTO listings (building_id, external_key, unit_label, floorplan_name, bedrooms, bathrooms, sqft)
SELECT id, 'demo-a1', 'A1', '1BR A', 1, 1, 720 FROM buildings WHERE slug = 'the-hepburn-dc'
ON CONFLICT (building_id, external_key) DO NOTHING;

INSERT INTO listings (building_id, external_key, unit_label, floorplan_name, bedrooms, bathrooms, sqft)
SELECT id, 'demo-b2', 'B2', '2BR B', 2, 2, 1050 FROM buildings WHERE slug = 'the-bartlett-arlington'
ON CONFLICT (building_id, external_key) DO NOTHING;

INSERT INTO listings (building_id, external_key, unit_label, floorplan_name, bedrooms, bathrooms, sqft)
SELECT id, 'demo-s1', 'S1', 'Studio S', 0, 1, 550 FROM buildings WHERE slug = 'the-muse-alexandria'
ON CONFLICT (building_id, external_key) DO NOTHING;

INSERT INTO listings (building_id, external_key, unit_label, floorplan_name, bedrooms, bathrooms, sqft)
SELECT id, 'demo-1a', '1A', '1BR', 1, 1, 780 FROM buildings WHERE slug = 'verse-tysons'
ON CONFLICT (building_id, external_key) DO NOTHING;

INSERT INTO listings (building_id, external_key, unit_label, floorplan_name, bedrooms, bathrooms, sqft)
SELECT id, 'demo-c1', 'C1', '1BR Corner', 1, 1, 800 FROM buildings WHERE slug = 'the-harrison-silver-spring'
ON CONFLICT (building_id, external_key) DO NOTHING;

INSERT INTO listing_snapshots (
    listing_id, captured_at, base_rent_monthly, lease_term_months,
    concessions, fees, utilities_estimate, effective_rent_monthly, all_in_monthly,
    leasing_pressure_score, negotiation_score, parser_name
)
SELECT l.id, now() - interval '14 days', 2650.00, 12,
    '{"type": "one_time", "amount": 1000, "description": "move-in credit"}'::jsonb,
    '{"admin": 50, "amenity": 45, "parking": 150}'::jsonb,
    80.00,
    2521.67,
    2846.67,
    62,
    58,
    'seed'
FROM listings l JOIN buildings b ON l.building_id = b.id
WHERE b.slug = 'the-hepburn-dc' AND l.external_key = 'demo-a1';

INSERT INTO listing_snapshots (
    listing_id, captured_at, base_rent_monthly, lease_term_months,
    concessions, fees, utilities_estimate, effective_rent_monthly, all_in_monthly,
    leasing_pressure_score, negotiation_score, parser_name
)
SELECT l.id, now() - interval '1 day', 2595.00, 12,
    '{"type": "one_time", "amount": 1500, "description": "look and lease"}'::jsonb,
    '{"admin": 50, "amenity": 45, "parking": 150}'::jsonb,
    80.00,
    2451.25,
    2776.25,
    68,
    64,
    'seed'
FROM listings l JOIN buildings b ON l.building_id = b.id
WHERE b.slug = 'the-hepburn-dc' AND l.external_key = 'demo-a1';

INSERT INTO listing_snapshots (
    listing_id, captured_at, base_rent_monthly, lease_term_months,
    concessions, fees, utilities_estimate, effective_rent_monthly, all_in_monthly,
    leasing_pressure_score, negotiation_score, parser_name
)
SELECT l.id, now() - interval '7 days', 3100.00, 13,
    '{}'::jsonb,
    '{"admin": 25, "garage": 175}'::jsonb,
    90.00,
    3100.00,
    3390.00,
    48,
    45,
    'seed'
FROM listings l JOIN buildings b ON l.building_id = b.id
WHERE b.slug = 'the-bartlett-arlington' AND l.external_key = 'demo-b2';

INSERT INTO listing_snapshots (
    listing_id, captured_at, base_rent_monthly, lease_term_months,
    concessions, fees, utilities_estimate, effective_rent_monthly, all_in_monthly,
    leasing_pressure_score, negotiation_score, parser_name
)
SELECT l.id, now(), 3050.00, 13,
    '{"type": "percent_off", "percent": 4, "months": 2}'::jsonb,
    '{"admin": 25, "garage": 175}'::jsonb,
    90.00,
    3029.23,
    3319.23,
    55,
    52,
    'seed'
FROM listings l JOIN buildings b ON l.building_id = b.id
WHERE b.slug = 'the-bartlett-arlington' AND l.external_key = 'demo-b2';

INSERT INTO listing_snapshots (
    listing_id, captured_at, base_rent_monthly, lease_term_months,
    concessions, fees, utilities_estimate, effective_rent_monthly, all_in_monthly,
    leasing_pressure_score, negotiation_score, parser_name
)
SELECT l.id, now() - interval '3 days', 1895.00, 12,
    '{"type": "weeks_free", "weeks": 2}'::jsonb,
    '{"admin": 35, "pet": 35}'::jsonb,
    70.00,
    1764.58,
    1904.58,
    58,
    55,
    'seed'
FROM listings l JOIN buildings b ON l.building_id = b.id
WHERE b.slug = 'the-muse-alexandria' AND l.external_key = 'demo-s1';

INSERT INTO listing_snapshots (
    listing_id, captured_at, base_rent_monthly, lease_term_months,
    concessions, fees, utilities_estimate, effective_rent_monthly, all_in_monthly,
    leasing_pressure_score, negotiation_score, parser_name
)
SELECT l.id, now() - interval '2 days', 2425.00, 15,
    '{}'::jsonb,
    '{"amenity": 50, "parking": 125}'::jsonb,
    85.00,
    2425.00,
    2685.00,
    44,
    42,
    'seed'
FROM listings l JOIN buildings b ON l.building_id = b.id
WHERE b.slug = 'verse-tysons' AND l.external_key = 'demo-1a';

INSERT INTO listing_snapshots (
    listing_id, captured_at, base_rent_monthly, lease_term_months,
    concessions, fees, utilities_estimate, effective_rent_monthly, all_in_monthly,
    leasing_pressure_score, negotiation_score, parser_name
)
SELECT l.id, now() - interval '1 day', 2180.00, 12,
    '{"type": "one_time", "amount": 500}'::jsonb,
    '{"admin": 45}'::jsonb,
    75.00,
    2138.33,
    2258.33,
    52,
    50,
    'seed'
FROM listings l JOIN buildings b ON l.building_id = b.id
WHERE b.slug = 'the-harrison-silver-spring' AND l.external_key = 'demo-c1';
