# Crawler proxy (provider-agnostic)

Optional egress proxy for the Kayak crawler. Supports **Decodo**, **Bright
Data**, and any **custom** HTTP/SOCKS5 endpoint.

## Policy (non-negotiable)

- **Disabled by default** (`PROXY_ENABLED=false`).
- **Public pages only.** A proxy changes the egress IP for reliability
  (datacenter IP ranges are sometimes rate-limited); it is **not** an evasion
  tool.
- **Never bypass Cloudflare, CAPTCHAs, login walls, or explicit blocks.**
  Block/challenge pages fetched through a proxy are still classified
  `BLOCKED` by `crawler/block_detection.py`, exactly as without a proxy.
  Do not add stealth plugins, CAPTCHA solvers, or rotating "unblocker"
  products.
- **Credentials are never logged.** Proxy URLs contain username/password;
  the code logs only the provider name (`fetch_via_proxy provider=decodo`).
  `ProxyConfig`'s `repr` redacts URLs (`http://***:***@host:port`).

## Configuration

Env vars (placeholders in `.env.example` / `.env.production.example`):

| Variable | Default | Notes |
|---|---|---|
| `PROXY_ENABLED` | `false` | Master switch |
| `PROXY_PROVIDER` | `decodo` | `decodo`, `bright_data`, or `custom` |
| `PROXY_HTTP_URL` | *(empty)* | Full endpoint URL incl. credentials |
| `PROXY_HTTPS_URL` | *(empty)* | Falls back to `PROXY_HTTP_URL` if empty |
| `PROXY_MAX_RETRIES` | `1` | Retries for proxied fetches |
| `PROXY_TIMEOUT_SECONDS` | `20` | Timeout for proxied fetches |
| `PROXY_MONTHLY_GB_BUDGET` | `2` | Operator budget hint (dashboard alerting; not enforced in code) |

Behavior:

- `PROXY_ENABLED=true` with an **empty URL fails clearly** at fetch time with
  `ProxyConfigError` (message names the missing variable, never credentials).
- Per-source opt-in: `sources.use_proxy` (default `false`, migration
  `sql/migrations/008_crawler_proxy.sql`). A source goes through the proxy
  only when **both** `PROXY_ENABLED=true` and `use_proxy=true`.

```sql
-- Route one source through the proxy
UPDATE sources SET use_proxy = true WHERE id = '<source-uuid>';
```

Both fetch paths are covered: httpx (per-scheme transport mounts) and
Playwright (launch `proxy` with credentials passed as separate fields, not in
the server string).

## Decodo vs Bright Data for Kayak

Kayak's need is small: tens of public leasing pages per day, a few GB/month,
US (DMV) egress.

| | Decodo (ex-Smartproxy) | Bright Data |
|---|---|---|
| **Fit for Kayak's scale** | Good — small plans, simple pricing | Overkill unless you need enterprise features |
| **Entry cost** | Lower; small residential/ISP plans in the $/GB range with modest minimums | Higher minimums; pay-as-you-go per-GB rates typically higher at low volume |
| **Setup** | Single gateway host + port + user/pass; works as `PROXY_HTTP_URL` directly | Zone-based config (per-zone credentials); also a single URL, slightly more setup |
| **Geo-targeting** | Country/state/city via username parameters | Very granular (country/state/city/ASN) |
| **Compliance features** | Standard KYC | Strong KYC + policy tooling; strict on use cases |
| **"Unblocker" products** | Sold separately — **do not use** (violates Kayak policy) | Sold separately (Web Unlocker) — **do not use** |
| **When to pick** | Default choice for Kayak v1 (`PROXY_PROVIDER=decodo`) | If you later need enterprise SLAs, granular ASN targeting, or already have a contract |

Recommendation: start with **Decodo** on the smallest US-state-targeted plan
that covers `PROXY_MONTHLY_GB_BUDGET` (2 GB). Either provider plugs in via the
same two URL variables; switching providers is an `.env` change only
(`PROXY_PROVIDER` + URLs).

For any other endpoint (e.g. a self-hosted squid or a different vendor), use
`PROXY_PROVIDER=custom` with the same URL variables.

## Budget note

`PROXY_MONTHLY_GB_BUDGET` documents the intended spend so operators can set
provider-side alerts. Kayak does not meter proxy bandwidth in code — set usage
alerts in the provider dashboard at ~80% of budget.

## Verification

```bash
# Unit tests (config, redaction, block-through-proxy)
./.venv/bin/python -m pytest tests/test_crawler_proxy.py -q

# One-off proxied parse test against a public page (after setting .env):
# set sources.use_proxy=true for the source, then
./.venv/bin/python -m crawler.test_parse --url "https://<public-floorplans-url>" --strategy http
```

If a proxied fetch returns a challenge page, the source is marked `blocked` —
fix the source (different public URL or partner/API access), do not escalate
proxy tooling.
