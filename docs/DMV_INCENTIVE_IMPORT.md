# DMV verified incentive import — operational workflow

Load the first **30–75 real** apartment move-in specials into production. Kayak does not ship fabricated inventory — every row must come from a leasing office or property website you verified.

**Do not import:** [`fixtures/incentives_import_example.csv`](../fixtures/incentives_import_example.csv) (example rows are rejected).

**Use instead:** [`fixtures/incentives_import_template.csv`](../fixtures/incentives_import_template.csv) (blank, production-ready header).

Related: [VERIFIED_INCENTIVES.md](VERIFIED_INCENTIVES.md) · [LAUNCH_CHECKLIST.md](../LAUNCH_CHECKLIST.md) §6

---

## Workflow (summary)

| Step | Action |
|------|--------|
| 1 | Copy template → `verified_specials.csv` |
| 2 | Enter 30–75 verified rows (field guide below) |
| 3 | Run quality checklist |
| 4 | Dry-run validate (no DB writes) |
| 5 | Import |
| 6 | Confirm `/search` and `/specials` |

---

## Step 1 — Create your CSV

From repo root:

```bash
cp fixtures/incentives_import_template.csv verified_specials.csv
```

Open `verified_specials.csv` in a spreadsheet editor or text editor. **One row per special.** Do not add comment lines above the header — the first line must be the column names.

`verified_specials.csv` is gitignored — do not commit real leasing data.

---

## Step 2 — Field guide (how to verify each column)

Verify every value against the **source URL** before you save the row.

### `building_name` (required)

- Use the **official property name** as shown on the leasing site or building signage.
- Match spelling and branding (e.g. “The Meridian at Courthouse” not a nickname).
- Do not prefix with `[EXAMPLE ONLY]` or “Sample”.

### `address` (recommended)

- Street address of the building, as listed on the property website.
- Used when Kayak creates a new building record. Format: `123 Main St` (city/state go in their own columns).

### `city` + `state` (recommended; required for new buildings)

- Two-letter state: `VA`, `MD`, or `DC`.
- City must be a **recognizable DMV market** (e.g. Arlington, Alexandria, Washington, Silver Spring, Bethesda, Reston, Tysons, Ashburn). Unknown cities fail import when the building does not already exist.

### `neighborhood` (optional)

- Submarket or neighborhood label shown on the site (e.g. `Courthouse`, `Logan Circle`, `Reston Town Center`).
- Alias: `market`.

### `source_url` (required)

- **Direct HTTPS link** to the page where you read the special (floorplan page, specials banner, or leasing office listing).
- Must start with `http://` or `https://`.
- Must **not** use `example.com`, `example.org`, or `example.net`.
- Open the URL in a browser before saving the row — if it 404s or requires login, fix or skip the row.

### `listed_rent` (required)

- **Advertised base monthly rent** in dollars for the unit/floorplan the special applies to (integer, no `$` required).
- Must match what the source page shows for that lease term (before concessions).

### `lease_months` (required)

- Minimum lease term the special requires (e.g. `12`, `14`, `15`).
- Alias: `lease_term_months`. Must be 1–60.

### Concession — at least one required

Fill the field that matches how the site states the deal:

| Column | When to use | Example |
|--------|-------------|---------|
| `free_months` | “X months free” | `2` or `1.5` |
| `free_weeks` | “X weeks free” | `6` |
| `rent_credit` | Dollar credit toward rent | `500` |
| `waived_fees` | Admin/app/deposit fee waiver in dollars | `250` |
| `notes` | Exact special wording when it does not fit above | `1 month free + $500 look-and-lease on 14-month leases` |

If the site lists multiple concessions, fill every applicable column and put the full sentence in `notes`.

### `expires_at` (optional)

- Last day the special is valid, if the site shows one.
- Format: `YYYY-MM-DD` or `MM/DD/YYYY`.
- Leave blank if no expiration is published.

---

## Step 3 — Quality checklist

Before dry-run, confirm **every row**:

- [ ] **Source URL opens** in a browser and shows the special (or the floorplan/rent the special applies to).
- [ ] **Special text matches CSV values** — rent, lease term, and concession fields reflect what the page says (not memory or a third-party aggregator alone).
- [ ] **No `example.com`** (or `example.org` / `example.net`) in any `source_url`.
- [ ] **No `[EXAMPLE ONLY]`** (or “sample only”, “do not import”) in building name or notes.
- [ ] **`listed_rent` and `lease_months`** are filled and greater than zero.
- [ ] **At least one concession** column or `notes` is filled.
- [ ] **`city` and `state`** are set for any building not already in Kayak.
- [ ] **30–75 rows** for launch inventory (fewer is OK for a pilot; do not pad with unverified rows).

After import, confirm:

- [ ] **`is_demo=false`** for all imported incentives (SQL or API below).
- [ ] Buildings appear on **`/search`** and **`/specials`** with `SHOW_DEMO_DATA=false`.

---

## Step 4 — Dry-run (validate only)

Requires API running and an admin JWT (or email/password).

```bash
export API_URL=https://api.example.com   # or http://127.0.0.1:8000 locally
export ADMIN_EMAIL=ops@your-company.com
export ADMIN_PASSWORD='your-admin-password'

# Option A: script logs in for you
ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  ./scripts/import_incentives_csv.sh --dry-run verified_specials.csv

# Option B: existing token
TOKEN="$ADMIN_TOKEN" ./scripts/import_incentives_csv.sh --dry-run verified_specials.csv
```

**Success:** JSON with `created_count` = number of valid rows, `error_count` = 0, message `Validation OK — N row(s) ready to import.`

**Failure:** JSON lists `errors` with row number, field, and message. Fix the CSV and re-run dry-run until `error_count` is 0.

Dry-run does **not** write to the database.

**Alternative — Admin UI:** `/admin/incentives` → upload CSV → **Validate** (same API, `dry_run=true`).

---

## Step 5 — Final import

Only after dry-run passes with zero errors:

```bash
ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  ./scripts/import_incentives_csv.sh verified_specials.csv

# or
TOKEN="$ADMIN_TOKEN" ./scripts/import_incentives_csv.sh verified_specials.csv
```

Each imported row is created with:

| Field | Value |
|-------|-------|
| `status` | `verified` |
| `is_demo` | `false` |
| `capture_method` | `admin_csv_import` |
| `verification_method` | `admin_csv_verified` |

New buildings get a minimal listing so they appear in search results.

---

## Step 6 — Verify public surfaces

```bash
# API — specials list
curl -s "$API_URL/incentives?include_demo=false" | jq '.[].building_name'

# API — search (buildings with listings)
curl -s "$API_URL/search?include_demo=false" | jq '.[].name'

# DB — no demo flags on recent imports
psql "$MIGRATE_DATABASE_URL" -c \
  "SELECT b.name, i.status, i.is_demo, i.capture_method
   FROM incentives i
   JOIN buildings b ON b.id = i.building_id
   WHERE i.capture_method = 'admin_csv_import'
   ORDER BY i.created_at DESC LIMIT 20;"
```

**Web** (production: `SHOW_DEMO_DATA=false`):

- `$APP_URL/specials` — imported specials listed
- `$APP_URL/search` — imported buildings searchable by rent/area

---

## Column reference (quick)

| Column | Required | Notes |
|--------|----------|-------|
| `building_name` | Yes | Official property name |
| `address` | Recommended | Street address |
| `city` | Recommended | Required for new buildings |
| `state` | Recommended | `VA`, `MD`, or `DC` |
| `neighborhood` | Optional | Submarket label |
| `source_url` | Yes | Leasing page URL (`https://…`) |
| `listed_rent` | Yes | Monthly rent ($) |
| `lease_months` | Yes | Lease term (months) |
| `free_months` | One of* | Fractional OK |
| `free_weeks` | One of* | |
| `rent_credit` | One of* | Dollar amount |
| `waived_fees` | One of* | Dollar amount |
| `expires_at` | Optional | `YYYY-MM-DD` |
| `notes` | One of* | Verbatim special text |

\*At least one concession field or `notes` per row.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| Row looks like example/sample data | Remove `[EXAMPLE ONLY]`, fix `example.com` URLs |
| `city or parseable address_or_area is required` | Add `city` and `state` columns |
| Could not infer `dmv_area` | Use a supported DMV city name |
| `listed_rent is required` | Fill rent for that row |
| Provide at least one concession | Add free months/weeks, credit, fees, or notes |
| HTTP 403 on import | Log in as admin (`ADMIN_EMAILS` or `is_admin=true`) |

Automated tests: `tests/test_incentive_csv_import.py`
