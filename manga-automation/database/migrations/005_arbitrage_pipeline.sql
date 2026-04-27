-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 005: Autonomous Content Arbitrage Pipeline
-- Adds tables for TikTok trend discovery, YouTube asset sourcing, and
-- multi-platform distribution tracking.
-- ─────────────────────────────────────────────────────────────────────────────

-- Trending hashtags/topics discovered from TikTok Creative Center via Apify
CREATE TABLE IF NOT EXISTS trend_intel (
    id              SERIAL PRIMARY KEY,
    hashtag         VARCHAR(200) NOT NULL,
    region          VARCHAR(10)  DEFAULT 'US',
    avg_views       BIGINT,
    post_count      INTEGER,
    trend_velocity  DECIMAL(10,4),  -- post_count_change * avg_engagement_rate
    source          VARCHAR(50)  DEFAULT 'apify_tiktok',
    status          VARCHAR(20)  DEFAULT 'new',  -- new | sourcing | done | skipped
    discovered_at   TIMESTAMP    DEFAULT NOW(),
    processed_at    TIMESTAMP,
    UNIQUE (hashtag, region)
);

CREATE INDEX IF NOT EXISTS idx_trend_status   ON trend_intel(status, trend_velocity DESC);
CREATE INDEX IF NOT EXISTS idx_trend_hashtag  ON trend_intel(hashtag);

-- YouTube assets sourced for a given trend
CREATE TABLE IF NOT EXISTS arbitrage_assets (
    id              SERIAL PRIMARY KEY,
    trend_id        INTEGER      REFERENCES trend_intel(id) ON DELETE CASCADE,
    youtube_url     TEXT         NOT NULL UNIQUE,
    youtube_title   TEXT,
    youtube_views   BIGINT,
    duration_secs   INTEGER,
    local_path      TEXT,           -- absolute path after yt-dlp download
    file_size_mb    DECIMAL(8,2),
    status          VARCHAR(20)  DEFAULT 'pending',  -- pending | downloaded | distributed | failed
    error_message   TEXT,
    created_at      TIMESTAMP    DEFAULT NOW(),
    updated_at      TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assets_status ON arbitrage_assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_trend  ON arbitrage_assets(trend_id);

-- Per-platform upload results for each asset
CREATE TABLE IF NOT EXISTS arbitrage_uploads (
    id              SERIAL PRIMARY KEY,
    asset_id        INTEGER      REFERENCES arbitrage_assets(id) ON DELETE CASCADE,
    platform        VARCHAR(20)  NOT NULL,  -- tiktok | youtube | instagram
    caption         TEXT,
    hashtags        TEXT[],
    platform_url    TEXT,
    platform_post_id VARCHAR(200),
    status          VARCHAR(20)  DEFAULT 'pending',  -- pending | success | failed
    error_message   TEXT,
    uploaded_at     TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arb_uploads_asset    ON arbitrage_uploads(asset_id);
CREATE INDEX IF NOT EXISTS idx_arb_uploads_platform ON arbitrage_uploads(platform, status);

-- Add arbitrage_videos data directory to volumes tracking
-- (actual directory created via docker-compose volume mount)
