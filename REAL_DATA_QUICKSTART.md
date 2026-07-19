# Kayak local real-data quickstart

Use this workflow to replace visible demo incentives with manually verified DMV
apartment specials. Do not fabricate rows, bypass Cloudflare, or commit source
files, screenshots, credentials, or completed CSVs.

For the full field guide, see
[docs/DMV_INCENTIVE_IMPORT.md](docs/DMV_INCENTIVE_IMPORT.md).

## 1. Configure local real-data mode

Edit the repo-root `.env`:

```dotenv
SHOW_DEMO_DATA=false
ADMIN_EMAILS=you@example.com
```

`ADMIN_EMAILS` must contain the same email you use to register or log in.
Restart the API after editing `.env`; settings are loaded by the API process.
The local web app can remain configured with
`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.

```bash
# Terminal 1
docker compose up -d postgres
./scripts/dev-api.sh

# Terminal 2
./scripts/dev-web.sh
```

With `SHOW_DEMO_DATA=false`, requests without an `include_demo` query parameter
hide demo incentives. For an explicit check, use `include_demo=false`.
This setting hides demo rows; it does not delete them.

> Production uses `scripts/bootstrap_prod_db.sh`, which loads plans but no demo
> seeds. Never run `scripts/bootstrap_db.sh` or any `seed*.sql` demo file in
> production.

## 2. Collect each special manually

Collect only information you can verify on the apartment's own leasing page or
directly with its leasing office:

- official building name
- street address, city, state, and optional neighborhood
- direct source URL where the offer can be checked
- advertised base monthly rent
- qualifying lease term in months
- exact concession: free months, free weeks, rent credit, or waived fees
- expiration date, if published
- exact offer wording in `notes`, especially eligibility details

Open every source URL yourself. If a page is blocked by Cloudflare, requires a
login, or no longer shows the offer, do not work around the block and do not
import the row. Verify through an allowed leasing-office source instead or omit
it.

## 3. Create and fill the private CSV

From the repo root:

```bash
cp fixtures/incentives_import_template.csv verified_specials.csv
```

Fill one special per row. Keep the header unchanged:

```text
building_name,address,city,state,neighborhood,source_url,listed_rent,lease_months,free_months,free_weeks,rent_credit,waived_fees,expires_at,notes
```

Rules:

- `building_name`, `source_url`, `listed_rent`, and `lease_months` are required.
- Include `city` and `state` for buildings that may not exist in Kayak yet.
- Fill at least one of `free_months`, `free_weeks`, `rent_credit`,
  `waived_fees`, or `notes`.
- Use `YYYY-MM-DD` for `expires_at` when known; otherwise leave it blank.
- Preserve commas in a value by quoting the cell.
- Do not use `example.com`, `[EXAMPLE ONLY]`, guessed values, or sample rows.

Completed real-data CSVs are local-only. `.gitignore` excludes
`verified_specials.csv`, `real_specials.csv`, `*.real.csv`, `data/`,
`real-data/`, and `real_data/`.

## 4. Create or log in as the local admin

First ensure `.env` has `ADMIN_EMAILS=you@example.com`, then restart the API.

### Browser

1. Open `http://localhost:3000/register` and register that email, or use
   `http://localhost:3000/login` if it already exists.
2. Open `http://localhost:3000/admin/incentives`.
3. The page must show **Bulk import verified specials (CSV)**. A redirect or
   “Admin access required” means the login email does not match
   `ADMIN_EMAILS` or the API was not restarted.

### CLI

Do not put the password in a committed file. Export it only in your current
shell:

```bash
export API_URL=http://127.0.0.1:8000
export ADMIN_EMAIL=you@example.com
export ADMIN_PASSWORD='your-local-password'
```

The import script logs in through `POST /auth/login` and uses the returned
access token. Alternatively, pass an existing token as `TOKEN`.

## 5. Run local preflight and dry-run

The preflight does not import anything:

```bash
ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  ./scripts/check_real_data_ready.sh verified_specials.csv
```

It checks:

- `SHOW_DEMO_DATA=false`
- API health
- admin token or email/password is supplied
- CSV exists and contains at least one data row
- required template headers exist
- no example domains or `[EXAMPLE ONLY]` markers occur

Then ask the real importer to validate every row without database writes:

```bash
ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  ./scripts/import_incentives_csv.sh --dry-run verified_specials.csv
```

Do not proceed until output shows `error_count: 0` and:

```text
Validation OK — N row(s) ready to import.
```

Browser alternative: `/admin/incentives` → choose the CSV → **Validate**.

## 6. Import

Run only after a successful dry-run:

```bash
ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  ./scripts/import_incentives_csv.sh verified_specials.csv
```

Browser alternative: use **Import** on `/admin/incentives` after validation.

The API creates imported incentives with:

- `status=verified`
- `is_demo=false`
- `capture_method=admin_csv_import`
- `verification_method=admin_csv_verified`

It also creates a minimal listing for a new building so that building can
appear in `/search`.

## 7. Verify the API and app

Explicitly exclude demos from both API checks:

```bash
curl -s "$API_URL/incentives?include_demo=false" | \
  jq '.[] | {building_name, status, is_demo, source_url}'

curl -s "$API_URL/search?include_demo=false" | \
  jq '.[] | {name, city, best_incentive_id, incentive_is_demo}'
```

Confirm that:

- imported incentives are present and `is_demo` is `false`
- imported buildings appear in search with a `best_incentive_id`
- no demo incentive is returned

Then open:

- `http://localhost:3000/specials`
- `http://localhost:3000/search`

Because the restarted API has `SHOW_DEMO_DATA=false`, both pages should show
real verified imports and no “Demo data” badges. The `/search` page also has an
**Exclude demo data** control for an explicit `include_demo=false` request.

## Common CSV errors

| Error | Fix |
|---|---|
| `Row looks like example/sample data` | Remove sample markers and replace example domains with the verified direct source URL. |
| Missing required column | Start again from `fixtures/incentives_import_template.csv`; keep its header unchanged. |
| `listed_rent is required` | Enter the published monthly base rent as a positive number. |
| `lease_term_months is required` | Enter the qualifying lease length in months (1–60). |
| `source_url must start with http:// or https://` | Use the full direct leasing-page URL. |
| `Provide at least one concession` | Fill free months/weeks, credit, waived fees, or exact offer text in `notes`. |
| Invalid expiration date | Use `YYYY-MM-DD` or `MM/DD/YYYY`, or leave it blank if unpublished. |
| `city or parseable address_or_area is required` | Add separate `address`, `city`, and two-letter `state` values. |
| Could not infer `dmv_area` | Verify the city is in the supported DMV markets; do not invent a replacement. |
| HTTP 401 | Log in again or pass a fresh admin JWT. |
| HTTP 403 / `admin_only` | Ensure login email matches `ADMIN_EMAILS`, then restart the API and log in again. |
| CSV values shift columns | Quote fields containing commas and save as UTF-8 CSV. |

## Safety guarantees already enforced

- The importer rejects `example.com`, `example.org`, `example.net`, and obvious
  example/sample markers.
- A dry-run performs validation without inserting rows.
- Public `include_demo=false` queries exclude demo incentives.
- Real CSVs, local screenshots, and leasing-office download folders are
  gitignored.
- Production bootstrap does not run demo seeds.
