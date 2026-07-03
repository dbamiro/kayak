# Abuse protection (v1)

Kayak uses **in-process per-IP rate limits** for v1. Suitable for single-instance deploys; use an edge proxy (nginx, Cloudflare, Render/Fly rate limits) when running multiple API replicas.

## Protected endpoints

| Route | Protection |
|-------|------------|
| `POST /auth/register` | Rate limit (`RATE_LIMIT_AUTH_REGISTER_PER_MINUTE`, default 5/min) |
| `POST /auth/login` | Rate limit (default 20/min) |
| `POST /incentives/submit` | Rate limit (default 6/min), text validation, duplicate detection |
| `/admin/*` | **Admin JWT required** + rate limit (default 120/min) |

Set any `RATE_LIMIT_*` to **`0`** to disable that limit (local dev).

## Incentive submission rules

- `building_name` or `building_id` required
- `raw_special_text`: 10–4000 chars; rejects obvious spam (repeated characters, insufficient letters)
- `rent` required (1–50000), `lease_term_months` 1–60
- Optional URLs must start with `http://` or `https://`
- Duplicate identical text from same IP within 10 minutes → `429 duplicate_submission`

Submissions always land in `pending_review` until admin verifies.

## Admin routes

All `/admin/*` handlers require `AdminUser`:

- `users.is_admin = true`, or
- email listed in `ADMIN_EMAILS`

Non-admins receive **403** `admin_only`.

## Production recommendations

1. Keep defaults in `.env.production.example`
2. Add edge rate limits on `/auth/*` and `/incentives/submit` at your reverse proxy
3. Monitor `429` responses and `stripe_webhook_events` separately (webhooks are not rate-limited)

## Local dev

`.env.example` uses the same defaults; increase limits or set `RATE_LIMIT_*=0` if testing heavy flows.
