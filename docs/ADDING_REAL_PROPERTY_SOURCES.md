# Adding a real property source

Kayak stores **one crawl URL per row** in `sources`, tied to a `buildings` record. Parsed rows become `listings` + append-only `listing_snapshots`.

## Triage workflow (new sources)

**Step 1 — registry parse (auto)**

```bash
python -m crawler.test_parse --url "https://YOUR-FLOORPLANS-URL" --strategy playwright --parser auto
```

Check JSON: `listing_count`, `diagnostics`, `summary.triage_classification`.

**Step 2 — if 0 listings, inspect rendered HTML**

```bash
python scripts/debug_rendered_page.py \
  --url "https://YOUR-FLOORPLANS-URL" \
  --out tmp/debug_html/site.html
```

**Step 3 — if HTML has no rent/unit text, discover XHR/API**

```bash
python scripts/debug_xhr.py --url "https://YOUR-FLOORPLANS-URL"
```

**Step 4 — classify**

| Classification | Meaning |
|----------------|---------|
| `PASS` | Listings extracted |
| `NEEDS_HTML_PARSER` | Rent/unit text in HTML; tune `floorplan_cards_html` or add site parser |
| `NEEDS_XHR_PARSER` | Data likely in JSON API (build allowed client parser; no auth bypass) |
| `BLOCKED` | Cloudflare / captcha / access denied — use another URL; deactivate source |
| `NOT_VIABLE` | Marketing-only page with no inventory signals |

**Parser order (registry / `auto`):** `next_data` → `rentcafe_html` → `floorplan_cards_html` → `generic_html`

Force a parser: `--parser floorplan_cards_html` | `rentcafe_html` | `next_data`

**Do not** add Cloudflare bypass, CAPTCHA solvers, stealth plugins, or login scraping.

## 1. Find the right URL

Use the building’s **availability / floorplans / pricing** page — not always the marketing homepage.

- Open the site in a browser and navigate to “Floor Plans”, “Availability”, or “Apply”.
- Copy the **address bar URL** after the list loads.
- Check **robots.txt** and site terms; do not bypass login, paywalls, or CAPTCHAs.

Good signals for **`next_data`** parser:

- View Source contains `<script id="__NEXT_DATA__" type="application/json">…</script>`

If rent loads only after JavaScript or XHR:

- Use **`playwright`** crawl strategy and optionally a **`wait_selector`** (CSS) for the price table.

## 2. Pilot building in this repo

Apply the pilot seed (once):

```bash
cat sql/seed_real_data_pilot.sql | docker compose exec -T postgres psql -U dmv_user -d dmv_apartments
```

Or with local `psql`:

```bash
psql "$DATABASE_URL" -f sql/seed_real_data_pilot.sql
```

Then update the pilot source (replace URLs; enable when ready):

```sql
UPDATE buildings
SET property_url = 'https://YOUR-BUILDING-HOMEPAGE'
WHERE slug = 'real-data-pilot-dc';

UPDATE sources s
SET
    url = 'https://YOUR-REAL-FLOORPLANS-URL',
    crawl_strategy = 'playwright',  -- or 'http'
    wait_selector = NULL,            -- e.g. '[data-testid=floorplans]'
    active = true,
    metadata = metadata || '{"parser_type": "next_data"}'::jsonb
FROM buildings b
WHERE s.building_id = b.id AND b.slug = 'real-data-pilot-dc';
```

Get IDs:

```sql
SELECT s.id AS source_id, b.id AS building_id, s.url, s.active, s.crawl_strategy
FROM sources s
JOIN buildings b ON b.id = s.building_id
WHERE b.slug = 'real-data-pilot-dc';
```

## 3. Choose `crawl_strategy`

| Strategy | When |
|----------|------|
| `http` | Static HTML or `__NEXT_DATA__` in initial response |
| `playwright` | Client-rendered lists, heavy JS, need wait for selectors |

Set on `sources.crawl_strategy` (enum `http` | `playwright`).

## 4. Choose `parser_type`

Stored in `sources.metadata.parser_type` (documentation hint; runtime uses parser registry):

| Value | Meaning |
|-------|---------|
| `next_data` | Force Next.js `__NEXT_DATA__` extraction (`--parser next_data`) |
| `rentcafe_html` | RentCafe / Yardi SI floorplan cards (`--parser rentcafe_html`) |
| `floorplan_cards_html` | Generic rent/bed/bath/unit card heuristics (`--parser floorplan_cards_html`) |
| `generic_html` | DOM placeholder (usually empty; last resort) |
| `auto` / *(omit)* | Registry: `next_data` → `rentcafe_html` → `floorplan_cards_html` → `generic_html` |

CLI: `python -m crawler.test_parse --parser next_data` or `--parser registry`.

## 5. Test without writing to DB

```bash
cd /path/to/Kayak
source .venv/bin/activate
export PYTHONPATH="$(pwd)"

python -m crawler.test_parse \
  --url "https://YOUR-REAL-FLOORPLANS-URL" \
  --strategy playwright \
  --parser next_data \
  --wait-selector "optional-css-selector"
```

### Example: Dominion (RentCafe / Yardi — no `__NEXT_DATA__`)

Floorplan availability page:

`https://www.dominionapts.com/floorplans/b1a`

```bash
python -m crawler.test_parse \
  --url "https://www.dominionapts.com/floorplans/b1a" \
  --strategy playwright \
  --parser rentcafe_html
```

Expect `listing_count` ≥ 1 (units such as 617, 626, 717 with “Starting at” rents).

Configure the source (replace URL, enable, set parser hint):

```sql
UPDATE sources s
SET
  url = 'https://www.dominionapts.com/floorplans/b1a',
  crawl_strategy = 'playwright',
  active = true,
  metadata = s.metadata || '{"parser_type": "rentcafe_html"}'::jsonb
FROM buildings b
WHERE s.building_id = b.id AND s.id = 'eb84153f-b6c4-4791-9aa8-4cd85dabd684';
```

Persist snapshots:

```bash
export DATABASE_URL="postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments"
python jobs/daily_run.py --source-id eb84153f-b6c4-4791-9aa8-4cd85dabd684 --mode playwright
```

Verify:

```sql
SELECT last_listings_count, last_crawl_status, last_crawl_at
FROM sources WHERE id = 'eb84153f-b6c4-4791-9aa8-4cd85dabd684';
```

```bash
curl -s "http://127.0.0.1:8000/search" | jq '.[] | select(.name | test("Dominion|B1A"; "i"))'
```

Output includes a **`summary`** block (count, parser, confidence) and **`listings`**. If count is 0, read **`zero_listings_help`** in the JSON.

## 6. Persist one source (daily job)

```bash
export PYTHONPATH="$(pwd)"
export DATABASE_URL="postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments"

python jobs/daily_run.py --source-id YOUR_SOURCE_UUID
```

This will:

1. Fetch and save **`raw_documents`** (and legacy `raw_captures`) before parse  
2. Parse and append **`listing_snapshots`**  
3. Insert **`snapshot_concessions`** / **`snapshot_fees`** when text is present  
4. Update **`sources.last_*`** health columns  
5. Print a per-source summary (no crash on single-source failure)

Optional write from test CLI:

```bash
python -m crawler.test_parse --url "..." --strategy playwright --parser next_data \
  --write --building-id BUILDING_UUID --source-id SOURCE_UUID
```

## 7. Verify in the API

```bash
curl -s "http://127.0.0.1:8000/search" | jq '.[0:3]'
curl -s "http://127.0.0.1:8000/buildings/BUILDING_UUID" | jq .
curl -s "http://127.0.0.1:8000/buildings/BUILDING_UUID/history" | jq .
```

Pilot building should appear once snapshots exist for its listings.

## 8. Verify in the frontend

```bash
cd web && npm run dev
```

Open **http://localhost:3000/search** (set `NEXT_PUBLIC_API_BASE_URL` to your API port).

## 9. Blocked sources (Cloudflare / security challenge pages)

**Cloudflare/security challenge pages are not valid crawl results.** Kayak must not treat them as successful fetches or run parsers on them.

Examples Kayak detects (`crawler.block_detection.is_block_page()`):

| Signal | Example |
|--------|---------|
| Title | `Attention Required! \| Cloudflare`, **`Just a moment...`** |
| Body | `Sorry, you have been blocked`, `Access denied`, `enable cookies` |
| Host/markup | `challenges.cloudflare.com`, `cf-error-details`, Turnstile challenge scripts |

Real case: `https://www.edisonunionmarket.com/floorplans` may return **307 → 403** with title **“Just a moment...”** and `challenges.cloudflare.com` — that is **BLOCKED**, not apartment HTML.

**Behavior:**

- **`test_parse`**: `parse_status` = `"blocked"`, `listing_count` = 0, parsers **not** run  
- **`daily_run`**: `last_crawl_status` = `"blocked"`, `last_listings_count` = 0, **no snapshots**; continues to next source  
- **`debug_rendered_page` / `debug_xhr`**: `block_page_detected: true` + recommendation to deactivate source  
- Raw HTML may still be stored in `raw_documents` for audit only  

**Do not** bypass access controls: no stealth browsers, CAPTCHA solvers, Cloudflare bypass, proxy rotation, or anti-detection plugins.

**What to do instead:**

1. Use another **public direct property** floorplans URL, or **official partner/API** access when available.  
2. **Deactivate** blocked sources:

```sql
UPDATE sources
SET active = false,
    notes = COALESCE(notes, '') || ' [blocked by Cloudflare challenge — use direct site]'
WHERE last_crawl_status = 'blocked';

-- Or one URL:
-- UPDATE sources SET active = false WHERE url = 'https://www.edisonunionmarket.com/floorplans';
```

3. Check admin grouping: `GET /admin/sources/status-summary` → `blocked` vs `parser_failures`.

```bash
python -m crawler.test_parse \
  --url "https://www.edisonunionmarket.com/floorplans" \
  --strategy playwright
# Expect parse_status: blocked when Cloudflare challenge is returned

python scripts/debug_rendered_page.py \
  --url "https://www.edisonunionmarket.com/floorplans" \
  --out tmp/debug_html/edison.html
# Expect block_page_detected: true
```

## 10. If the parser returns 0 listings

1. Confirm the URL is the **availability** page, not marketing-only.  
2. Retry with **`--strategy playwright`**.  
3. View page source for **`__NEXT_DATA__`**; if missing, data may be XHR-only → site-specific parser.  
4. Add **`--wait-selector`** for the element that appears when units load.  
5. Save HTML from `raw_documents` and inspect embedded JSON manually.  
6. Do not fabricate rents — fix extraction or choose another allowed URL.

## 11. Smoke script

```bash
./scripts/smoke_real_data.sh
API_URL=http://127.0.0.1:8001 TEST_PARSE_URL="https://example.com/" ./scripts/smoke_real_data.sh
```
