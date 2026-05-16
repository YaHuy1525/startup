# AiToEarn — AI-Powered Content Marketing Platform

Autonomous 5-stage content arbitrage pipeline: **Trend → Create → Publish → Engage → Monetize**. Detects trending topics across 8 categories (tech, gaming, finance, fiction, anime, movies, art, TikTok trending) from TikTok, X/Twitter, YouTube, and Reddit; generates original and repurposed content with AI; publishes to 40+ platforms; auto-engages via browser automation; and matches creators with CPS/CPE/CPM marketplace tasks — orchestrated by CrewAI agents.

**Pipeline Stages:**
- **Trend Detection** — Cross-platform trend discovery across all categories with velocity scoring
- **Content Creation** — AI-generated videos, captions, and scripts from trending topics
- **Publishing** — Official AiToEarn API/MCP first, local multi-platform fallback (TikTok, YouTube Shorts, Instagram, Pinterest + 40 more)
- **Engagement** — Browser-based auto-like, comment, follow, and comment mining
- **Monetization** — CPS/CPE/CPM merchant task matching and settlement tracking

## Architecture

```
AiToEarn Pipeline (5 Stages)
  │
  ├─► Stage 1: Trend Detection
  │   ├─► fetch_tiktok_trends.py → trend_intel
  │   ├─► fetch_twitter_trends.py → trend_intel
  │   ├─► fetch_youtube_trends.py → trend_intel
  │   ├─► fetch_reddit_trends.py → trend_intel + genesis_signals
  │   └─► TrendDetector Agent (Mastra) → ranked cross-domain trends
  │
  ├─► Stage 2: Content Creation
  │   ├─► trend_content_planner.py → content concepts
  │   ├─► scriptwriter.ts / captionGenerator.ts → AI scripts
  │   └─► generate_video.py / finance_video_generator.py → video assets
  │
  ├─► Stage 3: Publishing
  │   ├─► upload_tiktok.py (Playwright + curl_cffi stealth)
  │   ├─► upload_youtube.py / upload_instagram.py / upload_pinterest.py
  │   └─► omnichannel_distributor.py → 40+ platforms
  │
  ├─► Stage 4: Engagement (Browser Automation)
  │   ├─► scripts/engage/liker.py → auto-like
  │   ├─► scripts/engage/commenter.py → AI smart replies
  │   ├─► scripts/engage/follower.py → auto-follow
  │   └─► scripts/engage/comment_miner.py → signal extraction
  │
  └─► Stage 5: Monetization
      ├─► scripts/monetize/marketplace.py → merchant task matching
      └─► scripts/monetize/settlement.py → CPS/CPE/CPM earnings
```

### Services

| Service | Port | Purpose |
|---|---|---|
| PostgreSQL | 5434 | Primary database |
| Redis | 6380 | API response cache |
| manga-agents | 3001 | Mastra AI agents (Node 20) |
| python-worker | 8080 | Python scripts (FFmpeg + Playwright + CrewAI) |
| n8n | 5679 | Workflow orchestrator |
| ChromaDB | 8001 | Vector memory for trend performance |
| Dashboard | 3000 | React analytics + control panel |

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
   - `01_trend_detection.json` - Fetches trending topics and populates queue
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
| `AITOEARN_PRIMARY` | No | `false` | Enable official AiToEarn-first routing for Hermes + publish stage |
| `AITOEARN_API_KEY` | Cond. | — | `x-api-key` used against official AiToEarn endpoints |
| `AITOEARN_BASE_URL` | No | `https://aitoearn.ai` | Official AiToEarn environment base URL |
| `AITOEARN_MCP_URL` | No | `https://aitoearn.ai/api/unified/mcp` | MCP endpoint reference (global) |
| `AITOEARN_FALLBACK_LOCAL` | No | `true` | Allow local worker fallback when remote publish/stages fail |
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
| `PINTEREST_DEFAULT_BOARD` | No | `trending-content` | Fallback queue board for Pinterest pins |
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
- `/fetch_trending 20` - Fetch trending topics across categories
- `/generate_video <id>` - Render a video
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
LAST30DAYS_DEFAULT_QUERIES='viral tech innovations||trending gaming clips||finance market updates'
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
# Run full AiToEarn pipeline
python3 scripts/aitoearn_pipeline.py --once --category tech

# Run single stage
python3 scripts/aitoearn_pipeline.py --stage trend --category gaming

# Fetch trends from all platforms
python3 scripts/fetch_tiktok_trends_apify.py --region US --limit 20
python3 scripts/fetch_twitter_trends.py --region US --limit 20
python3 scripts/fetch_youtube_trends.py --region US --limit 20
python3 scripts/fetch_reddit_trends.py --category-slug tech --limit 20

# Generate video from trend
python3 -m scripts.generate_video --trend-id 5

# Upload video to TikTok
python3 -m scripts.upload_tiktok --video-id 3

# Run engagement cycle
python3 scripts/engage/engine.py --platform tiktok --mode full

# Match creator with marketplace tasks
python3 -m scripts.monetize.marketplace --creator-id 1

# Run CrewAI autonomous pipeline
python3 scripts/crew/pipeline_crew.py --prompt "Post 5 viral tech clips" --count 5
```

## AiToEarn Pipeline Endpoints (python-worker :8080)

### Full Pipeline
```
POST /aitoearn/pipeline            Body: { category?: "tech", mode?: "light"|"full" }
                                   → Runs all 5 stages: Trend → Create → Publish → Engage → Monetize
```

### Individual Stages
```
POST /aitoearn/stage/trend         Body: { category?: "tech", limit?: 10 }
POST /aitoearn/stage/create        Body: { limit?: 5 }
POST /aitoearn/stage/publish       Body: {}
POST /aitoearn/stage/engage        Body: { platform?: "tiktok" }
POST /aitoearn/stage/monetize      Body: { creator_id?: 1 }
```

### CrewAI Agent Pipeline
```
POST /api/summon-agent             Body: { prompt: "...", target_count?: 5, dry_run?: false }
                                   → 7-agent autonomous pipeline (Scout → Harvester → Operator → Analyst → Engager → Monetizer)
```

### Arbitrage Pipeline (YouTube → TikTok/YouTube Shorts)
```
POST /arbitrage/discover-trends    Body: { region?: "US", limit?: 20 }
POST /arbitrage/source-assets      Body: { limit?: 5 }
POST /arbitrage/download           Body: { batch?: 10 }
POST /arbitrage/distribute         Body: { platforms?: ["tiktok"], batch?: 5 }
```

### TikTok Uploader (option — Playwright + curl_cffi stealth)
```
POST /upload-tiktok                Body: { video_id: 1 }
POST /upload-youtube               Body: { video_id: 1 }
```

### Trend-Driven Autopilot
```
POST /autopilot/plan-content       Body: { limit?: 10, repurpose_ratio?: 0.5 }
POST /autopilot/execute-content-plan Body: { limit?: 10, repurpose_ratio?: 0.5, batch?: 3 }
```

### Legacy Manga Endpoints (deprecated — use AiToEarn pipeline instead)
```
POST /fetch-trending               Body: { limit: 20 }
POST /generate-video               Body: { chapter_id: 1 }
POST /detect-shadow-ban            Body: {}
```

### Monetization Control Endpoints
```
POST /monetization/kpi/evaluate    Body: { days?: 7, write_alerts?: true }
POST /monetization/optimize-weekly Body: {}
```

## AiToEarn-First Best Use Cases

These are the highest-value operator flows when `AITOEARN_PRIMARY=true`:

1. **Daily Revenue Loop**
   - Run once each morning to refresh trend/create/publish/engage/monetize in one pass.
   - `POST /hermes/full-ops` body: `{"category":"finance","mode":"full","profile":"minimal"}`
2. **Campaign Burst (time-boxed launch)**
   - Re-run publish + engage with strict idempotency keys for a single campaign window.
   - `POST /aitoearn/stage/publish` body: `{"profile":"full","idempotency_key":"campaign-2026-05-16"}`
3. **Recovery / Replay**
   - Keep local routes as fallback while AiToEarn remote is degraded.
   - Set `AITOEARN_FALLBACK_LOCAL=true`; rerun `/hermes/full-ops` with same `run_id`.
4. **Low-Risk Brand Protection**
   - Use light engagement mode and diagnose-only Hermes cycles.
   - `POST /hermes/full-ops` body: `{"mode":"light","engage_platform":"tiktok"}`
5. **Dry-Run Validation Before Go-Live**
   - Confirm endpoint wiring and key validity without triggering writes.
   - `POST /hermes/full-ops` body: `{"dry_run":true}`

## Running Tests

```bash
# From project root
pip install -r requirements.txt
pytest tests/ -v
```

## AiToEarn Pipeline Usage

### Run the Full Pipeline

```bash
# Full 5-stage pipeline (Trend → Create → Publish → Engage → Monetize)
curl -X POST http://localhost:8080/aitoearn/pipeline \
  -H "Content-Type: application/json" \
  -d '{"category": "tech", "mode": "full"}'

# Light mode (skips engagement)
curl -X POST http://localhost:8080/aitoearn/pipeline \
  -H "Content-Type: application/json" \
  -d '{"category": "gaming", "mode": "light"}'
```

### Run Individual Stages

```bash
# Stage 1: Detect trends for a category
curl -X POST http://localhost:8080/aitoearn/stage/trend \
  -H "Content-Type: application/json" \
  -d '{"category": "finance", "limit": 10}'

# Stage 2: Create content from top trends
curl -X POST http://localhost:8080/aitoearn/stage/create \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}'

# Stage 3: Publish ready videos
curl -X POST http://localhost:8080/aitoearn/stage/publish \
  -H "Content-Type: application/json" \
  -d '{}'

# Stage 4: Run engagement cycle
curl -X POST http://localhost:8080/aitoearn/stage/engage \
  -H "Content-Type: application/json" \
  -d '{"platform": "tiktok"}'

# Stage 5: Monetization matching
curl -X POST http://localhost:8080/aitoearn/stage/monetize \
  -H "Content-Type: application/json" \
  -d '{"creator_id": 1}'
```

### TikTok Uploader (Option)

```bash
# Use the Playwright + curl_cffi stealth TikTok uploader directly
curl -X POST http://localhost:8080/upload-tiktok \
  -H "Content-Type: application/json" \
  -d '{"video_id": 1}'
```

### CrewAI Autonomous Pipeline

```bash
# Full autonomous agent pipeline with natural language
curl -X POST http://localhost:8080/api/summon-agent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Post 5 viral tech clips today", "target_count": 5}'

# Dry run (plan only, no uploads)
curl -X POST http://localhost:8080/api/summon-agent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Find trending gaming content", "dry_run": true}'
```

### Content Creation Modes

The pipeline supports two content creation paths:
- **generate_original** — AI-generated scripts + video rendering (for original content)
- **repurpose_youtube** — Source trending YouTube clips, download, and redistribute (arbitrage)

### Caption Formulas

1. **Emotional Hook** - "This {topic} moment changed everything 💔"
2. **Question** - "What's your take on {trend}? 🤔"
3. **Relatable** - "POV: When you discover {topic} for the first time 😱"
4. **Recommendation** - "You NEED to check out {trend} 🔥"
5. **Statement + Emoji** - "{category} is about to blow up 💯"

### Hashtag Strategy

Each video gets 3-5 hashtags following the tiered system:
- **1 mega hashtag** - #fyp or #foryou
- **2-3 core hashtags** - Category-specific (#tech, #gaming, #finance, #anime, etc.)
- **1-2 niche hashtags** - Topic-specific based on trend analysis

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
SELECT v.title, pv.platform_url, va.views, va.likes, va.comments
FROM video_analytics va
JOIN published_videos pv ON va.published_video_id = pv.id
JOIN videos v ON pv.video_id = v.id
ORDER BY va.views DESC
LIMIT 10;

-- Top trending topics
SELECT hashtag, confidence, trend_velocity, post_count, category_id
FROM trend_intel
WHERE status IN ('new', 'sourcing')
ORDER BY confidence DESC, trend_velocity DESC
LIMIT 20;

-- Engagement run summary
SELECT er.mode, er.platform, er.actions_taken, er.completed_at
FROM engagement_runs er
ORDER BY er.completed_at DESC
LIMIT 10;

-- Marketplace earnings
SELECT m.name AS merchant, pt.title, e.amount, e.calculated_at
FROM earnings e
JOIN task_assignments ta ON e.assignment_id = ta.id
JOIN promotion_tasks pt ON ta.task_id = pt.id
JOIN merchants m ON pt.merchant_id = m.id
ORDER BY e.calculated_at DESC
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
├── database/
│   ├── schema.sql                 PostgreSQL schema (all tables)
│   └── migrations/                Schema updates (013+ for AiToEarn)
├── scripts/                       Python automation layer
│   ├── aitoearn_pipeline.py       Master 5-stage pipeline orchestrator
│   ├── fetch_tiktok_trends_apify.py TikTok trend fetcher
│   ├── fetch_twitter_trends.py    X/Twitter trend fetcher
│   ├── fetch_youtube_trends.py    YouTube trending fetcher
│   ├── fetch_reddit_trends.py     Reddit hot posts fetcher
│   ├── trend_content_planner.py   AI content planning from trends
│   ├── generate_video.py          FFmpeg video builder
│   ├── upload_tiktok.py           Playwright + curl_cffi TikTok uploader
│   ├── upload_youtube.py          YouTube Shorts uploader
│   ├── upload_instagram.py        Instagram Reels uploader
│   ├── omnichannel_distributor.py 40+ platform distributor
│   ├── platform_catalog.py        40+ platform definitions
│   ├── engage/                    Browser automation engagement
│   │   ├── engine.py              Orchestrator (light/medium/full modes)
│   │   ├── commenter.py           AI smart comment replies
│   │   ├── liker.py               Auto-like automation
│   │   ├── follower.py            Auto-follow automation
│   │   ├── comment_miner.py       Comment signal extraction
│   │   └── browser.py             Playwright stealth browser
│   ├── monetize/                  Marketplace monetization
│   │   ├── marketplace.py         CPS/CPE/CPM task matching
│   │   ├── settlement.py          Earnings tracking
│   │   └── merchant_api.py        Merchant-facing API
│   ├── crew/                      CrewAI agent orchestration
│   │   ├── agents.py              7 AI agents (Scout→Harvester→Operator→Analyst→Engager→Monetizer)
│   │   ├── pipeline_crew.py       7-task autonomous pipeline
│   │   └── tools.py               Agent tool definitions
│   └── utils/                     database.py, logger.py
├── mastra-agents/src/             TypeScript AI agents (Mastra + Claude)
│   ├── agents/
│   │   ├── trendDetector.ts       Cross-domain trend detection (8 categories)
│   │   ├── scriptwriter.ts        AI script generation
│   │   ├── captionGenerator.ts    Viral caption generation
│   │   ├── contentOptimizer.ts    Analytics-based optimization
│   │   └── shadowBanDetector.ts   Shadow ban analysis
│   ├── tools/                     database.ts, trendSources.ts, scraper.ts
│   └── server.ts                  Express API server
├── dashboard/                     React + Vite analytics dashboard
├── n8n-workflows/                 Workflow definitions (fallback to CrewAI)
├── tests/                         pytest test suite
├── docker-compose.yml             8-service Docker setup
├── Dockerfile                     Node 20 multi-stage build
└── Dockerfile.python              Python 3.11 + FFmpeg + Playwright
```
