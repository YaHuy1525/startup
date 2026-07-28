-- Anime Theory pipeline run history (Supabase / Postgres)
-- Tracks topic → render → caption → publish for dashboard + Hermes.

CREATE TABLE IF NOT EXISTS anime_theory_runs (
    id              SERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,
    title           TEXT,
    anime           TEXT,
    context         TEXT,
    file_path       TEXT,
    public_url      TEXT,
    cover_url       TEXT,
    thumbnail_path  TEXT,
    caption         TEXT,
    hashtags        TEXT[],
    scene_count     INTEGER,
    scenes          JSONB,
    size_mb         DECIMAL(10,2),
    duration_secs   DECIMAL(10,2),
    video_id        INTEGER REFERENCES videos(id) ON DELETE SET NULL,
    workflow_id     TEXT,
    publish_ok      BOOLEAN,
    published_count INTEGER DEFAULT 0,
    failed_count    INTEGER DEFAULT 0,
    publish_result  JSONB,
    channels        TEXT[],
    status          VARCHAR(50) DEFAULT 'ready',
    -- ready | rendered | published | failed | dry_run
    error           TEXT,
    dry_run         BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anime_theory_runs_created
    ON anime_theory_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_anime_theory_runs_status
    ON anime_theory_runs(status);
CREATE INDEX IF NOT EXISTS idx_anime_theory_runs_anime
    ON anime_theory_runs(anime);

COMMENT ON TABLE anime_theory_runs IS
    'Anime-theory Shorts pipeline runs (script → Remotion → caption → AiToEarn)';
