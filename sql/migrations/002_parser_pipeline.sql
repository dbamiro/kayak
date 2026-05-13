-- Parser pipeline: sources, raw_documents, floorplans, units, snapshot aux tables.
-- Apply after base schema: psql "$DATABASE_URL" -f sql/migrations/002_parser_pipeline.sql

CREATE TABLE IF NOT EXISTS sources (
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

CREATE INDEX IF NOT EXISTS idx_sources_building ON sources (building_id);

CREATE TABLE IF NOT EXISTS raw_documents (
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

CREATE INDEX IF NOT EXISTS idx_raw_documents_building_time ON raw_documents (building_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS floorplans (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    external_key      TEXT NOT NULL,
    name              TEXT,
    bedrooms          NUMERIC (4, 1),
    bathrooms         NUMERIC (4, 1),
    sqft              INTEGER,
    metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (building_id, external_key)
);

CREATE INDEX IF NOT EXISTS idx_floorplans_building ON floorplans (building_id);

CREATE TABLE IF NOT EXISTS units (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id     UUID NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
    floorplan_id      UUID REFERENCES floorplans (id) ON DELETE SET NULL,
    external_key      TEXT NOT NULL,
    unit_label        TEXT,
    metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (building_id, external_key)
);

CREATE INDEX IF NOT EXISTS idx_units_building ON units (building_id);

ALTER TABLE listings ADD COLUMN IF NOT EXISTS floorplan_id UUID REFERENCES floorplans (id) ON DELETE SET NULL;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS unit_id UUID REFERENCES units (id) ON DELETE SET NULL;

ALTER TABLE listing_snapshots ADD COLUMN IF NOT EXISTS raw_document_id UUID REFERENCES raw_documents (id) ON DELETE SET NULL;
ALTER TABLE listing_snapshots ADD COLUMN IF NOT EXISTS parser_confidence NUMERIC (8, 5);
ALTER TABLE listing_snapshots ADD COLUMN IF NOT EXISTS raw_fragment JSONB;
ALTER TABLE listing_snapshots ADD COLUMN IF NOT EXISTS field_confidences JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS snapshot_concessions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_snapshot_id UUID NOT NULL REFERENCES listing_snapshots (id) ON DELETE CASCADE,
    raw_text            TEXT NOT NULL,
    parser_confidence   NUMERIC (8, 5),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS snapshot_fees (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_snapshot_id UUID NOT NULL REFERENCES listing_snapshots (id) ON DELETE CASCADE,
    raw_text            TEXT NOT NULL,
    parser_confidence   NUMERIC (8, 5),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
