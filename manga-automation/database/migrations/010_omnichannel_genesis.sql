-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 010: Omnichannel Genesis — Trending Discovery & Multi-Platform
-- Adds tables for cross-category trend discovery (Pod 0) and multi-platform
-- distribution tracking (Pods 1-5).
-- ─────────────────────────────────────────────────────────────────────────────

-- Categories the Genesis Agent tracks (fiction, tech, movies, art, etc.)
CREATE TABLE IF NOT EXISTS genesis_categories (
    id              SERIAL PRIMARY KEY,
    slug            VARCHAR(50) UNIQUE NOT NULL,  -- 'fiction', 'tech', 'movies', 'art', 'tiktok_trending'
    display_name    VARCHAR(100) NOT NULL,
    subreddits      TEXT[] DEFAULT '{}',           -- r/ subs to crawl for this category
    hackernews      BOOLEAN DEFAULT false,         -- whether to crawl HN for this category
    tiktok_hashtags TEXT[] DEFAULT '{}',           -- seed hashtags to monitor on TikTok
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Raw scraped signals before LLM evaluation
CREATE TABLE IF NOT EXISTS genesis_signals (
    id              SERIAL PRIMARY KEY,
    category_id     INTEGER REFERENCES genesis_categories(id) ON DELETE CASCADE,
    source_platform VARCHAR(50) NOT NULL,          -- 'reddit', 'hackernews', 'tiktok', 'x'
    source_url      TEXT,
    title           TEXT NOT NULL,
    body_preview    TEXT,                           -- first 500 chars of the post/comment
    score           INTEGER DEFAULT 0,             -- upvotes, points, likes
    comment_count   INTEGER DEFAULT 0,
    velocity_score  DECIMAL(10,4) DEFAULT 0,       -- score / hours_since_post
    scraped_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (source_platform, source_url)
);

CREATE INDEX IF NOT EXISTS idx_genesis_signals_cat    ON genesis_signals(category_id, scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_genesis_signals_vel    ON genesis_signals(velocity_score DESC);

-- LLM-evaluated content briefs (output of Pod 0)
CREATE TABLE IF NOT EXISTS content_briefs (
    id                  SERIAL PRIMARY KEY,
    category_id         INTEGER REFERENCES genesis_categories(id),
    trend_name          VARCHAR(255) NOT NULL,
    viral_hook          TEXT,
    target_audience     VARCHAR(255),
    suggested_monetization VARCHAR(255),
    base_narrative      TEXT NOT NULL,              -- 500-word core story / breakdown
    virality_score      INTEGER DEFAULT 0,          -- 0-100 LLM-assigned
    status              VARCHAR(30) DEFAULT 'draft', -- draft | approved | producing | distributed
    source_signal_ids   INTEGER[] DEFAULT '{}',     -- genesis_signals.id array
    created_at          TIMESTAMP DEFAULT NOW(),
    approved_at         TIMESTAMP,
    produced_at         TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_briefs_status ON content_briefs(status, virality_score DESC);

-- Master assets: the generated content before platform-specific mutation
CREATE TABLE IF NOT EXISTS master_assets (
    id              SERIAL PRIMARY KEY,
    brief_id        INTEGER REFERENCES content_briefs(id) ON DELETE SET NULL,
    category        VARCHAR(100),
    title           VARCHAR(500),
    base_script     TEXT,
    base_video_path VARCHAR(500),
    base_audio_path VARCHAR(500),
    thumbnail_path  VARCHAR(500),
    status          VARCHAR(50) DEFAULT 'raw',     -- raw | processing | ready | archived
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_master_assets_status ON master_assets(status);

-- Per-platform distribution tracking
CREATE TABLE IF NOT EXISTS platform_distributions (
    id                  SERIAL PRIMARY KEY,
    master_asset_id     INTEGER REFERENCES master_assets(id) ON DELETE CASCADE,
    platform            VARCHAR(100) NOT NULL,      -- 'tiktok', 'youtube', 'substack', 'etsy', etc.
    format              VARCHAR(50) NOT NULL,        -- 'short_video', 'article', 'audio', 'digital_product'
    localized_content   JSONB,                       -- platform-specific titles, tags, translations
    target_url          VARCHAR(1000),               -- URL once published
    monetization_vector VARCHAR(255),                -- affiliate link or product ID used
    status              VARCHAR(50) DEFAULT 'pending', -- pending | scheduled | published | failed
    error_log           TEXT,
    scheduled_for       TIMESTAMP,
    published_at        TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (master_asset_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_plat_dist_status ON platform_distributions(status);
CREATE INDEX IF NOT EXISTS idx_plat_dist_platform ON platform_distributions(platform);

-- Digital products generated for Gumroad/Etsy/Redbubble/etc.
CREATE TABLE IF NOT EXISTS digital_products (
    id              SERIAL PRIMARY KEY,
    master_asset_id INTEGER REFERENCES master_assets(id) ON DELETE SET NULL,
    product_type    VARCHAR(100),                   -- 'pdf_guide', 'procreate_brush', 'tshirt_design'
    title           VARCHAR(500),
    file_path       VARCHAR(500),
    price_usd       DECIMAL(10,2),
    japanese_title  VARCHAR(500),
    japanese_desc   TEXT,
    listing_url     VARCHAR(1000),
    platform        VARCHAR(100),                   -- 'gumroad', 'etsy', 'redbubble', 'booth_pm'
    status          VARCHAR(50) DEFAULT 'draft',    -- draft | listed | sold
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Extend trend_intel with category linkage
ALTER TABLE trend_intel
    ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES genesis_categories(id),
    ADD COLUMN IF NOT EXISTS brief_id    INTEGER REFERENCES content_briefs(id);

-- ─── Seed: Default categories ────────────────────────────────────────────────
INSERT INTO genesis_categories (slug, display_name, subreddits, hackernews, tiktok_hashtags) VALUES
  ('fiction',          'Fiction & Stories',     ARRAY['writingprompts','nosleep','shortstories','HFY'],           false, ARRAY['booktok','storytime','fiction']),
  ('tiktok_trending',  'TikTok Trending',      ARRAY['tiktok','TikTokCringe','TikTokNude'],                     false, ARRAY['fyp','viral','trending']),
  ('tech',            'Technology & AI',        ARRAY['technology','artificial','MachineLearning','programming'], true,  ARRAY['tech','ai','coding']),
  ('movies',          'Movies & TV',            ARRAY['movies','television','MovieDetails','marvelstudios'],      false, ARRAY['movietok','film','cinema']),
  ('art',             'Digital Art & Design',   ARRAY['digitalart','Art','DigitalPainting','ImaginaryWorlds'],    false, ARRAY['digitalart','arttok','aiart']),
  ('anime',           'Anime & Manga',          ARRAY['anime','manga','OnePiece','JuJutsuKaisen'],               false, ARRAY['anime','manga','otaku']),
  ('gaming',          'Gaming',                 ARRAY['gaming','Games','pcgaming','IndieGaming'],                 false, ARRAY['gaming','gamer','esports']),
  ('finance',         'Finance & Business',     ARRAY['wallstreetbets','investing','Entrepreneur','startups'],    true,  ARRAY['moneytok','investing','finance'])
ON CONFLICT (slug) DO NOTHING;
