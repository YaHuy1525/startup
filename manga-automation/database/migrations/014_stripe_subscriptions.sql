-- 014_stripe_subscriptions.sql
-- Stripe billing support for AiToEarn SaaS.
-- Requires: 004_multi_tenancy.sql (organizations table with stripe_customer_id)

-- Subscription tracking — one active row per Stripe subscription
CREATE TABLE IF NOT EXISTS subscriptions (
    id                      SERIAL PRIMARY KEY,
    organization_id         INTEGER NOT NULL REFERENCES organizations(id),
    stripe_customer_id      VARCHAR(100) NOT NULL,
    stripe_subscription_id  VARCHAR(100) NOT NULL UNIQUE,
    price_id                VARCHAR(100),
    plan_tier               VARCHAR(50) NOT NULL DEFAULT 'hobbyist',
    status                  VARCHAR(30) NOT NULL DEFAULT 'incomplete',
    current_period_end      TIMESTAMP,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_org ON subscriptions(organization_id);
CREATE INDEX idx_subscriptions_customer ON subscriptions(stripe_customer_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);

-- Audit log — every Stripe event that touches a subscription
CREATE TABLE IF NOT EXISTS subscription_events (
    id                  SERIAL PRIMARY KEY,
    subscription_id     INTEGER REFERENCES subscriptions(id),
    event_type          VARCHAR(100) NOT NULL,
    stripe_event_id     VARCHAR(100),
    raw_payload         JSONB,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_subscription_events_sub ON subscription_events(subscription_id);
CREATE INDEX idx_subscription_events_type ON subscription_events(event_type);
