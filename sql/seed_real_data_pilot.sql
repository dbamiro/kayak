-- Real Data Pilot: one building + source row for end-to-end crawl/search testing.
-- Run after schema + base seed (optional): psql "$DATABASE_URL" -f sql/seed_real_data_pilot.sql
--
-- BEFORE CRAWLING: replace placeholder URLs with a real, allowed availability/floorplans page.
-- Then: UPDATE sources SET active = true WHERE ... OR edit below and re-run.

INSERT INTO buildings (
    name, slug, address_line1, city, state, postal_code, neighborhood, dmv_area,
    latitude, longitude, property_url, portal_urls, metadata
) VALUES (
    'Real Data Pilot (configure URL)',
    'real-data-pilot-dc',
    '1 Configure Me St NW',
    'Washington',
    'DC',
    '20001',
    'Downtown',
    'DC',
    38.9072,
    -77.0369,
    -- Marketing / property site (replace with real homepage if useful for ops)
    'https://example.com/replace-with-building-marketing-site',
    '[]'::jsonb,
    jsonb_build_object(
        'seed', true,
        'pilot', true,
        'submarket', 'Downtown DC',
        'notes', 'TEMPLATE — set property_url to the building marketing site; set sources.url to floorplans/availability.'
    )
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    metadata = buildings.metadata || EXCLUDED.metadata,
    updated_at = now();

-- Primary crawl target: direct floorplans / availability URL (NOT the marketing homepage).
INSERT INTO sources (
    building_id, url, source_type, crawl_strategy, wait_selector, active, notes, metadata
)
SELECT
    b.id,
    'https://example.com/replace-with-real-floorplans-url',
    'direct_site',
    'playwright'::fetch_mode,
    NULL,
    false,
    'PILOT: Replace url with real floorplans page. Set active=true after test_parse succeeds. parser_type=next_data in metadata.',
    jsonb_build_object(
        'seed', true,
        'pilot', true,
        'parser_type', 'next_data',
        'crawl_strategy_hint', 'playwright',
        'wait_selector', null,
        'workflow', 'See docs/ADDING_REAL_PROPERTY_SOURCES.md'
    )
FROM buildings b
WHERE b.slug = 'real-data-pilot-dc'
ON CONFLICT (building_id, url) DO UPDATE SET
    notes = EXCLUDED.notes,
    metadata = sources.metadata || EXCLUDED.metadata,
    crawl_strategy = EXCLUDED.crawl_strategy;
