-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 004 v2: Multi-Tenancy & SaaS Features (Compatible with existing schema)
-- ─────────────────────────────────────────────────────────────────────────────

-- ─── Update Users Table ───────────────────────────────────────────────────────
-- Add missing columns to existing users table
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS name VARCHAR(255),
ADD COLUMN IF NOT EXISTS avatar_url TEXT,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP;

-- ─── Update Organizations Table ───────────────────────────────────────────────
-- Add missing columns to existing organizations table
ALTER TABLE organizations 
ADD COLUMN IF NOT EXISTS slug VARCHAR(100),
ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
ADD COLUMN IF NOT EXISTS max_accounts INTEGER DEFAULT 3,
ADD COLUMN IF NOT EXISTS max_videos_day INTEGER DEFAULT 10,
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- Create unique constraint on slug if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'organizations_slug_key'
    ) THEN
        ALTER TABLE organizations ADD CONSTRAINT organizations_slug_key UNIQUE (slug);
    END IF;
END $$;


-- ─── Organization Members Table ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organization_members (
    id              SERIAL PRIMARY KEY,
    organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role            VARCHAR(50) DEFAULT 'member',
    invited_by      INTEGER REFERENCES users(id),
    joined_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE(organization_id, user_id)
);

-- ─── Update Proxies Table ─────────────────────────────────────────────────────
-- Add missing columns to existing proxies table
ALTER TABLE proxies 
ADD COLUMN IF NOT EXISTS name VARCHAR(255),
ADD COLUMN IF NOT EXISTS country VARCHAR(2),
ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS failure_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- ─── Video Variants Table ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS video_variants (
    id              SERIAL PRIMARY KEY,
    video_id        INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    variant_type    VARCHAR(50) NOT NULL,
    variant_data    JSONB NOT NULL,
    is_selected     BOOLEAN DEFAULT false,
    performance_score DECIMAL(5,2),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ─── Update Workflow Executions Table ─────────────────────────────────────────
-- Add missing columns to existing workflow_executions table
ALTER TABLE workflow_executions 
ADD COLUMN IF NOT EXISTS workflow_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS trigger_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS triggered_by INTEGER REFERENCES users(id),
ADD COLUMN IF NOT EXISTS input_data JSONB,
ADD COLUMN IF NOT EXISTS output_data JSONB,
ADD COLUMN IF NOT EXISTS error_message TEXT,
ADD COLUMN IF NOT EXISTS duration_ms INTEGER;

-- ─── Update Workflow Steps Table ──────────────────────────────────────────────
-- Add missing columns to existing workflow_steps table
ALTER TABLE workflow_steps 
ADD COLUMN IF NOT EXISTS step_order INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS output_data JSONB,
ADD COLUMN IF NOT EXISTS error_message TEXT,
ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS duration_ms INTEGER;

-- ─── Add scheduled_for to videos ──────────────────────────────────────────────
ALTER TABLE videos 
ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMP;

-- ─── Enhanced Analytics Columns ───────────────────────────────────────────────
ALTER TABLE video_analytics 
ADD COLUMN IF NOT EXISTS engagement_rate DECIMAL(5,2),
ADD COLUMN IF NOT EXISTS completion_rate DECIMAL(5,2),
ADD COLUMN IF NOT EXISTS avg_watch_time_secs INTEGER,
ADD COLUMN IF NOT EXISTS profile_visits INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS follower_growth INTEGER DEFAULT 0;

-- ─── Indexes for Performance ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug);
CREATE INDEX IF NOT EXISTS idx_organizations_owner ON organizations(owner_id);
CREATE INDEX IF NOT EXISTS idx_org_members_org ON organization_members(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_members_user ON organization_members(user_id);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_exec ON workflow_steps(execution_id);
CREATE INDEX IF NOT EXISTS idx_video_variants_video ON video_variants(video_id);
CREATE INDEX IF NOT EXISTS idx_videos_scheduled ON videos(scheduled_for);

-- ─── Seed Data: Demo Organization ─────────────────────────────────────────────
-- Update existing demo organization with slug
UPDATE organizations 
SET slug = 'demo-org', 
    max_accounts = 10, 
    max_videos_day = 100,
    is_active = true
WHERE id = 1 AND slug IS NULL;

-- Update existing demo user
UPDATE users 
SET name = 'Demo User'
WHERE id = 1 AND name IS NULL;

-- Set owner for demo organization
UPDATE organizations 
SET owner_id = 1
WHERE id = 1 AND owner_id IS NULL;

-- Create organization member entry
INSERT INTO organization_members (organization_id, user_id, role) 
VALUES (1, 1, 'owner')
ON CONFLICT (organization_id, user_id) DO NOTHING;

