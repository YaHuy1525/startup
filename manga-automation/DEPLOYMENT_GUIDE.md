# Deployment Guide - Manga Automation Improvements

## Overview

This guide walks you through deploying the new queue-based manga automation system that scales from 20 videos/week to 630+ videos/week (90/day).

## What's New

The system now includes:
- **Queue-based chapter posting** - Systematically posts all chapters oldest-to-latest
- **Manual chapter selection** - Webhook to queue specific chapters on-demand
- **Enhanced video generation** - Remotion with Ken Burns effects and templates
- **Viral captions** - 5 proven formulas with emoji integration
- **Strategic hashtags** - Tiered system (mega/core/niche) for maximum reach

## Prerequisites

- Docker and Docker Compose installed
- Anthropic API key (for Claude)
- PostgreSQL database (included in docker-compose)
- At least 8GB RAM and 50GB disk space

---

## Step 1: Apply Database Migrations

The new features require database schema changes. Apply the migration:

```bash
cd manga-automation

# Connect to your database
docker compose exec postgres psql -U manga_user -d manga_automation

# Or if containers aren't running yet, start just the database:
docker compose up -d postgres

# Wait a few seconds for postgres to start
sleep 5

# Apply migration
docker compose exec postgres psql -U manga_user -d manga_automation -f /docker-entrypoint-initdb.d/migrations/003_queue_system_and_templates.sql
```

**Alternative: Apply migration from host machine**

```bash
# Copy migration to a temporary location
docker cp manga-automation/database/migrations/003_queue_system_and_templates.sql manga-automation-postgres-1:/tmp/

# Execute it
docker compose exec postgres psql -U manga_user -d manga_automation -f /tmp/003_queue_system_and_templates.sql
```

**Verify migration:**

```bash
docker compose exec postgres psql -U manga_user -d manga_automation -c "\dt"
```

You should see these new tables:
- `chapter_posting_queue`
- `video_templates`
- `caption_templates`
- `hashtags`
- `video_performance`

---

## Step 2: Rebuild Docker Containers

The new code needs to be built into the Docker images:

```bash
cd manga-automation

# Stop existing containers
docker compose down

# Rebuild with no cache to ensure fresh build
docker compose build --no-cache manga-agents

# Or rebuild all services
docker compose build --no-cache

# Start all services
docker compose up -d

# Check logs to ensure services started correctly
docker compose logs -f manga-agents
```

**Verify services are running:**

```bash
# Check manga-agents health
curl http://localhost:3001/health

# Should return: {"status":"ok","service":"manga-agents","timestamp":"..."}

# Check python-worker health
curl http://localhost:8080/health
```

---

## Step 3: Install Dependencies (if needed)

If you modified package.json or added new dependencies:

```bash
# For Node.js dependencies (manga-agents)
docker compose exec manga-agents npm install

# For Remotion renderer
docker compose exec manga-agents sh -c "cd remotion-renderer && npm install"

# Restart the service
docker compose restart manga-agents
```

---

## Step 4: Update N8N Workflows

The N8N workflows have been updated to use the new queue system.

### Import Updated Workflows

1. Open N8N: http://localhost:5679
2. Login with your credentials
3. For each workflow, go to **Workflows** → **Import from File**
4. Import these files in order:
   - `n8n-workflows/01_trend_detection.json`
   - `n8n-workflows/02_video_generation.json`
   - `n8n-workflows/03_publisher.json`
   - `n8n-workflows/05_manual_chapter_selection.json`

5. For each imported workflow:
   - Update PostgreSQL credentials (if needed)
   - Activate the workflow

### Workflow Changes Summary

**01_trend_detection.json**
- Now calls `/pipeline/populate-queue` to queue all chapters
- Uses MangaDex API (already implemented)

**02_video_generation.json**
- Queries `chapter_posting_queue` instead of `selected_panels`
- Passes `queueId` to render endpoint
- Handles split chapters automatically

**03_publisher.json**
- Calls `/captions/generate` for viral captions
- Uses tiered hashtag system

**05_manual_chapter_selection.json** (NEW)
- Webhook endpoint for manual chapter queuing
- Webhook URL: `http://n8n:5678/webhook/queue-chapter`

---

## Step 5: Test the New Features

### Test 1: Queue Population

```bash
# Add a manga to the database (if you don't have one)
docker compose exec postgres psql -U manga_user -d manga_automation -c "
INSERT INTO manga (title, mangadex_id, tags, status, is_active, trending_score, created_at, updated_at)
VALUES ('Test Manga', 'test-manga-123', '{\"genre\": \"action\"}', 'ongoing', true, 100, NOW(), NOW())
RETURNING id;
"

# Note the returned ID (e.g., 1)

# Populate queue with all chapters for this manga
curl -X POST http://localhost:3001/pipeline/populate-queue \
  -H "Content-Type: application/json" \
  -d '{"manga_id": 1}'

# Check queue status
docker compose exec postgres psql -U manga_user -d manga_automation -c "
SELECT id, manga_id, chapter_number, priority, status, created_at 
FROM chapter_posting_queue 
ORDER BY priority DESC, chapter_number ASC 
LIMIT 10;
"
```

### Test 2: Manual Chapter Selection

```bash
# Queue a specific chapter with high priority
curl -X POST http://localhost:3001/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{
    "manga_id": 1,
    "chapter_number": "42",
    "priority": 100
  }'

# Queue a chapter range
curl -X POST http://localhost:3001/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{
    "manga_id": 1,
    "start_chapter": "1",
    "end_chapter": "10",
    "priority": 150
  }'
```

### Test 3: Caption Generation

```bash
# Generate viral caption for a video
curl -X POST http://localhost:3001/captions/generate \
  -H "Content-Type: application/json" \
  -d '{
    "videoId": 1,
    "mangaTitle": "One Piece",
    "chapterNumber": "1000",
    "genre": "action"
  }'

# Should return caption with emojis and strategic hashtags
```

### Test 4: Hashtag Selection

```bash
# Get strategic hashtag combination
curl "http://localhost:3001/hashtags/select?mangaTitle=One%20Piece&genre=action"

# Should return 3-5 hashtags (1 mega, 2-3 core, 1-2 niche)
```

---

## Step 6: Monitor the System

### Check Queue Status

```sql
-- Connect to database
docker compose exec postgres psql -U manga_user -d manga_automation

-- View queue status
SELECT 
    status,
    COUNT(*) as count,
    MIN(chapter_number) as oldest_chapter,
    MAX(chapter_number) as newest_chapter
FROM chapter_posting_queue
GROUP BY status;

-- View next chapters to post
SELECT 
    cpq.id,
    m.title,
    cpq.chapter_number,
    cpq.priority,
    cpq.status,
    cpq.created_at
FROM chapter_posting_queue cpq
JOIN manga_chapters mc ON cpq.chapter_id = mc.id
JOIN manga m ON cpq.manga_id = m.id
WHERE cpq.status = 'pending'
ORDER BY cpq.priority DESC, cpq.chapter_number ASC
LIMIT 10;
```

### Check Video Generation Rate

```sql
-- Videos generated in last 24 hours
SELECT 
    DATE_TRUNC('hour', posted_at) as hour,
    COUNT(*) as videos_posted
FROM chapter_posting_queue
WHERE posted_at > NOW() - INTERVAL '24 hours'
  AND status = 'posted'
GROUP BY hour
ORDER BY hour DESC;

-- Success rate
SELECT 
    status,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM chapter_posting_queue
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY status;
```

### View Logs

```bash
# View manga-agents logs
docker compose logs -f manga-agents

# View specific service logs
docker compose logs -f postgres
docker compose logs -f n8n

# View last 100 lines
docker compose logs --tail=100 manga-agents
```

---

## How It Works Now

### Automatic Workflow (Every 4 Hours)

1. **Trend Detection** (N8N Workflow 01)
   - Fetches trending manga from MangaDex
   - Saves manga to database
   - **NEW**: Calls `/pipeline/populate-queue` to queue ALL chapters for each manga
   - Fetches latest chapters and downloads panels

2. **Video Generation** (N8N Workflow 02, Every 1 Hour)
   - **NEW**: Queries `chapter_posting_queue` for next pending chapter (priority DESC, chapter_number ASC)
   - **NEW**: Updates queue status to 'processing'
   - Renders video using Remotion with Ken Burns effects
   - **NEW**: Updates queue status to 'posted' with video_id
   - Generates caption using viral formulas
   - Triggers publisher workflow

3. **Publishing** (N8N Workflow 03, Every 2 Hours)
   - **NEW**: Generates viral caption with emoji integration
   - **NEW**: Selects strategic hashtags (1 mega + 2-3 core + 1-2 niche)
   - Uploads to TikTok
   - Marks video as published

### Manual Workflow (On-Demand)

You can manually queue specific chapters via webhook:

```bash
# Queue a single chapter
curl -X POST http://localhost:3001/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{
    "manga_id": 1,
    "chapter_number": "42",
    "priority": 100
  }'

# Queue a chapter range (e.g., chapters 1-50)
curl -X POST http://localhost:3001/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{
    "manga_id": 1,
    "start_chapter": "1",
    "end_chapter": "50",
    "priority": 150
  }'
```

**Priority System:**
- Default queue entries: priority = 0
- Manual selections: priority = 100 (or custom)
- Higher priority = posted first
- Same priority = oldest chapter first (lowest chapter_number)

---

## Troubleshooting

### Issue: "Table chapter_posting_queue does not exist"

**Solution:** Apply the database migration (Step 1)

```bash
docker compose exec postgres psql -U manga_user -d manga_automation -f /docker-entrypoint-initdb.d/migrations/003_queue_system_and_templates.sql
```

### Issue: "Cannot find module 'queueManager'"

**Solution:** Rebuild the Docker container (Step 2)

```bash
docker compose down
docker compose build --no-cache manga-agents
docker compose up -d
```

### Issue: Queue not processing

**Check:**
1. N8N workflow 02 is active
2. Queue has pending entries: `SELECT * FROM chapter_posting_queue WHERE status='pending' LIMIT 5;`
3. Manga-agents service is running: `docker compose ps`

**Solution:**
```bash
# Restart manga-agents
docker compose restart manga-agents

# Check logs
docker compose logs -f manga-agents
```

### Issue: Videos not generating

**Check:**
1. Queue entry exists and is pending
2. Chapter has panels: `SELECT panel_urls, local_paths FROM manga_chapters WHERE id=<chapter_id>;`
3. Remotion renderer is working: `docker compose logs manga-agents | grep remotion`

**Solution:**
```bash
# Test render endpoint directly
curl -X POST http://localhost:3001/pipeline/render-video \
  -H "Content-Type: application/json" \
  -d '{"queueId": 1, "randomTemplate": true}'

# Check for errors in logs
docker compose logs --tail=100 manga-agents
```

### Issue: Captions not generating

**Check:**
1. Caption templates exist: `SELECT * FROM caption_templates LIMIT 5;`
2. Hashtags exist: `SELECT * FROM hashtags LIMIT 10;`

**Solution:**
```bash
# Re-run migration to seed data
docker compose exec postgres psql -U manga_user -d manga_automation -f /docker-entrypoint-initdb.d/migrations/003_queue_system_and_templates.sql
```

---

## Performance Tuning

### Target: 90+ Videos Per Day

**Current bottlenecks:**
1. Video rendering time (~10-15 minutes per video)
2. Database query performance
3. Concurrent rendering limit

**Optimizations:**

1. **Increase concurrent renders** (edit docker-compose.yml):
```yaml
services:
  manga-agents:
    environment:
      - VIDEO_CONCURRENT_LIMIT=5
      - REMOTION_CONCURRENCY=5
```

2. **Optimize database** (run in postgres):
```sql
-- Ensure indexes exist
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_queue_status_priority 
  ON chapter_posting_queue(status, priority DESC, chapter_number ASC);

-- Analyze tables
ANALYZE chapter_posting_queue;
ANALYZE manga_chapters;
ANALYZE videos;
```

3. **Increase N8N workflow frequency** (edit workflow 02):
- Change trigger from "Every 1 hour" to "Every 30 minutes"

4. **Monitor queue depth**:
```sql
SELECT status, COUNT(*) 
FROM chapter_posting_queue 
GROUP BY status;
```

If queue depth grows too large (>500 pending), consider:
- Increasing concurrent renders
- Running multiple instances of workflow 02
- Optimizing video rendering settings

---

## Rollback Plan

If you need to rollback to the old system:

```bash
# Stop containers
docker compose down

# Checkout previous version
git checkout <previous-commit>

# Rebuild
docker compose build --no-cache
docker compose up -d

# Restore database (if needed)
# You'll need a backup from before the migration
```

**Note:** The new tables won't interfere with the old system, so you can keep them in the database.

---

## Next Steps

1. **Monitor for 24 hours** - Watch queue processing and video generation
2. **Test manual selection** - Queue a few chapters manually to verify webhook works
3. **Check caption quality** - Review generated captions and hashtags
4. **Measure throughput** - Track videos/day to ensure hitting 90+ target
5. **Optimize as needed** - Adjust concurrent limits, workflow frequency, etc.

For detailed technical information, see:
- `TECHNICAL_GUIDE.md` - Architecture and API documentation
- `PERFORMANCE_TESTING.md` - Performance testing guide
- `README.md` - Quick start and overview

---

## Support

If you encounter issues:
1. Check logs: `docker compose logs -f manga-agents`
2. Verify database: `docker compose exec postgres psql -U manga_user -d manga_automation`
3. Test endpoints: Use curl commands from this guide
4. Review error messages in N8N workflows

Common issues are documented in the Troubleshooting section above.
