-- DMV Apartment Intelligence — PostgreSQL schema (MVP + parser pipeline)
-- Run: psql $DATABASE_URL -f sql/schema.sql
-- Existing DBs created from an older schema: also run sql/migrations/002_parser_pipeline.sql

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
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'direct_site',
    crawl_strategy  fetch_mode NOT NULL DEFAULT 'http',
    wait_selector   TEXT,
    active          BOOLEAN NOT NULL DEFAULT true,
    notes           TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
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

CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT,
    label           TEXT,
    criteria        JSONB NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
