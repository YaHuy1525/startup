-- ============================================================
-- Migration 008: AI Gig Copilot Tables
-- Platform: DataAnnotation / Outlier / Babel
-- ============================================================

-- gig_platform_profiles: per-user platform config
CREATE TABLE IF NOT EXISTS gig_platform_profiles (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT        NOT NULL,
    platform        TEXT        NOT NULL CHECK (platform IN ('dataannotation','outlier','babel')),
    country         TEXT,
    skills          TEXT[]      DEFAULT '{}',
    hourly_target   NUMERIC(10,2),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, platform)
);

-- gig_rubrics: scoring rubrics per platform + task type (pre-seeded)
CREATE TABLE IF NOT EXISTS gig_rubrics (
    id          SERIAL PRIMARY KEY,
    platform    TEXT    NOT NULL,
    task_type   TEXT    NOT NULL,  -- prompt-writing | response-rating | factual-eval | voice-script
    rubric_json JSONB   NOT NULL,
    active      BOOLEAN DEFAULT TRUE,
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (platform, task_type)
);

-- gig_tasks: one row per task loaded by user
CREATE TABLE IF NOT EXISTS gig_tasks (
    id                  SERIAL PRIMARY KEY,
    user_id             TEXT        NOT NULL,
    platform            TEXT        NOT NULL,
    task_type           TEXT        NOT NULL,
    task_prompt         TEXT        NOT NULL,
    reference_context   TEXT,
    status              TEXT        DEFAULT 'drafted'
                            CHECK (status IN (
                                'drafted','reviewed','submitted_manual','rejected','accepted'
                            )),
    time_spent_minutes  INTEGER,
    estimated_payout    NUMERIC(10,2),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gig_tasks_user_status
    ON gig_tasks (user_id, status, created_at DESC);

-- gig_outputs: AI-generated drafts + scores per task
CREATE TABLE IF NOT EXISTS gig_outputs (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER     REFERENCES gig_tasks(id) ON DELETE CASCADE,
    draft_output    TEXT,
    final_output    TEXT,
    quality_score   NUMERIC(5,2),
    risk_flags_json JSONB       DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- gig_sessions: aggregated work session record
CREATE TABLE IF NOT EXISTS gig_sessions (
    id                      SERIAL PRIMARY KEY,
    user_id                 TEXT        NOT NULL,
    started_at              TIMESTAMPTZ DEFAULT NOW(),
    ended_at                TIMESTAMPTZ,
    tasks_completed         INTEGER     DEFAULT 0,
    effective_hourly_rate   NUMERIC(10,2)
);

-- prompt_templates: versioned templates with win-rate learning
CREATE TABLE IF NOT EXISTS prompt_templates (
    id              SERIAL PRIMARY KEY,
    platform        TEXT        NOT NULL,
    task_type       TEXT        NOT NULL,
    template_name   TEXT        NOT NULL,
    template_text   TEXT        NOT NULL,
    win_rate        NUMERIC(5,2) DEFAULT 0.0,
    use_count       INTEGER     DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (platform, task_type, template_name)
);

-- ── Seed default rubrics ──────────────────────────────────────────────────────

INSERT INTO gig_rubrics (platform, task_type, rubric_json) VALUES
('dataannotation', 'prompt-writing', '{
  "dimensions": [
    {"name": "clarity",       "weight": 0.30, "description": "Is the prompt clear and unambiguous?"},
    {"name": "creativity",    "weight": 0.25, "description": "Is the prompt original and interesting?"},
    {"name": "difficulty",    "weight": 0.20, "description": "Does the prompt challenge the model appropriately?"},
    {"name": "safety",        "weight": 0.15, "description": "Is the prompt free of harmful content?"},
    {"name": "coverage",      "weight": 0.10, "description": "Does the prompt cover the required topic fully?"}
  ],
  "min_pass_score": 0.70
}'),
('dataannotation', 'response-rating', '{
  "dimensions": [
    {"name": "accuracy",      "weight": 0.35, "description": "Is the response factually correct?"},
    {"name": "completeness",  "weight": 0.25, "description": "Does it fully answer the prompt?"},
    {"name": "reasoning",     "weight": 0.25, "description": "Is the reasoning clear and logical?"},
    {"name": "safety",        "weight": 0.15, "description": "Is the response free of harmful content?"}
  ],
  "min_pass_score": 0.70
}'),
('outlier', 'prompt-writing', '{
  "dimensions": [
    {"name": "specificity",   "weight": 0.30, "description": "Is the prompt specific and well-scoped?"},
    {"name": "novelty",       "weight": 0.25, "description": "Is it a novel prompt not easily found online?"},
    {"name": "complexity",    "weight": 0.25, "description": "Does it require multi-step reasoning?"},
    {"name": "safety",        "weight": 0.20, "description": "Does it comply with platform guidelines?"}
  ],
  "min_pass_score": 0.72
}'),
('babel', 'factual-eval', '{
  "dimensions": [
    {"name": "accuracy",      "weight": 0.40, "description": "Are all factual claims verifiable?"},
    {"name": "sourcing",      "weight": 0.30, "description": "Can claims be traced to authoritative sources?"},
    {"name": "clarity",       "weight": 0.20, "description": "Is the evaluation clearly written?"},
    {"name": "neutrality",    "weight": 0.10, "description": "Is the tone neutral and unbiased?"}
  ],
  "min_pass_score": 0.75
}')
ON CONFLICT (platform, task_type) DO NOTHING;
