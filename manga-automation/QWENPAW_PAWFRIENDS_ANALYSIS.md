# QwenPaw & PawFriends — Usage Analysis for manga-automation (AiToEarn)

**Date:** 2026-06-08
**Research scope:** Deep-dive into both platforms — what they are, how they work, and exactly how they can be integrated into the AiToEarn content arbitrage pipeline.

---

## Part 1: QwenPaw

### What Is It?

**QwenPaw** (formerly CoPaw) is a self-hosted personal AI assistant platform built by the AgentScope team. It runs locally — all data, memory, and agent configurations stay on your machine. It connects to chat platforms (Telegram, Discord, DingTalk, WeChat, etc.) and lets you create multiple independent AI agents, each with their own personality, skills, memory, and channels.

- **Repo:** [github.com/agentscope-ai/QwenPaw](https://github.com/agentscope-ai/QwenPaw)
- **Stars:** 17.3k | **License:** Apache 2.0
- **Version:** v1.1.10 (June 2026)
- **Stack:** Python 76.4% + TypeScript 18.5% (React console) + Tauri (desktop app)
- **Requirements:** Python ≥3.10, <3.14

### Core Architecture

```
┌────────────────────────────────────────────────────┐
│                   QwenPaw Instance                   │
│                                                      │
│  ┌─ Web Console (React) ─── http://127.0.0.1:8088   │
│  │  Chat UI · Agent Manager · Settings · Skills      │
│  ├──────────────────────────────────────────────────┤
│  │  FastAPI Backend (Python)                         │
│  │  ├─ Agent Runner (ReAct loop)                     │
│  │  ├─ Skill Pool (Python plugins)                   │
│  │  ├─ MCP Client (model context protocol)           │
│  │  ├─ Memory Engine (long-term + reflection)        │
│  │  ├─ Cron Scheduler (heartbeat + jobs)             │
│  │  └─ Multi-Channel Gateway                        │
│  ├──────────────────────────────────────────────────┤
│  │  Agent Workspaces (per-agent isolation)           │
│  │  ~/.qwenpaw/workspaces/{agent_id}/                │
│  │  ├─ agent.json      (config)                     │
│  │  ├─ chats.json      (conversation history)        │
│  │  ├─ AGENTS.md       (persona)                    │
│  │  ├─ SOUL.md         (character)                  │
│  │  ├─ PROFILE.md      (auto-generated for collab)  │
│  │  └─ skills/          (per-agent skill enablement) │
│  └──────────────────────────────────────────────────┘
│                                                      │
│  External Channels:                                   │
│  Telegram ←→ Discord ←→ DingTalk ←→ Feishu ←→ WeChat │
└────────────────────────────────────────────────────┘
```

### Key Features Relevant to AiToEarn

| Feature | What It Does | AiToEarn Relevance |
|---------|-------------|-------------------|
| **Multi-Agent Collaboration** | Agents call each other via built-in skill; each has own workspace, memory, persona | Maps 1:1 to 7 CrewAI agents (Manager, Scout, Harvester, Operator, Analyst, Engager, Monetizer) |
| **Skills System** | Python plugins auto-loaded from filesystem; no vendor lock-in | Wrap each pipeline stage as a Skill (trend detection, video rendering, upload, engagement) |
| **Cron / Heartbeat** | Scheduled task execution with configurable intervals | Replace n8n for pipeline scheduling ("run trend discovery every 6 hours") |
| **Memory Engine** | Long-term memory that evolves — learns from interactions, reflects on experience | Replace ChromaDB/ReMe with integrated memory for trend performance, account health, content fingerprints |
| **spawn_subagent** | Ephemeral sub-agents with optional git worktree isolation + background mode | Offload video rendering, upload tasks to isolated sub-agents that report back when done |
| **Multi-Channel** | Telegram, Discord, DingTalk, Feishu, WeChat, QQ, iMessage | Expose pipeline control plane via Telegram (already used) + Discord |
| **MCP Support** | Model Context Protocol client — connect to external tool servers | Connect to MangaDex MCP, TikTok MCP, YouTube MCP as standardized tool interfaces |
| **Coding Mode** | Three-panel Web IDE with git worktree + file tree + diff review | Debug pipeline scripts directly from the chat interface |
| **Desktop App (Beta)** | Tauri-based native app for Win/Mac; zero-config, double-click launch | Pipeline monitoring dashboard without browser |
| **REST API** | Full CRUD for agents, chats, skills, cron, tools, MCP | Drive pipeline programmatically while keeping chat UI for human oversight |
| **Docker Deploy** | Single `docker run` with 3 named volumes | Add to existing `docker-compose.yml` as a new service |
| **Local LLM Support** | llama.cpp, Ollama, LM Studio — no API key needed | Offline trend analysis, caption generation with local models |

---

### 8 Concrete Integration Paths for AiToEarn

#### Path 1: Telegram Control Plane (Lowest Effort, Highest Immediate Value)

**Current state:** manga-automation has a `telegram-bot` Docker service (`scripts/telegram_bot.py`) with custom command handling.

**With QwenPaw:** Replace the custom Telegram bot with QwenPaw's native Telegram channel. The pipeline becomes controllable via natural language in Telegram:

```
User in Telegram → QwenPaw (Telegram channel) → Pipeline Agent → executes tools → replies in Telegram

Examples:
  "Post 5 viral anime clips to TikTok today"
  "Show me account health for @manga_vault"
  "What trends are declining this week?"
  "Run a full arbitrage cycle for gaming content"
  "Pause all uploads — shadow ban detected on account 3"
```

**Implementation:**
```bash
# 1. Add QwenPaw to docker-compose.yml
# 2. Configure Telegram channel in QwenPaw Console
# 3. Create a "Pipeline Manager" agent with custom skills
# 4. Wire skills to existing scripts/ functions
```

**Files affected:** `docker-compose.yml` (add qwenpaw service), `scripts/telegram_bot.py` (can be retired)

---

#### Path 2: Agent-per-Pipeline-Stage (Full CrewAI Replacement)

**Current state:** 7 CrewAI agents defined in `scripts/crew/agents.py`, orchestrated in `scripts/crew/pipeline_crew.py` with `Process.sequential`.

**With QwenPaw:** Each agent becomes an independent QwenPaw agent with its own workspace, memory, and skills. The Manager agent uses the Multi-Agent Collaboration skill to delegate to specialists.

```
QwenPaw Agent Workspaces:
  ~/.qwenpaw/workspaces/
  ├── pipeline-manager/     # Leader — routes tasks, handles failures
  │   ├── AGENTS.md         # "You are the Pipeline Manager..."
  │   └── skills/           # Multi-agent collaboration + pipeline orchestration
  ├── trend-scout/          # Specialist — trend discovery
  │   ├── AGENTS.md         # "You are a cross-domain trend analyst..."
  │   └── skills/           # TikTok trends, Reddit trends, YouTube trending
  ├── content-harvester/    # Specialist — asset sourcing
  │   ├── AGENTS.md         # "You find high-quality source videos..."
  │   └── skills/           # yt-dlp, duplicate check, quality filter
  ├── platform-publisher/   # Specialist — upload execution
  │   ├── AGENTS.md         # "You publish to TikTok and YouTube..."
  │   └── skills/           # TikTok upload V1/V2, YouTube upload, account health
  ├── performance-analyst/  # Specialist — reporting + memory
  │   ├── AGENTS.md         # "You analyze results and maintain memory..."
  │   └── skills/           # ChromaDB/ReMe write, dashboard push, report gen
  ├── engagement-agent/     # Specialist — auto-engagement
  │   ├── AGENTS.md         # "You drive algorithmic reach..."
  │   └── skills/           # Playwright browser, smart commenting, like/follow
  └── monetization-agent/   # Specialist — revenue optimization
      ├── AGENTS.md         # "You maximize creator earnings..."
      └── skills/           # Marketplace matching, CPS/CPE/CPM tracking
```

**Key advantage over CrewAI:** The Manager agent dynamically decides which specialist to call and in what order, rather than following a static sequential DAG. If a trend suddenly goes cold mid-run, the Manager can abort sourcing and pivot to the next trend — CrewAI would finish the full sequence first.

---

#### Path 3: Skills as Pipeline Wrappers

**Current state:** Pipeline functions are spread across `scripts/` (Python) and `mastra-agents/src/` (TypeScript). They're called via n8n webhooks or direct CLI.

**With QwenPaw:** Each pipeline function becomes a QwenPaw Skill — a Python plugin that the agent can invoke in conversation.

**Skill structure for a pipeline function:**
```python
# ~/.qwenpaw/workspaces/pipeline-manager/skills/run_trend_discovery.py

"""
Skill: Trend Discovery
Triggers: "find trends", "what's trending", "trend discovery"
Description: Queries TikTok, Reddit, YouTube, and X for trending topics
             across all genesis_categories. Returns ranked list with
             viral_potential scores.
"""
import subprocess
import json

async def execute(args: dict, agent_context: dict) -> dict:
    """Called by QwenPaw when the agent decides to use this skill."""
    category = args.get("category", "all")
    count = args.get("count", 20)

    # Call the existing script
    result = subprocess.run(
        ["uv", "run", "python", "scripts/aitoearn_pipeline.py",
         "--stage", "trends", "--category", category, "--count", str(count)],
        capture_output=True, text=True, cwd="/app"
    )

    return json.loads(result.stdout)
```

**Skills to create:**
| Skill Name | Wraps | Trigger Phrases |
|-----------|-------|----------------|
| `trend_discovery` | `scripts/fetch_tiktok_trends_apify.py`, `fetch_twitter_trends.py`, etc. | "find trends", "what's trending" |
| `content_sourcing` | `scripts/arbitrage_worker.py` (YouTube sourcing) | "source content", "find videos for" |
| `video_render` | `scripts/generate_video.py`, Remotion renderer | "render video", "generate clip" |
| `tiktok_publish` | `TiktokAutoUploader` + `tiktok_v2.py` | "upload to TikTok", "publish" |
| `youtube_publish` | YouTube API upload | "upload to YouTube" |
| `engagement_cycle` | `scripts/engage/engine.py` | "run engagement", "auto-engage" |
| `account_health` | `scripts/detect_shadow_ban.py` | "check accounts", "shadow ban status" |
| `performance_report` | `scripts/crew/tools.py` (record/query functions) | "how did X perform", "pipeline report" |

---

#### Path 4: spawn_subagent for Long-Running Tasks

**Current state:** Remotion rendering (30-180s) and TikTok uploads block the pipeline. n8n has timeout issues.

**With QwenPaw:** The `spawn_subagent` tool with `background=True` offloads these tasks:

```python
# Agent conversation (in Telegram, Discord, or Console):

User: "Post this video to TikTok using account @manga_vault"

Agent: [internally calls spawn_subagent with background=True]
       → Subagent runs tiktok_publish skill in isolated workspace
       → Agent continues working on other tasks

[90 seconds later]

Agent: "✅ Published to TikTok: https://tiktok.com/@manga_vault/video/123456
        Account health: good (FYP ratio: 0.42)
        Also published to YouTube Shorts: https://youtube.com/shorts/abc123"
```

**For video rendering specifically:**
```python
# fork=True creates a git worktree — file-system isolated render
# background=True returns immediately with a TASK_ID
task = await spawn_subagent(
    instruction="Render the Remotion video for JJK Chapter 261 recap",
    fork=True,           # isolated git worktree
    background=True      # don't block the agent
)

# Agent receives TASK_ID and can poll:
#   check_agent_task(task_id="task_abc123")
# Returns: "running" → "finished" with video path
```

---

#### Path 5: Cron Jobs → Replace n8n Scheduling

**Current state:** n8n handles cron triggers for pipeline runs. The `agent-scheduler` service in docker-compose handles interval-based jobs.

**With QwenPaw:** Built-in cron replaced both:

```
QwenPaw Cron → Agent Heartbeat → Pipeline Execution

Examples:
  "0 */6 * * *"  → Run trend discovery every 6 hours
  "0 9 * * *"    → Morning briefing: top trends + account health
  "0 21 * * *"   → Evening pipeline: full arbitrage cycle
  "*/30 * * * *" → Check shadow-ban status on all accounts
```

**QwenPaw CLI for cron:**
```bash
qwenpaw cron add \
  --agent-id pipeline-manager \
  --schedule "0 */6 * * *" \
  --prompt "Run full trend discovery across all categories. Report top 20 trends."

qwenpaw cron add \
  --agent-id pipeline-manager \
  --schedule "0 21 * * *" \
  --prompt "Run the full arbitrage pipeline: find trends → source 3 videos → render → publish all → report."
```

---

#### Path 6: Memory Engine → Trend Intelligence Over Time

**Current state:** ChromaDB is planned with 3 collections (`trend_memory`, `account_health`, `content_fingerprints`). Memory manager is not yet live.

**With QwenPaw:** The built-in memory engine provides:

- **Trend memory:** Agent remembers which trends performed well, their velocity curves, and seasonal patterns — all through natural conversation, no vector DB queries
- **Account health:** Per-account upload history, shadow-ban flags, and FYP ratios are tracked in the agent's memory
- **Content fingerprints:** The agent remembers what was already posted and avoids duplicates

**How it works in practice:**
```
Week 1:
  User: "Post 5 anime clips"
  Agent: [posts 5 clips, records which ones in memory]

Week 2:
  User: "Post 5 anime clips"
  Agent: "Last week's JJK Chapter 261 recap got 120k views (↑40% vs previous).
          One Piece Chapter 1111 is declining (-30% week-over-week).
          I recommend: 3 JJK clips + 2 Solo Leveling clips (rising trend).
          Also — avoid Re:Zero, it got a shadow-ban flag last Tuesday."
```

No explicit "query ChromaDB" — the agent naturally recalls and reasons about past performance.

---

#### Path 7: Desktop App → Pipeline Monitoring Dashboard

**Current state:** React dashboard on port 3000 with 7 pages (Overview, Manga, Publisher, Workflows, TikTok, Calendar, Analytics).

**With QwenPaw:** The desktop app (Tauri, Win/Mac, beta) provides a native alternative:

- **Chat interface** → Pipeline CLI via natural language
- **Agent Manager** → See all 7 pipeline agents, their status, their last actions
- **Coding Mode** → Debug pipeline scripts directly
- **Skills Panel** → Enable/disable pipeline stages visually

**Use case:** The desktop app sits in the system tray. When a pipeline run completes (or fails), the agent sends a notification. One click opens the chat to see the full report.

---

#### Path 8: MCP Bridge → Unify Node.js + Python Tools

**Current state:** Mastra agents (Node.js/TypeScript) and CrewAI agents (Python) have separate tool implementations that don't share state.

**With QwenPaw MCP:** Both sides connect to the same MCP servers:

```
                    ┌─── MangaDex MCP Server ────┐
                    │  - search_manga             │
 Mastra (Node) ─────┤  - get_chapter_panels       ├──── QwenPaw (Python)
                    │  - fetch_trending           │
                    └─────────────────────────────┘

                    ┌─── TikTok MCP Server ───────┐
                    │  - upload_video              │
 Mastra (Node) ─────┤  - get_stats                 ├──── QwenPaw (Python)
                    │  - detect_shadow_ban         │
                    └──────────────────────────────┘
```

This enables the hybrid architecture: keep Mastra for Node-specific agents, use QwenPaw for Python pipeline control, share tools via MCP.

---

### Installation for manga-automation

#### Option A: Add to docker-compose.yml (Recommended)

```yaml
# New service in existing docker-compose.yml
qwenpaw:
  image: agentscope/qwenpaw:latest
  restart: unless-stopped
  networks: [ manga-net ]
  ports:
    - "8088:8088"
  environment:
    # LLM provider — use the same Anthropic key already in .env
    ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    ANTHROPIC_BASE_URL: ${ANTHROPIC_BASE_URL:-}
    # Channel API keys
    TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
    DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN:-}
    # External tool keys
    TAVILY_API_KEY: ${TAVILY_API_KEY:-}
    APIFY_API: ${APIFY_API}
    YOUTUBE_API_KEY: ${YOUTUBE_API_KEY}
    # Pipeline-specific env vars
    DATABASE_URL: postgresql://manga_user:${DB_PASSWORD}@postgres:5432/manga_automation
    CHROMADB_URL: http://chromadb:8000
    PYTHON_WORKER_URL: http://python-worker:8080
  volumes:
    - qwenpaw-data:/app/working
    - qwenpaw-secrets:/app/working.secret
    - qwenpaw-backups:/app/working.backups
    # Mount pipeline scripts so QwenPaw skills can call them
    - ./scripts:/app/scripts:ro
    - ./data/videos:/data/videos
    - ./data/arbitrage_videos:/data/arbitrage_videos
  depends_on:
    postgres:
      condition: service_healthy
    python-worker:
      condition: service_started

volumes:
  qwenpaw-data:
  qwenpaw-secrets:
  qwenpaw-backups:
```

#### Option B: Local dev install (for testing)

```bash
# Windows (PowerShell)
irm https://qwenpaw.agentscope.io/install.ps1 | iex

# Or via pip
pip install qwenpaw
qwenpaw init --defaults
qwenpaw app
# → Open http://127.0.0.1:8088/
```

#### Option C: Desktop app (for pipeline monitoring)

Download the Windows `.exe` from [GitHub Releases](https://github.com/agentscope-ai/QwenPaw/releases). Double-click to launch. Connects to the same QwenPaw backend (Docker or local).

---

### Effort Estimate

| Integration Path | Effort | When |
|-----------------|--------|------|
| Path 1: Telegram Control Plane | 1-2 days | Immediately |
| Path 2: Agent-per-Pipeline-Stage | 1-2 weeks | After AgentScope Agent Team validation |
| Path 3: Skills as Pipeline Wrappers | 3-5 days | Incrementally, per skill |
| Path 4: spawn_subagent for Rendering | 1-2 days | After Path 1 |
| Path 5: Cron Jobs (replace n8n) | 2-3 days | After Path 3 (needs skills) |
| Path 6: Memory Engine | 0 days (built-in) | Automatic with Path 2 |
| Path 7: Desktop App | 0 days (download) | Anytime |
| Path 8: MCP Bridge | 1 week | After AgentScope MCP setup |

---

## Part 2: PawFriends

### What Is It?

**PawFriends** (`pawfriends.live`) is billed as "Social media for AI agents" on the AgentScope homepage. The concept: AI agents have their own social network where they autonomously post, comment, debate, and build relationships with other AIs — no human coding required.

### Current Status: Pre-Launch / Placeholder

**PawFriends is not yet a functional product.** Here's the evidence:

| Signal | Status |
|--------|--------|
| Website (`pawfriends.live`) | Bare page — only shows "PawFriends - Where AI Agents Connect" with zero content, no sign-up, no docs |
| GitHub repository | Does NOT exist in the agentscope-ai org (confirmed: zero PawFriends repos among 20 listed) |
| PyPI package | Does not exist |
| Documentation | None on doc.agentscope.io |
| Skills integration | Not in the agentscope-ai/skills repo |
| Web search results | Zero articles, tutorials, or mentions beyond the agentscope.io homepage tagline |
| AgentScope homepage mention | One sentence: "Social media for AI agents — it posts, comments, debates, and builds relationships with other AIs on its own. No coding." |

**Conclusion:** PawFriends is a concept/announcement, likely in early internal development at Alibaba Cloud's Apsara Lab. It is not ready for external use.

### What It Promises (Based on AgentScope Homepage Description)

From the single sentence on `agentscope.io`: *"Social media for AI agents — it posts, comments, debates, and builds relationships with other AIs on its own. No coding."*

Inferred capabilities (when launched):
- Autonomous posting by AI agents
- Agents comment on each other's posts
- Debate/discussion between agents
- Agent-to-agent relationship building
- Zero-code setup — agents operate independently

### Potential Relevance to AiToEarn (When Launched)

Once PawFriends is live, here's how it could serve the content arbitrage pipeline:

| Use Case | How It Works |
|----------|-------------|
| **Content distribution channel** | AiToEarn agents post videos/clips to PawFriends as an additional platform. Other AI agents engage, boosting algorithmic visibility. |
| **Trend signal mining** | PawFriends becomes a real-time feed of what AI agents (trained on internet-scale data) find interesting. If 500 agents are posting about a specific topic, it's trending before it hits human social media. |
| **Agent reputation building** | The AiToEarn agents build reputation on PawFriends through quality content. This reputation could translate to better recommendations when the agents interact on human platforms. |
| **Cross-agent collaboration** | The Monetizer agent finds other agents on PawFriends that need content creation services → automated B2B agent services. |
| **Competitive intelligence** | The Scout agent monitors what other content-creator agents are posting → identifies trending formats, hashtags, and niches before they saturate human platforms. |
| **Engagement amplification** | The Engager agent likes/comments on other agents' posts → reciprocity drives engagement back → algorithmic boost on the platform. |

### Action Plan for PawFriends

1. **Monitor** — Watch `pawfriends.live` and the agentscope-ai GitHub org for a PawFriends repository
2. **Join Discord** — The AgentScope Discord (`discord.gg/eYMpfnkG8h`) may have preview/alpha access
3. **Prepare agents** — When it launches, the existing 7 QwenPaw pipeline agents (Path 2 above) should be immediately registerable as PawFriends personas since they share the AgentScope ecosystem
4. **No current action required** — All effort should go to QwenPaw integration (Part 1)

---

## Summary: What to Actually Do Now

### Week 1-2: QwenPaw Telegram Control Plane
```bash
# 1. Add QwenPaw to docker-compose.yml (see Option A above)
# 2. Configure Anthropic API key + Telegram bot token
# 3. Create "Pipeline Manager" agent
# 4. Test: "What's trending on TikTok for anime?" in Telegram
```

### Week 3-4: Skills + Cron
```bash
# 1. Wrap trend_discovery as a QwenPaw Skill
# 2. Wrap content_sourcing as a QwenPaw Skill
# 3. Set up cron: "Run trend discovery every 6 hours"
# 4. Test full pipeline trigger from Telegram
```

### Month 2: Agent-per-Stage
```bash
# 1. Create all 7 agent workspaces
# 2. Enable multi-agent collaboration skill
# 3. Wire skills to existing scripts/
# 4. Test: Manager → Scout → Harvester → Publisher → Analyst flow
```

### PawFriends: Wait
Check `pawfriends.live` monthly. Join AgentScope Discord for alpha access.

---

## Sources

- [QwenPaw GitHub](https://github.com/agentscope-ai/QwenPaw) — primary source
- [QwenPaw DeepWiki](https://deepwiki.com/agentscope-ai/QwenPaw) — architecture + multi-agent docs
- [QwenPaw PyPI](https://pypi.org/project/qwenpaw/) — package metadata + features
- [QwenPaw Official Site](https://qwenpaw.agentscope.io/) — documentation
- [AgentScope GitHub Org](https://github.com/orgs/agentscope-ai/repositories) — all 20 repos (confirmed no PawFriends repo)
- [AgentScope Skills Repo](https://github.com/agentscope-ai/skills) — available skills catalog
- [AgentScope Homepage](https://agentscope.io/) — PawFriends mention (one sentence)
- [QwenPaw Multi-Agent Docs](https://github.com/abo123456789/QwenPaw20260602/blob/main/website/public/docs/multi-agent.en.md) — collaboration + spawn_subagent details
- Current manga-automation codebase: `D:\Code\startup\manga-automation\`
  - `scripts/crew/agents.py` — 7 CrewAI agents to port
  - `scripts/crew/pipeline_crew.py` — sequential pipeline to replace
  - `docker-compose.yml` — target for QwenPaw service addition
  - `scripts/telegram_bot.py` — candidate for QwenPaw replacement
