# Manga TikTok Automation System

Fully automated pipeline that fetches trending manga from MangaDex, systematically posts all chapters in chronological order, generates professional vertical TikTok videos with Remotion effects, and publishes them with viral captions and strategic hashtags — all orchestrated by n8n.

**New Features:**
- **Queue-based chapter posting** - Posts all manga chapters oldest-to-latest (90+ videos/day)
- **Manual chapter selection** - Webhook endpoint for on-demand chapter queuing
- **Enhanced video generation** - Remotion-powered videos with Ken Burns effects and smooth transitions
- **Viral caption system** - 5 proven caption formulas with emoji integration
- **Strategic hashtag selection** - Tiered hashtag system (mega/core/niche) for maximum reach

## Architecture

```
n8n (every 4h)
  │
  ├─► TrendDetector Agent  → manga table
  ├─► /pipeline/populate-queue → chapter_posting_queue (all chapters)
  ├─► /pipeline/render-video → Remotion videos with effects
  ├─► /captions/generate → viral captions + strategic hashtags
  └─► Python: upload_tiktok.py (Playwright) → TikTok

n8n (every 6h)
  └─► ShadowBanDetector Agent → pause banned accounts

n8n (webhook)
  └─► /webhook/queue-chapter → manual chapter selection
```

### Services

| Service | Port | Purpose |
|---|---|---|
| PostgreSQL | 5434 | Primary database |
| Redis | 6380 | API response cache |
| manga-agents | 3001 | Mastra AI agents (Node 20) |
| python-worker | 8080 | Python scripts (FFmpeg + Playwright) |
| n8n | 5679 | Workflow orchestrator |

## Quick Start

### 1. Prerequisites
- Docker + Docker Compose
- An Anthropic API key

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env and fill in your values (at minimum ANTHROPIC_API_KEY and DB_PASSWORD)
```

### 3. Start All Services
```bash
docker compose up -d
```

### 4. Verify Everything is Running
```bash
# Check health
curl http://localhost:3001/health        # manga-agents
curl http://localhost:8080/health        # python-worker

# Open n8n
open http://localhost:5679              # admin / <N8N_PASSWORD>
```

### 5. Import n8n Workflows
In the n8n UI (http://localhost:5679):
1. Settings → Import from File
2. Import workflow files from `n8n-workflows/` in order:
   - `01_trend_detection.json` - Fetches trending manga and populates queue
   - `02_video_generation.json` - Renders videos from queue with Remotion
   - `03_publisher.json` - Generates captions/hashtags and uploads to TikTok
   - `04_shadow_ban_monitor.json` - Monitors accounts for shadow bans
   - `05_manual_chapter_selection.json` - Webhook for manual chapter queuing
   - `06_arbitrage_pipeline.json` - Full arbitrage trend->source->download->multi-platform distribution
   - `10_balanced_multiplatform_schedule.json` - Balanced TikTok/YouTube/Instagram/Facebook/Pinterest cadence
   - `11_monetization_weekly_optimization.json` - Weekly KPI evaluation and allocation optimization
3. In each workflow, update the **PostgreSQL credential** to point to `postgres:5432` with your `DB_PASSWORD`
4. Activate all workflows

### 6. Add TikTok Accounts
```sql
-- Connect to DB
docker compose exec postgres psql -U manga_user -d manga_automation

-- Add your TikTok account
INSERT INTO tiktok_accounts (username, account_status)
VALUES ('your_tiktok_username', 'active');
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `DB_PASSWORD` | Yes | — | PostgreSQL password |
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `TIKTOK_EMAIL` | Yes | — | TikTok account email |
| `TIKTOK_PASSWORD` | Yes | — | TikTok account password |
| `N8N_PASSWORD` | Yes | — | n8n admin password |
| `REDIS_URL` | No | `redis://localhost:6380` | Redis URL |
| `PANELS_DIR` | No | `/data/panels` | Panel image storage |
| `VIDEOS_DIR` | No | `/data/videos` | Video output directory |
| `LOGS_DIR` | No | `/data/logs` | Log file directory |
| `MAX_UPLOADS_PER_ACCOUNT_DAY` | No | `3` | Daily upload limit per account |
| `DUPLICATE_MAX_USES` | No | `5` | Max times a panel can be reused |
| `VIDEO_MIN_DURATION_SECONDS` | No | `60` | Minimum video length |
| `SHADOW_BAN_FYP_THRESHOLD` | No | `0.10` | FYP% below which = shadow ban |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token for remote control/reporting |
| `TELEGRAM_ALLOWED_CHAT_IDS` | No | empty (allow all) | Comma-separated chat IDs allowed to use bot commands |
| `TELEGRAM_POLL_INTERVAL` | No | `2` | Long-poll retry delay (seconds) for Telegram bot |
| `LAST30DAYS_COMMAND_TEMPLATE` | No | `last30days "{query}"` | Wrapper command used to invoke the installed last30days skill |
| `LAST30DAYS_DEFAULT_QUERIES` | No | empty | Default scheduled research queries separated by new lines or `||` |
| `LAST30DAYS_REGION` | No | `US` | Region label used when persisting research runs |
| `LAST30DAYS_SCHEDULE_SECONDS` | No | `21600` | Scheduled ingest interval for last30days runner |
| `DEERFLOW_URL` | No | `http://localhost:2026` | DeerFlow base URL used by worker/Telegram hybrid commands |
| `DEERFLOW_GATEWAY_URL` | No | `http://localhost:2026/api` | DeerFlow gateway API URL |
| `DEERFLOW_LANGGRAPH_URL` | No | `http://localhost:2026/api/langgraph` | DeerFlow LangGraph API URL |
| `DEERFLOW_MODEL_NAME` | No | empty | Optional DeerFlow model override for hybrid planning commands |
| `SUMMON_BACKEND` | No | `crewai` | Set to `deerflow` to feature-flag `/summon` over to DeerFlow |
| `ARBITRAGE_UPLOAD_RETRIES` | No | `2` | Max retries per platform upload in arbitrage distribution |
| `ARBITRAGE_UPLOAD_RETRY_DELAY_SECONDS` | No | `8` | Delay between upload retries |
| `INSTAGRAM_USER_ID` | No | — | Instagram Graph user id for Reels publishing |
| `INSTAGRAM_ACCESS_TOKEN` | No | — | Instagram Graph API access token |
| `FACEBOOK_PAGE_ID` | No | — | Facebook page id for Reels publishing |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | No | — | Facebook page access token |
| `PINTEREST_DEFAULT_BOARD` | No | `manga-reading-guides` | Fallback queue board for Pinterest pins |
| `PINTEREST_DEFAULT_LANDING_URL` | No | empty | Landing URL attached to Pinterest queue entries |

## Telegram Bot Control

The stack includes a `telegram-bot` service that lets you trigger pipelines and receive status reports from Telegram.

### Setup

1. Set these values in `.env`:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_ALLOWED_CHAT_IDS` (recommended for security)
2. Start or restart services:
```bash
docker compose up -d --build python-worker telegram-bot
```
3. Open your bot chat and send `/help`.

### Key Commands

- `/status` - Worker + agent health and memory summary
- `/fetch_trending 20` - Fetch trending manga
- `/generate_video <chapter_id>` - Render a video
- `/upload_tiktok <video_id>` - Upload to TikTok
- `/arb_discover US 20` - Discover arbitrage trends
- `/arb_download 10` - Download sourced assets
- `/arb_distribute tiktok,youtube 5` - Distribute downloaded assets
- `/research_topic <query>` - Run a last30days ingest query and persist hashtags/channels
- `/research_status` - Show recent last30days ingest runs
- `/plan_campaign <goal>` - Ask DeerFlow for a campaign plan
- `/recover_last_run` - Ask DeerFlow to propose recovery steps from recent DB failures
- `/deerflow <prompt>` - Send an ad hoc prompt to DeerFlow
- `/summon <prompt>` - Trigger CrewAI pipeline prompt
- `/worker <path> [json]` - Direct worker endpoint control
- `/mastra <METHOD> <path> [json]` - Direct Mastra API control

## last30days Research Ingest

The stack can ingest trend research from the `last30days` skill and store structured hints in Postgres for later sourcing and caption generation.

### How it works

1. `research-scheduler` runs queries from `LAST30DAYS_DEFAULT_QUERIES`
2. `scripts/research_ingest_last30days.py` stores:
   - summary
   - confidence
   - candidate channels
   - candidate hashtags
   - evidence URLs
3. `source_youtube_assets.py` prefers these stored channel/hashtag candidates before generic searches
4. upload metadata builders reuse the ingested hashtags during caption generation

### Setup

1. Install `last30days` on the machine/container path referenced by `LAST30DAYS_COMMAND_TEMPLATE`
2. Set:
```bash
LAST30DAYS_COMMAND_TEMPLATE='last30days "{query}"'
LAST30DAYS_DEFAULT_QUERIES='best anime comedy shorts||viral manga edits'
```
3. Start the scheduler:
```bash
docker compose up -d --build research-scheduler
```

### Manual ingest

```bash
curl -X POST http://localhost:8080/research/ingest \
  -H "Content-Type: application/json" \
  -d '{"query":"best anime comedy shorts"}'
```

## DeerFlow Hybrid Mode

DeerFlow is integrated as an optional planning/research layer and does not replace the existing runtime worker in the first phase.

### What DeerFlow handles

- research-heavy prompts
- campaign planning
- recovery suggestions after failed runs
- optional feature-flagged `/summon` execution

### Start DeerFlow

The compose file includes an optional `deerflow` profile:

```bash
docker compose --profile deerflow up -d deerflow
```

### Feature flag for `/summon`

Keep the current CrewAI path:

```bash
SUMMON_BACKEND=crewai
```

Switch `/summon` to DeerFlow:

```bash
SUMMON_BACKEND=deerflow
```

## Python Scripts (Direct Usage)

All scripts can be run standalone for testing:

```bash
# Fetch trending manga and save to DB
python3 -m scripts.fetch_trending_manga --limit 20

# Fetch latest chapter for manga with db id=1
python3 -m scripts.fetch_chapter_images --manga-id 1

# Download panels for chapter id=5
python3 -m scripts.download_panels --chapter-id 5

# Check for duplicate panels
python3 -m scripts.check_duplicates --chapter-id 5

# Generate video from selected panels
python3 -m scripts.generate_video --chapter-id 5

# Upload video to TikTok
python3 -m scripts.upload_tiktok --video-id 3

# Detect shadow bans
python3 -m scripts.detect_shadow_ban --min-posts 5 --threshold 0.10
```

## Mastra Agent Endpoints

### Agent Endpoints
```
POST /agents/detect-trends        Run trend detection
POST /agents/select-panels        Body: { chapterId: N }
POST /agents/generate-caption     Body: { videoId: N }
POST /agents/optimize             Run content optimization
POST /agents/detect-shadow-ban    Run shadow ban detection
```

### Pipeline Endpoints
```
POST /pipeline/fetch-chapters     Fetch all active manga chapters
POST /pipeline/populate-queue     Body: { manga_id: N } - Queue all chapters for a manga
POST /pipeline/render-video       Body: { queueId: N, templateId?: N, randomTemplate?: boolean }
GET  /pipeline/pending-chapters   Chapters not yet panel-selected
GET  /pipeline/ready-videos       Videos ready to publish
POST /pipeline/mark-published     Body: { videoId, platform, ... }
GET  /pipeline/shadow-banned-accounts
```

### Monetization Control Endpoints (python-worker)
```
POST /monetization/kpi/evaluate   Body: { days?: 7, write_alerts?: true }
POST /monetization/weekly-plan    Body: {}
POST /monetization/snapshot       Body: { platform, metric_key, metric_value, source? }
POST /monetization/should-post-ad Body: { platform, days?: 7 }
POST /monetization/membership-cta Body: { slot_index?: 0 }
POST /monetization/high-cpm-field Body: { week_seed?: number }
POST /monetization/offer-matrix   Body: {}
POST /monetization/optimize-weekly Body: {}
```

### Trend-Driven Autopilot Endpoints (python-worker)
```
POST /autopilot/plan-content
Body: { limit?: 10, repurpose_ratio?: 0.5 }
-> returns ranked topics with mode:
   - generate_original
   - repurpose_youtube

POST /autopilot/execute-content-plan
Body: { limit?: 10, repurpose_ratio?: 0.5, batch?: 3 }
-> executes first N items:
   - repurpose items queue YouTube assets
   - original items return script/render queue payload
```

### Voiceover Endpoints (ElevenLabs + Kokoro local)
```
POST /voiceover/synthesize
Body: {
  text: string,
  provider?: "elevenlabs" | "kokoro",
  voice_id?: string,   // ElevenLabs voice id
  model_id?: string,   // provider model id
  output_path?: string
}
```
If provider is `elevenlabs` and it fails, the service can optionally fallback
to local Kokoro (`VOICE_ENABLE_FALLBACK=true`).

### Queue Management Endpoints
```
POST /webhook/queue-chapter       Body: { manga_id, chapter_number, priority? }
                                  OR { manga_id, start_chapter, end_chapter, priority? }
                                  - Manually queue specific chapters or chapter ranges
```

### Caption & Hashtag Endpoints
```
POST /captions/generate           Body: { videoId, mangaTitle?, chapterNumber?, genre?, formulaType? }
                                  - Generate viral caption with strategic hashtags
GET  /hashtags/select             Query: ?mangaTitle=...&genre=...&emotionalTone=...&isRecommendation=...
                                  - Get strategic hashtag combination (1 mega + 2-3 core + 1-2 niche)
```

## Running Tests

```bash
# From project root
pip install -r requirements.txt
pytest tests/ -v
```

## Queue System

The system now uses a database-backed queue to systematically post all manga chapters in chronological order, enabling 90+ videos per day.

### How It Works

1. **Queue Population**: When a manga is added, all chapters are queued oldest-to-latest
2. **Priority Ordering**: Chapters are selected by priority (DESC) then chapter_number (ASC)
3. **Status Tracking**: Each queue entry tracks status (pending/processing/posted/failed)
4. **Automatic Progression**: System automatically moves to next manga when all chapters are posted

### Manual Chapter Selection

Queue specific chapters on-demand via webhook:

```bash
# Queue a single chapter with high priority
curl -X POST http://localhost:3001/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{"manga_id": 1, "chapter_number": "42", "priority": 100}'

# Queue a chapter range
curl -X POST http://localhost:3001/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{"manga_id": 1, "start_chapter": "1", "end_chapter": "10", "priority": 100}'
```

Response includes queue position and IDs:
```json
{
  "success": true,
  "queued_count": 1,
  "queue_ids": [123],
  "queue_position": 5
}
```

### Database Tables

**chapter_posting_queue** - Tracks which chapters to post and in what order
- `id`, `manga_id`, `chapter_id`, `chapter_number`
- `priority` (default: 0, manual: 100)
- `status` (pending/processing/posted/failed)
- `scheduled_for`, `posted_at`, `video_id`
- `part_number`, `total_parts` (for split chapters)

**video_templates** - Predefined video styles and effects
- `name`, `type`, `panel_duration`, `transition_type`
- `effects_config` (JSON: zoom intensity, pan direction, etc.)

**caption_templates** - Viral caption formulas
- `formula_type` (emotional_hook/question/relatable/recommendation/statement_emoji)
- `template` (e.g., "This scene from {manga} broke me {emoji}")
- `emoji_suggestions`

**hashtags** - Strategic hashtag database
- `tag`, `tier` (1=mega, 2=core, 3=niche, 4=specific)
- `category`, `views_estimate`

## Video Generation

Videos are now generated using Remotion with professional effects:

### Video Templates

- **Emotional Scene** - Slow zoom with crossfade transitions (5s per panel)
- **Character Edit** - Dynamic zoom with slide transitions (3s per panel)
- **Manga Recommendation** - Moderate zoom with zoom transitions (4s per panel)
- **Panel Appreciation** - Intense zoom for single panels (8s per panel)
- **Fast Paced Action** - Quick cuts with wipe transitions (2s per panel)

### Motion Types

- `zoom_center` - Scale 1.0 → 1.25 (character reveals, close-ups)
- `pan_right` - Horizontal drift (action scenes, wide panels)
- `pan_up` - Vertical drift (establishing shots, tall scenes)
- `pan_down` - Vertical drift reverse

### Caption Formulas

1. **Emotional Hook** - "This scene from {manga} broke me 💔"
2. **Question** - "Who's your favorite character in {manga}? 🤔"
3. **Relatable** - "POV: You just finished {manga} chapter {chapter} 😱"
4. **Recommendation** - "You NEED to read {manga} 🔥📚"
5. **Statement + Emoji** - "{manga} chapter {chapter} hits different 💯"

### Hashtag Strategy

Each video gets 3-5 hashtags following the tiered system:
- **1 mega hashtag** - #fyp or #foryou
- **2-3 core hashtags** - #manga, #anime, #animetiktok
- **1-2 niche hashtags** - Genre-specific (#shonen, #romance) or manga-specific

## Running Tests

```bash
# From project root
pip install -r requirements.txt
pytest tests/ -v
```

## Monitoring Queries

```sql
-- Daily upload success rate (last 7 days)
SELECT
    DATE(uploaded_at)  AS date,
    COUNT(*) FILTER (WHERE success = true)  AS successful,
    COUNT(*) FILTER (WHERE success = false) AS failed,
    ROUND(100.0 * COUNT(*) FILTER (WHERE success = true) / NULLIF(COUNT(*), 0), 2) AS success_rate_pct
FROM upload_results
WHERE uploaded_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(uploaded_at)
ORDER BY date DESC;

-- Shadow banned accounts
SELECT username, shadow_ban_detected_at, upload_failures, account_status
FROM tiktok_accounts
WHERE shadow_banned = true;

-- Top performing videos
SELECT m.title, pv.platform_url, va.views, va.likes, va.comments
FROM video_analytics va
JOIN published_videos pv ON va.published_video_id = pv.id
JOIN videos v ON pv.video_id = v.id
JOIN manga_chapters mc ON v.chapter_id = mc.id
JOIN manga m ON mc.manga_id = m.id
ORDER BY va.views DESC
LIMIT 10;
```

## Monetization KPI Setup

Run migration `database/migrations/009_monetization_control_plane.sql` to provision:
- `monetization_kpi_thresholds` (go/warn thresholds)
- `monetization_channel_config` (platform cadence + ad-ratio controls)
- `monetization_performance_snapshots` (daily KPI values)
- `monetization_alerts` (automatic threshold violations)

Weekly optimizer flow:
1. `POST /monetization/optimize-weekly`
2. snapshots are updated for `upload_success_rate`, `error_rate`, `revenue_per_video_usd`
3. KPI evaluator emits alerts and recommends scale/cautious_scale/stabilize decisions

## Voiceover Setup

1. Set ElevenLabs keys in `.env`:
```bash
VOICE_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
```
2. Optional local Kokoro fallback:
```bash
VOICE_ENABLE_FALLBACK=true
KOKORO_RUNNER_PATH=/app/scripts/kokoro_tts_runner.mjs
KOKORO_MODEL_ID=onnx-community/Kokoro-82M-v1.0-ONNX
KOKORO_VOICE=af_sky
KOKORO_DTYPE=q8
```
3. Install `kokoro-js` where worker runs local node scripts:
```bash
npm i kokoro-js
```

## Project Structure

```
manga-automation/
├── database/schema.sql          PostgreSQL schema (all tables)
├── scripts/                     Python automation layer
│   ├── fetch_trending_manga.py  MangaDex + AniList trend fetch
│   ├── fetch_chapter_images.py  Chapter panel URL scraping
│   ├── download_panels.py       Image downloader
│   ├── check_duplicates.py      SHA-256 dedup checker
│   ├── generate_video.py        FFmpeg video builder
│   ├── upload_tiktok.py         Playwright TikTok uploader
│   ├── detect_shadow_ban.py     FYP% shadow ban detector
│   ├── worker.py                HTTP wrapper for n8n calls
│   └── utils/                   database.py, image_hash.py, logger.py
├── mastra-agents/src/           TypeScript AI agents (Mastra + Claude)
│   ├── agents/
│   │   ├── trendDetector.ts
│   │   ├── panelSelector.ts     Claude Vision panel scoring
│   │   ├── captionGenerator.ts  Viral caption generation
│   │   ├── contentOptimizer.ts  Analytics-based optimization
│   │   └── shadowBanDetector.ts Shadow ban analysis
│   ├── tools/                   database.ts, mangadex.ts, scraper.ts
│   └── server.ts                Express API server
├── n8n-workflows/               4 workflow JSON files
├── scripts-bash/                generate_manga_video.sh (FFmpeg)
├── tests/                       pytest test suite
├── docker-compose.yml           5-service Docker setup
├── Dockerfile                   Node 20 multi-stage build
└── Dockerfile.python            Python 3.11 + FFmpeg + Playwright
```
