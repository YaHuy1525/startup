# Manga TikTok Automation System

Fully automated pipeline that fetches trending manga from MangaDex, selects the best panels using Claude Vision, generates vertical TikTok videos with FFmpeg, and publishes them — all orchestrated by n8n.

## Architecture

```
n8n (every 4h)
  │
  ├─► TrendDetector Agent  → manga table
  ├─► /pipeline/fetch-chapters → download panels
  ├─► PanelSelector Agent (Claude Vision) → selected_panels
  ├─► Python: generate_video.py (FFmpeg) → videos
  ├─► CaptionGenerator Agent → caption + hashtags
  └─► Python: upload_tiktok.py (Playwright) → TikTok

n8n (every 6h)
  └─► ShadowBanDetector Agent → pause banned accounts
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
2. Import all 4 files from `n8n-workflows/` in order:
   - `01_trend_detection.json`
   - `02_video_generation.json`
   - `03_publisher.json`
   - `04_shadow_ban_monitor.json`
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

```
POST /agents/detect-trends        Run trend detection
POST /agents/select-panels        Body: { chapterId: N }
POST /agents/generate-caption     Body: { videoId: N }
POST /agents/optimize             Run content optimization
POST /agents/detect-shadow-ban    Run shadow ban detection

POST /pipeline/fetch-chapters     Fetch all active manga chapters
GET  /pipeline/pending-chapters   Chapters not yet panel-selected
GET  /pipeline/ready-videos       Videos ready to publish
POST /pipeline/mark-published     Body: { videoId, platform, ... }
GET  /pipeline/shadow-banned-accounts
```

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
