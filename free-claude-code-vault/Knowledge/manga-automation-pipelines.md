---
date: 2026-05-12
type: knowledge
tags:
  - knowledge
  - pipelines
  - manga-automation
  - content-automation
related-projects:
  - "[[Projects/manga-automation]]"
ai-first: true
---

## For future Claude
Documents the two parallel content pipelines in manga-automation as of 2026-05-12. Pipeline A (MangaDex → Remotion → TikTok) is fully operational. Pipeline B (Apify Trends → YouTube → Multi-platform Arbitrage) is planned with an 8-phase implementation totaling ~14 hours. This note explains how both work.

---

# manga-automation — Pipeline A & B

## Pipeline A: Manga Recap (Production)

```
n8n Cron Trigger
    │
    ▼
[Mastra: Trend Agent] → Detects trending manga
    │
    ▼
[Mastra: Panel Agent] → Fetches chapters from MangaDex
    │
    ▼
[scripts/download_panels.py] → Downloads panel images
    │
    ▼
[Remotion Renderer] → Generates recap video
    │  • Ken Burns effects (zoom, pan)
    │  • Background music
    │  • Chapter splitting (>60s)
    │
    ▼
[Mastra: Caption Agent] → Generates viral caption (5 formulas)
[Mastra: Hashtag Agent] → Selects tiered hashtags
    │
    ▼
[scripts/upload_tiktok.py] → Publishes to TikTok
```

**Status:** Fully operational. Tested with chapter 79.1 — generated 80.57 MB video (128 seconds).

**API Endpoints:**
- `POST /pipeline/populate-queue` — Queue all chapters for a manga
- `POST /pipeline/render-video` — Generate video from queue
- `POST /webhook/queue-chapter` — Manual chapter selection
- `POST /captions/generate` — Generate viral captions
- `GET /hashtags/select` — Select strategic hashtags

---

## Pipeline B: Content Arbitrage (Planned)

A second pipeline running alongside Pipeline A. Sources trending content from YouTube and distributes to TikTok + YouTube Shorts + Instagram Reels.

```
[Apify: TikTok Trends Scraper]
    │  madoka_trendpulse/tiktok-trends-scraper
    │  Pulls trending hashtags with velocity scores
    ▼
[Mastra: Trend Evaluator]
    │  Validates trends against velocity threshold
    │  Deduplicates against existing trend_intel table
    ▼
[Apify: YouTube Search]
    │  ecomscrape/youtube-video-search-scraper
    │  Finds videos matching trend hashtags
    │  Filters: >10K views, <180s duration
    ▼
[scripts/arbitrage_worker.py]
    │  yt-dlp download
    │  Saves to data/arbitrage_videos/
    ▼
[scripts/distribute_arbitrage.py]
    ├── TikTok (TiktokAutoUploader)
    ├── YouTube Shorts (upload_youtube.py)
    └── Instagram Reels (future)
```

### New Database Tables (Migration 005)

| Table | Purpose |
|---|---|
| `trend_intel` | Trending hashtags with velocity scores, region, source |
| `arbitrage_assets` | YouTube videos sourced per trend, with local paths |
| `arbitrage_uploads` | Per-platform upload results (tiktok, youtube, instagram) |

### Implementation Phases

| Phase | Task | Time | Priority |
|---|---|---|---|
| 1 | DB migration (005_arbitrage_pipeline.sql) | 1h | HIGH |
| 2 | fetch_tiktok_trends_apify.py | 2h | HIGH |
| 3 | source_youtube_assets.py | 2h | HIGH |
| 4 | arbitrage_worker.py (yt-dlp) | 1h | HIGH |
| 5 | distribute_arbitrage.py | 3h | HIGH |
| 6 | n8n workflow (06_arbitrage_pipeline.json) | 2h | MEDIUM |
| 7 | New API endpoints + worker routes | 1h | MEDIUM |
| 8 | Dashboard Arbitrage page | 2h | LOW |

**Total: ~14 hours**

### Prerequisites
- Apify account + API token
- Apify actor subscriptions (TikTok trends scraper, YouTube search scraper)
- YouTube OAuth (`client_secrets.json`)
- TikTok account phone verification

---

## Shared Infrastructure

Both pipelines share:
- **PostgreSQL** — Single source of truth for all data
- **Redis** — Queue state and caching
- **n8n** — Cron-based workflow orchestration
- **Dashboard** — Unified monitoring UI
- **Python worker** — Route dispatch for all script execution
