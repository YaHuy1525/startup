-- Migration 007: last30days research ingest + DeerFlow support

ALTER TABLE trend_intel
    ADD COLUMN IF NOT EXISTS source_engine VARCHAR(50),
    ADD COLUMN IF NOT EXISTS research_summary TEXT,
    ADD COLUMN IF NOT EXISTS confidence DECIMAL(5,4),
    ADD COLUMN IF NOT EXISTS channel_candidates JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS hashtag_candidates TEXT[] DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS evidence_urls JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS raw_research_ref TEXT,
    ADD COLUMN IF NOT EXISTS last_researched_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS trend_research_runs (
    id              SERIAL PRIMARY KEY,
    source_engine   VARCHAR(50)  NOT NULL DEFAULT 'last30days',
    query           TEXT         NOT NULL,
    region          VARCHAR(10)  DEFAULT 'US',
    status          VARCHAR(20)  NOT NULL DEFAULT 'started',
    result_count    INTEGER      NOT NULL DEFAULT 0,
    confidence      DECIMAL(5,4),
    parsed_summary  TEXT,
    raw_output      TEXT,
    raw_output_path TEXT,
    error_message   TEXT,
    started_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trend_research_runs_status
    ON trend_research_runs(status, started_at DESC);

ALTER TABLE arbitrage_assets
    ADD COLUMN IF NOT EXISTS source_query TEXT,
    ADD COLUMN IF NOT EXISTS source_channel_id VARCHAR(128),
    ADD COLUMN IF NOT EXISTS source_hashtags TEXT[] DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS selection_reason TEXT,
    ADD COLUMN IF NOT EXISTS research_run_id INTEGER REFERENCES trend_research_runs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_assets_research_run
    ON arbitrage_assets(research_run_id);
