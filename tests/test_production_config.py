"""Production configuration validation."""

from __future__ import annotations

import pytest

from app.config import get_settings


def test_validate_production_rejects_weak_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "short")
    monkeypatch.setenv("MOCK_AUTH_MODE", "false")
    monkeypatch.setenv("MOCK_CHECKOUT_MODE", "false")
    monkeypatch.setenv("SHOW_DEMO_DATA", "false")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    monkeypatch.setenv("STRIPE_PRICE_HUNT_PASS_30", "price_x")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        get_settings().validate_production()


def test_validate_production_passes_with_valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "a" * 32
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.setenv("MOCK_AUTH_MODE", "false")
    monkeypatch.setenv("MOCK_CHECKOUT_MODE", "false")
    monkeypatch.setenv("SHOW_DEMO_DATA", "false")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    monkeypatch.setenv("STRIPE_PRICE_HUNT_PASS_30", "price_x")
    get_settings.cache_clear()
    get_settings().validate_production()
