-- Migration 012: Engagement Automation Tables
-- Auto-like, comment, follow, comment mining, and brand monitoring schema.

CREATE TABLE IF NOT EXISTS engagement_runs (
    id              SERIAL PRIMARY KEY,
    platform        VARCHAR(50) NOT NULL,
    mode            VARCHAR(20) NOT NULL DEFAULT 'light',
    actions_count   INTEGER DEFAULT 0,
    details         JSONB DEFAULT '[]',
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_engagement_runs_platform
    ON engagement_runs(platform, created_at DESC);

CREATE TABLE IF NOT EXISTS engagement_tasks (
    id              SERIAL PRIMARY KEY,
    platform        VARCHAR(50) NOT NULL,
    task_type       VARCHAR(50) NOT NULL,       -- 'like', 'comment', 'follow', 'mine'
    target_url      TEXT,
    target_query    VARCHAR(500),
    status          VARCHAR(30) DEFAULT 'pending', -- pending | running | completed | failed
    priority        INTEGER DEFAULT 0,
    max_actions     INTEGER DEFAULT 10,
    executed_count  INTEGER DEFAULT 0,
    last_run_at     TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_engagement_tasks_status
    ON engagement_tasks(status, priority DESC);

CREATE TABLE IF NOT EXISTS comment_analytics (
    id              SERIAL PRIMARY KEY,
    platform        VARCHAR(50) NOT NULL,
    content_url     TEXT,
    comment_text    TEXT,
    signal_types    JSONB DEFAULT '[]',
    signal_score    INTEGER DEFAULT 0,
    mined_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comment_analytics_platform
    ON comment_analytics(platform, mined_at DESC);
