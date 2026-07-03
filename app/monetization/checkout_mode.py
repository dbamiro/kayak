"""Checkout mode helpers — mock for local dev, Stripe for production."""

from __future__ import annotations

from app.config import Settings

PRODUCTION_ENVS = frozenset({"production", "prod"})

STRIPE_PRICE_ENV_BY_PLAN = {
    "hunt_pass_30": "stripe_price_hunt_pass_30",
    "premium_plus_30": "stripe_price_premium_plus_30",
    "concierge_one_time": "stripe_price_concierge_one_time",
}


def stripe_configured(settings: Settings) -> bool:
    return bool(settings.stripe_secret_key and settings.stripe_secret_key.strip())


def stripe_webhook_configured(settings: Settings) -> bool:
    return stripe_configured(settings) and bool(
        settings.stripe_webhook_secret and settings.stripe_webhook_secret.strip()
    )


def mock_checkout_allowed(settings: Settings) -> bool:
    """Mock checkout is dev-only and disabled when Stripe is configured."""
    if not settings.mock_checkout_mode:
        return False
    if settings.app_env.lower() in PRODUCTION_ENVS:
        return False
    if stripe_configured(settings):
        return False
    return True


def stripe_price_id(settings: Settings, plan_code: str) -> str | None:
    attr = STRIPE_PRICE_ENV_BY_PLAN.get(plan_code)
    if not attr:
        return None
    value = getattr(settings, attr, None)
    return str(value).strip() if value else None


def checkout_uses_stripe(settings: Settings) -> bool:
    return stripe_configured(settings)


def response_mock_mode(settings: Settings) -> bool:
    return mock_checkout_allowed(settings) and not checkout_uses_stripe(settings)
