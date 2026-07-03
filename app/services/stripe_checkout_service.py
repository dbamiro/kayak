"""Create Stripe Checkout sessions for Hunt Pass and other plans."""

from __future__ import annotations

import logging
from uuid import UUID

from app.config import Settings
from app.monetization.checkout_mode import stripe_price_id

logger = logging.getLogger(__name__)


def create_stripe_checkout_session(
    settings: Settings,
    *,
    user_id: UUID,
    plan_code: str,
    checkout_session_row_id: UUID,
    success_url: str | None,
    cancel_url: str | None,
) -> tuple[str, str]:
    """Return (checkout_url, stripe_session_id). Raises ValueError when misconfigured."""
    import stripe

    price_id = stripe_price_id(settings, plan_code)
    if not price_id:
        raise ValueError(f"missing_stripe_price_for_{plan_code}")

    stripe.api_key = settings.stripe_secret_key
    success = success_url or f"{settings.app_base_url}/billing/success"
    cancel = cancel_url or f"{settings.app_base_url}/billing/cancel"
    mode = "payment" if plan_code == "concierge_one_time" else "subscription"

    session = stripe.checkout.Session.create(
        mode=mode,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel,
        client_reference_id=str(user_id),
        metadata={
            "user_id": str(user_id),
            "plan_code": plan_code,
            "checkout_session_row": str(checkout_session_row_id),
        },
    )
    if not session.url or not session.id:
        raise RuntimeError("stripe_session_missing_url_or_id")
    return session.url, session.id
