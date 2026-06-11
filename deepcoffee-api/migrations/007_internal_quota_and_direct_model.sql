-- DeepCoffee-owned AI quota.
-- Run before deploying the direct model gateway version.

CREATE TABLE IF NOT EXISTS user_ai_quota_settings (
    user_id VARCHAR PRIMARY KEY REFERENCES user_profiles(id) ON DELETE CASCADE,
    monthly_limit INTEGER,
    updated_by VARCHAR REFERENCES user_profiles(id) ON DELETE SET NULL,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_usage_adjustments (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT,
    actor_id VARCHAR REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS user_ai_quota_settings_updated_by_idx
    ON user_ai_quota_settings(updated_by);

CREATE INDEX IF NOT EXISTS ai_usage_adjustments_user_period_idx
    ON ai_usage_adjustments(user_id, period_start, period_end);

DROP TABLE IF EXISTS newapi_billing_links;
