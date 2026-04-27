# Autonomous Content Arbitrage Pipeline — Implementation Plan

## What This Is

A second pipeline ("Pipeline B") that runs **alongside** the existing MangaDex/Remotion pipeline.

- **Pipeline A (existing):** n8n → Mastra Agents → MangaDex → Remotion → TikTok upload
- **Pipeline B (new):** Apify TikTok trend scraper → YouTube sourcing → yt-dlp download → multi-platform upload (TikTok + YouTube Shorts + Instagram Reels)

Both pipelines share the existing PostgreSQL database. No SQLite, no Airtable — we already have the DB layer.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     PIPELINE B (NEW)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Apify: TikTok Trends]  →  [Mastra Agent: Trend Evaluator]    │
│           ↓                                                     │
│  [Apify: YouTube Search] →  [Mastra Agent: Asset Sourcer]      │
│           ↓                                                     │
│  [yt-dlp: Download]      →  [scripts/arbitrage_worker.py]      │
│           ↓                                                     │
│  [Distribution]                                                 │
│    ├── TikTok (TiktokAutoUploader)                              │
│    ├── YouTube Shorts (upload_youtube.py)                       │
│    └── Instagram Reels (future)                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
         ↕ shared
┌─────────────────────────────────────────────────────────────────┐
│              PostgreSQL (existing)                              │
│  + new tables: trend_intel, arbitrage_assets, arbitrage_logs   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Database Schema (1-2 hours)

Add 3 new tables to the existing schema via a migration file.

**File:** `database/migrations/005_arbitrage_pipeline.sql`

```sql
-- Trending hashtags/topics discovered from TikTok
CREATE TABLE IF NOT EXISTS trend_intel (
    id              SERIAL PRIMARY KEY,
    hashtag         VARCHAR(200) NOT NULL,
    region          VARCHAR(10) DEFAULT 'US',
    avg_views       BIGINT,
    post_count      INTEGER,
    trend_velocity  DECIMAL(10,4),  -- rate of change * avg engagement
    source          VARCHAR(50) DEFAULT 'apify_tiktok',
    status          VARCHAR(20) DEFAULT 'new',  -- new, sourcing, done, skipped
    discovered_at   TIMESTAMP DEFAULT NOW(),
    processed_at    TIMESTAMP
);

CREATE INDEX idx_trend_status ON trend_intel(status, trend_velocity DESC);

-- YouTube assets sourced for a trend
CREATE TABLE IF NOT EXISTS arbitrage_assets (
    id              SERIAL PRIMARY KEY,
    trend_id        INTEGER REFERENCES trend_intel(id),
    youtube_url     TEXT NOT NULL,
    youtube_title   TEXT,
    youtube_views   BIGINT,
    local_path      TEXT,           -- path after yt-dlp download
    file_size_mb    DECIMAL(8,2),
    duration_secs   INTEGER,
    status          VARCHAR(20) DEFAULT 'pending',  -- pending, downloaded, uploaded, failed
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_assets_status ON arbitrage_assets(status);
CREATE INDEX idx_assets_trend  ON arbitrage_assets(trend_id);

-- Upload results per platform
CREATE TABLE IF NOT EXISTS arbitrage_uploads (
    id              SERIAL PRIMARY KEY,
    asset_id        INTEGER REFERENCES arbitrage_assets(id),
    platform        VARCHAR(20) NOT NULL,  -- tiktok, youtube, instagram
    caption         TEXT,
    hashtags        TEXT[],
    platform_url    TEXT,
    status          VARCHAR(20) DEFAULT 'pending',  -- pending, success, failed
    error_message   TEXT,
    uploaded_at     TIMESTAMP DEFAULT NOW()
);
```

---

## Phase 2: Apify Integration — Trend Discovery (2-3 hours)

**File:** `scripts/fetch_tiktok_trends_apify.py`

Uses Apify's `madoka_trendpulse/tiktok-trends-scraper` to pull trending hashtags from TikTok Creative Center.

```python
# Key logic
import os, requests
from dotenv import load_dotenv
load_dotenv()

APIFY_TOKEN = os.environ["APIFY_TOKEN"]

def fetch_tiktok_trends(region="US", limit=20):
    """Call Apify actor and return trending hashtags with velocity scores."""
    url = f"https://api.apify.com/v2/acts/madoka_trendpulse~tiktok-trends-scraper/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN}
    payload = {"region": region, "limit": limit}
    r = requests.post(url, params=params, json=payload, timeout=120)
    return r.json()

def calculate_velocity(item):
    """Trend velocity = post_count_change * avg_engagement_rate."""
    return item.get("postCountChange", 0) * item.get("avgEngagementRate", 0)

def save_trends(trends):
    """Save to trend_intel table, skip duplicates."""
    # INSERT ... ON CONFLICT (hashtag, region) DO UPDATE ...
```

**Env vars needed in `manga-automation/.env`:**
```
APIFY_TOKEN=your_apify_api_token
APIFY_YOUTUBE_SEARCH_ACTOR=ecomscrape/youtube-video-search-scraper
APIFY_YOUTUBE_DOWNLOADER_ACTOR=crawlerbros/youtube-video-downloader
VELOCITY_THRESHOLD=0.5
```

---

## Phase 3: YouTube Sourcing Agent (2-3 hours)

**File:** `scripts/source_youtube_assets.py`

For each validated trend, search YouTube for relevant content and queue downloads.

```python
def search_youtube_for_trend(hashtag, limit=5):
    """Use Apify YouTube search actor to find relevant videos."""
    # Strip # from hashtag, build search query
    query = f"{hashtag.lstrip('#')} manga anime 2025"
    # Call ecomscrape/youtube-video-search-scraper via Apify
    # Filter: view_count > 10000, duration < 180s (for Shorts compatibility)
    # Return list of {youtube_url, title, views, duration}

def queue_asset_downloads(trend_id, videos):
    """Insert into arbitrage_assets with status=pending."""
```

---

## Phase 4: Download Worker (1-2 hours)

**File:** `scripts/arbitrage_worker.py`

Processes `arbitrage_assets` with `status=pending`, downloads via `yt-dlp`, updates DB.

```python
import yt_dlp, os
from scripts.utils import database as db

DOWNLOAD_DIR = os.environ.get("ARBITRAGE_VIDEOS_DIR", "/data/arbitrage_videos")

def download_asset(asset):
    output_path = os.path.join(DOWNLOAD_DIR, f"asset_{asset['id']}.mp4")
    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]",
        "outtmpl": output_path,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([asset["youtube_url"]])
    # Update DB: status=downloaded, local_path, file_size_mb, duration_secs

def process_pending():
    assets = db.execute_many("SELECT * FROM arbitrage_assets WHERE status='pending' LIMIT 10")
    for asset in assets:
        download_asset(asset)
```

---

## Phase 5: Multi-Platform Distribution (3-4 hours)

**File:** `scripts/distribute_arbitrage.py`

Takes downloaded assets and uploads to configured platforms.

```python
def distribute_asset(asset_id, platforms=["tiktok", "youtube"]):
    asset = db.execute_one("SELECT * FROM arbitrage_assets WHERE id=%s", (asset_id,))
    trend = db.execute_one("SELECT * FROM trend_intel WHERE id=%s", (asset["trend_id"],))
    
    caption = generate_caption(trend["hashtag"])
    hashtags = select_hashtags(trend["hashtag"])
    
    for platform in platforms:
        if platform == "tiktok":
            upload_to_tiktok(asset["local_path"], caption, hashtags)
        elif platform == "youtube":
            upload_to_youtube_shorts(asset["local_path"], caption, hashtags)
        # log result to arbitrage_uploads

def generate_caption(hashtag):
    """Reuse existing captionGenerator from mastra-agents."""
    # Call POST http://localhost:3001/captions/generate
    # or use the caption templates from DB directly

def upload_to_tiktok(video_path, caption, hashtags):
    """Call existing python worker: POST http://localhost:8080/upload-tiktok"""
    # Requires a video_id in the videos table — insert a temp record first

def upload_to_youtube_shorts(video_path, caption, hashtags):
    """Use TiktokAutoUploader/upload_youtube.py logic."""
    import subprocess
    subprocess.run([
        "python", "TiktokAutoUploader/upload_youtube.py",
        "-v", video_path,
        "-t", caption[:100],
        "--tags", *hashtags
    ])
```

---

## Phase 6: n8n Workflow — Pipeline B (2 hours)

**File:** `n8n-workflows/06_arbitrage_pipeline.json`

New n8n workflow that orchestrates the full Pipeline B:

```
[Cron: every 6h]
    → [HTTP: POST /arbitrage/discover-trends]   (calls fetch_tiktok_trends_apify.py)
    → [HTTP: POST /arbitrage/source-assets]     (calls source_youtube_assets.py)
    → [HTTP: POST /arbitrage/download]          (calls arbitrage_worker.py)
    → [HTTP: POST /arbitrage/distribute]        (calls distribute_arbitrage.py)
    → [HTTP: POST /api/workflows/log-step]      (existing workflow logging)
```

New endpoints to add to `mastra-agents/src/server.ts`:
```typescript
POST /arbitrage/discover-trends   // triggers fetch_tiktok_trends_apify.py via python worker
POST /arbitrage/source-assets     // triggers source_youtube_assets.py
POST /arbitrage/download          // triggers arbitrage_worker.py
POST /arbitrage/distribute        // triggers distribute_arbitrage.py
GET  /arbitrage/status            // returns counts from all 3 tables
```

---

## Phase 7: Dashboard Integration (2-3 hours)

Add a new "Arbitrage" page to the existing React dashboard.

**File:** `dashboard/src/pages/Arbitrage.tsx`

Sections:
- **Trend Intel** — table of discovered hashtags with velocity scores, status badges
- **Asset Queue** — list of YouTube videos pending download/upload
- **Upload Log** — recent uploads per platform with status
- **Controls** — manual "Run Discovery", "Run Download", "Run Distribute" buttons

All data fetched from the new API endpoints above.

---

## Phase 8: Python Worker Routes (1 hour)

Add new routes to `scripts/worker.py`:

```python
import scripts.fetch_tiktok_trends_apify as trend_discovery
import scripts.source_youtube_assets as asset_sourcer
import scripts.arbitrage_worker as downloader
import scripts.distribute_arbitrage as distributor

ROUTES = {
    # ... existing routes ...
    "/arbitrage/discover-trends": lambda body: trend_discovery.main(body.get("region", "US")),
    "/arbitrage/source-assets":   lambda body: asset_sourcer.main(body.get("limit", 5)),
    "/arbitrage/download":        lambda body: downloader.process_pending(),
    "/arbitrage/distribute":      lambda body: distributor.process_pending(body.get("platforms", ["tiktok"])),
}
```

---

## Environment Variables to Add

In `manga-automation/.env`:
```
# Apify
APIFY_TOKEN=

# Arbitrage pipeline
ARBITRAGE_VIDEOS_DIR=/data/arbitrage_videos
VELOCITY_THRESHOLD=0.5
ARBITRAGE_PLATFORMS=tiktok,youtube
MAX_ASSETS_PER_TREND=3

# YouTube OAuth (for Shorts upload)
# client_secrets.json must be placed in TiktokAutoUploader/
```

---

## Docker Changes

Add `arbitrage_videos` volume to `docker-compose.yml`:
```yaml
volumes:
  - ./data/arbitrage_videos:/data/arbitrage_videos
```

---

## Implementation Order

| Phase | Task | Time | Priority |
|-------|------|------|----------|
| 1 | DB migration (005_arbitrage_pipeline.sql) | 1h | HIGH |
| 2 | fetch_tiktok_trends_apify.py | 2h | HIGH |
| 3 | source_youtube_assets.py | 2h | HIGH |
| 4 | arbitrage_worker.py (yt-dlp download) | 1h | HIGH |
| 5 | distribute_arbitrage.py | 3h | HIGH |
| 6 | n8n workflow 06_arbitrage_pipeline.json | 2h | MEDIUM |
| 7 | New server.ts endpoints + worker.py routes | 1h | MEDIUM |
| 8 | Dashboard Arbitrage page | 2h | LOW |

**Total: ~14 hours**

---

## What We're NOT Doing (from the research doc)

- **OpenClaw/Clawdbot** — we already have n8n + Mastra agents doing the same job
- **Airtable** — we have PostgreSQL + our own dashboard
- **SQLite DevLog** — we have workflow_executions table
- **upload-post.com** — we have direct uploaders already
- **Capability evolver / self-improving agent** — out of scope for now

---

## Prerequisites Before Starting

1. **Apify account** — sign up at apify.com, get API token
2. **Apify actor subscriptions:**
   - `madoka_trendpulse/tiktok-trends-scraper` (~$3/1000 results)
   - `ecomscrape/youtube-video-search-scraper` (free tier available)
3. **YouTube OAuth** — `client_secrets.json` in `TiktokAutoUploader/` (for Shorts upload)
4. **TikTok account verified** — `nuggerchicken433` needs phone verification before uploads work

---

## Next Step

Run the DB migration first:
```powershell
docker exec -it manga-automation-postgres-1 psql -U manga_user -d manga_automation -f /migrations/005_arbitrage_pipeline.sql
```

Then start with Phase 2 (`fetch_tiktok_trends_apify.py`) once you have the Apify token.
