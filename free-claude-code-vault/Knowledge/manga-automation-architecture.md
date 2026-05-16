---
date: 2026-05-12
type: knowledge
tags:
  - knowledge
  - architecture
  - manga-automation
related-projects:
  - "[[Projects/manga-automation]]"
ai-first: true
---

## For future Claude
Deep-dive into the manga-automation system architecture as of 2026-05-12 (snapshot from project CURRENT_STATUS.md dated 2026-03-31). Covers 6 Docker services, database schema, API routes, agent types, and deployment layout. This note is a reference for understanding how the subsystems connect.

---

# manga-automation — System Architecture

## Service Topology

```
                    ┌──────────────┐
                    │   n8n (:5679) │  ← Cron triggers, workflow orchestration
                    └──────┬───────┘
                           │ HTTP calls
                    ┌──────▼───────┐
                    │ manga-agents  │  ← Node.js/Express (:3001)
                    │  (Mastra)     │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────▼───┐ ┌─────▼──────┐ ┌───▼──────────┐
     │ PostgreSQL  │ │   Redis    │ │ python-worker │
     │   (:5434)   │ │  (:6380)   │ │   (:8080)     │
     └────────────┘ └────────────┘ └───┬───────────┘
                                       │
                          ┌────────────┼────────────┐
                          │            │            │
                   ┌──────▼─────┐ ┌───▼────┐ ┌─────▼──────┐
                   │  Remotion  │ │ TikTok │ │ YouTube/IG │
                   │  Renderer  │ │Uploader│ │  Uploaders │
                   └────────────┘ └────────┘ └────────────┘

     ┌──────────────┐
     │  dashboard    │  ← React/Vite (:3000)
     │  (React SPA)  │
     └──────────────┘
```

## Database Schema (PostgreSQL)

Core tables (from `database/schema.sql` + migrations):

| Table | Purpose |
|---|---|
| `manga` | Manga series metadata (title, author, status) |
| `chapters` | Individual chapters linked to manga |
| `panels` | Downloaded manga panels with local paths |
| `videos` | Generated videos with file paths, captions, hashtags |
| `video_analytics` | Per-video engagement metrics |
| `video_variants` | A/B test variants for videos |
| `users` | Multi-tenant user accounts (Phase 2.1) |
| `organizations` | Tenant organizations (Phase 2.1) |
| `organization_members` | Role-based membership (Phase 2.1) |
| `proxies` | TikTok proxy configurations with protocol, is_active (Phase 2.3) |
| `tiktok_accounts` | Per-account proxy assignments and shadow-ban flags |
| `workflows` | Workflow definitions |
| `workflow_executions` | Execution history with status tracking |
| `workflow_steps` | Individual step logs within executions |
| `caption_templates` | Viral caption formula templates |
| `hashtag_templates` | Tiered hashtag strategy templates |

Migration files: `database/migrations/` — incremental schema changes.

## Mastra Agents (Node.js)

AI agents in `mastra-agents/src/agents/`:

| Agent | Purpose |
|---|---|
| Trend Agent | Detects trending manga from TikTok/Reddit signals |
| Panel Agent | Selects best panels from chapters for video composition |
| Caption Agent | Generates viral captions (5 formula types: cliffhanger, question, etc.) |
| Hashtag Agent | Selects tiered hashtags based on content type and genre |

Tools in `mastra-agents/src/tools/`:
- `database.ts` — PostgreSQL queries
- `queue.ts` — Chapter queue management
- `hashtags.ts` — Hashtag selection logic
- `captions.ts` — Caption generation

## Python Workers (scripts/)

**Core pipeline:**
- `worker.py` — Main worker with HTTP route dispatch
- `fetch_trending_manga.py` — MangaDex trending scraper
- `download_panels.py` — Panel image downloader
- `generate_video.py` — Remotion render trigger
- `upload_tiktok.py` — TikTok upload via Playwright/phantomwright

**Arbitrage pipeline (Pipeline B):**
- `fetch_tiktok_trends_apify.py` — Apify TikTok trend scraper
- `source_youtube_assets.py` — YouTube content sourcing
- `arbitrage_worker.py` — yt-dlp download worker
- `distribute_arbitrage.py` — Multi-platform distribution
- `upload_youtube.py` — YouTube Shorts upload
- `upload_instagram.py` — Instagram Reels upload
- `upload_pinterest.py` — Pinterest upload

**Agentic upgrade (CrewAI):**
- `scripts/crew/agents.py` — Agent definitions (Manager, Scout, Harvester, Operator, Analyst)
- `scripts/crew/pipeline_crew.py` — Crew assembly and orchestration
- `scripts/crew/tools.py` — Custom CrewAI tools
- `memory_manager.py` — ChromaDB vector memory (trend, account, fingerprint collections)

**Monetization & growth:**
- `monetization_activation.py` — TikTok Creator Rewards activation
- `monetization_ops.py` — Ongoing monetization operations
- `earnings_proof_ingest.py` — Screenshot-to-data ingestion
- `weekly_optimizer.py` — Weekly content strategy optimization

## Remotion Renderer

React-based video generation (`remotion-renderer/src/`):
- `MangaRecap.tsx` — Main composition (panel sequencing, transitions)
- `KenBurnsPanel.tsx` — Ken Burns effect (zoom/pan on still panels)
- `render-video.ts` — CLI entry point for headless rendering

Features: multiple motion types, background music, chapter splitting (>60s), video templates.

## Dashboard (React + Vite)

Pages (`dashboard/src/pages/`):
- `Analytics.tsx` — Video performance stats
- `MangaManager.tsx` — Manga series CRUD
- `PublisherDashboard.tsx` — Publishing queue and status
- `Workflows.tsx` — n8n workflow monitoring
- `TikTokAccounts.tsx` — Account + proxy management
- `ContentCalendar.tsx` — Scheduled video calendar
- `Arbitrage.tsx` — Pipeline B monitoring (Phase 2.5)

Auth removed in Phase 2.4 — single-user deployment, no login needed.
