-- ─────────────────────────────────────────────────────────────────────────────
-- Manga Automation System - PostgreSQL Schema
-- ─────────────────────────────────────────────────────────────────────────────

-- Manga series tracking
CREATE TABLE IF NOT EXISTS manga (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(500) NOT NULL UNIQUE,
    title_ja        VARCHAR(500),
    mal_id          INTEGER,
    anilist_id      INTEGER,
    mangadex_id     VARCHAR(100),
    genre           VARCHAR(200),
    tags            TEXT[],
    status          VARCHAR(50),   -- 'ongoing' | 'completed' | 'hiatus'
    trending_score  DECIMAL(10,2) DEFAULT 0,
    is_active       BOOLEAN DEFAULT true,
    added_at        TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Fetched chapters
CREATE TABLE IF NOT EXISTS manga_chapters (
    id              SERIAL PRIMARY KEY,
    manga_id        INTEGER REFERENCES manga(id) ON DELETE CASCADE,
    chapter_number  VARCHAR(20),
    chapter_title   VARCHAR(500),
    mangadex_id     VARCHAR(100) UNIQUE,
    source_url      TEXT,
    panel_urls      JSONB NOT NULL DEFAULT '[]',   -- Array of remote image URLs
    local_paths     JSONB DEFAULT '[]',             -- Downloaded local file paths
    scraped_at      TIMESTAMP DEFAULT NOW(),
    processed       BOOLEAN DEFAULT false
);

-- Panel hash tracking (duplicate prevention)
CREATE TABLE IF NOT EXISTS panel_hashes (
    id              SERIAL PRIMARY KEY,
    panel_hash      VARCHAR(64) UNIQUE NOT NULL,
    manga_id        INTEGER REFERENCES manga(id),
    chapter_id      INTEGER REFERENCES manga_chapters(id),
    panel_index     INTEGER,
    first_used_at   TIMESTAMP DEFAULT NOW(),
    times_used      INTEGER DEFAULT 1
);

-- AI-selected panels for content
CREATE TABLE IF NOT EXISTS selected_panels (
    id                SERIAL PRIMARY KEY,
    chapter_id        INTEGER REFERENCES manga_chapters(id) ON DELETE CASCADE,
    panels            JSONB NOT NULL,   -- [{index, url, score, reasoning, emotion, dialogue}]
    selection_score   DECIMAL(5,2),     -- Average score of selected panels
    music_path        TEXT,             -- Absolute path to a local audio file (fallback)
    tiktok_sound_id   TEXT,             -- TikTok sound ID to apply on publish
    tiktok_sound_title TEXT,            -- Human-readable title for the chosen sound
    selected_at       TIMESTAMP DEFAULT NOW()
);

-- ─── TikTok Sound Catalogue ──────────────────────────────────────────────────
-- Populated by scripts/fetch_tiktok_sounds.py.
-- The MusicSelector agent queries this table to pick the best sound per upload.
CREATE TABLE IF NOT EXISTS tiktok_sounds (
    id              SERIAL PRIMARY KEY,
    tiktok_id       TEXT UNIQUE NOT NULL,   -- TikTok's numeric sound ID (string)
    title           TEXT NOT NULL,
    author          TEXT,
    duration_secs   INTEGER,
    emotion_tags    TEXT[]  DEFAULT '{}',   -- ['epic','action','intense'] etc.
    use_count       INTEGER DEFAULT 0,      -- how many times we've applied this sound
    trending_rank   INTEGER,                -- lower = more trending (1 is best)
    is_active       BOOLEAN DEFAULT true,
    last_fetched_at TIMESTAMP DEFAULT NOW(),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Generated videos ready for publication
CREATE TABLE IF NOT EXISTS videos (
    id              SERIAL PRIMARY KEY,
    chapter_id      INTEGER REFERENCES manga_chapters(id) ON DELETE CASCADE,
    file_path       TEXT NOT NULL,
    thumbnail_path  TEXT,
    duration_secs   DECIMAL(5,2),
    file_size_mb    DECIMAL(8,2),
    caption         TEXT,
    hashtags        TEXT[],
    status          VARCHAR(50) DEFAULT 'ready',  -- 'ready' | 'publishing' | 'published' | 'failed'
    created_at      TIMESTAMP DEFAULT NOW()
);

-- TikTok accounts
CREATE TABLE IF NOT EXISTS tiktok_accounts (
    id                      SERIAL PRIMARY KEY,
    username                VARCHAR(100) NOT NULL UNIQUE,
    account_status          VARCHAR(50) DEFAULT 'active',  -- 'active' | 'paused' | 'banned'
    cookies_file            TEXT,
    access_token            TEXT,
    shadow_banned           BOOLEAN DEFAULT false,
    shadow_ban_detected_at  TIMESTAMP,
    upload_failures         INTEGER DEFAULT 0,
    last_post_at            TIMESTAMP,
    total_posts             INTEGER DEFAULT 0,
    created_at              TIMESTAMP DEFAULT NOW()
);

-- Instagram accounts
CREATE TABLE IF NOT EXISTS instagram_accounts (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100) NOT NULL UNIQUE,
    ig_user_id      VARCHAR(100),
    access_token    TEXT,
    account_status  VARCHAR(50) DEFAULT 'active',
    last_post_at    TIMESTAMP,
    total_posts     INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Published content tracking
CREATE TABLE IF NOT EXISTS published_videos (
    id                   SERIAL PRIMARY KEY,
    video_id             INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    account_id           INTEGER,
    platform             VARCHAR(50) NOT NULL,   -- 'tiktok' | 'instagram' | 'youtube'
    account_name         VARCHAR(100),
    platform_post_id     VARCHAR(200),
    platform_url         TEXT,
    tiktok_video_id      VARCHAR(200),
    tiktok_url           TEXT,
    instagram_media_id   VARCHAR(200),
    instagram_url        TEXT,
    caption              TEXT,
    hashtags             TEXT[],
    status               VARCHAR(50) DEFAULT 'published',
    published_at         TIMESTAMP DEFAULT NOW()
);

-- Upload results (detailed per-attempt tracking)
CREATE TABLE IF NOT EXISTS upload_results (
    id              SERIAL PRIMARY KEY,
    video_id        INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    account_id      INTEGER REFERENCES tiktok_accounts(id) ON DELETE CASCADE,
    platform        VARCHAR(20) DEFAULT 'tiktok',
    success         BOOLEAN NOT NULL,
    error_message   TEXT,
    tiktok_post_id  TEXT,
    tiktok_url      TEXT,
    uploaded_at     TIMESTAMP DEFAULT NOW()
);

-- Performance analytics
CREATE TABLE IF NOT EXISTS video_analytics (
    id                  SERIAL PRIMARY KEY,
    published_video_id  INTEGER REFERENCES published_videos(id) ON DELETE CASCADE,
    upload_result_id    INTEGER REFERENCES upload_results(id) ON DELETE SET NULL,
    views               INTEGER DEFAULT 0,
    likes               INTEGER DEFAULT 0,
    comments            INTEGER DEFAULT 0,
    shares              INTEGER DEFAULT 0,
    fyp_views           INTEGER DEFAULT 0,
    following_views     INTEGER DEFAULT 0,
    watch_time_secs     INTEGER DEFAULT 0,
    scraped_at          TIMESTAMP DEFAULT NOW()
);

-- Panel scoring history (for AI learning)
CREATE TABLE IF NOT EXISTS panel_scores (
    id              SERIAL PRIMARY KEY,
    manga_id        INTEGER REFERENCES manga(id),
    emotion_type    VARCHAR(50),  -- 'epic' | 'sad' | 'funny' | 'shocking' | 'romantic'
    avg_views       INTEGER DEFAULT 0,
    sample_count    INTEGER DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (manga_id, emotion_type)
);

-- Shadow ban event log
CREATE TABLE IF NOT EXISTS shadow_ban_events (
    id                SERIAL PRIMARY KEY,
    account_id        INTEGER REFERENCES tiktok_accounts(id),
    detected_at       TIMESTAMP DEFAULT NOW(),
    detection_method  VARCHAR(50),   -- 'fyp_percentage' | 'manual' | 'ai_analysis'
    fyp_percentage    DECIMAL(5,2),
    resolved_at       TIMESTAMP,
    notes             TEXT
);

-- ─── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_manga_trending      ON manga(trending_score DESC);
CREATE INDEX IF NOT EXISTS idx_manga_active        ON manga(is_active);
CREATE INDEX IF NOT EXISTS idx_chapters_processed  ON manga_chapters(processed);
CREATE INDEX IF NOT EXISTS idx_chapters_manga      ON manga_chapters(manga_id);
CREATE INDEX IF NOT EXISTS idx_panel_hash          ON panel_hashes(panel_hash);
CREATE INDEX IF NOT EXISTS idx_videos_status       ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_created      ON videos(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_published_platform  ON published_videos(platform);
CREATE INDEX IF NOT EXISTS idx_analytics_scraped   ON video_analytics(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_tiktok_status       ON tiktok_accounts(account_status);
CREATE INDEX IF NOT EXISTS idx_tiktok_shadow_banned ON tiktok_accounts(shadow_banned);
CREATE INDEX IF NOT EXISTS idx_instagram_status    ON instagram_accounts(account_status);
CREATE INDEX IF NOT EXISTS idx_upload_results_acct ON upload_results(account_id);

-- ─── Seed: Initial popular manga series ──────────────────────────────────────
-- MangaDex-hosted manga (pages accessible without licensing restrictions).
-- Licensed manga (One Piece, Chainsaw Man, etc.) redirect to Viz/Shonen Jump
-- and cannot be scraped via the at-home API.
INSERT INTO manga (title, mangadex_id, genre, tags, status, trending_score) VALUES
  ('Kage no Jitsuryokusha ni Naritakute!', '77bee52c-d2d6-44ad-a33a-1734c1fe696a', 'Action/Comedy/Fantasy',  ARRAY['isekai','op-mc','comedy','action'],    'ongoing',   95.0),
  ('Sono Bisque Doll wa Koi o Suru',       'aa6c76f7-5f5f-46b6-a800-911145f81b9b', 'Romance/Comedy',         ARRAY['romance','cosplay','school','wholesome'],'completed', 92.0),
  ('Berserk',                              '801513ba-a712-498c-8f57-cae55b38cc92', 'Action/Dark Fantasy',    ARRAY['dark','epic','fantasy','violence'],     'ongoing',   90.0),
  ('Vinland Saga',                         'c0ee660b-f9f2-45c3-8068-5123ff53f84a', 'Action/Historical',      ARRAY['vikings','dark','historical','epic'],   'ongoing',   88.0),
  ('Mushoku Tensei',                       'ece3c651-5a0b-47e4-9e5f-ae1773a8dd1c', 'Fantasy/Isekai',         ARRAY['isekai','fantasy','action','adventure'],'ongoing',   86.0),
  ('Dungeon Meshi',                        '53cf1d0d-d616-4ed1-bc73-adfaa5eab47e', 'Fantasy/Comedy',         ARRAY['dungeon','cooking','fantasy','comedy'], 'completed', 84.0),
  ('Blue Lock',                            'b3b1d2c6-c7b4-4cb8-90ce-dfb09be45e98', 'Sports/Action',          ARRAY['soccer','sports','action','shonen'],   'ongoing',   82.0),
  ('Kaiju No. 8',                          '60c84ee1-82bd-4d42-a813-7c2bc3e5b5c4', 'Action/Sci-Fi',          ARRAY['kaiju','action','monster','sci-fi'],   'ongoing',   80.0)
ON CONFLICT (title) DO NOTHING;

-- ─── Seed: Known popular anime / manga TikTok sounds ────────────────────────
-- tiktok_id is the numeric ID visible in TikTok sound URLs.
-- Add more by running scripts/fetch_tiktok_sounds.py or inserting manually.
INSERT INTO tiktok_sounds (tiktok_id, title, author, duration_secs, emotion_tags, trending_rank) VALUES
  ('7206621854882285338', 'Oshi no Ko - Idol',               'YOASOBI',            276, ARRAY['epic','romantic'],         1),
  ('7194953577049161498', 'Jujutsu Kaisen - Opening',        'King Gnu',            90, ARRAY['epic','shocking'],         2),
  ('7170843636893876226', 'Attack on Titan - Rumbling',      'SiM',                213, ARRAY['epic','shocking'],         3),
  ('7198436698019870977', 'Spy x Family Theme',              'Official HIGE DANdism', 60, ARRAY['funny','neutral'],       4),
  ('7156501411041896218', 'Vinland Saga - If I Could',       'Milet',               60, ARRAY['sad','romantic'],         5),
  ('7244633643504458501', 'Demon Slayer Kimetsu no Yaiba',   'LiSA',                90, ARRAY['epic','sad'],             6),
  ('7210494319685453570', 'Haikyuu!! - Fly High',            'BURNOUT SYNDROMES',   90, ARRAY['epic','funny'],           7),
  ('7225049088948419330', 'Chainsaw Man - Kick Back',        'Kenshi Yonezu',       90, ARRAY['shocking','funny'],       8),
  ('7182461478285477634', 'One Piece - We Are!',             'Hiroshi Kitadani',    90, ARRAY['epic','neutral'],         9),
  ('7167022578890450178', 'Violet Evergarden OST',           'Evan Call',           90, ARRAY['sad','romantic'],        10)
ON CONFLICT (tiktok_id) DO NOTHING;

-- ─── Seed: Demo TikTok account ───────────────────────────────────────────────
INSERT INTO tiktok_accounts (username, account_status) VALUES
  ('manga_clips_official', 'active')
ON CONFLICT (username) DO NOTHING;

-- ─── Seed: Demo Instagram account ────────────────────────────────────────────
INSERT INTO instagram_accounts (username, ig_user_id, access_token, account_status) VALUES
  ('manga_clips_official', '0', 'REPLACE_WITH_REAL_TOKEN', 'active')
ON CONFLICT (username) DO NOTHING;
