# Verified incentive inventory (production v1)

Kayak does **not** ship fabricated building specials in production. Search (`/search`), specials (`/incentives`, web `/specials`), and Deal Reports show only **`verified`** incentives with `is_demo=false` when `SHOW_DEMO_DATA=false`.

Demo seed data (`seed.sql`, `seed_incentives.sql`) is **dev only** — never run `./scripts/bootstrap_db.sh` in production.

---

## A. Admin CSV bulk import (recommended for launch)

Bulk-load verified DMV apartment move-in specials from a spreadsheet export.

**Operational workflow (first 30–75 real specials):** [DMV_INCENTIVE_IMPORT.md](DMV_INCENTIVE_IMPORT.md) — blank template, field guide, quality checklist, dry-run and import commands.

### CSV columns

| Column | Required | Notes |
|--------|----------|-------|
| `building_name` | Yes | Matched to existing building by name+city, or new building created |
| `address` | Recommended | Street address (alias: `address_or_area`) |
| `city` | Recommended | Required when creating a new building |
| `state` | Recommended | Two-letter state code |
| `neighborhood` | Optional | Or `market` — stored on building + metadata |
| `source_url` | Yes | Leasing office or listing URL (`https://…`) |
| `listed_rent` | Yes | Monthly rent in dollars |
| `lease_months` | Yes | Alias: `lease_term_months` |
| `free_months` | One of* | Fractional months OK (e.g. `1.5`) |
| `free_weeks` | One of* | Converted to fractional months |
| `rent_credit` | One of* | Dollar amount |
| `waived_fees` | One of* | Dollar amount |
| `expires_at` | Optional | `YYYY-MM-DD` or `MM/DD/YYYY` |
| `notes` | One of* | Free text; included in raw_text |

\*At least one concession field or `notes` is required per row.

**Production template (blank):** [`fixtures/incentives_import_template.csv`](../fixtures/incentives_import_template.csv) — copy to `verified_specials.csv` and fill with real data.

**Example file (do not import):** [`fixtures/incentives_import_example.csv`](../fixtures/incentives_import_example.csv) — rows marked `[EXAMPLE ONLY]` are **rejected** at import.

### Import methods

**1. Admin web UI**

1. Log in as admin (`ADMIN_EMAILS` or `users.is_admin=true`).
2. Open **`/admin/incentives`** → **Bulk import verified specials (CSV)**.
3. **Validate** (dry-run) then **Import**.

**2. API**

```bash
curl -X POST "http://127.0.0.1:8000/admin/incentives/import" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@verified_specials.csv"

# Dry-run (validate only):
curl -X POST "http://127.0.0.1:8000/admin/incentives/import?dry_run=true" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@verified_specials.csv"
```

**3. CLI script**

```bash
chmod +x scripts/import_incentives_csv.sh
TOKEN=$ADMIN_TOKEN ./scripts/import_incentives_csv.sh verified_specials.csv
TOKEN=$ADMIN_TOKEN ./scripts/import_incentives_csv.sh --dry-run verified_specials.csv
```

### What import creates

| Field | Value |
|-------|-------|
| `status` | `verified` |
| `is_demo` | `false` |
| `capture_method` | `admin_csv_import` |
| `verification_method` | `admin_csv_verified` |
| `reviewed_by_user_id` | Importing admin |
| Building | Created if missing (with minimal listing for `/search`) |

### Validation errors

Invalid rows are skipped with row number, field, and message — e.g. missing rent, bad URL, example/sample markers, no concession fields. Other valid rows still import.

### Verify after import

```bash
curl -s "http://127.0.0.1:8000/incentives?include_demo=false" | jq '.[].building_name'
curl -s "http://127.0.0.1:8000/search?include_demo=false" | jq '.[].name'
```

Web: `/specials` and `/search` should list imported buildings (production: `SHOW_DEMO_DATA=false`).

---

## B. Admin direct entry (single special)

1. Ensure building exists in `buildings` (or let CSV import create it).
2. **POST `/admin/incentives`**:

```json
{
  "building_id": "<uuid>",
  "raw_text": "2 months free on 14-month leases",
  "listed_rent": 2400,
  "lease_term_months": 14,
  "source_url": "https://leasing-office-or-listing-url",
  "verification_method": "leasing_office_verified"
}
```

Creates `status=verified`, `is_demo=false`, `capture_method=manual_admin`.

---

## C. User submission → admin review

1. User submits at **`/submit-special`** → `status=pending_review` (hidden from public).
2. Admin opens **`/admin/incentives`** → verify or reject.

---

## D. Crawler-derived (pending until verified)

Crawl stores `capture_method=crawler`, `status=pending_review`. Admin verifies before public display.

**Do not** crawl blocked sites or bypass logins.

---

## Production settings

```bash
SHOW_DEMO_DATA=false
```

Bootstrap production DB (plans only, no demo seeds):

```bash
ALLOW_PROD_BOOTSTRAP=yes ./scripts/bootstrap_prod_db.sh
```

---

## Launch checklist

1. Bootstrap prod DB (plans only).
2. Import 3–5 verified specials via CSV or admin entry.
3. Confirm `GET /incentives?include_demo=false` and `GET /search?include_demo=false` return real rows.
4. Confirm demo specials are hidden when `SHOW_DEMO_DATA=false`.

Automated tests: `tests/test_incentive_csv_import.py`
