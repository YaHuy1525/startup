---
date: 2026-05-12
updated: 2026-05-12
type: project
status: active
tags:
  - project
  - automation
  - manga
  - tiktok
  - content-creation
  - ai-agents
related-projects:
  - "[[Projects/free-claude-code]]"
ai-first: true
---

## For future Claude
manga-automation is an AI-powered manga content factory that scrapes manga panels, generates recap videos with Remotion, and auto-publishes to TikTok/YouTube/Instagram. Status: active as of 2026-05-12, currently in Phase 2 (SaaS transformation). It has two pipelines — Pipeline A (MangaDex → Remotion → TikTok) and Pipeline B (Apify trends → YouTube sourcing → multi-platform arbitrage). The Overview explains the full stack; Key Decisions documents major directional choices; Architecture section links to detailed knowledge notes.

---

# manga-automation

Automated manga content creation pipeline — AI agents scrape trending manga, generate recap videos with Ken Burns effects, and auto-publish across TikTok, YouTube Shorts, and Instagram Reels.

**Repo:** `D:\Code\startup\manga-automation`
**Stack:** Node.js 20 + TypeScript (Mastra agents), Python 3.x (workers), PostgreSQL 15, Redis 7, Remotion (React-based video), n8n (orchestration), React + Vite (dashboard), Docker Compose
**Last status update:** 2026-03-31 (as of `CURRENT_STATUS.md`)

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                PIPELINE A (Manga/Remotion)        │
│  n8n → Mastra Agents → MangaDex → Remotion →     │
│  TikTok upload                                    │
├──────────────────────────────────────────────────┤
│                PIPELINE B (Arbitrage)             │
│  Apify TikTok Trends → YouTube Sourcing →        │
│  yt-dlp Download → Multi-Platform Distribution    │
└──────────────────────────────────────────────────┘
           ↕ shared PostgreSQL + Redis
```

### Services (Docker Compose)

| Service | Port | Purpose |
|---|---|---|
| `postgres` | 5434 | Database — schema, migrations, all persistent state |
| `redis` | 6380 | Cache — queue state, session data |
| `manga-agents` | 3001 | Node.js API server — Mastra agents, webhooks, pipeline endpoints |
| `python-worker` | 8080 | Python worker — TikTok upload, yt-dlp download, trend discovery |
| `n8n` | 5679 | Workflow orchestrator — cron triggers, pipeline sequencing |
| `dashboard` | 3000 | React frontend — analytics, manga manager, publisher, workflows |

### Key Directories

| Directory | Purpose |
|---|---|
| `mastra-agents/` | Node.js backend — AI agents (trend, panel, caption), API server |
| `remotion-renderer/` | React-based video generation — Ken Burns effects, music overlay |
| `scripts/` | Python workers — TikTok/YouTube/Instagram upload, trend fetching, CrewAI agents |
| `dashboard/` | React + Vite frontend — 7 pages (Overview, Manga, Publisher, Workflows, TikTok, Calendar, Analytics) |
| `database/` | PostgreSQL schema + migrations |
| `n8n-workflows/` | 5 n8n workflow JSON definitions |
| `data/` | Persistent data — panels, videos, music, chromadb, postgres, redis |

---

## Current Status (Phase 2 — SaaS Transformation)

### Phase 1 — Complete
- Queue-based chapter posting with priority ordering
- Remotion video rendering with Ken Burns effects
- Viral caption generation (5 formula types)
- Strategic hashtag selection (tiered system)
- API endpoints: populate-queue, render-video, queue-chapter, generate-captions
- All workflows validated and tested

### Phase 2 — In Progress (4-week plan)
- ✅ Phase 2.1: Multi-tenancy database (users, organizations, proxies, video_variants)
- ✅ Phase 2.2: Workflow tracking API (list, execute, log steps, complete)
- ✅ Phase 2.3: TikTok multi-account & proxy management (CRUD + test endpoints)
- ✅ Phase 2.4: Dashboard data integration (all pages fetch real DB data, auth removed)
- ⏳ Phase 2.5: Advanced dashboard features (modal forms, drag-drop calendar, real-time monitoring)

---

## Key Decisions

- **Auth removed from dashboard** — Single-user deployment, auth was unnecessary overhead
- **PostgreSQL as single source of truth** — No SQLite, no Airtable; everything shares the same DB
- **n8n for orchestration** — Not Airflow or Temporal; n8n's visual editor + webhooks fit the content pipeline model
- **Remotion over FFmpeg scripts** — React-based compositions enable reusable templates and complex Ken Burns effects
- **V2 uploader isolation** — TikTok security bypass tested on separate file; production `tiktok.py` untouched until validated

---

## Open Questions (from CURRENT_STATUS.md)

1. Auth Provider: Supabase Auth or Clerk?
2. Proxy Service: Which provider to integrate?
3. Notification Service: SendGrid, AWS SES, or other?
4. Deployment Strategy: Keep Docker Compose or move to Kubernetes?
5. Monitoring: Sentry, LogRocket, or custom?

---

## Related Knowledge Notes

- [[Knowledge/manga-automation-architecture]] — Full system architecture deep-dive
- [[Knowledge/manga-automation-pipelines]] — Pipeline A (Manga/Remotion) and Pipeline B (Arbitrage) details
- [[Knowledge/manga-automation-agentic-upgrade]] — CrewAI, ChromaDB, TikTok security V2 plans
- [[Knowledge/manga-automation-saas-transformation]] — Phase 2 multi-tenancy SaaS plan

---

## Recent Activity

```dataview
LIST FROM "Daily"
WHERE contains(file.outlinks, this.file.link)
SORT date DESC
LIMIT 10
```
