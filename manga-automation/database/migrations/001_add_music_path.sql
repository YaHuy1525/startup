-- Migration 001: add music_path to selected_panels
-- Run once against your Supabase (or local) database.
-- Safe to re-run — uses IF NOT EXISTS semantics.

ALTER TABLE selected_panels
    ADD COLUMN IF NOT EXISTS music_path TEXT;

COMMENT ON COLUMN selected_panels.music_path IS
    'Absolute path to the background audio file chosen by the MusicSelector agent';
