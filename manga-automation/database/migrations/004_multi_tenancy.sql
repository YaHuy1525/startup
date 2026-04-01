-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 004: Multi-Tenancy & SaaS Features
-- ─────────────────────────────────────────────────────────────────────────────
-- This migration adds support for:
-- - Multi-user authentication
-- - Organization-based data isolation
-- - Proxy management for TikTok accounts
-- - Workflow execution tracking
-- - Enhanced analytics

-- ─── Users Table ──────────────────────────────────────────────────────────────
-- Stores user accounts (integrates with Supabase Auth)
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) NOT NULL UNIQUE,
    name            VARCHAR(255),
    avatar_url      TEXT,
    auth_provider   VARCHAR(50) DEFAULT 'email',  -- 'email' | 'google' | 'github'
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    last_login_at   TIMESTAMP
);

-- ─── Organizations Table ──────────────────────────────────────────────────────
-- Stores organization/workspace information
CREATE TABLE IF NOT EXISTS organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) NOT NULL UNIQUE,
    owner_id        UUID REFERENCES users(id) ON DELETE CASCADE,
    plan_tier       VARCHAR(50) DEFAULT 'free',  -- 'free' | 'starter' | 'pro' | 'enterprise'
    max_accounts    INTEGER DEFAULT 3,           -- Max TikTok accounts allowed
    max_videos_day  INTEGER DEFAULT 10,          -- Max videos per day
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- ─── Organization Members Table ───────────────────────────────────────────────
-- Maps users to organizations with roles
CREATE TABLE IF NOT EXISTS organization_members (
    id              SERIAL PRIMARY KEY,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    role            VARCHAR(50) DEFAULT 'member',  -- 'owner' | 'admin' | 'member'
    invited_by      UUID REFERENCES users(id),
    joined_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE(organization_id, user_id)
);

-- ─── Proxies Table ────────────────────────────────────────────────────────────
-- Stores proxy configurations for TikTok uploads
CREATE TABLE IF NOT EXISTS proxies (
    id              SERIAL PRIMARY KEY,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    protocol        VARCHAR(10) DEFAULT 'http',  -- 'http' | 'https' | 'socks5'
    host            VARCHAR(255) NOT NULL,
    port            INTEGER NOT NULL,
    username        VARCHAR(255),
    password        VARCHAR(255),
    country         VARCHAR(2),                  -- ISO country code
    is_active       BOOLEAN DEFAULT true,
    last_checked_at TIMESTAMP,
    last_success_at TIMESTAMP,
    failure_count   INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- ─── Workflow Executions Table ────────────────────────────────────────────────
-- Tracks n8n workflow execution history
CREATE TABLE IF NOT EXISTS workflow_executions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    workflow_name   VARCHAR(255) NOT NULL,
    workflow_id     VARCHAR(100),                -- n8n workflow ID
    status          VARCHAR(50) DEFAULT 'running',  -- 'running' | 'completed' | 'failed' | 'cancelled'
    trigger_type    VARCHAR(50),                 -- 'manual' | 'scheduled' | 'webhook'
    triggered_by    UUID REFERENCES users(id),
    input_data      JSONB,
    output_data     JSONB,
    error_message   TEXT,
    started_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP,
    duration_ms     INTEGER
);

-- ─── Workflow Steps Table ─────────────────────────────────────────────────────
-- Tracks individual steps within workflow executions
CREATE TABLE IF NOT EXISTS workflow_steps (
    id              SERIAL PRIMARY KEY,
    execution_id    UUID REFERENCES workflow_executions(id) ON DELETE CASCADE,
    step_name       VARCHAR(255) NOT NULL,
    step_order      INTEGER NOT NULL,
    status          VARCHAR(50) DEFAULT 'running',  -- 'running' | 'completed' | 'failed' | 'skipped'
    input_data      JSONB,
    output_data     JSONB,
    error_message   TEXT,
    started_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP,
    duration_ms     INTEGER
);

-- ─── Video Variants Table ─────────────────────────────────────────────────────
-- Stores A/B test variants for videos (captions, thumbnails, etc.)
CREATE TABLE IF NOT EXISTS video_variants (
    id              SERIAL PRIMARY KEY,
    video_id        INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    variant_type    VARCHAR(50) NOT NULL,        -- 'caption' | 'thumbnail' | 'hashtags'
    variant_data    JSONB NOT NULL,
    is_selected     BOOLEAN DEFAULT false,       -- Which variant was used
    performance_score DECIMAL(5,2),              -- Calculated after 24 hours
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ─── Add organization_id to existing tables ───────────────────────────────────
-- Add organization_id column to manga table
ALTER TABLE manga 
ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

-- Add organization_id column to tiktok_accounts table
ALTER TABLE tiktok_accounts 
ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

-- Add proxy_id column to tiktok_accounts table
ALTER TABLE tiktok_accounts 
ADD COLUMN IF NOT EXISTS proxy_id INTEGER REFERENCES proxies(id) ON DELETE SET NULL;

-- Add organization_id column to videos table
ALTER TABLE videos 
ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

-- Add scheduled_for column to videos table for smart scheduling
ALTER TABLE videos 
ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMP;

-- Add organization_id column to manga_chapters table
ALTER TABLE manga_chapters 
ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

-- ─── Enhanced Analytics Columns ───────────────────────────────────────────────
-- Add more detailed tracking to video_analytics
ALTER TABLE video_analytics 
ADD COLUMN IF NOT EXISTS engagement_rate DECIMAL(5,2),
ADD COLUMN IF NOT EXISTS completion_rate DECIMAL(5,2),
ADD COLUMN IF NOT EXISTS avg_watch_time_secs INTEGER,
ADD COLUMN IF NOT EXISTS profile_visits INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS follower_growth INTEGER DEFAULT 0;

-- ─── Indexes for Performance ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug);
CREATE INDEX IF NOT EXISTS idx_organizations_owner ON organizations(owner_id);
CREATE INDEX IF NOT EXISTS idx_org_members_org ON organization_members(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_members_user ON organization_members(user_id);
CREATE INDEX IF NOT EXISTS idx_proxies_org ON proxies(organization_id);
CREATE INDEX IF NOT EXISTS idx_proxies_active ON proxies(is_active);
CREATE INDEX IF NOT EXISTS idx_workflow_exec_org ON workflow_executions(organization_id);
CREATE INDEX IF NOT EXISTS idx_workflow_exec_status ON workflow_executions(status);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_exec ON workflow_steps(execution_id);
CREATE INDEX IF NOT EXISTS idx_video_variants_video ON video_variants(video_id);
CREATE INDEX IF NOT EXISTS idx_manga_org ON manga(organization_id);
CREATE INDEX IF NOT EXISTS idx_tiktok_accounts_org ON tiktok_accounts(organization_id);
CREATE INDEX IF NOT EXISTS idx_tiktok_accounts_proxy ON tiktok_accounts(proxy_id);
CREATE INDEX IF NOT EXISTS idx_videos_org ON videos(organization_id);
CREATE INDEX IF NOT EXISTS idx_videos_scheduled ON videos(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_chapters_org ON manga_chapters(organization_id);

-- ─── Seed Data: Demo Organization ─────────────────────────────────────────────
-- Create a demo user and organization for testing
INSERT INTO users (id, email, name, auth_provider) VALUES
    ('00000000-0000-0000-0000-000000000001', 'demo@mangaautomation.com', 'Demo User', 'email')
ON CONFLICT (email) DO NOTHING;

INSERT INTO organizations (id, name, slug, owner_id, plan_tier, max_accounts, max_videos_day) VALUES
    ('00000000-0000-0000-0000-000000000001', 'Demo Organization', 'demo-org', 
     '00000000-0000-0000-0000-000000000001', 'pro', 10, 100)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO organization_members (organization_id, user_id, role) VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'owner')
ON CONFLICT (organization_id, user_id) DO NOTHING;

-- Assign existing data to demo organization
UPDATE manga SET organization_id = '00000000-0000-0000-0000-000000000001' 
WHERE organization_id IS NULL;

UPDATE tiktok_accounts SET organization_id = '00000000-0000-0000-0000-000000000001' 
WHERE organization_id IS NULL;

UPDATE videos SET organization_id = '00000000-0000-0000-0000-000000000001' 
WHERE organization_id IS NULL;

UPDATE manga_chapters SET organization_id = '00000000-0000-0000-0000-000000000001' 
WHERE organization_id IS NULL;

-- ─── Comments ─────────────────────────────────────────────────────────────────
COMMENT ON TABLE users IS 'User accounts integrated with Supabase Auth';
COMMENT ON TABLE organizations IS 'Organization/workspace for multi-tenancy';
COMMENT ON TABLE organization_members IS 'Maps users to organizations with roles';
COMMENT ON TABLE proxies IS 'Proxy configurations for TikTok uploads';
COMMENT ON TABLE workflow_executions IS 'Tracks n8n workflow execution history';
COMMENT ON TABLE workflow_steps IS 'Tracks individual steps within workflows';
COMMENT ON TABLE video_variants IS 'A/B test variants for videos';

