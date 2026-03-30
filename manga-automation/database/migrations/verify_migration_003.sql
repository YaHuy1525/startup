-- Verification queries for migration 003
-- Run these after applying the migration to verify schema changes

-- Check if chapter_posting_queue table exists
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'chapter_posting_queue'
) AS chapter_posting_queue_exists;

-- Check chapter_posting_queue columns
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'chapter_posting_queue'
ORDER BY ordinal_position;

-- Check chapter_posting_queue indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'chapter_posting_queue';

-- Check manga_chapters new columns
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'manga_chapters'
AND column_name IN ('posted', 'post_count', 'total_panels', 'analyzed');

-- Check if hashtags table exists
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'hashtags'
) AS hashtags_exists;

-- Count hashtags by tier
SELECT tier, COUNT(*) as count
FROM hashtags
GROUP BY tier
ORDER BY tier;

-- Check if caption_templates table exists
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'caption_templates'
) AS caption_templates_exists;

-- Count caption templates by formula type
SELECT formula_type, COUNT(*) as count
FROM caption_templates
GROUP BY formula_type
ORDER BY formula_type;

-- Check if video_templates table exists
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'video_templates'
) AS video_templates_exists;

-- Count video templates
SELECT COUNT(*) as total_templates, 
       COUNT(DISTINCT type) as unique_types
FROM video_templates;

-- Check if video_performance table exists
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'video_performance'
) AS video_performance_exists;

-- Summary report
SELECT 
    'chapter_posting_queue' as table_name,
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'chapter_posting_queue') as exists,
    (SELECT COUNT(*) FROM chapter_posting_queue) as row_count
UNION ALL
SELECT 
    'hashtags',
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'hashtags'),
    (SELECT COUNT(*) FROM hashtags)
UNION ALL
SELECT 
    'caption_templates',
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'caption_templates'),
    (SELECT COUNT(*) FROM caption_templates)
UNION ALL
SELECT 
    'video_templates',
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'video_templates'),
    (SELECT COUNT(*) FROM video_templates)
UNION ALL
SELECT 
    'video_performance',
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'video_performance'),
    (SELECT COUNT(*) FROM video_performance);
