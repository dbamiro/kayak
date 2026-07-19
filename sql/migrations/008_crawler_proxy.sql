-- Per-source opt-in proxy flag for the crawler (see docs/CRAWLER_PROXY.md).
-- Proxy is disabled globally by default (PROXY_ENABLED=false) and is never
-- used to bypass Cloudflare, CAPTCHAs, logins, or explicit blocks.

ALTER TABLE sources ADD COLUMN IF NOT EXISTS use_proxy BOOLEAN NOT NULL DEFAULT false;
