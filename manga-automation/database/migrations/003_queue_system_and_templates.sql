-- Migration 003: Queue system and content templates
-- Implements queue-based chapter posting, hashtag system, caption templates, and video templates
-- Safe to re-run with IF NOT EXISTS semantics

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Chapter Posting Queue
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chapter_posting_queue (
    id SERIAL PRIMARY KEY,
    manga_id INTEGER NOT NULL REFERENCES manga(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES manga_chapters(id) ON DELETE CASCADE,
    chapter_number TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    scheduled_for TIMESTAMP,
    posted_at TIMESTAMP,
    video_id INTEGER REFERENCES videos(id) ON DELETE SET NULL,
    part_number INTEGER DEFAULT 1,
    total_parts INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_chapter_part UNIQUE(chapter_id, part_number)
);

-- Indexes for queue performance
CREATE INDEX IF NOT EXISTS idx_queue_status_priority 
    ON chapter_posting_queue(status, priority DESC, chapter_number ASC);
CREATE INDEX IF NOT EXISTS idx_queue_manga 
    ON chapter_posting_queue(manga_id);
CREATE INDEX IF NOT EXISTS idx_queue_scheduled 
    ON chapter_posting_queue(scheduled_for) WHERE status = 'pending';

COMMENT ON TABLE chapter_posting_queue IS
    'Queue system for systematic chapter posting in chronological order';
COMMENT ON COLUMN chapter_posting_queue.priority IS
    'Higher priority chapters post first (manual selections use 100, automatic use 0)';
COMMENT ON COLUMN chapter_posting_queue.status IS
    'pending | processing | posted | failed';
COMMENT ON COLUMN chapter_posting_queue.part_number IS
    'For split chapters: which part this is (1, 2, 3, etc.)';
COMMENT ON COLUMN chapter_posting_queue.total_parts IS
    'For split chapters: total number of parts';

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Extend manga_chapters table
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE manga_chapters
    ADD COLUMN IF NOT EXISTS posted BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS post_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_panels INTEGER,
    ADD COLUMN IF NOT EXISTS analyzed BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_chapters_posted ON manga_chapters(posted);

COMMENT ON COLUMN manga_chapters.posted IS
    'Whether this chapter has been posted to prevent duplicate posting';
COMMENT ON COLUMN manga_chapters.post_count IS
    'Number of times this chapter has been posted (for split chapters)';
COMMENT ON COLUMN manga_chapters.total_panels IS
    'Total number of panels in this chapter';
COMMENT ON COLUMN manga_chapters.analyzed IS
    'Whether this chapter has been analyzed for video splitting';

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Hashtags table
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hashtags (
    id SERIAL PRIMARY KEY,
    tag VARCHAR(100) UNIQUE NOT NULL,
    tier INTEGER NOT NULL,
    category VARCHAR(50),
    views_estimate BIGINT,
    usage_count INTEGER DEFAULT 0,
    avg_views DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hashtags_tier ON hashtags(tier);
CREATE INDEX IF NOT EXISTS idx_hashtags_category ON hashtags(category);

COMMENT ON TABLE hashtags IS
    'Strategic hashtag library with tiered reach classification';
COMMENT ON COLUMN hashtags.tier IS
    '1=mega (#fyp), 2=core (#manga), 3=niche (#shonen), 4=specific (#onepiece)';
COMMENT ON COLUMN hashtags.category IS
    'Content category: action, romance, comedy, drama, fantasy, general';

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Caption templates table
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS caption_templates (
    id SERIAL PRIMARY KEY,
    formula_type VARCHAR(50) NOT NULL,
    template TEXT NOT NULL,
    emoji_suggestions TEXT[],
    usage_count INTEGER DEFAULT 0,
    avg_engagement DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_captions_formula ON caption_templates(formula_type);

COMMENT ON TABLE caption_templates IS
    'Viral caption formulas with template variables and emoji suggestions';
COMMENT ON COLUMN caption_templates.formula_type IS
    'emotional_hook | question | relatable | recommendation | statement_emoji';
COMMENT ON COLUMN caption_templates.template IS
    'Template with variables: {manga}, {chapter}, {genre}, {emotion}';

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Video templates table
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS video_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    panel_duration INTEGER DEFAULT 4,
    transition_type VARCHAR(50) DEFAULT 'crossfade',
    transition_duration DECIMAL(3,2) DEFAULT 0.5,
    effects_config JSONB,
    usage_count INTEGER DEFAULT 0,
    avg_views DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE video_templates IS
    'Video style templates with effect configurations for Remotion';
COMMENT ON COLUMN video_templates.type IS
    'emotional_scene | character_edit | recommendation | top_list | panel_appreciation';
COMMENT ON COLUMN video_templates.panel_duration IS
    'Seconds per panel';
COMMENT ON COLUMN video_templates.effects_config IS
    'JSON config: {zoomIntensity, panDirection, colorGrading, overlayEffects}';

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Video performance tracking table
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS video_performance (
    id SERIAL PRIMARY KEY,
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    watch_time_avg DECIMAL(5,2),
    retention_rate DECIMAL(5,2),
    caption_formula VARCHAR(50),
    hashtags TEXT[],
    template_id INTEGER REFERENCES video_templates(id) ON DELETE SET NULL,
    fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_performance_video ON video_performance(video_id);
CREATE INDEX IF NOT EXISTS idx_performance_template ON video_performance(template_id);

COMMENT ON TABLE video_performance IS
    'Performance metrics for analyzing what content performs best';

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. Seed Data: Hashtags
-- ─────────────────────────────────────────────────────────────────────────────

-- Mega hashtags (tier 1)
INSERT INTO hashtags (tag, tier, category, views_estimate) VALUES
('#fyp', 1, 'general', 1000000000000),
('#foryou', 1, 'general', 900000000000),
('#foryoupage', 1, 'general', 800000000000)
ON CONFLICT (tag) DO NOTHING;

-- Core hashtags (tier 2)
INSERT INTO hashtags (tag, tier, category, views_estimate) VALUES
('#manga', 2, 'general', 50000000000),
('#anime', 2, 'general', 100000000000),
('#animetiktok', 2, 'general', 30000000000),
('#mangarecommendation', 2, 'general', 5000000000)
ON CONFLICT (tag) DO NOTHING;

-- Niche hashtags (tier 3)
INSERT INTO hashtags (tag, tier, category, views_estimate) VALUES
('#shonen', 3, 'action', 10000000000),
('#shoujo', 3, 'romance', 5000000000),
('#seinen', 3, 'action', 3000000000),
('#mangareview', 3, 'general', 2000000000),
('#mangaedit', 3, 'general', 4000000000),
('#isekai', 3, 'fantasy', 8000000000),
('#romance', 3, 'romance', 6000000000),
('#action', 3, 'action', 7000000000),
('#comedy', 3, 'comedy', 5000000000),
('#drama', 3, 'drama', 4000000000)
ON CONFLICT (tag) DO NOTHING;

-- Specific hashtags (tier 4)
INSERT INTO hashtags (tag, tier, category, views_estimate) VALUES
('#onepiece', 4, 'action', 15000000000),
('#naruto', 4, 'action', 12000000000),
('#attackontitan', 4, 'action', 10000000000),
('#demonslayer', 4, 'action', 11000000000),
('#myheroacademia', 4, 'action', 9000000000),
('#jujutsukaisen', 4, 'action', 13000000000),
('#chainsawman', 4, 'action', 8000000000),
('#tokyoghoul', 4, 'action', 7000000000),
('#berserk', 4, 'action', 5000000000),
('#vinlandsaga', 4, 'action', 4000000000)
ON CONFLICT (tag) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 8. Seed Data: Caption Templates
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO caption_templates (formula_type, template, emoji_suggestions) VALUES
('emotional_hook', 'This scene from {manga} broke me', ARRAY['💔', '😭', '😢']),
('emotional_hook', '{manga} chapter {chapter} hit different', ARRAY['😭', '💔', '🥺']),
('emotional_hook', 'I wasn''t ready for this {manga} moment', ARRAY['😭', '💔', '😱']),
('question', 'Who''s your favorite character in {manga}?', ARRAY['🤔', '❤️', '👇']),
('question', 'Have you read {manga} yet?', ARRAY['📚', '🤔', '👀']),
('question', 'What did you think of {manga} chapter {chapter}?', ARRAY['🤔', '💭', '👇']),
('relatable', 'POV: You just finished {manga} chapter {chapter}', ARRAY['😱', '🤯', '😭']),
('relatable', 'When you realize {manga} is peak fiction', ARRAY['🔥', '💯', '😤']),
('relatable', 'Me after reading {manga}', ARRAY['😭', '🥺', '💔']),
('recommendation', 'You NEED to read {manga}', ARRAY['🔥', '📚', '💯']),
('recommendation', '{manga} is criminally underrated', ARRAY['😤', '🔥', '📖']),
('recommendation', 'If you haven''t read {manga}, what are you doing?', ARRAY['📚', '🔥', '👀']),
('statement_emoji', '{manga} chapter {chapter} is insane', ARRAY['🔥', '💯', '😱']),
('statement_emoji', '{manga} never misses', ARRAY['🔥', '💯', '👑']),
('statement_emoji', 'This is why {manga} is the best', ARRAY['🔥', '💯', '😤'])
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 9. Seed Data: Video Templates
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO video_templates (name, type, panel_duration, transition_type, transition_duration, effects_config) VALUES
('Emotional Scene', 'emotional_scene', 5, 'crossfade', 0.5, 
 '{"zoomIntensity": 1.15, "panDirection": "random", "colorGrading": "desaturated"}'::jsonb),
('Character Edit', 'character_edit', 3, 'slide', 0.3, 
 '{"zoomIntensity": 1.3, "panDirection": "left-to-right", "overlayEffects": ["vignette"]}'::jsonb),
('Manga Recommendation', 'recommendation', 4, 'zoom', 0.4, 
 '{"zoomIntensity": 1.2, "panDirection": "top-to-bottom"}'::jsonb),
('Panel Appreciation', 'panel_appreciation', 8, 'zoom', 0.5, 
 '{"zoomIntensity": 1.4, "panDirection": "random"}'::jsonb),
('Fast Paced Action', 'character_edit', 2, 'wipe', 0.2, 
 '{"zoomIntensity": 1.25, "panDirection": "random", "overlayEffects": ["motion_blur"]}'::jsonb)
ON CONFLICT DO NOTHING;
