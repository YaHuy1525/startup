-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 011 — Finance Category + Referral Platform Registry
-- Implements the @mini.money.matters affiliate strategy onto the Genesis pipeline.
-- ─────────────────────────────────────────────────────────────────────────────

-- ─── 1. Finance Genesis Category ─────────────────────────────────────────────
-- Seeds a new "finance" category so genesis_discover.py crawls GPT/passive-income
-- subreddits and TikTok hashtags automatically on every 6h research cycle.

INSERT INTO genesis_categories (
    slug,
    display_name,
    is_active,
    subreddits,
    tiktok_hashtags,
    hackernews
) VALUES (
    'finance',
    'Side Hustle & Passive Income',
    true,
    ARRAY[
        'beermoney',
        'passive_income',
        'moneysideoflife',
        'swagbucks',
        'beermoneyglobal',
        'WorkOnline',
        'digitalnomad',
        'financialindependence'
    ],
    ARRAY[
        'passiveincome',
        'sidehustle',
        'honeygain',
        'swagbucks',
        'makemoney',
        'beermoney',
        'attapoll',
        'moneytok',
        'earnmoney',
        'workfromhome',
        'sidehustleideas',
        'microinvesting'
    ],
    false
) ON CONFLICT (slug) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    is_active       = EXCLUDED.is_active,
    subreddits      = EXCLUDED.subreddits,
    tiktok_hashtags = EXCLUDED.tiktok_hashtags,
    hackernews      = EXCLUDED.hackernews;


-- ─── 2. Referral Platform Registry ───────────────────────────────────────────
-- Central table for all affiliate/referral platforms you promote.
-- The brief generator reads this table to embed your actual referral URLs
-- inside every AI-generated caption.

CREATE TABLE IF NOT EXISTS referral_platforms (
    id                   SERIAL PRIMARY KEY,
    slug                 TEXT UNIQUE NOT NULL,        -- machine key: 'honeygain'
    display_name         TEXT NOT NULL,               -- human label: 'Honeygain'
    referral_url         TEXT NOT NULL DEFAULT '',    -- your actual ref link
    tier                 INTEGER DEFAULT 2            -- 1=top earner, 2=mid, 3=low
                         CHECK (tier BETWEEN 1 AND 3),
    category             TEXT DEFAULT 'passive'       -- 'passive'|'survey'|'gpt'|'banking'|'invest'
                         CHECK (category IN ('passive','survey','gpt','banking','invest','crypto')),
    monthly_payout_usd   NUMERIC(10,2) DEFAULT 0,    -- manually updated weekly
    signup_bonus_usd     NUMERIC(8,2) DEFAULT 0,     -- bonus earned per referral
    notes                TEXT DEFAULT '',
    is_active            BOOLEAN DEFAULT true,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_referral_tier     ON referral_platforms(tier, is_active);
CREATE INDEX IF NOT EXISTS idx_referral_category ON referral_platforms(category);

-- ─── 3. Earnings Snapshots ────────────────────────────────────────────────────
-- Populated by earnings_proof_ingest.py watching data/earnings_screenshots/.
-- Each row = one payout proof screenshot (used to auto-generate weekly recap posts).

CREATE TABLE IF NOT EXISTS earnings_snapshots (
    id               SERIAL PRIMARY KEY,
    platform_slug    TEXT REFERENCES referral_platforms(slug) ON DELETE SET NULL,
    amount_usd       NUMERIC(10,2) NOT NULL,
    screenshot_path  TEXT NOT NULL,              -- absolute path inside container
    week_iso         TEXT NOT NULL,              -- e.g. '2026-W19'
    notes            TEXT DEFAULT '',
    brief_generated  BOOLEAN DEFAULT false,      -- true once recap brief is created
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_week   ON earnings_snapshots(week_iso);
CREATE INDEX IF NOT EXISTS idx_snapshots_slug   ON earnings_snapshots(platform_slug);

-- ─── 4. Seed: default referral platforms (fill referral_url with your real links)
-- Replace 'YOUR_REF_ID' with your actual referral codes.

INSERT INTO referral_platforms (slug, display_name, referral_url, tier, category, signup_bonus_usd, notes) VALUES
    ('honeygain',   'Honeygain',     'https://join.honeygain.com/HUYTR78E72', 1, 'passive',  5.00, 'Sells unused bandwidth. Set and forget.'),
    ('chime',       'Chime',         'https://chime.com/r/YOUR_REF_ID',    1, 'banking', 50.00, 'Banking referral. $50+ bonus per signup.'),
    ('swagbucks',   'Swagbucks',     'https://swagbucks.com/?cmd=sb-register&rb=YOUR_REF_ID', 1, 'gpt', 3.00, 'Largest GPT platform. Very well known.'),
    ('attapoll',    'Attapoll',      'https://attapoll.app/join/YOUR_REF_ID', 2, 'survey', 0.50, 'Survey app. Easy to screenshot dashboards.'),
    ('pawns',       'Pawns App',     'https://pawns.app/?r=YOUR_REF_ID',   2, 'passive',  2.00, 'Bandwidth + surveys combo.'),
    ('gemsloot',    'Gemsloot',      'https://gemsloot.com/r/YOUR_REF_ID', 2, 'gpt',     1.00, 'Offerwall rewards.'),
    ('earnapp',     'Earn App',      'https://earnapp.com/i/YOUR_REF_ID',  2, 'passive',  1.00, 'Passive bandwidth sharing.'),
    ('repocket',    'Repocket',      'https://repocket.co/?rp=YOUR_REF_ID',2, 'passive',  1.00, 'Bandwidth monetization.'),
    ('jumptask',    'JumpTask',      'https://app.jumptask.io/r/YOUR_REF_ID', 2, 'gpt', 1.00, 'Micro-task platform.'),
    ('robinhood',   'Robinhood',     'https://join.robinhood.com/YOUR_REF_ID', 1, 'invest', 5.00, 'Stock investing. Central to the story arc.'),
    ('kryptex',     'Kryptex',       'https://www.kryptex.com/?ref=YOUR_REF_ID', 3, 'crypto', 0.50, 'GPU crypto mining. GPU required.')
ON CONFLICT (slug) DO NOTHING;
