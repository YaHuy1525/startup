-- Migration 013: Marketplace Monetization Tables
-- Merchants, promotion tasks (CPS/CPE/CPM), task assignments, and earnings tracking.

CREATE TABLE IF NOT EXISTS merchants (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) UNIQUE NOT NULL,
    category        VARCHAR(100),
    contact_email   VARCHAR(255),
    status          VARCHAR(30) DEFAULT 'active',
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS promotion_tasks (
    id                SERIAL PRIMARY KEY,
    merchant_id       INTEGER REFERENCES merchants(id),
    title             VARCHAR(500) NOT NULL,
    description       TEXT,
    model             VARCHAR(20) NOT NULL DEFAULT 'cps',  -- cps | cpe | cpm
    reward            DECIMAL(12,6) DEFAULT 0,
    budget            DECIMAL(12,2) DEFAULT 0,
    target_platforms  JSONB DEFAULT '["tiktok","youtube"]',
    status            VARCHAR(30) DEFAULT 'open',  -- open | assigned | completed | cancelled
    created_at        TIMESTAMP DEFAULT NOW(),
    expires_at        TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_promotion_tasks_status
    ON promotion_tasks(status, budget DESC);

CREATE TABLE IF NOT EXISTS task_assignments (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER REFERENCES promotion_tasks(id),
    creator_id      INTEGER REFERENCES users(id),
    status          VARCHAR(30) DEFAULT 'accepted',  -- accepted | completed | rejected
    assigned_at     TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_assignments_creator
    ON task_assignments(creator_id, assigned_at DESC);

CREATE TABLE IF NOT EXISTS earnings (
    id              SERIAL PRIMARY KEY,
    assignment_id   INTEGER REFERENCES task_assignments(id),
    model           VARCHAR(20) NOT NULL,
    views           INTEGER DEFAULT 0,
    engagements     INTEGER DEFAULT 0,
    amount          DECIMAL(12,6) DEFAULT 0,
    calculated_at   TIMESTAMP DEFAULT NOW(),
    UNIQUE (assignment_id, calculated_at)
);

CREATE INDEX IF NOT EXISTS idx_earnings_assignment
    ON earnings(assignment_id, calculated_at DESC);
