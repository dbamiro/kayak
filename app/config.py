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


@lru_cache
def get_settings() -> Settings:
    return Settings()
