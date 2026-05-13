# DMV Apartment Intelligence (starter)

Kayak/Expedia-style **rental search + intelligence** starter for the DMV: tracks **prices, concessions, fees, availability**, and **negotiation-oriented signals**. Parsing is **modular**: start from **`__NEXT_DATA__`** hydration JSON, then add stack-specific parsers (Entrata, RENTCafé, RealPage, AppFolio, etc.) as needed.

## MVP scope

- **Geography**: DC, Arlington, Alexandria, Tysons, Reston, Ashburn, Silver Spring, Bethesda (`dmv_area` enum).
- **Sources**: **`sources` table** — per-building crawl URLs + strategy (`http` | `playwright`).
- **Storage**: **`raw_documents`** (preferred audit trail), legacy **`raw_captures`**, append-only **`listing_snapshots`**, optional **`snapshot_concessions`** / **`snapshot_fees`** text rows.
- **Analytics**: **effective rent**, **all-in monthly cost**, **leasing pressure**, **negotiation** scores.

## Folder layout

```
Kayak/
├── app/                     # FastAPI API
├── crawler/
│   ├── fetcher.py           # HTTP + Playwright (retries, spacing, optional wait selector / failure screenshot)
│   ├── persist.py           # raw_captures + raw_documents
│   ├── writer.py            # CanonicalListing → floorplans / units / snapshots + fee & concession rows
│   ├── run.py               # Source-driven crawl + parser registry
│   └── test_parse.py        # CLI: fetch + parse → JSON (optional --write)
├── models/
│   └── canonical_listing.py # Pydantic canonical row
├── parsers/
│   ├── base.py              # BaseParser + legacy ParsedListing dataclass
│   ├── listing_extract.py   # deep_find_candidate_objects + normalizers + confidence
│   ├── next_data_parser.py  # Next.js __NEXT_DATA__ recursive extraction
│   ├── generic_html.py      # DOM placeholder (last resort)
│   └── registry.py          # ordered parser chain
├── normalize/
├── jobs/daily_run.py
├── sql/
│   ├── schema.sql           # full schema (new installs)
│   ├── migrations/002_parser_pipeline.sql   # ALTERs for DBs created from an older repo snapshot
│   └── seed.sql             # buildings + sources (template URLs) + demo snapshots
├── tests/
└── docker-compose.yml
```

## Prerequisites

- Python **3.11+** (3.13 works in smoke tests).
- **Docker** for Postgres, or your own PostgreSQL 16+.

## Setup

### 1) Database

**Option A — Docker Compose**

```bash
cd Kayak
docker compose up -d
cat sql/schema.sql sql/seed.sql | docker compose exec -T postgres psql -U dmv_user -d dmv_apartments
```

**Existing database from an older checkout:** apply incremental DDL once:

```bash
psql "$DATABASE_URL" -f sql/migrations/002_parser_pipeline.sql
```

### 2) Python

```bash
cd Kayak
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set DATABASE_URL
```

### 3) Playwright browsers

Needed for `--strategy playwright` / sources using `playwright`:

```bash
playwright install chromium
```

### 4) Tests (optional)

```bash
export PYTHONPATH="$(pwd)"
pytest tests/test_next_data_parser.py -q
```

## Run the API

```bash
export PYTHONPATH="$(pwd)"
export DATABASE_URL="postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Docs: `http://localhost:8000/docs`

## Parser test CLI (no DB by default)

Fetch a **real** floorplans URL you are allowed to access, parse, print **`CanonicalListing`** JSON:

```bash
export PYTHONPATH="$(pwd)"
python -m crawler.test_parse \
  --url "https://YOUR_ALLOWED_PROPERTY_URL/floorplans" \
  --strategy playwright \
  --parser next_data
```

- **`--parser registry`** (default when omitted): tries **`NextDataParser`** then **`GenericHtmlApartmentParser`**.
- **`--write`**: persists **`raw_documents`** + snapshots — requires **`--building-id`** (UUID).
- **`--wait-selector "css.selector"`**: optional Playwright wait (respectful timeouts only).

## Daily crawl job

Uses **`sources`** rows (`active = true`). If none exist, falls back to **`buildings.property_url`**.

```bash
export PYTHONPATH="$(pwd)"
export DATABASE_URL="postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments"
python jobs/daily_run.py --mode playwright --limit 3
```

Flow per source:

1. Fetch (**strategy** from each source row, overridable via `--mode` only on fallback path — sources define their own `crawl_strategy`).
2. **`insert_raw_document`** (then legacy **`raw_captures`**) — raw HTML **before** parsing.
3. **`parse_page`** registry → **`CanonicalListing`** list.
4. **`persist_canonical_listing`** — upsert **`floorplans`** / **`units`**, **append** **`listing_snapshots`**, insert **`snapshot_concessions`** / **`snapshot_fees`** when text exists.

Parser failures are logged and recorded in **`crawl_runs.stats`**; they do **not** stop other sources.

### Respectful crawling defaults

Configured via **`.env`** / **`app/config.py`**:

- User-Agent string
- Request timeout
- **`CRAWLER_MAX_RETRIES`** / **`CRAWLER_RETRY_BACKOFF_SECONDS`**
- **`CRAWLER_MIN_INTERVAL_MS`** minimum spacing between requests
- **`PLAYWRIGHT_SCREENSHOT_ON_ERROR`** (optional debugging — **no stealth / anti-bot evasion**)

Always obey **robots.txt**, site **terms of service**, and **access restrictions**. Do **not** bypass authentication, paywalls, CAPTCHAs, or private APIs.

---

## How to add a real property site

1. **Find** the building’s **availability / floorplans** URL (often different from the marketing homepage).
2. **Insert or update** a row in **`sources`** (`url`, `crawl_strategy`, optional **`wait_selector`**). Seed data uses **`https://example.com/replace-with-…`** templates — swap those for **your** URLs after compliance review.
3. Run **`python -m crawler.test_parse --url … --strategy playwright`** (start with **`--parser next_data`**).
4. **Inspect** saved HTML locally (or DevTools → Elements) for  
   `<script id="__NEXT_DATA__" type="application/json">…</script>`  
   View Source / Save Page often shows this without executing suspicious scripts.
5. If **`next_data`** extracts **`CanonicalListing`** rows with sane rents, proceed; if noise dominates, tighten **`deep_find_candidate_objects`** **`min_score`** or add a **site-specific parser**.
6. If **`__NEXT_DATA__`** is absent, implement a new **`BaseParser`** subclass (DOM selectors, embedded JSON under another key, XHR replay patterns — still compliant).
7. Register it **ahead of** generics in **`parsers/registry.py`**.
8. Run **`jobs/daily_run.py`** and verify **`listing_snapshots`**, **`snapshot_concessions`**, **`snapshot_fees`**.
9. Tune **`normalize/scores.py`** weights once you trust extraction density.

### Platform parsers to consider next

After **`NextDataParser`**, typical DMV stacks include **Entrata**, **RENTCafé**, **RealPage** / **Knock**, **Yardi**, **AppFolio** — usually easiest as **one parser class per vendor**, optionally parameterized by hostname.

---

## How pieces fit together

| Step | Module | Role |
|------|--------|------|
| Fetch | `crawler/fetcher.py` | HTTP / Playwright |
| Raw | `crawler/persist.py` | `raw_documents` + `raw_captures` |
| Parse | `parsers/registry.py` | Ordered **`BaseParser`** chain |
| Canonical model | `models/canonical_listing.py` | Rent range, confidence, raw fragment |
| Write | `crawler/writer.py` | Floorplans, units, snapshots (append-only), fee/concession side tables |

---

## Next.js frontend (later)

Use **`GET /search`**, **`GET /buildings/{id}`**, **`GET /buildings/{id}/history`**, **`POST /compare`**, **`POST /alerts`** from a Next.js app.

## License

Starter template — adopt a license when you ship.
# kayak
