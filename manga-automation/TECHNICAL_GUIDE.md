# Manga Automation — Technical Guide

> Reference for coding agents & developers maintaining the manga-to-video pipeline.

## Architecture Overview

```
n8n (cron)
  │
  ├─► TrendDetector Agent  → manga table
  ├─► /pipeline/populate-queue → chapter_posting_queue (all chapters)
  ├─► /pipeline/render-video (Remotion) → videos
  ├─► /captions/generate → viral captions + strategic hashtags
  └─► upload_tiktok.py (Playwright) → TikTok

n8n (webhook)
  └─► /webhook/queue-chapter → manual chapter selection
```

### Services

| Service | Port | Purpose |
|---|---|---|
| PostgreSQL 15 | 5434 | Primary database |
| Redis 7 | 6380 | API cache |
| manga-agents | 3001 | Mastra AI agents + Remotion renderer |
| python-worker | 8080 | Scraping, upload, analytics |
| n8n | 5679 | Workflow orchestrator |

---

## Queue System Architecture

The system now uses a database-backed queue to systematically post all manga chapters in chronological order, scaling from 20 videos/week to 630+ videos/week (90/day).

### Core Concept

Instead of waiting for new chapter releases, the system:
1. Fetches **all available chapters** for a manga (regardless of publication date)
2. Queues them in **oldest-to-latest order** (by chapter_number)
3. Posts them systematically with **priority-based ordering**
4. Tracks status to **prevent duplicate posting**

### Database Schema

#### chapter_posting_queue

Primary queue table that tracks which chapters should be posted and in what order.

```sql
CREATE TABLE chapter_posting_queue (
    id SERIAL PRIMARY KEY,
    manga_id INTEGER NOT NULL REFERENCES manga(id),
    chapter_id INTEGER NOT NULL REFERENCES manga_chapters(id),
    chapter_number TEXT NOT NULL,
    priority INTEGER DEFAULT 0,              -- Higher = posted first
    status VARCHAR(20) DEFAULT 'pending',    -- pending/processing/posted/failed
    scheduled_for TIMESTAMP,                 -- Optional scheduled posting time
    posted_at TIMESTAMP,                     -- When video was posted
    video_id INTEGER REFERENCES videos(id),  -- Generated video reference
    part_number INTEGER DEFAULT 1,           -- For split chapters
    total_parts INTEGER DEFAULT 1,           -- Total parts if split
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(chapter_id, part_number)
);

CREATE INDEX idx_queue_status_priority 
    ON chapter_posting_queue(status, priority DESC, chapter_number ASC);
```

**Key Features:**
- **Unique constraint** on `(chapter_id, part_number)` prevents duplicates
- **Priority ordering** allows manual chapters to jump the queue
- **Status tracking** enables workflow coordination
- **Part support** for chapters split into multiple videos

#### video_templates

Stores predefined video styles and effect configurations.

```sql
CREATE TABLE video_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    panel_duration INTEGER DEFAULT 4,        -- Seconds per panel
    transition_type VARCHAR(50) DEFAULT 'crossfade',
    transition_duration DECIMAL(3,2) DEFAULT 0.5,
    effects_config JSONB,                    -- Zoom, pan, color grading
    usage_count INTEGER DEFAULT 0,
    avg_views DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Example effects_config:**
```json
{
  "zoomIntensity": 1.2,
  "panDirection": "random",
  "colorGrading": "desaturated",
  "overlayEffects": ["vignette"]
}
```

#### caption_templates

Viral caption formulas with emoji suggestions.

```sql
CREATE TABLE caption_templates (
    id SERIAL PRIMARY KEY,
    formula_type VARCHAR(50) NOT NULL,
    template TEXT NOT NULL,
    emoji_suggestions TEXT[],
    usage_count INTEGER DEFAULT 0,
    avg_engagement DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Formula Types:**
- `emotional_hook` - "This scene from {manga} broke me {emoji}"
- `question` - "Who's your favorite character in {manga}? {emoji}"
- `relatable` - "POV: You just finished {manga} chapter {chapter} {emoji}"
- `recommendation` - "You NEED to read {manga} {emoji}"
- `statement_emoji` - "{manga} chapter {chapter} hits different {emoji}"

#### hashtags

Strategic hashtag database with tiered classification.

```sql
CREATE TABLE hashtags (
    id SERIAL PRIMARY KEY,
    tag VARCHAR(100) UNIQUE NOT NULL,
    tier INTEGER NOT NULL,                   -- 1=mega, 2=core, 3=niche, 4=specific
    category VARCHAR(50),                    -- action, romance, comedy, etc.
    views_estimate BIGINT,
    usage_count INTEGER DEFAULT 0,
    avg_views DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Tier System:**
- **Tier 1 (Mega)** - #fyp, #foryou (1B+ views)
- **Tier 2 (Core)** - #manga, #anime, #animetiktok (10M-100M views)
- **Tier 3 (Niche)** - #shonen, #mangarecommendation (1M-10M views)
- **Tier 4 (Specific)** - #onepiece, #naruto (100K-1M views)

### Queue Manager Component

TypeScript class that manages queue operations.

**Key Methods:**

```typescript
// Populate queue with all chapters for a manga
async populateQueue(mangaId: number): Promise<QueueEntry[]>

// Get next chapter to post (priority DESC, chapter_number ASC)
async getNextChapter(): Promise<QueueEntry | null>

// Add chapter with priority (for manual selection)
async addChapterWithPriority(
  mangaId: number, 
  chapterNumber: string, 
  priority: number
): Promise<QueueEntry>

// Update queue entry status
async updateStatus(
  queueId: number, 
  status: QueueStatus, 
  videoId?: number
): Promise<void>

// Add bulk chapters (for chapter ranges)
async addChapterRange(
  mangaId: number, 
  startChapter: string, 
  endChapter: string, 
  priority: number
): Promise<QueueEntry[]>
```

**Selection Algorithm:**
1. Query `chapter_posting_queue` WHERE `status = 'pending'`
2. Order by `priority DESC, chapter_number ASC`
3. Return first entry
4. If no pending entries, return null

**Idempotency:**
- When adding a chapter already in queue, update its priority instead of creating duplicate
- Unique constraint on `(chapter_id, part_number)` enforces this at DB level

### Chapter Analyzer Component

Determines if chapters need splitting based on panel count.

**Splitting Logic:**

```typescript
interface VideoSplitPlan {
  chapterId: number;
  totalPanels: number;
  videoCount: number;
  splits: VideoSegment[];
}

interface VideoSegment {
  partNumber: number;
  startPanel: number;
  endPanel: number;
  estimatedDuration: number;
  splitReason: 'scene_change' | 'dramatic_moment' | 'panel_limit' | 'duration_limit';
}
```

**Rules:**
- Target duration: 60-180 seconds (1-3 minutes)
- Estimate ~4 seconds per panel with transitions
- If chapter has >30 panels, split into multiple videos
- Prioritize splitting at scene changes or dramatic moments
- Create multiple queue entries with `part_number` and `total_parts`

**Example:**
- Chapter with 50 panels → Split into 2 videos
  - Part 1: Panels 1-25 (100 seconds)
  - Part 2: Panels 26-50 (100 seconds)
- Queue entries: "Chapter 42 - Part 1", "Chapter 42 - Part 2"

---

## API Endpoints

### Queue Management

#### POST /pipeline/populate-queue

Populate queue with all chapters for a manga.

**Request:**
```json
{
  "manga_id": 1
}
```

**Response:**
```json
{
  "success": true,
  "queued_count": 45,
  "queue_ids": [1, 2, 3, ...],
  "manga_title": "One Piece"
}
```

**Behavior:**
- Fetches all chapters for the manga from `manga_chapters` table
- Creates queue entries in chronological order (oldest first)
- Skips chapters already in queue (unique constraint)
- Returns count and IDs of queued chapters

#### POST /webhook/queue-chapter

Manually queue specific chapters with high priority.

**Request (Single Chapter):**
```json
{
  "manga_id": 1,
  "chapter_number": "42",
  "priority": 100
}
```

**Request (Chapter Range):**
```json
{
  "manga_id": 1,
  "start_chapter": "1",
  "end_chapter": "10",
  "priority": 100
}
```

**Response:**
```json
{
  "success": true,
  "queued_count": 1,
  "queue_ids": [123],
  "queue_position": 5
}
```

**Behavior:**
- Validates manga_id and chapter_number exist
- Default priority: 100 (higher than automatic queue entries at 0)
- If chapter already in queue, updates priority instead of creating duplicate
- Returns queue position based on current priority ordering
- Supports bulk queuing for chapter ranges

#### POST /pipeline/render-video

Generate video from queue entry using Remotion.

**Request:**
```json
{
  "queueId": 123,
  "templateId": 2,
  "randomTemplate": false
}
```

**Response:**
```json
{
  "success": true,
  "videoId": 456,
  "filePath": "/data/videos/manga_1_chapter_42_part_1.mp4",
  "durationSecs": 75,
  "fileSizeMb": 12.5,
  "template": "Character Edit"
}
```

**Workflow:**
1. Query queue entry by `queueId`
2. Update status to 'processing'
3. Fetch chapter panels from `manga_chapters`
4. Analyze if chapter needs splitting (ChapterAnalyzer)
5. Select video template (random or specified)
6. Generate Remotion composition with effects
7. Render video using Remotion
8. Insert video record into `videos` table
9. Update queue entry: status='posted', video_id, posted_at
10. Return video details

### Caption & Hashtag Generation

#### POST /captions/generate

Generate viral caption with strategic hashtags.

**Request:**
```json
{
  "videoId": 456,
  "mangaTitle": "One Piece",
  "chapterNumber": "42",
  "genre": "action",
  "formulaType": "emotional_hook"
}
```

**Response:**
```json
{
  "success": true,
  "caption": "This scene from One Piece broke me 💔😭",
  "hashtags": ["#fyp", "#manga", "#anime", "#shonen", "#onepiece"],
  "formula": "emotional_hook",
  "emojis": ["💔", "😭"]
}
```

**Behavior:**
- Selects caption formula (random if not specified)
- Replaces template variables: `{manga}`, `{chapter}`, `{genre}`
- Selects 1-3 emojis from template suggestions
- Calls hashtag selector for strategic combination
- Updates `videos` table with caption and hashtags
- Returns generated caption and hashtags

#### GET /hashtags/select

Get strategic hashtag combination.

**Request:**
```
GET /hashtags/select?mangaTitle=One%20Piece&genre=action&emotionalTone=intense&isRecommendation=false
```

**Response:**
```json
{
  "success": true,
  "hashtags": ["#fyp", "#manga", "#anime", "#shonen", "#onepiece"],
  "composition": {
    "mega": ["#fyp"],
    "core": ["#manga", "#anime"],
    "niche": ["#shonen"],
    "specific": ["#onepiece"]
  }
}
```

**Selection Algorithm:**
1. Select exactly 1 mega hashtag (tier 1) randomly
2. Select 2-3 core hashtags (tier 2), always include #manga
3. Select 1-2 niche/specific hashtags (tier 3-4) based on genre and manga title
4. Total: 3-5 hashtags
5. Return hashtag array and composition breakdown

---

## TikTok CRP Requirements (2026)

| Requirement | Value |
|---|---|
| Minimum duration | **60 seconds** |
| Originality | Must be original content (not re-upload) |
| Qualified views | From unique, real accounts in eligible regions |
| RPM range | $0.20–$1.00+ depending on retention |

**Our target: 10 panels × 8s = ~75s net after transitions.**

---

## Video Rendering (Remotion)

The renderer lives in `remotion-renderer/` and produces 1080×1920 vertical MP4s at 30fps with professional effects.

### Pipeline

1. Server receives `POST /pipeline/render-video { queueId, templateId?, randomTemplate? }`
2. Queries `chapter_posting_queue` for chapter details
3. Fetches panels from `manga_chapters` table
4. Analyzes if chapter needs splitting (ChapterAnalyzer)
5. Selects video template (from `video_templates` table)
6. Builds JSON props with panels, template config, and effects
7. Spawns `render-video.ts` with Remotion
8. Remotion renders via Chrome Headless Shell
9. Output MP4 inserted into `videos` table
10. Queue entry updated: status='posted', video_id, posted_at

### Components

| Component | Purpose |
|---|---|
| `MangaRecap.tsx` | Root composition: TransitionSeries + audio |
| `KenBurnsPanel.tsx` | CSS transform Ken Burns effects (zoom + pan) |
| `TitleOverlay.tsx` | Fade-in/hold/fade-out title card |

### Video Templates

Templates define video style, timing, and effects:

| Template | Type | Panel Duration | Transition | Effects |
|---|---|---|---|---|
| Emotional Scene | emotional_scene | 5s | crossfade | Slow zoom (1.15x), desaturated |
| Character Edit | character_edit | 3s | slide | Dynamic zoom (1.3x), vignette |
| Manga Recommendation | recommendation | 4s | zoom | Moderate zoom (1.2x) |
| Panel Appreciation | panel_appreciation | 8s | zoom | Intense zoom (1.4x) |
| Fast Paced Action | character_edit | 2s | wipe | Quick zoom (1.25x), motion blur |

**Template Selection:**
- If `templateId` specified, use that template
- If `randomTemplate=true`, select random template from database
- Otherwise, use default template (Emotional Scene)

### Motion Types

Each panel can have a motion type that defines its animation:

| Type | Effect | CSS Transform | Best for |
|---|---|---|---|
| `zoom_center` | Scale 1.0→1.25 | `scale(${interpolate(...)})` | Character reveals, close-ups |
| `pan_right` | Horizontal drift | `translateX(${interpolate(...)})` | Action scenes, wide panels |
| `pan_up` | Vertical drift | `translateY(${interpolate(...)})` | Establishing shots, tall scenes |
| `pan_down` | Vertical drift reverse | `translateY(${interpolate(...)})` | Dramatic reveals |

**Implementation:**
```typescript
const scale = interpolate(frame, [0, fps * duration], [1.0, 1.25]);
const translateX = interpolate(frame, [0, fps * duration], [0, -100]);

<Img
  src={panel.imageUrl}
  style={{
    transform: `scale(${scale}) translateX(${translateX}px)`,
    width: '100%',
    height: '100%',
    objectFit: 'cover'
  }}
/>
```

### Chapter Splitting

When a chapter has too many panels for one video:

**Rules:**
- Target duration: 60-180 seconds (1-3 minutes)
- Estimate ~4 seconds per panel with transitions
- If chapter has >30 panels, split into multiple videos
- Prioritize splitting at scene changes or dramatic moments

**Process:**
1. ChapterAnalyzer determines split points
2. Creates multiple queue entries with `part_number` and `total_parts`
3. Each part rendered as separate video
4. Queue entries labeled: "Chapter 42 - Part 1", "Chapter 42 - Part 2"

**Example:**
- Chapter with 50 panels → 2 videos
  - Part 1: Panels 1-25 (100 seconds)
  - Part 2: Panels 26-50 (100 seconds)

---

## AI Agents

### Panel Selector

- Analyses up to 15 evenly-spaced panels via Claude Vision
- Selects top 10 by engagement score
- Outputs: `score`, `emotion`, `motionType`, `audioMood`
- Motion types inform Remotion rendering
- Audio mood informs music selection

### Caption Generator

Generates viral captions using proven formulas with emoji integration.

**Formula Types:**

1. **Emotional Hook** - "This scene from {manga} broke me 💔"
   - Best for: Sad/dramatic scenes
   - Emojis: 💔, 😭, 😢, 🥺

2. **Question** - "Who's your favorite character in {manga}? 🤔"
   - Best for: Character-focused content
   - Emojis: 🤔, ❤️, 👇, 💭
   - Drives comment engagement

3. **Relatable** - "POV: You just finished {manga} chapter {chapter} 😱"
   - Best for: Cliffhangers, plot twists
   - Emojis: 😱, 🤯, 😭, 💀

4. **Recommendation** - "You NEED to read {manga} 🔥"
   - Best for: Introducing new manga
   - Emojis: 🔥, 📚, 💯, 📖

5. **Statement + Emoji** - "{manga} chapter {chapter} hits different 💯"
   - Best for: General content
   - Emojis: 🔥, 💯, 😤, ✨

**Generation Process:**
1. Select formula (random or specified by `formulaType`)
2. Replace template variables: `{manga}`, `{chapter}`, `{genre}`, `{emotion}`
3. Select 1-3 emojis from template suggestions
4. Call hashtag selector for strategic combination
5. Combine caption + hashtags
6. Update `videos` table

**Example Output:**
```
Caption: "This scene from One Piece broke me 💔😭"
Hashtags: #fyp #manga #anime #shonen #onepiece
```

### Hashtag Selector

Uses the **3-5 Rule** tiered hashtag architecture for maximum reach:

**Tier System:**
- **Tier 1 (Mega)** - 1 hashtag - #fyp, #foryou (1B+ views)
- **Tier 2 (Core)** - 2-3 hashtags - #manga, #anime, #animetiktok (10M-100M views)
- **Tier 3 (Niche)** - 1-2 hashtags - #shonen, #mangarecommendation (1M-10M views)
- **Tier 4 (Specific)** - 0-1 hashtag - #onepiece, #naruto (100K-1M views)

**Selection Algorithm:**
1. Pick 1 random mega hashtag (tier 1)
2. Pick 2-3 core hashtags (tier 2), always include #manga
3. Pick 1-2 niche/specific hashtags (tier 3-4) based on:
   - Genre (action → #shonen, romance → #shoujo)
   - Manga title (One Piece → #onepiece)
   - Emotional tone (sad → #emotional, exciting → #hype)
   - Content type (recommendation → #mangarecommendation)
4. Total: 3-5 hashtags

**Example Combinations:**
- Action manga: `#fyp #manga #anime #shonen #onepiece`
- Romance manga: `#foryou #manga #animetiktok #romance #shoujo`
- Recommendation: `#fyp #manga #mangarecommendation #mustread`

**Anti-spam Rules:**
- Never use generic spam tags like #viral, #trending
- Avoid overused tags that don't add value
- Focus on discoverability + relevance

Caption must end with an engagement-trigger **question** for comment velocity.

---

## N8N Workflows

The system uses 5 n8n workflows for automation:

### 01_trend_detection.json

**Trigger:** Cron (every 4 hours)

**Flow:**
1. Call `POST /agents/detect-trends` to fetch trending manga from MangaDex
2. Upsert manga into `manga` table
3. Call `POST /pipeline/populate-queue` to queue all chapters for each manga
4. Log results

**Key Changes:**
- Now uses MangaDex API instead of MyAnimeList
- Calls populate-queue endpoint after upserting manga
- Removed "Has New Chapters?" condition (posts all chapters, not just new ones)

### 02_video_generation.json

**Trigger:** Cron (every 1 hour) or manual

**Flow:**
1. Query `chapter_posting_queue` WHERE status='pending' ORDER BY priority DESC, chapter_number ASC LIMIT 1
2. Update queue entry status to 'processing'
3. Call `POST /pipeline/render-video` with queueId
4. On success: Update queue entry status to 'posted', set video_id and posted_at
5. On error: Update queue entry status to 'failed', log error

**Key Changes:**
- Queries `chapter_posting_queue` instead of `selected_panels`
- Updates queue status at each stage
- Handles split chapters (multiple queue entries per chapter)

### 03_publisher.json

**Trigger:** Cron (every 2 hours) or manual

**Flow:**
1. Query `videos` WHERE caption IS NULL AND file_path IS NOT NULL LIMIT 1
2. Call `POST /captions/generate` with videoId
3. Call `POST /pipeline/mark-published` after TikTok upload
4. Log results

**Key Changes:**
- Uses new viral caption formulas
- Uses tiered hashtag system
- Maintains compatibility with existing TikTok uploader

### 04_shadow_ban_monitor.json

**Trigger:** Cron (every 6 hours)

**Flow:**
1. Call `POST /agents/detect-shadow-ban`
2. Query `GET /pipeline/shadow-banned-accounts`
3. Pause banned accounts (set account_status='paused')
4. Send notification to monitoring channel

**No changes** - existing workflow still works

### 05_manual_chapter_selection.json

**Trigger:** Webhook (POST request)

**Flow:**
1. Receive webhook with manga_id, chapter_number, priority
2. Call `POST /webhook/queue-chapter` to add chapter to queue
3. Trigger `02_video_generation.json` workflow
4. Return success response

**New workflow** - enables manual chapter queuing via webhook

**Example Webhook Call:**
```bash
curl -X POST https://your-n8n-instance.com/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{"manga_id": 1, "chapter_number": "42", "priority": 100}'
```

---

## Key Files

| File | Purpose |
|---|---|
| `remotion-renderer/src/MangaRecap.tsx` | Video composition with TransitionSeries |
| `remotion-renderer/src/KenBurnsPanel.tsx` | Ken Burns effects (zoom + pan) |
| `remotion-renderer/src/render-video.ts` | CLI render script |
| `mastra-agents/src/server.ts` | Express API + all endpoints |
| `mastra-agents/src/agents/panelSelector.ts` | Claude Vision panel scoring |
| `mastra-agents/src/agents/captionGenerator.ts` | Caption + hashtag generation |
| `mastra-agents/src/components/QueueManager.ts` | Queue management logic |
| `mastra-agents/src/components/ChapterAnalyzer.ts` | Chapter splitting logic |
| `mastra-agents/src/components/CaptionGenerator.ts` | Viral caption formulas |
| `mastra-agents/src/components/HashtagSelector.ts` | Tiered hashtag selection |
| `database/schema.sql` | Database schema with queue tables |
| `n8n-workflows/01_trend_detection.json` | Trend detection + queue population |
| `n8n-workflows/02_video_generation.json` | Video generation from queue |
| `n8n-workflows/03_publisher.json` | Caption generation + TikTok upload |
| `n8n-workflows/04_shadow_ban_monitor.json` | Shadow ban detection |
| `n8n-workflows/05_manual_chapter_selection.json` | Manual chapter queuing webhook |
| `scripts/generate_video.py` | Python entry point (calls Remotion) |
| `scripts-bash/generate_manga_video.sh` | **DEPRECATED** FFmpeg fallback |

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `VIDEOS_DIR` | `/data/videos` | Video output directory |
| `PANELS_DIR` | `/data/panels` | Panel image storage |
| `MANGA_AGENTS_URL` | `http://localhost:3001` | Agents server URL |
| `VIDEO_MIN_DURATION_SECONDS` | `60` | Minimum video duration |
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `DATABASE_URL` | — | PostgreSQL connection string |

---

## Deployment

```bash
# Build and start all services
docker compose up -d --build

# Verify health
curl http://localhost:3001/health
curl http://localhost:8080/health

# Test render endpoint
curl -X POST http://localhost:3001/pipeline/render-video \
  -H "Content-Type: application/json" \
  -d '{"queueId": 1, "randomTemplate": true}'

# Test queue population
curl -X POST http://localhost:3001/pipeline/populate-queue \
  -H "Content-Type: application/json" \
  -d '{"manga_id": 1}'

# Test manual chapter selection
curl -X POST http://localhost:3001/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{"manga_id": 1, "chapter_number": "42", "priority": 100}'

# Test caption generation
curl -X POST http://localhost:3001/captions/generate \
  -H "Content-Type: application/json" \
  -d '{"videoId": 1, "mangaTitle": "One Piece", "genre": "action"}'

# Test hashtag selection
curl "http://localhost:3001/hashtags/select?mangaTitle=One%20Piece&genre=action"
```

---

## Testing

### Unit Tests

```bash
# Run all tests
cd mastra-agents
npm test

# Run specific test file
npm test -- QueueManager.test.ts

# Run with coverage
npm test -- --coverage
```

### Property-Based Tests

Property tests verify universal correctness properties across 100+ random inputs:

```bash
# Run property tests
npm test -- --testNamePattern="Property"

# Run specific property test
npm test -- --testNamePattern="Property 2: Chronological queue ordering"
```

**Key Properties:**
- Property 1: Complete chapter retrieval
- Property 2: Chronological queue ordering
- Property 3: Posted status prevents reposting
- Property 6: Unique chapter constraint
- Property 7: Priority-based ordering
- Property 12: Video format compliance
- Property 20: Hashtag composition compliance

### Integration Tests

```bash
# Run end-to-end integration tests
npm test -- integration.test.ts

# Test complete workflow
npm test -- --testNamePattern="end-to-end"
```

---

## Monitoring

### Queue Status Queries

```sql
-- Current queue status
SELECT 
    status,
    COUNT(*) as count,
    MIN(chapter_number) as oldest_chapter,
    MAX(chapter_number) as newest_chapter
FROM chapter_posting_queue
GROUP BY status;

-- Next chapters to post
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

-- Queue processing rate (last 24 hours)
SELECT 
    DATE_TRUNC('hour', posted_at) as hour,
    COUNT(*) as videos_posted
FROM chapter_posting_queue
WHERE posted_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;

-- Failed queue entries
SELECT 
    cpq.id,
    m.title,
    cpq.chapter_number,
    cpq.status,
    cpq.updated_at
FROM chapter_posting_queue cpq
JOIN manga m ON cpq.manga_id = m.id
WHERE cpq.status = 'failed'
ORDER BY cpq.updated_at DESC;
```

### Performance Metrics

```sql
-- Video generation success rate (last 7 days)
SELECT
    DATE(posted_at) AS date,
    COUNT(*) FILTER (WHERE status = 'posted') AS successful,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'posted') / NULLIF(COUNT(*), 0), 2) AS success_rate_pct
FROM chapter_posting_queue
WHERE posted_at > NOW() - INTERVAL '7 days' OR updated_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(posted_at)
ORDER BY date DESC;

-- Template usage and performance
SELECT 
    vt.name,
    vt.type,
    COUNT(v.id) as usage_count,
    AVG(va.views) as avg_views,
    AVG(va.retention_rate) as avg_retention
FROM video_templates vt
LEFT JOIN videos v ON v.template_id = vt.id
LEFT JOIN video_analytics va ON va.video_id = v.id
GROUP BY vt.id, vt.name, vt.type
ORDER BY avg_views DESC;

-- Caption formula performance
SELECT 
    ct.formula_type,
    COUNT(v.id) as usage_count,
    AVG(va.likes) as avg_likes,
    AVG(va.comments) as avg_comments
FROM caption_templates ct
LEFT JOIN videos v ON v.caption LIKE '%' || ct.template || '%'
LEFT JOIN video_analytics va ON va.video_id = v.id
GROUP BY ct.formula_type
ORDER BY avg_likes DESC;

-- Hashtag performance
SELECT 
    h.tag,
    h.tier,
    h.usage_count,
    h.avg_views
FROM hashtags h
ORDER BY h.avg_views DESC
LIMIT 20;
```

### Alerting Rules

Monitor these metrics and alert if thresholds are exceeded:

- Queue processing stops for >30 minutes
- Video generation failure rate >10%
- API error rate >5%
- Database connection failures
- Disk space <20% free
- Memory usage >90%
- Queue size >1000 pending entries

---

## Troubleshooting

### Queue Not Processing

**Symptoms:** No videos being generated, queue status stuck at 'pending'

**Checks:**
1. Verify n8n workflow `02_video_generation.json` is active
2. Check queue for pending entries: `SELECT * FROM chapter_posting_queue WHERE status='pending' LIMIT 10`
3. Check for failed entries: `SELECT * FROM chapter_posting_queue WHERE status='failed'`
4. Verify Remotion renderer is running: `curl http://localhost:3001/health`

**Solutions:**
- Restart n8n workflow
- Reset failed entries: `UPDATE chapter_posting_queue SET status='pending' WHERE status='failed'`
- Check logs: `docker compose logs manga-agents`

### Video Generation Failures

**Symptoms:** Queue entries stuck at 'processing' or marked as 'failed'

**Checks:**
1. Check video generation logs: `docker compose logs manga-agents | grep render-video`
2. Verify panel images exist: `SELECT * FROM manga_chapters WHERE id=<chapter_id>`
3. Check disk space: `df -h`
4. Verify Remotion dependencies: `cd remotion-renderer && npm list`

**Solutions:**
- Retry failed entries: `UPDATE chapter_posting_queue SET status='pending' WHERE id=<queue_id>`
- Re-download panels: `POST /pipeline/fetch-chapters`
- Clear old videos: `rm -rf /data/videos/*.mp4`

### Caption Generation Issues

**Symptoms:** Videos have no captions or generic captions

**Checks:**
1. Verify caption templates exist: `SELECT * FROM caption_templates`
2. Verify hashtags exist: `SELECT * FROM hashtags`
3. Check caption generation logs: `docker compose logs manga-agents | grep captions`

**Solutions:**
- Seed caption templates: Run seed data SQL from schema
- Seed hashtags: Run seed data SQL from schema
- Regenerate caption: `POST /captions/generate` with videoId

### Manual Chapter Selection Not Working

**Symptoms:** Webhook returns error or chapter not added to queue

**Checks:**
1. Verify manga_id exists: `SELECT * FROM manga WHERE id=<manga_id>`
2. Verify chapter exists: `SELECT * FROM manga_chapters WHERE manga_id=<manga_id> AND chapter_number='<chapter_number>'`
3. Check webhook logs: `docker compose logs manga-agents | grep webhook`

**Solutions:**
- Fetch chapters first: `POST /pipeline/fetch-chapters`
- Check chapter number format (should be string, e.g., "42" not 42)
- Verify priority is integer (default: 100)


