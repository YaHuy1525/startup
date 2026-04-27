-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 009: Monetization Control Plane
-- Adds KPI thresholds, channel configuration, and performance snapshots used
-- by automated decisioning for balanced multi-platform monetization.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS monetization_kpi_thresholds (
    id                  SERIAL PRIMARY KEY,
    metric_key          VARCHAR(80) NOT NULL UNIQUE,
    warn_threshold      NUMERIC(12,4) NOT NULL,
    go_threshold        NUMERIC(12,4) NOT NULL,
    unit                VARCHAR(32) NOT NULL DEFAULT 'ratio',
    evaluation_window   VARCHAR(32) NOT NULL DEFAULT '7d',
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monetization_channel_config (
    id                          SERIAL PRIMARY KEY,
    platform                    VARCHAR(30) NOT NULL UNIQUE,
    enabled                     BOOLEAN NOT NULL DEFAULT TRUE,
    daily_min_posts             INTEGER NOT NULL DEFAULT 0,
    daily_max_posts             INTEGER NOT NULL DEFAULT 0,
    min_delay_minutes           INTEGER NOT NULL DEFAULT 0,
    ad_ratio_denominator        INTEGER NOT NULL DEFAULT 5,
    requires_manual_review      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at                  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monetization_performance_snapshots (
    id                          SERIAL PRIMARY KEY,
    snapshot_date               DATE NOT NULL,
    platform                    VARCHAR(30) NOT NULL,
    metric_key                  VARCHAR(80) NOT NULL,
    metric_value                NUMERIC(14,4) NOT NULL,
    source                      VARCHAR(50) NOT NULL DEFAULT 'automation',
    created_at                  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, platform, metric_key)
);

CREATE TABLE IF NOT EXISTS monetization_alerts (
    id                          SERIAL PRIMARY KEY,
    platform                    VARCHAR(30) NOT NULL,
    metric_key                  VARCHAR(80) NOT NULL,
    severity                    VARCHAR(12) NOT NULL, -- warn | critical
    observed_value              NUMERIC(14,4) NOT NULL,
    threshold_value             NUMERIC(14,4) NOT NULL,
    message                     TEXT NOT NULL,
    created_at                  TIMESTAMP NOT NULL DEFAULT NOW(),
    acknowledged                BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_monetization_snapshots_platform_date
    ON monetization_performance_snapshots(platform, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_monetization_alerts_platform_created
    ON monetization_alerts(platform, created_at DESC);

-- Seed KPI thresholds aligned with balanced plan go/no-go logic.
INSERT INTO monetization_kpi_thresholds (metric_key, warn_threshold, go_threshold, unit, evaluation_window)
VALUES
    ('retention_60s', 0.5500, 0.7000, 'ratio', '7d'),
    ('completion_rate', 0.6500, 0.8000, 'ratio', '7d'),
    ('affiliate_ctr', 0.0080, 0.0150, 'ratio', '7d'),
    ('affiliate_conversion_rate', 0.0100, 0.0200, 'ratio', '7d'),
    ('revenue_per_video_usd', 0.9000, 1.5000, 'usd', '7d'),
    ('upload_success_rate', 0.9200, 0.9700, 'ratio', '7d'),
    ('error_rate', 0.0800, 0.0300, 'inverse_ratio', '7d'),
    ('membership_conversion_rate', 0.0030, 0.0080, 'ratio', '30d'),
    ('high_cpm_content_share', 0.1000, 0.2000, 'ratio', '30d')
ON CONFLICT (metric_key) DO UPDATE SET
    warn_threshold = EXCLUDED.warn_threshold,
    go_threshold = EXCLUDED.go_threshold,
    unit = EXCLUDED.unit,
    evaluation_window = EXCLUDED.evaluation_window,
    updated_at = NOW();

-- Seed channel cadence defaults for balanced strategy.
INSERT INTO monetization_channel_config (
    platform, enabled, daily_min_posts, daily_max_posts, min_delay_minutes, ad_ratio_denominator, requires_manual_review
)
VALUES
    ('tiktok', true, 3, 5, 0, 4, false),
    ('youtube_shorts', true, 2, 3, 30, 6, false),
    ('instagram_reels', true, 1, 2, 60, 6, false),
    ('facebook_reels', true, 1, 1, 90, 8, false),
    ('pinterest', true, 3, 5, 0, 5, false),
    ('youtube_longform', true, 0, 1, 0, 10, true)
ON CONFLICT (platform) DO UPDATE SET
    enabled = EXCLUDED.enabled,
    daily_min_posts = EXCLUDED.daily_min_posts,
    daily_max_posts = EXCLUDED.daily_max_posts,
    min_delay_minutes = EXCLUDED.min_delay_minutes,
    ad_ratio_denominator = EXCLUDED.ad_ratio_denominator,
    requires_manual_review = EXCLUDED.requires_manual_review,
    updated_at = NOW();
