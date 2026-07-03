# Kayak DMV — Apartment Incentive Discovery

**Kayak is an apartment incentive discovery engine** for the DMV. It helps renters compare:

- **Sticker rent** vs **effective rent** after free months and concessions  
- **Total savings** and **discount %** on the full lease  
- **Waived fees**, gift cards, and parking perks  
- **True all-in monthly cost** (when fee data is available)

Under the hood it still crawls listings, stores snapshots, and runs Deal Reports — but the **product promise** is: *find apartments with the biggest real savings from move-in specials.*

Crawler/parser stack remains modular (`__NEXT_DATA__`, RentCafe HTML, floorplan cards, etc.).

## Quick start (local dev)

**Prerequisites:** Python 3.12+, Node 20+, `psql` / `pg_isready`. Docker optional (used to start Postgres).

```bash
cd Kayak

# 1. Python API
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env          # JWT + DATABASE_URL defaults are fine for local dev
cp web/.env.local.example web/.env.local

# 2. Database (starts docker postgres if needed, applies schema + seeds)
./scripts/bootstrap_db.sh

# 3. Terminal A — API on :8000
./scripts/dev-api.sh

# 4. Terminal B — Web on :3000
cd web && npm install && cd ..
./scripts/dev-web.sh

# 5. Smoke test (API must be running)
./scripts/smoke.sh
```

## Testing

Tests split into **unit** (no Postgres) and **DB integration** (`@pytest.mark.db`). Integration tests use an isolated database (`kayak_test` by default) with deterministic seed data — never your dev `dmv_apartments` DB or production.

**Prerequisites for DB tests:** Postgres running (e.g. `docker compose up -d postgres`).

```bash
export PYTHONPATH="$(pwd)"

# Unit tests only (fast, no database required)
pytest tests/ -m "not db"

# DB/API integration tests (creates/resets kayak_test automatically)
docker compose up -d postgres   # if not already running
./scripts/bootstrap_test_db.sh  # optional manual bootstrap; pytest also bootstraps on first db test
pytest tests/ -m db

# Full suite
pytest tests/
```

| Variable | Purpose |
|----------|---------|
| `TEST_DATABASE_URL` | Isolated pytest DB (default `postgresql://dmv_user:dmv_pass@localhost:5432/kayak_test`) |
| `DATABASE_URL` | Overridden to `TEST_DATABASE_URL` during pytest — dev/prod URLs are not used |

Seed file: `tests/fixtures/test_seed.sql` (fixed UUIDs, 2 demo buildings, incentives, RentCafe source). Reloaded before each `@pytest.mark.db` test via truncate + insert.

If Postgres is unreachable, DB tests **skip** with a message pointing to `docker compose up -d postgres && ./scripts/bootstrap_test_db.sh`.

**Verify in browser**

| URL | What you should see |
|-----|---------------------|
| http://localhost:8000/health | `{"status":"ok"}` |
| http://localhost:8000/docs | OpenAPI |
| http://localhost:3000/search | Buildings ranked/filtered by incentives |
| http://localhost:3000/specials | Demo move-in specials (labeled **Demo data**) |
| http://localhost:3000/calculator | Savings calculator |
| http://localhost:3000/search → building | Floorplans + Deal Report preview |

**Manual equivalents** (if you prefer not to use helper scripts):

```bash
export PYTHONPATH="$(pwd)"
docker compose up -d postgres && ./scripts/bootstrap_db.sh
./.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# separate terminal:
cd web && npm run dev
```

**Troubleshooting**

- **`Connection refused` on :5432** — run `docker compose up -d postgres` or point `DATABASE_URL` at your Postgres.
- **Empty `/search`** — run `./scripts/bootstrap_db.sh` (loads `seed.sql` + `seed_incentives.sql`).
- **Frontend can't reach API** — `web/.env.local` → `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`; API `.env` → `CORS_ORIGINS` includes `http://localhost:3000`.
- **`/plans` or register fails** — migrations not applied; re-run `./scripts/bootstrap_db.sh`.

## MVP scope

- **Geography**: DC, Arlington, Alexandria, Tysons, Reston, Ashburn, Silver Spring, Bethesda (`dmv_area` enum).
- **Sources**: **`sources` table** — per-building crawl URLs + strategy (`http` | `playwright`).
- **Storage**: **`raw_documents`** (preferred audit trail), legacy **`raw_captures`**, append-only **`listing_snapshots`**, optional **`snapshot_concessions`** / **`snapshot_fees`** text rows.
- **Analytics**: **effective rent**, **all-in monthly cost**, **leasing pressure**, **negotiation** scores.

## Folder layout

```
Kayak/
├── app/
│   ├── monetization/        # paywall copy constants
│   ├── services/            # entitlements + deal report builders
│   └── routers/
│       ├── monetization_api.py
│       ├── search.py
│       └── ...
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
│   ├── migrations/002_parser_pipeline.sql
│   ├── migrations/003_monetization.sql
│   ├── migrations/004_production.sql
│   └── seed.sql             # buildings + sources (template URLs) + demo snapshots
├── tests/
├── web/                     # Phase 1: Next.js (login, register, account, …)
└── docker-compose.yml
```

## Phase 1 — Production auth + frontend shell

This phase adds **email/password auth** (bcrypt + JWT access tokens + opaque refresh tokens in Postgres), **`CurrentUser` dependencies** on identity and entitlement routes, and a **Next.js** app under `web/`.

| Piece | Notes |
|-------|--------|
| **API** | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/refresh`, `POST /auth/logout`. `GET /me/entitlements`, `POST /checkout/session`, and `POST /checkout/mock-complete` require **`Authorization: Bearer <access_token>`** (or `X-User-Id` only when `MOCK_AUTH_MODE=true`). |
| **Defaults** | `MOCK_AUTH_MODE` defaults to **`false`** in code (production-like). For local convenience, `.env.example` sets it to **`true`**; Docker Compose also sets `MOCK_AUTH_MODE=true`. |
| **Frontend** | `npm run dev` in `web/`: **Home**, **Login**, **Register**, **Search** (live API), **Building detail** + **Deal Report**, **Pricing** (mock checkout), **Account**, **`/billing/success`**. Copy `web/.env.local.example` → `web/.env.local`. |
| **Schema** | New installs: `sql/schema.sql` includes `users.password_hash`, `refresh_tokens`, etc. Existing DBs: run `sql/migrations/004_production.sql`. |
| **Tests** | Unit: `pytest tests/ -m "not db"`. DB integration: `pytest tests/ -m db` (isolated `kayak_test` DB). See [Testing](#testing). |

### Run Phase 1 locally

**Linux / macOS — use bash `activate`, not `Activate.ps1`.** On Debian/Ubuntu, if `pip install` says *externally-managed-environment*, your shell used system `pip` instead of the venv: call **`./.venv/bin/python -m pip`** (see below).

**Terminal 1 — API**

```bash
cd /path/to/Kayak
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env   # edit: JWT_SECRET, DATABASE_URL, MOCK_AUTH_MODE as needed
export PYTHONPATH="$(pwd)"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**If `source .venv/bin/activate` fails or `pip` still targets the system interpreter**, install and run via explicit paths (no activation needed):

```bash
cd /path/to/Kayak
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
export PYTHONPATH="$(pwd)"
./.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Web**

```bash
cd Kayak/web
npm install
# ensure NEXT_PUBLIC_API_BASE_URL matches API (default http://localhost:8000)
npm run dev
```

Open `http://localhost:3000` → **Register** → **Account** should show your email and entitlements.

## Incentive layer (migrations)

Kayak supports **any incentive amount** — not capped at four months free. Examples: **8 weeks free**, **5 months free**, **$1,500 rent credit**, **waived admin fee**, **free parking for 12 months**.

```bash
psql "$DATABASE_URL" -f sql/migrations/005_incentives.sql
psql "$DATABASE_URL" -f sql/migrations/006_real_incentives.sql
psql "$DATABASE_URL" -f sql/seed_incentives.sql   # demo specials on seed buildings only
```

API: `GET /incentives`, `POST /incentives/calculate`, `POST /incentives/parse`, `POST /incentives/submit`, `POST /admin/incentives` (admin)

**Real data workflow**

1. **Manual verified entry** — `POST /admin/incentives` with leasing-office or public-page text (`is_demo=false`).
2. **User submission** — `POST /incentives/submit` → `status=pending_review`, lower confidence.
3. **Crawler** — friendly public pages via existing `sources` + parsers (no blocked-site bypass).
4. **Admin CSV import** — `POST /admin/incentives/import` or `./scripts/import_incentives_csv.sh` (see [docs/VERIFIED_INCENTIVES.md](docs/VERIFIED_INCENTIVES.md)).

**Demo vs real**

- `SHOW_DEMO_DATA=true` in `.env` (default locally) includes demo rows in search.
- Production: set `SHOW_DEMO_DATA=false`; use `GET /search?include_demo=false` to exclude demo.
- Demo rows are labeled **Demo data** in the UI.

**Create a real incentive (admin curl example)**

```bash
curl -s -X POST http://127.0.0.1:8000/admin/incentives \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "building_name": "The Hepburn",
    "city": "Washington",
    "raw_text": "8 weeks free on 14-month leases",
    "listed_rent": 2450,
    "lease_term_months": 14,
    "source_url": "https://example.com/specials",
    "verification_method": "leasing_office_verified"
  }'
```

**Incentive-first search** (after seed + `seed_incentives.sql`):

```bash
curl -s 'http://127.0.0.1:8000/search?sort=savings' | jq '.[0] | {name, estimated_savings, effective_rent}'
curl -s 'http://127.0.0.1:8000/search?min_free_months=2' | jq 'length'
curl -s 'http://127.0.0.1:8000/search?has_incentive=true' | jq '.[0].best_incentive_id'
curl -s 'http://127.0.0.1:8000/search?min_free_months=5' | jq 'length'
curl -s 'http://127.0.0.1:8000/search?min_free_months=1.5&include_demo=true' | jq '.[0].free_months'
curl -s 'http://127.0.0.1:8000/search?include_demo=false' | jq '[.[] | select(.incentive_is_demo == true)] | length'
```

Web: **http://localhost:3000/search** — sort by biggest savings, filter by free months (1+ through 6+ or custom), minimum savings, hide demo data, or “Show specials only”.

## Demo flow — incentives

1. Start API + web (see Phase 1 above).  
2. Open **http://localhost:3000/specials** — ranked demo move-in specials.  
3. Open **http://localhost:3000/calculator** — try **$2,400 / 16 months / 4 months free** → **$1,800** effective.  
4. **http://localhost:3000/submit-special** — user-submitted offer.  
5. Open a building → **Deal Report** shows incentive + effective rent.  
6. **Pricing** — Hunt Pass unlocks full savings breakdowns and scripts.

## Demo flow (seed data)

Works with **`sql/seed.sql`** demo buildings — no crawler or Stripe required.

1. **API**: `MOCK_CHECKOUT_MODE=true` in `.env` (default in `.env.example`).
2. **Web**: `cp web/.env.local.example web/.env.local` — set `NEXT_PUBLIC_API_BASE_URL` if the API is not on port 8000.
3. **Register** at `http://localhost:3000/register`.
4. **Search** → open a building → scroll to **Deal Report** (preview: rent signal, locked sections, paywall).
5. Click **Unlock for $19** (or **Pricing** → **Unlock Hunt Pass**) — mock checkout grants `hunt_pass_30` and redirects to **`/billing/success`**.
6. Return to the same building → **Deal Report** shows **`access: full`** (fees, rent history, negotiation scripts when present in seed).

```bash
# Quick API check (no auth = preview)
curl -s "http://127.0.0.1:8000/search" | head -c 200
curl -s "http://127.0.0.1:8000/deal-reports/BUILDING_ID" | jq .access
```

## Move to live crawl data

You need **one real floorplans / availability URL** (robots/terms OK). Demo rows from `sql/seed.sql` stay in the DB until you deactivate them.

```bash
cd /path/to/Kayak
source .venv/bin/activate
export PYTHONPATH="$(pwd)"
export DATABASE_URL="postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments"

# 1) Configure URL, test parse, persist snapshots
./scripts/enable_live_crawl.sh "https://YOUR-REAL-FLOORPLANS-URL"

# Optional: only show crawled sources in scheduled jobs (demo placeholders off)
DEACTIVATE_DEMO=true ./scripts/enable_live_crawl.sh "https://YOUR-REAL-FLOORPLANS-URL"

# If the list is JS-rendered or parse returns 0:
CRAWL_STRATEGY=playwright WAIT_SELECTOR='[data-testid=floorplans]' \
  ./scripts/enable_live_crawl.sh "https://YOUR-REAL-FLOORPLANS-URL"
```

Manual steps and parser notes: [docs/ADDING_REAL_PROPERTY_SOURCES.md](docs/ADDING_REAL_PROPERTY_SOURCES.md).

After a successful run, **Search** and **Deal Reports** use the new `listing_snapshots` for that building (mixed with demo buildings until `DEACTIVATE_DEMO=true`).

## Real Data Smoke Test

One pilot building + source (`sql/seed_real_data_pilot.sql`). Full workflow: [docs/ADDING_REAL_PROPERTY_SOURCES.md](docs/ADDING_REAL_PROPERTY_SOURCES.md).

```bash
# 1) Pilot row (safe to re-run)
cat sql/seed_real_data_pilot.sql | docker compose exec -T postgres psql -U dmv_user -d dmv_apartments

# 2) Replace URL in DB (see docs), then get IDs:
# SELECT s.id, b.id FROM sources s JOIN buildings b ON b.id = s.building_id WHERE b.slug = 'real-data-pilot-dc';

# 3) Parse without DB (use YOUR real floorplans URL)
export PYTHONPATH="$(pwd)"
python -m crawler.test_parse \
  --url "https://YOUR-REAL-FLOORPLANS-URL" \
  --strategy playwright \
  --parser next_data

# 4) Crawl one source (works even if active=false)
python jobs/daily_run.py --source-id YOUR_SOURCE_UUID

# 5) API + UI
curl -s "http://127.0.0.1:8000/search" | head -c 400
# Frontend: http://localhost:3000/search

# 6) Optional smoke script
chmod +x scripts/smoke_real_data.sh
API_URL=http://127.0.0.1:8000 TEST_PARSE_URL="https://example.com/" ./scripts/smoke_real_data.sh
```

## Prerequisites

- Python **3.11+** (3.13 works in smoke tests).
- **Docker** for Postgres, or your own PostgreSQL 16+.

## Setup

### 1) Database

**Option A — Docker Compose (first-time empty database)**

```bash
cd Kayak
docker compose up -d postgres
cat sql/schema.sql sql/seed.sql | docker compose exec -T postgres psql -U dmv_user -d dmv_apartments
```

**If Postgres already has tables** (you see `already exists` errors), **do not** pipe `schema.sql` again — it only applies cleanly to an empty database. Use incremental migrations instead.

**Apply migrations without a local `psql` client** (uses the Postgres container):

```bash
cd Kayak
cat sql/migrations/002_parser_pipeline.sql | docker compose exec -T postgres psql -U dmv_user -d dmv_apartments
cat sql/migrations/003_monetization.sql     | docker compose exec -T postgres psql -U dmv_user -d dmv_apartments
cat sql/migrations/004_production.sql     | docker compose exec -T postgres psql -U dmv_user -d dmv_apartments
```

**If you already have a `psql` client** and `DATABASE_URL` points at the DB:

```bash
psql "$DATABASE_URL" -f sql/migrations/002_parser_pipeline.sql
psql "$DATABASE_URL" -f sql/migrations/003_monetization.sql
psql "$DATABASE_URL" -f sql/migrations/004_production.sql
```

### 2) Python

```bash
cd Kayak
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS: use this, not Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env   # set DATABASE_URL, JWT_SECRET (see Phase 1 section)
```

If you see **PEP 668 / externally-managed-environment**, you ran system `pip`. Use **`python -m pip`** after `activate`, or **`./.venv/bin/python -m pip install -r requirements.txt`** without activating.

### 3) Playwright browsers

Needed for `--strategy playwright` / sources using `playwright`:

```bash
playwright install chromium
```

### 4) Tests (optional)

```bash
export PYTHONPATH="$(pwd)"
pytest tests/ -m "not db"    # unit tests, no Postgres
pytest tests/ -m db          # DB integration (see Testing section)
pytest tests/test_next_data_parser.py -q
```

## Run the API

From the repo root, with the venv **activated** (or use `./.venv/bin/python -m uvicorn`):

```bash
export PYTHONPATH="$(pwd)"
export DATABASE_URL="postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Docs: `http://localhost:8000/docs`

### Auth (JWT)

- `POST /auth/register` — email + password (bcrypt) → access + refresh tokens  
- `POST /auth/login`  
- `GET /auth/me` — Bearer access token  
- `POST /auth/refresh` — body `{ "refresh_token": "…" }`  
- `POST /auth/logout` — revokes refresh token  

Set **`JWT_SECRET`** in production. With **`MOCK_AUTH_MODE=true`** (local default), legacy **`X-User-Id`** / `user_id` query still works for `/checkout/*` and optional deal-report identity; anonymous users get **Deal Report preview** without auth.

### Frontend (`web/`)

```bash
cd web
cp ../.env.example ../.env   # ensure NEXT_PUBLIC_API_BASE_URL matches API (default http://localhost:8000)
npm install
npm run dev
```

### Background jobs

```bash
export PYTHONPATH="$(pwd)"
python -m jobs.expire_entitlements
python -m jobs.run_alerts          # placeholder
python -m jobs.data_quality_check  # lightweight SQL counts
```

### Docker Compose (Postgres + API + web)

```bash
docker compose up --build
# Initialize schema + seed (first run only):
cat sql/schema.sql sql/seed.sql | docker compose exec -T postgres psql -U dmv_user -d dmv_apartments
```

### Admin API

Set **`ADMIN_EMAILS`** (comma-separated, lowercase) or `users.is_admin=true`. Endpoints under **`/admin/*`** (sources, crawl runs, raw documents, data-quality warnings, user/entitlement skim).

## Parser test CLI (no DB by default)

Fetch a **real** floorplans URL you are allowed to access, parse, print **`CanonicalListing`** JSON:

```bash
export PYTHONPATH="$(pwd)"
python -m crawler.test_parse \
  --url "https://example.com/" \
  --strategy http \
  --parser next_data
```

Use a **real hostname you are allowed to fetch** (the string `YOUR_ALLOWED_PROPERTY_URL` was documentation, not a valid DNS name). **`https://example.com/`** resolves but usually has no rent `__NEXT_DATA__`, so expect empty or generic parse — that still validates your network and CLI.

- **`--parser registry`** (default when omitted): tries **`NextDataParser`** then **`GenericHtmlApartmentParser`**.
- **`--write`**: persists **`raw_documents`** + snapshots — requires **`--building-id`** (UUID).
- **`--wait-selector "css.selector"`**: optional Playwright wait (respectful timeouts only).

## Daily crawl job

Uses **`sources`** rows (`active = true`). If none exist, falls back to **`buildings.property_url`**.

```bash
export PYTHONPATH="$(pwd)"
export DATABASE_URL="postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments"
python jobs/daily_run.py --mode http --limit 3
```

Each **`sources`** row uses its own **`crawl_strategy`** (`http` or `playwright` from the database). The **`--mode`** flag only applies to the **fallback** path when there are **no** active sources (then it uses `buildings.property_url` with that mode). Seeded sources often use **Playwright**, so install browsers: **`playwright install chromium`** (or `playwright install`).

Flow per source:

1. Fetch using each source row’s **`crawl_strategy`** (or the CLI **`--mode`** only when falling back to `property_url` with no active sources).
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

## Next.js frontend

The `web/` app calls **`GET /search`**, **`GET /buildings/{id}`**, **`GET /buildings/{id}/history`**, **`GET /deal-reports/{id}`**, **`GET /plans`**, **`POST /checkout/session`**, and **`POST /checkout/mock-complete`** (when `MOCK_CHECKOUT_MODE=true`). Compare and alerts APIs exist but are not wired in the UI yet.

---

## Monetization (Deal Reports, passes, Stripe-ready)

**Positioning:** Search and listing cards stay usable for free users. **Deal Reports** return a rich **preview** for everyone; **full** fee stack, rent history, negotiation scripts, and comparable deals unlock with **Premium Hunt Pass** (`hunt_pass_30`, $19 / 30 days) or **Premium Plus** (`premium_plus_30`, $39 / 30 days). **Concierge** (`concierge_one_time`, $149) stores a **placeholder** request — no automated fulfillment.

### Plans (seeded in DB)

| Code | Price | Notes |
|------|-------|--------|
| `free` | $0 | Implicit default |
| `hunt_pass_30` | $19 | Full Deal Reports, history, scripts, alerts, compare |
| `premium_plus_30` | $39 | Hunt Pass + enhanced export / shortlist **placeholders** |
| `concierge_one_time` | $149 | One-time; human workflow not implemented |

### Migrations

New installs: `sql/schema.sql` already includes monetization tables + plan seed.

Existing DB:

```bash
psql "$DATABASE_URL" -f sql/migrations/003_monetization.sql
```

### Environment (see `.env.example`)

**Local dev (mock checkout):**

- `APP_ENV=development`
- `MOCK_CHECKOUT_MODE=true`
- Leave `STRIPE_SECRET_KEY` empty — `POST /checkout/session` returns `mock_mode: true`; frontend calls `POST /checkout/mock-complete`.

**Production (Stripe):**

- `APP_ENV=production`
- `MOCK_CHECKOUT_MODE=false`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and `STRIPE_PRICE_HUNT_PASS_30` (plus other plan price IDs as needed)
- Register webhook endpoint: `POST /webhooks/stripe` for `checkout.session.completed`, `checkout.session.expired`, `invoice.payment_succeeded`, `customer.subscription.deleted`, `customer.subscription.updated`, `charge.refunded`

**Stripe test mode (before launch):**

- Set `MOCK_CHECKOUT_MODE=false` + test keys in `.env`
- `./scripts/stripe_webhook_listen.sh` — forward webhooks locally
- `./scripts/stripe_test_checkout.sh` — create test Hunt Pass checkout
- Full runbook: [docs/STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md)

Mock checkout is **blocked** when `APP_ENV=production` or when Stripe is configured.

### Production launch

See **[PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)**, **[LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md)**, **[LAUNCH.md](LAUNCH.md)**, and **[docs/PRODUCTION_DEPLOY.md](docs/PRODUCTION_DEPLOY.md)** for the full v1 deploy guide:

- `./scripts/check_prod_env.sh` — validate `.env` before deploy
- `ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap` — schema + migrations + plans (no demo seed)
- `./scripts/prod_verify_db.sh` — confirm required tables and zero demo incentives
- `docker compose -f docker-compose.prod.yml up -d --build`
- `./scripts/prod_smoke.sh` and `./scripts/verify_stripe.sh`

See [docs/DATABASE.md](docs/DATABASE.md) for dev vs production DB commands.

- Stripe checkout verification: [docs/STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md)
- Verified incentive inventory: [docs/VERIFIED_INCENTIVES.md](docs/VERIFIED_INCENTIVES.md)
- Scheduled jobs: `python -m jobs.run_scheduled` (entitlements); optional `--crawl` when `ENABLE_DAILY_CRAWL=true`

Copy [`.env.production.example`](.env.production.example) to `.env` on the server.

### Auth

Use **JWT** (`Authorization: Bearer <access_token>`) from `POST /auth/register` or `POST /auth/login`. `GET /me/entitlements` and checkout require a logged-in user.

### API quick reference

- `GET /plans` — active plans
- `GET /me/entitlements` — feature flags + active passes (JWT)
- `POST /checkout/session` — Stripe Checkout URL when configured, else mock flow (dev only)
- `POST /checkout/mock-complete` — dev-only instant grant (`hunt_pass_30` = 30 days)
- `GET /deal-reports/{building_id}` — preview for free/anonymous; `access: full` with Hunt Pass
- `POST /concierge/request` — requires Premium Plus **or** Concierge purchase
- `POST /webhooks/stripe` — grants Hunt Pass on successful checkout; extends on renewal; cancels on subscription delete/refund

### Local test flow

1. Register/login via `/auth/register` or `/auth/login` → save `access_token`.
2. `GET /deal-reports/{building_id}` with Bearer token (no pass) → **`access`: `preview`**.
3. **Pricing** → **Unlock Hunt Pass** (mock) or `POST /checkout/mock-complete` with `{ "plan_code": "hunt_pass_30" }`.
4. Same Deal Report → **`access`: `full`**, `full_report` populated.
5. After 30 days (or `jobs/expire_entitlements.py`), pass expires and preview returns.

## License

Starter template — adopt a license when you ship.
