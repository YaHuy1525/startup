# Database Migrations

This directory contains SQL migration files for the manga automation system.

## Migration Files

- `001_add_music_path.sql` - Adds music_path column to selected_panels
- `002_tiktok_sounds.sql` - Adds TikTok sound support and tiktok_sounds table
- `003_queue_system_and_templates.sql` - **NEW** Adds queue system, hashtags, caption templates, and video templates

## Migration 003: Queue System and Templates

This migration implements the core infrastructure for scaling to 90+ videos per day:

### New Tables

1. **chapter_posting_queue** - Queue system for systematic chapter posting
   - Tracks which chapters to post and in what order
   - Supports priority-based posting (manual selections get priority 100)
   - Handles split chapters with part_number and total_parts
   - Status tracking: pending → processing → posted/failed

2. **hashtags** - Strategic hashtag library with tiered reach
   - Tier 1: Mega hashtags (#fyp, #foryou)
   - Tier 2: Core hashtags (#manga, #anime)
   - Tier 3: Niche hashtags (#shonen, #isekai)
   - Tier 4: Specific hashtags (#onepiece, #naruto)

3. **caption_templates** - Viral caption formulas
   - 5 formula types: emotional_hook, question, relatable, recommendation, statement_emoji
   - Template variables: {manga}, {chapter}, {genre}, {emotion}
   - Emoji suggestions for each template

4. **video_templates** - Video style configurations for Remotion
   - 5 templates: Emotional Scene, Character Edit, Manga Recommendation, Panel Appreciation, Fast Paced Action
   - Effect configurations: zoom intensity, pan direction, transitions
   - Performance tracking: usage_count, avg_views

5. **video_performance** - Performance metrics for optimization
   - Tracks views, likes, comments, shares
   - Links to caption formula and hashtags used
   - Links to video template for A/B testing

### Modified Tables

**manga_chapters** - Added columns:
- `posted` (BOOLEAN) - Whether chapter has been posted
- `post_count` (INTEGER) - Number of times posted (for split chapters)
- `total_panels` (INTEGER) - Total panel count
- `analyzed` (BOOLEAN) - Whether chapter has been analyzed for splitting

### Seed Data

The migration includes comprehensive seed data:
- **33 hashtags** across all 4 tiers
- **15 caption templates** covering all 5 formula types
- **5 video templates** with different styles and effects

## Applying Migrations

### Option 1: Using Docker Compose (Recommended)

If the postgres container is running:

```bash
cd database/migrations
chmod +x apply_migration.sh
./apply_migration.sh 003_queue_system_and_templates.sql
```

### Option 2: Direct psql Connection

```bash
cd database/migrations
PGPASSWORD=your_password psql -h localhost -p 5434 -U manga_user -d manga_automation -f 003_queue_system_and_templates.sql
```

### Option 3: Using Docker Exec

```bash
cd manga-automation
docker compose exec -T postgres psql -U manga_user -d manga_automation < database/migrations/003_queue_system_and_templates.sql
```

## Verifying Migration

After applying the migration, run the verification script:

```bash
cd database/migrations
PGPASSWORD=your_password psql -h localhost -p 5434 -U manga_user -d manga_automation -f verify_migration_003.sql
```

Expected results:
- 5 new tables created
- 4 new columns added to manga_chapters
- 33 hashtags inserted
- 15 caption templates inserted
- 5 video templates inserted

## Rollback

If you need to rollback migration 003:

```sql
-- Drop new tables
DROP TABLE IF EXISTS video_performance CASCADE;
DROP TABLE IF EXISTS video_templates CASCADE;
DROP TABLE IF EXISTS caption_templates CASCADE;
DROP TABLE IF EXISTS hashtags CASCADE;
DROP TABLE IF EXISTS chapter_posting_queue CASCADE;

-- Remove columns from manga_chapters
ALTER TABLE manga_chapters
    DROP COLUMN IF EXISTS posted,
    DROP COLUMN IF EXISTS post_count,
    DROP COLUMN IF EXISTS total_panels,
    DROP COLUMN IF EXISTS analyzed;
```

## Migration Safety

All migrations use `IF NOT EXISTS` and `IF NOT EXISTS` semantics, making them safe to re-run. If a table or column already exists, the migration will skip that step without errors.

## Next Steps

After applying migration 003:

1. Verify the schema with `verify_migration_003.sql`
2. Implement the Queue Manager component (Task 2)
3. Update n8n workflows to use the new queue system
4. Test the queue population with existing manga data

## Troubleshooting

**Error: relation already exists**
- This is safe to ignore if re-running the migration
- The migration uses `IF NOT EXISTS` to prevent errors

**Error: column already exists**
- This is safe to ignore if re-running the migration
- The migration uses `ADD COLUMN IF NOT EXISTS`

**Error: duplicate key value violates unique constraint**
- This occurs when seed data already exists
- The migration uses `ON CONFLICT DO NOTHING` to handle this

**Connection refused**
- Ensure the postgres container is running: `docker compose ps postgres`
- Check the port is correct (5434 for docker, 5432 internal)
- Verify DATABASE_URL in .env file
