-- Production-safe: monetization plans only (no buildings, listings, or demo incentives).
-- Idempotent — safe to re-run after migrations.

INSERT INTO plans (code, name, price_cents, currency, duration_days, plan_type, description, is_active)
VALUES
    ('free', 'Free', 0, 'USD', NULL, 'free',
     'Browse listings, basic signals, and Deal Report previews.', true),
    ('hunt_pass_30', 'Premium Hunt Pass (30 days)', 1900, 'USD', 30, 'subscription',
     'Unlimited Deal Reports, full rent history, fee breakdown, negotiation tools, alerts, compare.', true),
    ('premium_plus_30', 'Premium Plus (30 days)', 3900, 'USD', 30, 'subscription',
     'Everything in Hunt Pass plus enhanced report export and decision-support placeholders.', true),
    ('concierge_one_time', 'Concierge (one-time)', 14900, 'USD', NULL, 'one_time',
     'Human-assisted shortlist and negotiation help — fulfillment is manual (placeholder).', true)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    price_cents = EXCLUDED.price_cents,
    duration_days = EXCLUDED.duration_days,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active;
