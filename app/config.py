from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration. Copy `.env.example` to `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments"
    crawler_user_agent: str = "DMV-ApartmentIntel/0.1 (+research)"
    crawler_timeout_seconds: float = 30.0
    playwright_headless: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    crawler_max_retries: int = 2
    crawler_retry_backoff_seconds: float = 1.5
    crawler_min_interval_ms: int = 500
    playwright_screenshot_on_error: bool = False

    # Monetization / Stripe (optional)
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_hunt_pass_30: str | None = None
    stripe_price_premium_plus_30: str | None = None
    stripe_price_concierge_one_time: str | None = None
    mock_checkout_mode: bool = True
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"

    # Auth (production: set jwt_secret; use mock_auth_mode=false + CORS for real apps)
    jwt_secret: str = ""
    jwt_expires_minutes: int = 60
    jwt_refresh_days: int = 14
    # False in production; set MOCK_AUTH_MODE=true locally if you still use X-User-Id without Bearer.
    mock_auth_mode: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    admin_emails: str = ""

    # Entitlement limits (compare / alerts)
    free_alert_limit: int = 1
    paid_alert_limit: int = 20
    free_compare_limit: int = 2
    paid_compare_limit: int = 10

    # Incentive demo data: true locally (SHOW_DEMO_DATA), false in production
    show_demo_data: bool = True
    app_env: str = "development"

    # Rate limits (per client IP per minute; 0 = disabled)
    rate_limit_auth_register_per_minute: int = 5
    rate_limit_auth_login_per_minute: int = 20
    rate_limit_incentive_submit_per_minute: int = 6
    rate_limit_admin_per_minute: int = 120

    # Scheduled jobs: set ENABLE_DAILY_CRAWL=true to allow jobs/run_scheduled --crawl
    enable_daily_crawl: bool = False
    # Pending user/crawler incentives without expires_at expire after N days
    pending_incentive_ttl_days: int = 90

    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")

    def validate_production(self) -> None:
        """Fail fast on unsafe production configuration."""
        if not self.is_production():
            return
        weak_secrets = {
            "",
            "change-me-in-production",
            "local-dev-change-me-not-for-production",
            "dev-insecure-jwt-secret-change-me",
        }
        if (self.jwt_secret or "").strip() in weak_secrets or len((self.jwt_secret or "").strip()) < 32:
            raise RuntimeError(
                "Production requires JWT_SECRET (32+ chars). Generate with: openssl rand -hex 32"
            )
        if self.mock_auth_mode:
            raise RuntimeError("Production requires MOCK_AUTH_MODE=false")
        if self.mock_checkout_mode:
            raise RuntimeError("Production requires MOCK_CHECKOUT_MODE=false")
        if not (self.stripe_secret_key and self.stripe_secret_key.strip()):
            raise RuntimeError("Production requires STRIPE_SECRET_KEY for Hunt Pass checkout")
        if not (self.stripe_webhook_secret and self.stripe_webhook_secret.strip()):
            raise RuntimeError("Production requires STRIPE_WEBHOOK_SECRET")
        if not (self.stripe_price_hunt_pass_30 and self.stripe_price_hunt_pass_30.strip()):
            raise RuntimeError("Production requires STRIPE_PRICE_HUNT_PASS_30")
        if self.show_demo_data:
            raise RuntimeError("Production requires SHOW_DEMO_DATA=false")


@lru_cache
def get_settings() -> Settings:
    return Settings()
