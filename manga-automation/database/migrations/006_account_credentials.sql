-- Migration 006: Add email and password columns to tiktok_accounts
-- Allows storing credentials alongside session cookies for automated re-login

ALTER TABLE tiktok_accounts
    ADD COLUMN IF NOT EXISTS email text,
    ADD COLUMN IF NOT EXISTS tiktok_password text;

-- Seed the real account if it doesn't exist yet
INSERT INTO tiktok_accounts (username, cookies_file, email, tiktok_password, account_status, shadow_banned)
VALUES ('nuggerchicken433', 'nuggerchicken433', 'nuggerchicken433@gmail.com', 'Huy15022005@', 'active', false)
ON CONFLICT (username) DO UPDATE
    SET cookies_file     = EXCLUDED.cookies_file,
        email            = EXCLUDED.email,
        tiktok_password  = EXCLUDED.tiktok_password,
        account_status   = 'active',
        shadow_banned    = false;

-- Remove any fake/placeholder accounts
DELETE FROM tiktok_accounts
WHERE username NOT IN ('nuggerchicken433')
  AND (email IS NULL OR email NOT LIKE '%@%');
