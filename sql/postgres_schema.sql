-- SyntaxMatrix Media Studio PostgreSQL schema
-- Target: Cloud SQL PostgreSQL / local PostgreSQL
-- Step 33A: persistence foundation

CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    billing_email TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    subscription_owner_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_customer_id
    ON workspaces(customer_id);

CREATE TABLE IF NOT EXISTS workspace_memberships (
    user_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_memberships_workspace_id
    ON workspace_memberships(workspace_id);

CREATE TABLE IF NOT EXISTS workspace_subscriptions (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    plan_key TEXT NOT NULL DEFAULT 'starter',
    plan_label TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    provider TEXT NOT NULL DEFAULT 'local',
    monthly_credit_limit NUMERIC,
    monthly_credits NUMERIC,
    monthly_price NUMERIC,
    customer_id TEXT,
    subscription_id TEXT,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    checkout_session_id TEXT,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    last_stripe_event_id TEXT,
    last_stripe_event_type TEXT,
    last_stripe_invoice_id TEXT,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_subscriptions_provider_status
    ON workspace_subscriptions(provider, status);

CREATE INDEX IF NOT EXISTS idx_workspace_subscriptions_stripe_subscription_id
    ON workspace_subscriptions(stripe_subscription_id);

CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    credits NUMERIC NOT NULL DEFAULT 0,
    provider TEXT,
    model TEXT,
    source_id TEXT,
    output_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_events_workspace_month
    ON usage_events(workspace_id, created_at);

CREATE INDEX IF NOT EXISTS idx_usage_events_event_type
    ON usage_events(event_type);

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_event_type
    ON stripe_webhook_events(event_type);

CREATE TABLE IF NOT EXISTS stripe_processed_events (
    event_id TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stripe_price_catalog (
    plan_key TEXT PRIMARY KEY,
    plan_label TEXT,
    product_id TEXT,
    price_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    unit_amount INTEGER NOT NULL,
    monthly_price NUMERIC,
    monthly_credits NUMERIC,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    stripe_mode TEXT NOT NULL DEFAULT 'test',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Durable saved voice identities. Provider voice IDs and display metadata live
-- in PostgreSQL; preview audio remains in object storage.
CREATE TABLE IF NOT EXISTS workspace_voices (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    voice_id TEXT NOT NULL,
    provider_voice_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    gender TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'upload',
    preview_object_key TEXT,
    preview_content_type TEXT NOT NULL DEFAULT 'audio/wav',
    status TEXT NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, voice_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_voices_workspace_status
    ON workspace_voices(workspace_id, status, updated_at DESC);


-- Durable global system voice identities managed by platform administrators.
CREATE TABLE IF NOT EXISTS system_voices (
    voice_id TEXT PRIMARY KEY,
    provider_voice_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    gender TEXT NOT NULL,
    preview_object_key TEXT,
    preview_content_type TEXT NOT NULL DEFAULT 'audio/wav',
    status TEXT NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_system_voices_status
    ON system_voices(status, updated_at DESC);
