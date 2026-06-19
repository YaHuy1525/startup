# QwenPaw + AgentScope Update — Summary

**Date:** 2026-06-08
**Status:** Phase 1 & 2 Complete — Ready for Docker deployment

---

## What Changed

This update adds **QwenPaw** (self-hosted multi-agent control plane) and **AgentScope Core** primitives to manga-automation, replacing Mastra + CrewAI + n8n as the agent orchestration layer while preserving **AiToEarn** as the publishing layer.

### Architecture: Before → After

```
BEFORE                               AFTER
──────                               ─────
n8n (12 workflows)            →      QwenPaw Cron Scheduler (5 cron jobs)
Mastra (9 TS agents)          →      QwenPaw Multi-Agent Workspaces (7 agents)
CrewAI (7 Py agents)          →      AgentScope Agent Team (leader-worker pattern)
ChromaDB (planned memory)     →      QwenPaw Memory Engine (ReMe, built-in)
telegram_bot.py (custom)      →      QwenPaw Telegram Channel (native)
AiToEarn MCP Client           →      AiToEarn MCP Client (PRESERVED — untouched)
All scripts/*.py              →      Wrapped as QwenPaw Skills (thin subprocess calls)
```

---

## Files Changed (2)

| File | Change |
|------|--------|
| `docker-compose.yml` | Added `qwenpaw` service (image: `agentscope/qwenpaw:latest`, port 8088, 3 named volumes, full env passthrough, healthcheck) + 3 volume declarations |
| `.env.example` | Added `QWENPAW_AUTH_ENABLED`, `QWENPAW_MODEL`, `SUMMON_BACKEND=qwenpaw` |

## Files Created (27)

### Skills Layer — `scripts/qwenpaw_skills/` (12 files)

| File | Wraps | Purpose |
|------|-------|---------|
| `__init__.py` | — | Shared constants, path setup |
| `_base.py` | — | `_run()` helper — subprocess with timeout, JSON parsing, error handling |
| `trend_discovery.py` | `aitoearn_pipeline.py --stage trend` | Query TikTok/Reddit/YouTube/X for trending topics |
| `content_sourcing.py` | `arbitrage_worker.py` | Source + download YouTube videos for trend concepts |
| `video_render.py` | `generate_video.py` | Trigger Remotion rendering (designed for `background=True` offloading) |
| `publish_content.py` | `aitoearn_pipeline.py --stage publish` | AiToEarn MCP fanout to 12 platforms with status polling |
| `engagement_cycle.py` | `engage/engine.py` | Auto-likes, AI comments, follows, comment mining |
| `account_health.py` | `detect_shadow_ban.py` | TikTok FYP ratio, shadow-ban detection |
| `performance_report.py` | `hermes_agent.py` | Pipeline stats, trend performance, revenue summary |
| `content_plan.py` | `genesis_discover.py` + `brief_generator.py` | Generate content briefs from trending topics |
| `finance_pipeline.py` | `hermes_agent.py --pipeline finance` | Earnings proof → AI video → publish via AiToEarn |
| `bootstrap_qwenpaw.py` | QwenPaw REST API | One-shot setup: creates 7 agents, Telegram channel, 5 cron jobs |

### Agent Personas — `scripts/qwenpaw_skills/workspaces/` (14 files)

| Agent | Files | Role |
|-------|-------|------|
| `pipeline-manager` | `AGENTS.md` + `SOUL.md` | Director — delegates to specialists, handles failures, makes strategic decisions |
| `trend-scout` | `AGENTS.md` + `SOUL.md` | Cross-platform trend discovery (TikTok, Reddit, YouTube, X) |
| `content-harvester` | `AGENTS.md` + `SOUL.md` | YouTube sourcing + quality verification + duplicate detection |
| `platform-publisher` | `AGENTS.md` + `SOUL.md` | AiToEarn-first publishing to 12 platforms, account health checks |
| `performance-analyst` | `AGENTS.md` + `SOUL.md` | Pipeline analytics, trend tracking, revenue correlations |
| `engagement-agent` | `AGENTS.md` + `SOUL.md` | Auto-engagement — likes, AI comments, follows, signal mining |
| `monetization-agent` | `AGENTS.md` + `SOUL.md` | Marketplace matching, CPS/CPE/CPM settlement tracking |

---

## Preserved (Zero Changes)

| Component | Preserved Because |
|-----------|-------------------|
| `scripts/adapters/aitoearn_client.py` | Core publishing — MCP fanout to 12 platforms with retry, status polling, fallback |
| `scripts/aitoearn_pipeline.py` | All 5 pipeline stages + AiToEarn-first routing logic |
| `scripts/crew/` (agents.py, pipeline_crew.py, tools.py) | CrewAI kept intact — switch via `SUMMON_BACKEND=crewai` env var |
| `scripts/engage/` (7 modules) | Browser automation, commenting, likes, follows, signal mining |
| `scripts/monetize/` (marketplace, settlement) | Revenue tracking and marketplace matching |
| `scripts/hermes_agent.py` | Ops monitoring — continues to run alongside QwenPaw |
| `scripts/telegram_bot.py` | Kept for rollback; QwenPaw Telegram channel replaces it when active |
| `mastra-agents/` (9 TS agents, server.ts) | Node.js layer preserved — MCP bridge for tool sharing |
| `dashboard/` (React + Vite + Nginx) | Continues to work unchanged |
| `database/` (PostgreSQL schema + migrations) | All tables and schemas unchanged |
| `n8n-workflows/` (12 JSON workflows) | Kept for rollback |
| `requirements.txt` | All existing dependencies kept |

---

## New Capabilities

### 1. Natural Language Pipeline Control
```
User in Telegram: "Post 5 viral anime clips to TikTok"
QwenPaw pipeline-manager: [delegates to trend-scout → content-harvester → platform-publisher]
→ AiToEarn publishes to 12 platforms → status confirmed → reports back in Telegram
```

### 2. Background Task Offloading
Long-running tasks (Remotion render 30-180s, TikTok upload) are offloaded via `spawn_subagent(background=True)`. The agent continues working while the task runs, then receives a wake-up with results.

### 3. Dynamic Pipeline (vs. Static DAG)
CrewAI used `Process.sequential` — fixed task order. QwenPaw's Agent Team pattern lets the pipeline-manager dynamically decide next steps. If a trend collapses mid-run, it pivots immediately instead of finishing the sequence.

### 4. Built-in Memory Engine
Replaces the planned ChromaDB (3 collections: trend_memory, account_health, content_fingerprints) with QwenPaw's native memory that learns from interactions and reflects on experience — no vector DB queries, just natural recall.

### 5. Cron-Based Automation (replaces n8n)
5 cron jobs on pipeline-manager:
- **Every 6 hours**: Trend discovery across all categories
- **Daily 8:57 AM**: Morning briefing (top trends + account health)
- **Daily 9:03 PM**: Full arbitrage pipeline (trends → source → publish → engage → report)
- **Every 30 minutes**: Shadow-ban monitoring on all accounts
- **Weekly Monday 9:47 AM**: Full performance + revenue report

### 6. Permission Guardrails
Publishing is gated: `platform-publisher` requires human confirmation before uploading. All other agents (trend discovery, sourcing, analysis) run bypassed.

---

## Rollback

Instant rollback — switch one env var:

```bash
# .env
SUMMON_BACKEND=crewai   # Back to CrewAI + n8n + telegram_bot.py
SUMMON_BACKEND=qwenpaw  # New QwenPaw multi-agent system
```

All old code is intact. No migration, no data loss risk.

---

## Quick Start

```bash
# 1. Start QwenPaw
docker compose up -d qwenpaw

# 2. Open Console → configure Anthropic API key + Telegram bot token
open http://localhost:8088

# 3. Bootstrap agents + cron jobs
docker compose exec qwenpaw python scripts/qwenpaw_skills/bootstrap_qwenpaw.py

# 4. Control pipeline from Telegram
# "Run full arbitrage pipeline for anime content"
# "What's trending on TikTok right now?"
# "Check account health — any shadow bans?"
```

---

## Files Listing

```
scripts/qwenpaw_skills/
├── __init__.py
├── _base.py
├── account_health.py
├── bootstrap_qwenpaw.py
├── content_plan.py
├── content_sourcing.py
├── engagement_cycle.py
├── finance_pipeline.py
├── performance_report.py
├── publish_content.py
├── trend_discovery.py
├── video_render.py
└── workspaces/
    ├── content-harvester/
    │   ├── AGENTS.md
    │   └── SOUL.md
    ├── engagement-agent/
    │   ├── AGENTS.md
    │   └── SOUL.md
    ├── monetization-agent/
    │   ├── AGENTS.md
    │   └── SOUL.md
    ├── performance-analyst/
    │   ├── AGENTS.md
    │   └── SOUL.md
    ├── pipeline-manager/
    │   ├── AGENTS.md
    │   └── SOUL.md
    ├── platform-publisher/
    │   ├── AGENTS.md
    │   └── SOUL.md
    └── trend-scout/
        ├── AGENTS.md
        └── SOUL.md
```

---

## Related Documents

- [AGENTSCOPE_ADOPTION_ANALYSIS.md](./AGENTSCOPE_ADOPTION_ANALYSIS.md) — 12-tool evaluation with adoption roadmap
- [QWENPAW_PAWFRIENDS_ANALYSIS.md](./QWENPAW_PAWFRIENDS_ANALYSIS.md) — Deep-dive into QwenPaw + PawFriends usage patterns
