"""Checkout mode helper tests (no database)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.monetization.checkout_mode import (
    checkout_uses_stripe,
    mock_checkout_allowed,
    response_mock_mode,
)


def _settings(**kwargs) -> Settings:
    return Settings(**kwargs)


def test_mock_allowed_in_development_without_stripe():
    s = _settings(mock_checkout_mode=True, app_env="development", stripe_secret_key=None)
    assert mock_checkout_allowed(s) is True
    assert response_mock_mode(s) is True
    assert checkout_uses_stripe(s) is False


def test_mock_blocked_in_production():
    s = _settings(mock_checkout_mode=True, app_env="production", stripe_secret_key=None)
    assert mock_checkout_allowed(s) is False


def test_mock_blocked_when_stripe_configured():
    s = _settings(mock_checkout_mode=True, app_env="development", stripe_secret_key="sk_test_x")
    assert mock_checkout_allowed(s) is False
    assert checkout_uses_stripe(s) is True
    assert response_mock_mode(s) is False


def test_mock_disabled_flag():
    s = _settings(mock_checkout_mode=False, app_env="development", stripe_secret_key=None)
    assert mock_checkout_allowed(s) is False
