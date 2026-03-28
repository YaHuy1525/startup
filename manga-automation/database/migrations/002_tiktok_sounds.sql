-- Migration 002: TikTok native sound support
-- Run once against your Supabase (or local) database.
-- Safe to re-run.

-- New columns on selected_panels
ALTER TABLE selected_panels
    ADD COLUMN IF NOT EXISTS tiktok_sound_id    TEXT,
    ADD COLUMN IF NOT EXISTS tiktok_sound_title TEXT;

-- New table
CREATE TABLE IF NOT EXISTS tiktok_sounds (
    id              SERIAL PRIMARY KEY,
    tiktok_id       TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    author          TEXT,
    duration_secs   INTEGER,
    emotion_tags    TEXT[]  DEFAULT '{}',
    use_count       INTEGER DEFAULT 0,
    trending_rank   INTEGER,
    is_active       BOOLEAN DEFAULT true,
    last_fetched_at TIMESTAMP DEFAULT NOW(),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Helpful index for emotion-based queries
CREATE INDEX IF NOT EXISTS idx_tiktok_sounds_emotion
    ON tiktok_sounds USING GIN (emotion_tags);

-- Seed: well-known anime / manga sounds
INSERT INTO tiktok_sounds (tiktok_id, title, author, duration_secs, emotion_tags, trending_rank) VALUES
  ('7206621854882285338', 'Oshi no Ko - Idol',               'YOASOBI',              276, ARRAY['epic','romantic'],       1),
  ('7194953577049161498', 'Jujutsu Kaisen - Opening',        'King Gnu',              90, ARRAY['epic','shocking'],       2),
  ('7170843636893876226', 'Attack on Titan - Rumbling',      'SiM',                  213, ARRAY['epic','shocking'],       3),
  ('7198436698019870977', 'Spy x Family Theme',              'Official HIGE DANdism', 60, ARRAY['funny','neutral'],       4),
  ('7156501411041896218', 'Vinland Saga - If I Could',       'Milet',                 60, ARRAY['sad','romantic'],        5),
  ('7244633643504458501', 'Demon Slayer Kimetsu no Yaiba',   'LiSA',                  90, ARRAY['epic','sad'],            6),
  ('7210494319685453570', 'Haikyuu!! - Fly High',            'BURNOUT SYNDROMES',     90, ARRAY['epic','funny'],          7),
  ('7225049088948419330', 'Chainsaw Man - Kick Back',        'Kenshi Yonezu',         90, ARRAY['shocking','funny'],      8),
  ('7182461478285477634', 'One Piece - We Are!',             'Hiroshi Kitadani',      90, ARRAY['epic','neutral'],        9),
  ('7167022578890450178', 'Violet Evergarden OST',           'Evan Call',             90, ARRAY['sad','romantic'],       10)
ON CONFLICT (tiktok_id) DO NOTHING;
