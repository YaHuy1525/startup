# Upgrade Guide: Autonomous Content Arbitrage (OpenClaw + YouTube Pipeline)

This guide provides a comprehensive, step-by-step plan to integrate the new **Autonomous Content Arbitrage** architecture into the existing Manga TikTok Automation System.

Crucially, **this new pipeline will run alongside the existing MangaDex/Remotion pipeline, not replace it.** The existing system will continue generating manga panel videos, while the new system will autonomously scrape TikTok trends, source high-fidelity assets from YouTube Shorts, and upload them.

## 1. Architecture Overview

The enhanced system will feature a "Dual-Pipeline" architecture:

1.  **Pipeline A (Existing):** n8n + Mastra Agents → MangaDex → Remotion → Python Uploader → TikTok.
2.  **Pipeline B (New):** OpenClaw Gateway → Apify Actors (TikTok Trends) → Apify Actors (YouTube Source) → TiktokAutoUploader → TikTok.

Both pipelines will share the existing PostgreSQL database for state management and logging, avoiding the need to migrate to SQLite or Airtable.

## 2. Prerequisites & Environment Setup

Before implementing the code changes, ensure the following tools and accounts are prepared:
-   **OpenClaw Runtime:** Node.js v22+ environment.
-   **Apify Account:** An active Apify account with API token, and subscriptions to:
    -   `madoka_trendpulse/tiktok-trends-scraper` (or equivalent for TikTok Creative Center)
    -   `ecomscrape/youtube-video-search-scraper`
    -   `crawlerbros/youtube-video-downloader`
-   **TiktokAutoUploader:** The `makiisthenes/TiktokAutoUploader` repository will be integrated into the python worker container.

## 3. Database Schema Extensions (PostgreSQL)

We need to extend the current Supabase PostgreSQL database to track trends, YouTube assets, and the new workflow status.

Execute the following SQL commands to create the new tables:

```sql
-- Track TikTok Trends identified by Apify
CREATE TABLE tiktok_trends (
    id SERIAL PRIMARY KEY,
    hashtag VARCHAR(255) NOT NULL,
    region VARCHAR(50) NOT NULL,
    trend_velocity FLOAT,
    avg_views BIGINT,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending' -- pending, sourced, ignored
);

-- Track YouTube videos sourced for arbitrage
CREATE TABLE youtube_assets (
    id SERIAL PRIMARY KEY,
    trend_id INTEGER REFERENCES tiktok_trends(id),
    youtube_url TEXT NOT NULL,
    video_title TEXT,
    channel_name TEXT,
    metadata_summary TEXT,
    local_path TEXT,
    status VARCHAR(50) DEFAULT 'downloaded', -- downloaded, processing, uploaded
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Extend upload_results or create a new table for Pipeline B
CREATE TABLE arbitrage_uploads (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES youtube_assets(id),
    tiktok_account_id INTEGER REFERENCES tiktok_accounts(id),
    tiktok_url TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN DEFAULT FALSE,
    error_log TEXT
);
```

## 4. Component Implementation Guide

### Phase 1: OpenClaw Gateway Integration
Instead of replacing n8n, OpenClaw will run as a new Docker service to handle the "probabilistic reasoning" (LLM-based planning).

1.  **Add OpenClaw to `docker-compose.yml`:**
    Create a new service block for OpenClaw.
    ```yaml
    openclaw-gateway:
      image: openclaw/gateway:latest
      container_name: openclaw-gateway
      environment:
        - OPENAI_API_KEY=${OPENAI_API_KEY} # Or Anthropic
        - APIFY_API_TOKEN=${APIFY_API_TOKEN}
        - DATABASE_URL=${DATABASE_URL}
      volumes:
        - ./openclaw_config:/app/config
        - ./data/videos:/data/videos
      restart: unless-stopped
    ```
2.  **Configure Heartbeat:** Set up `openclaw.json` to trigger a heartbeat every 30 minutes to run the `Trend Discovery` skill.

### Phase 2: Trend Discovery & Sourcing (Apify Integration)

Create a set of OpenClaw "Skills" (Node.js/TypeScript functions) that interface with Apify:

1.  **Trend Discovery Skill:**
    -   Triggered by the OpenClaw heartbeat.
    -   Calls `madoka_trendpulse/tiktok-trends-scraper` via Apify API.
    -   LLM evaluates the `trend_velocity`. If high enough, inserts a record into the `tiktok_trends` Postgres table.
2.  **Asset Sourcing Skill:**
    -   Triggered when a new trend is added to the DB.
    -   Calls `ecomscrape/youtube-video-search-scraper` using the hashtag/trend as a query (e.g., `#manga recommendations`).
    -   Filters for Shorts under 60 seconds.
    -   Calls `crawlerbros/youtube-video-downloader` to fetch the MP4.
    -   Saves the file to `/data/videos/arbitrage/` and inserts a record into `youtube_assets`.

### Phase 3: Distribution Engine (TiktokAutoUploader)

As verified, the `makiisthenes/TiktokAutoUploader` tool works reliably via CLI and supports direct YouTube links or local file uploads. We will integrate this into the existing `python-worker`.

1.  **Update Python Worker Dependencies:**
    Add the `TiktokAutoUploader` dependencies to `requirements.txt`. Note the specific version requirements to avoid conflicts:
    ```text
    selenium>=4.18.1
    setuptools==69.5.1
    moviepy==1.0.3
    pyppeteer
    websockets>=10.0
    # ... other requirements from TiktokAutoUploader
    ```
2.  **Clone Uploader into Worker:** Update `Dockerfile.python` to clone the uploader repository during the build process, or add it as a submodule.
3.  **Create Wrapper Script (`scripts/upload_arbitrage.py`):**
    Write a Python script that OpenClaw can trigger (via a CLI execution skill or HTTP webhook).
    This script will:
    - Query `youtube_assets` for `status = 'downloaded'`.
    - Execute the CLI command: `python TiktokAutoUploader/cli.py upload --user <account> -v <local_path> -t <generated_caption>`
    - Alternatively, it can skip the Apify download step entirely and use the `-yt` flag if the uploader's YouTube download feature is preferred: `python TiktokAutoUploader/cli.py upload --user <account> -yt <youtube_url> -t <caption>`
    - Update the `arbitrage_uploads` and `youtube_assets` tables based on success/failure.

### Phase 4: Workflow Orchestration

To tie it all together, we use the "Hybrid Orchestration" model mentioned in the design doc:

1.  **OpenClaw Planner:** OpenClaw runs the Heartbeat -> Scrapes Apify -> Decides what to source -> Saves to DB.
2.  **OpenClaw -> Python Worker Handoff:** Once the asset is ready, OpenClaw makes an HTTP POST request to a new endpoint on the `python-worker` (e.g., `POST /arbitrage/upload`).
3.  **Execution:** The Python worker runs the `TiktokAutoUploader` and reports back to the database.

## 5. Security & Guardrails

-   **Niche Locking:** Prompt the OpenClaw system heavily to *only* search for YouTube assets related to your specific niches (e.g., manga, anime) to prevent it from arbitraging unrelated viral content.
-   **Copyright Safety:** Consider adding an LLM filtering step in OpenClaw that checks the YouTube video description for "Original Animation" or "Do Not Repost" warnings before downloading.

## 6. Next Steps for the AI Agent

To execute this plan, the AI Agent should proceed with the following sequence:
1. Modify `docker-compose.yml` to include the `openclaw-gateway` service.
2. Create the SQL migration file in `database/` for the new tables.
3. Update the `Dockerfile.python` and `requirements.txt` to include `TiktokAutoUploader`.
4. Create the `scripts/upload_arbitrage.py` wrapper script.
5. Create the OpenClaw configuration and skill files for Apify interaction.
