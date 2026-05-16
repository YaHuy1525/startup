# AiToEarn — Full User Manual

Everything you need to install, configure, run, and monitor the AiToEarn autonomous content marketing platform.

---

## 1. System Overview

AiToEarn is an AI-powered content arbitrage pipeline: **Trend → Create → Publish → Engage → Monetize**.

It detects trending topics across 8 categories (tech, gaming, finance, fiction, anime, movies, art, TikTok trending) from TikTok, X/Twitter, YouTube, and Reddit. It generates content via AI, publishes to 40+ platforms, auto-engages via browser automation, and matches your content to paid marketplace promotion tasks (CPS/CPE/CPM).

```
AiToEarn Pipeline (5 Stages)
  │
  ├─► Stage 1: Trend Detection
  │     TikTok / X / YouTube / Reddit → trend_intel → scored & ranked
  │
  ├─► Stage 2: Content Creation
  │     Original (AI scripts + video)  OR  Repurpose (YouTube → download → redistribute)
  │
  ├─► Stage 3: Publishing
  │     TikTok (stealth) / YouTube Shorts / Instagram Reels / Pinterest / 40+ more
  │
  ├─► Stage 4: Engagement
  │     Auto-like / AI comments / auto-follow / comment signal mining
  │
  └─► Stage 5: Monetization
        CPS/CPE/CPM marketplace matching + settlement tracking
```

---

## 2. Prerequisites

- **Docker** + Docker Compose v2
- **Python 3.11+** (for running scripts outside Docker)
- **Node.js 20+** (for Mastra agents)
- **API Keys** (minimum):
  - `ANTHROPIC_API_KEY` — Claude API key (or configure free-claude-code proxy)
  - `TIKTOK_EMAIL` + `TIKTOK_PASSWORD` — For TikTok publishing
  - `DB_PASSWORD` — PostgreSQL password
- **Optional but recommended**:
  - `YOUTUBE_API_KEY` — YouTube trending + publishing
  - `X_BEARER_TOKEN` — X/Twitter trends
  - `TELEGRAM_BOT_TOKEN` — Remote control via Telegram
  - `REVID_API_KEY` or `CREATIFY_API_KEY` — AI video generation
  - `ELEVENLABS_API_KEY` — Voiceover/TTS

---

## 3. Installation & Setup

### 3.1 Clone and Configure

```bash
cd manga-automation
cp .env.example .env
```

Edit `.env` and fill in at minimum:
```ini
DB_PASSWORD=your_secure_password_here
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_BASE_URL=http://localhost:8082/v1   # optional: free-claude-code proxy
TIKTOK_EMAIL=your_email@example.com
TIKTOK_PASSWORD=your_password
N8N_PASSWORD=your_n8n_password
```

### 3.2 Start Services

```bash
docker compose up -d
```

Wait ~30 seconds for all services to become healthy, then verify:

```bash
curl http://localhost:3001/health    # manga-agents
curl http://localhost:8080/health    # python-worker
curl http://localhost:8001/api/v2/heartbeat  # ChromaDB
```

### 3.3 Import n8n Workflows (Optional)

n8n is a fallback orchestrator. The primary orchestrator is CrewAI (built into python-worker).

1. Open http://localhost:5679 (login: admin / your `N8N_PASSWORD`)
2. Settings → Import from File
3. Import from `n8n-workflows/` directory

---

## 4. Configuration Reference

### LLM / AI

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `ANTHROPIC_BASE_URL` | No | — | Point to free-claude-code proxy: `http://localhost:8082/v1` |
| `OPEN_ROUTER` | No | — | OpenRouter API key (alternative LLM backend) |
| `ENGAGE_AI_MODEL` | No | `claude-sonnet-4-6` | Model for engagement AI replies |

### Official AiToEarn API/MCP

| Variable | Required | Default | Description |
|---|---|---|---|
| `AITOEARN_PRIMARY` | No | `false` | Use official AiToEarn as the primary execution path |
| `AITOEARN_API_KEY` | Cond. | — | API key sent as `x-api-key` for official AiToEarn endpoints |
| `AITOEARN_BASE_URL` | No | `https://aitoearn.ai` | Base URL for global AiToEarn environment |
| `AITOEARN_MCP_URL` | No | `https://aitoearn.ai/api/unified/mcp` | MCP endpoint reference |
| `AITOEARN_SSE_URL` | No | `https://aitoearn.ai/api/unified/sse` | SSE endpoint reference |
| `AITOEARN_FALLBACK_LOCAL` | No | `true` | Enable local worker fallback if remote stage fails |

### TikTok

| Variable | Required | Default | Description |
|---|---|---|---|
| `TIKTOK_EMAIL` | Yes | — | TikTok account email |
| `TIKTOK_PASSWORD` | Yes | — | TikTok account password |
| `MAX_UPLOADS_PER_ACCOUNT_DAY` | No | `3` | Daily upload limit per account |
| `SHADOW_BAN_FYP_THRESHOLD` | No | `0.10` | FYP% below which = shadow banned |

### YouTube

| Variable | Required | Default | Description |
|---|---|---|---|
| `YOUTUBE_API_KEY` | No | — | YouTube Data API v3 key (trending + publishing) |
| `YOUTUBE_CLIENT_ID` | No | — | OAuth client ID for YouTube uploads |
| `YOUTUBE_CLIENT_SECRET` | No | — | OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | No | — | OAuth refresh token |

### Trend Detection

| Variable | Required | Default | Description |
|---|---|---|---|
| `X_BEARER_TOKEN` | No | — | X/Twitter API bearer token for trends |
| `REDDIT_CLIENT_ID` | No | — | Reddit API client ID |
| `REDDIT_CLIENT_SECRET` | No | — | Reddit API client secret |
| `REDDIT_TREND_LIMIT` | No | `20` | Max posts per subreddit |
| `TREND_PLANNER_LIMIT` | No | `10` | Max trends to plan content for |
| `TREND_REPURPOSE_RATIO` | No | `0.5` | Fraction of trends that use repurpose mode |
| `TREND_MIN_CONFIDENCE` | No | `0.3` | Minimum confidence to consider a trend |
| `APIFY_API` | No | — | Apify API key for TikTok scraping |
| `LAST30DAYS_DEFAULT_QUERIES` | No | — | Scheduled research queries (newline or `\|\|` separated) |
| `LAST30DAYS_SCHEDULE_SECONDS` | No | `21600` | Research ingest interval (6h) |

### Engagement

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENGAGE_HEADLESS` | No | `1` | Run browser in headless mode |
| `ENGAGE_MAX_LIKES` | No | `30` | Max likes per session |
| `ENGAGE_MAX_FOLLOWS` | No | `15` | Max follows per session |
| `ENGAGE_FOLLOW_COOLDOWN_HOURS` | No | `24` | Hours before re-following same account |
| `ENGAGE_PROXY_URL` | No | — | Proxy for engagement browser |

### Marketplace Monetization

| Variable | Required | Default | Description |
|---|---|---|---|
| `MARKETPLACE_DEFAULT_COMMISSION` | No | `0.10` | Default commission rate |

### AI Video Generation

| Variable | Required | Default | Description |
|---|---|---|---|
| `FINANCE_VIDEO_PROVIDER` | No | `revid` | `revid`, `creatify`, `heygen`, or `invideo` |
| `REVID_API_KEY` | No | — | Revid.ai API key |
| `REVID_BACKGROUND` | No | `subway_surfers` | Video background (`subway_surfers`, `minecraft`, `temple_run`, etc.) |
| `CREATIFY_API_ID` | No | — | Creatify API ID |
| `CREATIFY_API_KEY` | No | — | Creatify API key |
| `HEYGEN_API_KEY` | No | — | HeyGen API key |
| `INVIDEO_API_KEY` | No | — | InVideo API key |

### Voiceover (TTS)

| Variable | Required | Default | Description |
|---|---|---|---|
| `VOICE_PROVIDER` | No | `elevenlabs` | `elevenlabs` or `kokoro` |
| `ELEVENLABS_API_KEY` | No | — | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | No | — | Voice ID for ElevenLabs |
| `VOICE_ENABLE_FALLBACK` | No | `true` | Fallback to local Kokoro if ElevenLabs fails |
| `KOKORO_VOICE` | No | `af_sky` | Kokoro voice preset |

### Telegram Bot

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | No | — | Bot token from @BotFather |
| `TELEGRAM_ALLOWED_CHAT_IDS` | No | — | Comma-separated chat IDs (security) |
| `TELEGRAM_POLL_INTERVAL` | No | `2` | Long-poll interval in seconds |

### Paths (inside containers)

| Variable | Default | Description |
|---|---|---|
| `PANELS_DIR` | `/data/panels` | Downloaded image panels |
| `VIDEOS_DIR` | `/data/videos` | Generated videos |
| `LOGS_DIR` | `/data/logs` | Log files |
| `EARNINGS_SCREENSHOTS_DIR` | `/data/earnings_screenshots` | Payout proof screenshots |
| `FINANCE_VIDEOS_DIR` | `/data/finance_videos` | Finance niche videos |

---

## 5. Running the Pipeline

### 5.1 Full Pipeline (all 5 stages)

**Via CLI:**
```bash
# Full pipeline with all stages
python3 scripts/aitoearn_pipeline.py --once --category tech

# Light mode (skips engagement)
python3 scripts/aitoearn_pipeline.py --once --mode light

# Single stage only
python3 scripts/aitoearn_pipeline.py --stage trend --category gaming
python3 scripts/aitoearn_pipeline.py --stage engage
```

**Via API:**
```bash
# Full pipeline
curl -X POST http://localhost:8080/aitoearn/pipeline \
  -H "Content-Type: application/json" \
  -d '{"category": "tech", "mode": "full"}'

# Light mode
curl -X POST http://localhost:8080/aitoearn/pipeline \
  -H "Content-Type: application/json" \
  -d '{"category": "gaming", "mode": "light"}'

# Hermes AiToEarn-first full-ops
curl -X POST http://localhost:8080/hermes/full-ops \
  -H "Content-Type: application/json" \
  -d '{"category":"finance","mode":"full","profile":"minimal"}'
```

### 5.2 Individual Stages

```bash
# Stage 1: Trend Detection
curl -X POST http://localhost:8080/aitoearn/stage/trend \
  -H "Content-Type: application/json" \
  -d '{"category": "finance", "limit": 10}'

# Stage 2: Content Creation
curl -X POST http://localhost:8080/aitoearn/stage/create \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}'

# Stage 3: Publishing
curl -X POST http://localhost:8080/aitoearn/stage/publish \
  -H "Content-Type: application/json" \
  -d '{}'

# Stage 4: Engagement
curl -X POST http://localhost:8080/aitoearn/stage/engage \
  -H "Content-Type: application/json" \
  -d '{"platform": "tiktok"}'

# Stage 5: Monetization
curl -X POST http://localhost:8080/aitoearn/stage/monetize \
  -H "Content-Type: application/json" \
  -d '{"creator_id": 1}'
```

### 5.3 CrewAI Autonomous Pipeline

This is the most powerful mode — 7 AI agents run autonomously, handling failures and adapting strategy.

**Via CLI:**
```bash
python3 scripts/crew/pipeline_crew.py --prompt "Post 5 viral tech clips today" --count 5

# Dry run (plan only, no actual uploads)
python3 scripts/crew/pipeline_crew.py --prompt "Find trending gaming content" --count 3 --dry-run
```

**Via API:**
```bash
# Async (returns run_id immediately)
curl -X POST http://localhost:8080/api/summon-agent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Post 5 viral tech clips", "target_count": 5}'

# Sync (waits for completion)
curl -X POST http://localhost:8080/api/summon-agent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Find trending gaming content", "sync": true, "dry_run": true}'
```

**Via Telegram:**
```
/summon Post 5 viral finance clips today
/summon Find trending car content and post 3 videos
```

The CrewAI pipeline runs 7 agents in sequence:
```
Manager → Scout → Harvester → Operator → Analyst → Engager → Monetizer
```

The Manager handles failures autonomously: quarantines shadow-banned TikTok accounts, reassigns tasks, and pivots content strategy based on ChromaDB memory.

### 5.4 Arbitrage Pipeline (YouTube → TikTok/YouTube Shorts)

```bash
# Discover trends from TikTok
curl -X POST http://localhost:8080/arbitrage/discover-trends \
  -H "Content-Type: application/json" \
  -d '{"region": "US", "limit": 20}'

# Source matching YouTube assets
curl -X POST http://localhost:8080/arbitrage/source-assets \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}'

# Download queued assets
curl -X POST http://localhost:8080/arbitrage/download \
  -H "Content-Type: application/json" \
  -d '{"batch": 10}'

# Distribute to platforms
curl -X POST http://localhost:8080/arbitrage/distribute \
  -H "Content-Type: application/json" \
  -d '{"platforms": ["tiktok", "youtube"], "batch": 5}'
```

---

## 6. Content Creation

### 6.1 Two Creation Modes

The system automatically decides between two modes based on `TREND_REPURPOSE_RATIO`:

**generate_original** — AI creates fresh content:
1. AI generates script (scriptwriter.ts)
2. AI generates caption + hashtags (captionGenerator.ts)
3. Video rendered via FFmpeg or AI video provider

**repurpose_youtube** — Repurpose existing YouTube clips:
1. Search YouTube for matching videos (>50k views, <3 min)
2. Download with yt-dlp
3. Mutate (FFmpeg speed/contrast/crop adjustments for uniqueness)
4. Repost to TikTok + YouTube Shorts

### 6.2 Finance Video Generator

Generates @mini.money.matters-style vertical videos (1080×1920) from earnings screenshots.

```bash
# CLI
python3 scripts/finance_video_generator.py --type proof --week 2026-W19
python3 scripts/finance_video_generator.py --type voiceover --brief-id 42
python3 scripts/finance_video_generator.py --type hook --amount 47.23

# API
curl -X POST http://localhost:8080/finance/generate-video \
  -H "Content-Type: application/json" \
  -d '{"type": "proof", "week_iso": "2026-W19"}'
```

**Video types:**
- `proof` — Screenshot slideshow with earnings amounts as text overlay
- `voiceover` — Same as proof + TTS narration
- `hook` — 3-second bold hook card + proof slideshow

### 6.3 AI Video Providers

```bash
# Via API
curl -X POST http://localhost:8080/finance/ai-video \
  -H "Content-Type: application/json" \
  -d '{"provider": "revid", "week_iso": "2026-W19"}'

# List available avatars
curl -X POST http://localhost:8080/finance/list-avatars \
  -H "Content-Type: application/json" \
  -d '{"provider": "creatify"}'
```

### 6.4 Voiceover (TTS)

```bash
curl -X POST http://localhost:8080/voiceover/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "This trend is about to explode", "provider": "elevenlabs"}'
```

### 6.5 Trend Content Planner

```bash
# Plan content from current trends
curl -X POST http://localhost:8080/autopilot/plan-content \
  -H "Content-Type: application/json" \
  -d '{"limit": 10, "repurpose_ratio": 0.5}'

# Execute the plan
curl -X POST http://localhost:8080/autopilot/execute-content-plan \
  -H "Content-Type: application/json" \
  -d '{"limit": 5, "batch": 3}'
```

---

## 7. Publishing

### 7.1 TikTok (Stealth V2 — recommended)

Uses Playwright + curl_cffi TLS bypass to avoid bot detection. Two modes:
- **V2** (default): FFmpeg mutation + curl_cffi — higher stealth
- **V1** (fallback): Direct Playwright automation

```bash
# API
curl -X POST http://localhost:8080/upload-tiktok \
  -H "Content-Type: application/json" \
  -d '{"video_id": 1}'

# CLI
python3 -m scripts.upload_tiktok --video-id 1

# Telegram
/upload_tiktok 1
```

**How it identifies published vs draft:** After upload, the uploader checks whether the video appears in the TikTok profile feed. If yes → `published`, if only in drafts → `draft`.

### 7.2 YouTube Shorts

```bash
curl -X POST http://localhost:8080/upload-youtube \
  -H "Content-Type: application/json" \
  -d '{"video_id": 1}'
```

### 7.3 Instagram Reels

```bash
curl -X POST http://localhost:8080/upload/instagram \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/data/videos/my_video.mp4", "caption": "Check this out!", "hashtags": ["fyp", "viral"]}'
```

### 7.4 Pinterest

```bash
curl -X POST http://localhost:8080/upload/pinterest \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/data/videos/my_video.mp4", "caption": "Trending now"}'
```

### 7.5 Omnichannel Distribution (40+ platforms)

Distributes content across all 40+ platforms defined in `platform_catalog.py`.

```bash
# Auto-distribute top briefs
curl -X POST http://localhost:8080/omnichannel/auto \
  -H "Content-Type: application/json" \
  -d '{"action": "auto", "limit": 3}'

# Distribute a specific brief
curl -X POST http://localhost:8080/omnichannel/distribute \
  -H "Content-Type: application/json" \
  -d '{"brief_id": 1, "channels": "tiktok,youtube,instagram"}'

# Plan content for a category
curl -X POST http://localhost:8080/omnichannel/plan \
  -H "Content-Type: application/json" \
  -d '{"category_slug": "tech", "profile": "full"}'

# Plan for ALL categories
curl -X POST http://localhost:8080/omnichannel/plan-all \
  -H "Content-Type: application/json" \
  -d '{"profile": "full"}'
```

---

## 8. Engagement

### 8.1 CLI

```bash
# Light mode (likes only — safest)
python3 scripts/engage/engine.py --platform tiktok --mode light

# Medium mode (likes + comments)
python3 scripts/engage/engine.py --platform tiktok --mode medium

# Full mode (likes + comments + follows + comment mining)
python3 scripts/engage/engine.py --platform tiktok --mode full
```

### 8.2 API

```bash
curl -X POST http://localhost:8080/aitoearn/stage/engage \
  -H "Content-Type: application/json" \
  -d '{"platform": "tiktok"}'
```

### 8.3 Mode Reference

| Mode | Likes | Comments | Follows | Comment Mining | Risk |
|---|---|---|---|---|---|
| `light` | Yes | — | — | — | Low |
| `medium` | Yes | Yes (AI replies) | — | — | Moderate |
| `full` | Yes | Yes (AI replies) | Yes | Yes | High |

### 8.4 Engagement Configuration

```ini
# .env
ENGAGE_HEADLESS=1              # Run browser without UI
ENGAGE_MAX_LIKES=30            # Max likes per session
ENGAGE_MAX_FOLLOWS=15          # Max follows per session
ENGAGE_FOLLOW_COOLDOWN_HOURS=24 # Hours before re-following
ENGAGE_PROXY_URL=              # Optional proxy for browser
ENGAGE_AI_MODEL=claude-sonnet-4-6  # Model for AI replies
```

---

## 9. Monetization

### 9.1 Marketplace Task Matching

```bash
# Match creator to open tasks
curl -X POST http://localhost:8080/aitoearn/stage/monetize \
  -H "Content-Type: application/json" \
  -d '{"creator_id": 1}'
```

### 9.2 Python API

```python
from scripts.monetize.marketplace import create_merchant, create_task, match_creator, assign_task

# Create a merchant
merchant = create_merchant(name="TechGadgets Inc", category="tech")

# Create a promotion task (CPS model)
task = create_task(
    merchant_id=merchant["id"],
    title="Promote our new smartwatch",
    model="cps",          # cps | cpe | cpm
    reward=5.00,          # $5 per sale
    budget=500.00,
)

# Match a creator to open tasks
matches = match_creator(creator_id=1, limit=5)

# Assign a task to a creator
assign_task(task_id=task["id"], creator_id=1)
```

### 9.3 Settlement Tracking

```python
from scripts.monetize.settlement import calculate_earnings, get_creator_earnings

# Calculate earnings for an assignment
earnings = calculate_earnings(assignment_id=1)

# Get total creator earnings (last 7 days)
summary = get_creator_earnings(creator_id=1, days=7)
```

### 9.4 Earnings Models

| Model | Calculation | Use Case |
|---|---|---|
| **CPS** (Cost Per Sale) | engagements × reward × 0.05 estimated conversion | Affiliate products |
| **CPE** (Cost Per Engagement) | engagements × reward | Engagement campaigns |
| **CPM** (Cost Per Mille) | views / 1000 × reward | Brand awareness |

---

## 10. Telegram Bot

### 10.1 Setup

1. Create a bot with @BotFather on Telegram → get token
2. Set in `.env`:
```ini
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321   # optional but recommended
```
3. Start the bot service:
```bash
docker compose up -d --build telegram-bot
```

### 10.2 All Commands

**Pipeline & Content:**
| Command | Description |
|---|---|
| `/summon <prompt>` | Run the full CrewAI autonomous pipeline |
| `/fetch_trending [limit]` | Fetch trending topics |
| `/arb_discover [region] [limit]` | Discover arbitrage trends |
| `/arb_source [limit]` | Source YouTube assets |
| `/arb_download [batch]` | Download queued assets |
| `/arb_distribute [platforms] [batch]` | Distribute to platforms |
| `/upload_tiktok <video_id>` | Upload video to TikTok |
| `/upload_youtube <video_id>` | Upload video to YouTube |

**Finance & Earnings:**
| Command | Description |
|---|---|
| `/finance_pipeline [provider] [bg]` | Full auto: scan → video → post all platforms |
| `/viral_pipeline [provider] [bg]` | Full auto: trend → draft → video → post |
| `/finance_discover` | Scrape r/beermoney + TikTok #passiveincome |
| `/finance_briefs [top]` | Generate finance content briefs |
| `/finance_video [week] [type]` | Make proof video from screenshots |
| `/finance_ai_video [provider] [week] [bg]` | AI-generated video |
| `/earnings_scan` | Scan screenshots for new payout proofs |
| `/weekly_recap [week_iso]` | Generate earnings recap |
| `/referral_list` | Show active referral platforms |

**Gig Copilot (freelance gig tracking):**
| Command | Description |
|---|---|
| `/gig_new <platform> <type> <brief>` | Create a new gig task |
| `/gig_draft <task_id>` | Generate AI draft for task |
| `/gig_score <task_id>` | Run rubric scoring |
| `/gig_submit_done <id> <outcome> <mins> <payout>` | Log task completion |
| `/gig_today` | Today's KPI summary |
| `/gig_week` | 7-day performance breakdown |

**Research & Planning:**
| Command | Description |
|---|---|
| `/research_topic <query>` | Run research ingest |
| `/research_status [limit]` | Show recent research runs |
| `/plan_campaign <goal>` | Ask DeerFlow for campaign plan |
| `/recover_last_run` | Auto-recover from last failed run |

**System:**
| Command | Description |
|---|---|
| `/status` | Worker + agent health + memory stats |
| `/whoami` | Show your chat ID |
| `/help` | Show all commands |
| `/mastra <METHOD> <path> [json]` | Direct Mastra API call |
| `/worker <path> [json]` | Direct worker endpoint call |

---

## 11. Monitoring & Maintenance

### 11.1 Health Checks

```bash
# All services
curl http://localhost:3001/health    # manga-agents
curl http://localhost:8080/health    # python-worker
curl http://localhost:8001/api/v2/heartbeat  # ChromaDB
curl http://localhost:3000           # Dashboard
curl http://localhost:5679           # n8n

# Docker status
docker compose ps
```

### 11.2 View Logs

```bash
# Service logs
docker compose logs python-worker --tail 50
docker compose logs manga-agents --tail 50
docker compose logs telegram-bot --tail 20

# Pipeline run logs
tail -f data/logs/aitoearn_pipeline.log
tail -f data/logs/engage_engine.log
```

### 11.3 Database Access

```bash
docker compose exec postgres psql -U manga_user -d manga_automation
```

### 11.4 Useful Monitoring Queries

```sql
-- Daily upload success rate (last 7 days)
SELECT
    DATE(uploaded_at) AS date,
    COUNT(*) FILTER (WHERE success = true) AS successful,
    COUNT(*) FILTER (WHERE success = false) AS failed,
    ROUND(100.0 * COUNT(*) FILTER (WHERE success = true) / NULLIF(COUNT(*), 0), 2) AS success_rate_pct
FROM upload_results
WHERE uploaded_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(uploaded_at)
ORDER BY date DESC;

-- Top trending topics by velocity
SELECT hashtag, confidence, trend_velocity, post_count, category_id
FROM trend_intel
WHERE status IN ('new', 'sourcing')
ORDER BY confidence DESC, trend_velocity DESC
LIMIT 20;

-- Engagement run summary
SELECT mode, platform, actions_count, created_at
FROM engagement_runs
ORDER BY created_at DESC
LIMIT 10;

-- Marketplace earnings
SELECT m.name AS merchant, pt.title, pt.model, e.amount, e.calculated_at
FROM earnings e
JOIN task_assignments ta ON e.assignment_id = ta.id
JOIN promotion_tasks pt ON ta.task_id = pt.id
JOIN merchants m ON pt.merchant_id = m.id
ORDER BY e.calculated_at DESC
LIMIT 10;

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
```

### 11.5 Memory Stats

```bash
curl -X POST http://localhost:8080/api/memory/stats \
  -H "Content-Type: application/json" \
  -d '{}'
```

Returns counts for: `trend_memory`, `account_health`, `content_fingerprints`.

---

## 12. Troubleshooting

### TikTok upload fails
1. Check account isn't shadow-banned:
   ```sql
   SELECT * FROM tiktok_accounts WHERE shadow_banned = true;
   ```
2. Try manual login to verify credentials still work
3. Check if TikTok is showing a captcha — the V2 stealth uploader handles most cases, but extreme rate limiting may require waiting
4. Quarantine the account and use a different one:
   ```bash
   # The CrewAI Manager does this automatically. If manual:
   curl -X POST http://localhost:8080/detect-shadow-ban \
     -H "Content-Type: application/json" \
     -d '{"min_posts": 5, "threshold": 0.10}'
   ```

### Trend detection returns no results
1. Verify at least one trend source has API keys configured:
   - TikTok: `APIFY_API`
   - X/Twitter: `X_BEARER_TOKEN`
   - YouTube: `YOUTUBE_API_KEY`
   - Reddit: No auth required (uses public JSON API)
2. Check that `genesis_categories` have `is_active = true`:
   ```sql
   SELECT slug, display_name, is_active FROM genesis_categories;
   ```
3. Run a manual fetch to test:
   ```bash
   python3 scripts/fetch_reddit_trends.py --category-slug tech --limit 20
   ```

### Engagement browser won't start
1. Install Playwright browsers:
   ```bash
   playwright install chromium
   ```
2. If headless issues, try:
   ```ini
   ENGAGE_HEADLESS=0
   ```
3. Check proxy if configured:
   ```bash
   curl -x $ENGAGE_PROXY_URL https://www.tiktok.com -o /dev/null -w "%{http_code}"
   ```

### Database connection issues
```bash
# Verify postgres is healthy
docker compose exec postgres pg_isready -U manga_user -d manga_automation

# Check connection string
docker compose exec python-worker python3 -c "
from scripts.utils import database as db
print(db.execute('SELECT 1'))
"
```

### free-claude-code proxy not working
```bash
# Verify the proxy is running
curl http://localhost:8082/v1/models

# If not, fall back to direct Anthropic:
# Remove or comment out ANTHROPIC_BASE_URL from .env
```

### Docker services not starting
```bash
# Full restart
docker compose down
docker compose up -d --build

# Check for port conflicts
netstat -ano | findstr "5434 6380 3001 8080 5679 3000 8001"

# Check disk space for Docker volumes
docker system df
```

### Pipeline run times out
- The CrewAI pipeline can take 5-15 minutes for a full run with 7 agents
- For sync API calls, increase timeout or use async mode (omit `sync: true`)
- Check logs: `docker compose logs python-worker | tail -100`

---

## Appendix: Full API Reference

### AiToEarn Pipeline (primary)
```
POST /aitoearn/pipeline           { category?, mode? }
POST /aitoearn/stage/trend        { category?, limit? }
POST /aitoearn/stage/create       { limit? }
POST /aitoearn/stage/publish      {}
POST /aitoearn/stage/engage       { platform? }
POST /aitoearn/stage/monetize     { creator_id? }
POST /hermes/full-ops             { category?, mode?, profile?, dry_run?, run_id? }
```

### CrewAI Agent
```
POST /api/summon-agent            { prompt, target_count?, dry_run?, sync? }
POST /api/memory/stats            {}
POST /api/memory/query-trends     { query, n? }
POST /api/memory/declining        {}
```

### Arbitrage Pipeline
```
POST /arbitrage/discover-trends   { region?, limit? }
POST /arbitrage/source-assets     { limit? }
POST /arbitrage/download          { batch? }
POST /arbitrage/distribute        { platforms?, batch? }
```

### TikTok Uploader (kept as an option)
```
POST /upload-tiktok               { video_id }
POST /upload-youtube              { video_id }
```

### Content & Autopilot
```
POST /autopilot/plan-content      { limit?, repurpose_ratio? }
POST /autopilot/execute-content-plan  { limit?, repurpose_ratio?, batch? }
POST /voiceover/synthesize        { text, provider?, voice_id? }
POST /finance/generate-video      { type, week_iso?, brief_id? }
POST /finance/ai-video            { provider, week_iso?, style? }
POST /finance/list-avatars        { provider }
```

### Omnichannel
```
POST /omnichannel/distribute      { brief_id, profile?, channels? }
POST /omnichannel/auto            { action: "auto", limit? }
POST /omnichannel/plan            { category_slug, profile? }
POST /omnichannel/plan-all        { profile? }
```

### Genesis Discovery
```
POST /genesis/discover            { categories, limit? }
POST /genesis/briefs              { categories, top?, action }
```

### Monetization Control
```
POST /monetization/kpi/evaluate   { days?, write_alerts? }
POST /monetization/optimize-weekly {}
```

### Research
```
POST /research/ingest             { query, queries?, region? }
POST /research/status             { limit? }
```

### Platform Uploaders
```
POST /upload/instagram            { video_path, caption, account?, hashtags? }
POST /upload/meta/instagram       { video_url, caption }
POST /upload/meta/facebook        { video_url, caption }
POST /upload/meta/threads         { video_url, text }
POST /upload/pinterest            { video_path, caption }
```

### Gig Copilot
```
POST /gig/task/create             { user_id, platform, task_type, brief }
POST /gig/task/draft              { task_id }
POST /gig/task/score              { task_id }
POST /gig/task/finalize           { task_id, outcome, minutes?, payout? }
POST /gig/session/today           { user_id }
POST /gig/session/week            { user_id }
```

### Obsidian Sync
```
POST /obsidian/task               { action: "task", task, output }
POST /obsidian/session            { action: "session", summary }
POST /obsidian/template           { action: "template", platform, task_type, template_text, win_rate? }
```

### System
```
GET  /health                      Service health check
POST /detect-shadow-ban           { min_posts?, threshold? }
```

---

## Appendix: Quick Reference Card

```bash
# Start everything
docker compose up -d

# Run full pipeline
python3 scripts/aitoearn_pipeline.py --once --category tech

# Run autonomous agent pipeline
python3 scripts/crew/pipeline_crew.py --prompt "Post 5 viral clips" --count 5

# Fetch trends from all sources
python3 scripts/fetch_reddit_trends.py --category-slug tech
python3 scripts/fetch_youtube_trends.py --region US --limit 20

# Upload to TikTok
python3 -m scripts.upload_tiktok --video-id 1

# Engagement cycle
python3 scripts/engage/engine.py --platform tiktok --mode full

# Check status
curl http://localhost:8080/health
docker compose ps

# View logs
docker compose logs python-worker --tail 50 | grep -i error
```

---

*Generated: 2026-05-14. For the latest version, check the repository or run `/status` in Telegram.*
