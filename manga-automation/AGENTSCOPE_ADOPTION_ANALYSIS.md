# AgentScope Adoption Analysis for manga-automation (AiToEarn)

**Date:** 2026-06-08
**Author:** Research & Analysis
**Scope:** Full-stack evaluation — 12 AgentScope ecosystem tools mapped against the current manga-automation architecture

---

## Executive Summary

AgentScope (`agentscope.io`) is an Apache 2.0-licensed, production-grade multi-agent framework built by Alibaba Cloud's Apsara Lab. Its ecosystem spans the full agent lifecycle — framework (Core + Java + TypeScript), runtime hosting (Runtime), memory (ReMe), evaluation (OpenJudge), fine-tuning (Trinity-RFT), and visualization (Studio). Version 2.0 (June 2026) adds agent teams, background task offloading, workspace sandboxing, and a permission system.

**Verdict:** 7 of 12 tools map directly to existing or planned manga-automation components. The highest-value adoptions are ReMe (drop-in ChromaDB replacement), Agent Team pattern (CrewAI alternative), and Background Task Offloading (solve video rendering/upload timeout pain). AgentScope is Python-first, which aligns with the project's Python worker — the main friction is the Mastra Node.js agent layer, which would need to be ported or kept as a hybrid.

---

## Current Architecture (Baseline)

```
┌──────────────────────────────────────────────────────────┐
│  ORCHESTRATION: n8n (cron triggers, webhooks, sequencing) │
├──────────────────────────────────────────────────────────┤
│  AGENT LAYER                                              │
│  ┌─ Mastra (Node/TS) ────┐  ┌─ CrewAI (Python) ────────┐ │
│  │ trendDetector           │  │ Manager + 6 specialists   │ │
│  │ captionGenerator        │  │ scout, harvester, operator │ │
│  │ panelSelector           │  │ analyst, engager, monetizer│ │
│  │ shadowBanDetector       │  │ Pipeline: sequential tasks │ │
│  │ musicSelector           │  └──────────────────────────┘ │
│  │ scriptwriter, etc.      │                               │
│  └────────────────────────┘                               │
├──────────────────────────────────────────────────────────┤
│  MEMORY: ChromaDB (3 collections — planned, not live)     │
│  DB: PostgreSQL 15 (single source of truth)               │
│  CACHE: Redis 7                                            │
├──────────────────────────────────────────────────────────┤
│  WORKERS: Python (ffmpeg, Playwright, yt-dlp, uploaders)  │
│  RENDERER: Remotion (React-based video with Ken Burns)    │
│  DASHBOARD: React + Vite + Nginx                          │
└──────────────────────────────────────────────────────────┘
```

**Key pain points:**
- Mastra and CrewAI are separate agent systems — no shared memory, no unified observability
- Video rendering (Remotion) and TikTok uploads are long-running and block the pipeline
- ChromaDB integration is hand-rolled with custom `memory_manager.py`
- No automated quality evaluation — captions and videos are not scored before publishing
- Multi-tenancy (Phase 2) requires custom PostgreSQL schema work

---

## Tool-by-Tool Analysis

### 1. AgentScope Core → Replace/Consolidate Mastra + CrewAI

| Attribute | Current (Mastra + CrewAI) | AgentScope Core |
|-----------|--------------------------|-----------------|
| Language | Node/TS + Python | Python 3.11+ (single stack) |
| Agent Model | `@mastra/core/agent` + `crewai.Agent` | `agentscope.agent.Agent` |
| Model Backend | Anthropic SDK + custom LLM wrapper | `DashScopeChatModel` + multi-model with retry/fallback |
| Tool System | Zod schemas + `@tool` decorator | `Toolkit([Bash(), Grep(), Glob(), Read(), Write(), Edit()])` |
| Event System | None (polling) | Typed event bus (REPLY_START, MODEL_CALL_START, TEXT_BLOCK_DELTA, etc.) |
| Streaming | Manual SSE | Native async streaming with `agent.reply_stream()` |
| Middleware | None | Composable hooks for the reasoning-acting loop |

**Migration path:**
- Port 9 Mastra agents (`trendDetector.ts`, `captionGenerator.ts`, `panelSelector.ts`, etc.) to AgentScope Python agents
- Replace `CrewAI Agent(role=..., goal=..., backstory=...)` with AgentScope Agent + Team pattern
- Keep the `_make_llm()` pattern but use AgentScope's `DashScopeChatModel` wrapper

**Files to create:**
```
scripts/agentscope/
├── __init__.py
├── agents/
│   ├── trend_detector.py       # ← trendDetector.ts
│   ├── caption_generator.py    # ← captionGenerator.ts
│   ├── panel_selector.py       # ← panelSelector.ts
│   ├── shadow_ban_detector.py  # ← shadowBanDetector.ts
│   ├── music_selector.py       # ← musicSelector.ts
│   ├── content_optimizer.py    # ← contentOptimizer.ts
│   ├── scriptwriter.py         # ← scriptwriter.ts
│   ├── gig_draft_generator.py  # ← gigDraftGenerator.ts
│   └── gig_rubric_scorer.py    # ← gigRubricScorer.ts
├── tools/
│   ├── mangadex_tools.py       # MangaDex API wrappers
│   ├── tiktok_tools.py         # TikTok upload + stats
│   ├── youtube_tools.py        # YouTube sourcing + upload
│   ├── ffmpeg_tools.py         # Video processing (sandboxed)
│   └── database_tools.py       # PostgreSQL queries
├── memory/
│   └── reme_config.py          # ReMe vector + file memory (see §2)
└── pipeline.py                 # Agent Team orchestration (see §3)
```

**Effort:** Medium (9 agents × ~2 hours each = ~18 hours)
**Risk:** Medium — porting TypeScript logic to Python, Zod → Python type validation
**Priority:** Phase 4 (after ReMe and background tasks are validated)

---

### 2. ReMe (Memory Management Kit) → Replace Planned ChromaDB

**Status:** ChromaDB is in `docker-compose.yml` (port 8001) but the three collections are still planned per `manga-automation-agentic-upgrade.md`.

| Attribute | Current (ChromaDB Plan) | ReMe |
|-----------|------------------------|------|
| Vector Memory | `chromadb` container, custom `memory_manager.py` | Built-in, file-based + vector-based |
| Agent Integration | Manual: agents call `query_trend_memory()`, `record_trend_performance()` | Native: agents remember preferences, learn from past interactions |
| Collections | 3 manual: `trend_memory`, `account_health`, `content_fingerprints` | Automatic categorization + metadata |
| Persistence | Docker volume (`./data/chromadb`) | Configurable backend |
| Migration Path | N/A (not live yet) | Zero migration — adopt directly |

**Mapping of planned ChromaDB collections to ReMe:**

| ChromaDB Collection | ReMe Equivalent |
|---------------------|-----------------|
| `trend_memory` — viral topics + view counts + dates + performance scores | ReMe episodic memory — auto-tagged with topic, platform, velocity score |
| `account_health` — per-account upload history + shadow-ban flags + view averages | ReMe file memory — JSON records with metadata indexing |
| `content_fingerprints` — video hashes to prevent re-uploads | ReMe vector memory — perceptual hash embeddings for dedup |

**Impact on existing feedback loop:**
```
Current (ChromaDB plan):
  Trend Agent → ChromaDB manual query → Python comparison logic → recommendation

With ReMe:
  Trend Agent → Agent.reply("What's declining this week?") → ReMe auto-retrieves context
```

**Files to change:**
- `scripts/memory_manager.py` — replace ChromaDB client with ReMe setup
- `scripts/crew/tools.py` — replace `query_trend_memory()`, `get_account_health_tool()`, `check_content_duplicate()` with ReMe-native calls
- `docker-compose.yml` — optional: keep ChromaDB for backward compat, add ReMe config

**Effort:** Low (1-2 days)
**Risk:** Low — ChromaDB is not yet in production use
**Priority: HIGH — adopt immediately**

---

### 3. Agent Team (Leader-Worker Pattern) → Replace CrewAI Sequential Pipeline

**Released:** June 2026, matches the project's CrewAI Manager + 6 specialist architecture.

| Attribute | Current (CrewAI) | AgentScope Agent Team |
|-----------|-----------------|----------------------|
| Pattern | `Process.sequential` — fixed task order | Leader spawns workers dynamically, coordinates via built-in team tools |
| Failure Handling | Manual quarantine logic in Manager prompt | Built-in: leader detects failures, reassigns autonomously |
| Memory Integration | ChromaDB via tool calls | ReMe natively integrated |
| Sandbox | None (tools run in-process) | Workspace isolation (local / Docker / E2B) |
| Rate Limiting | `max_rpm=10` hard cap | Configurable per-agent |

**Architecture mapping:**
```
Current CrewAI:
  Manager (Agent, allow_delegation=True)
    ├── Scout (Task: trend_discovery)
    ├── Harvester (Task: source_assets → download)
    ├── Operator (Task: upload)
    ├── Analyst (Task: report)
    ├── Engager (Task: engage)
    └── Monetizer (Task: monetize)

AgentScope Team:
  Leader Agent (with Team tools)
    ├── TrendScout Agent (self-directed, uses ReMe memory)
    ├── Harvester Agent (self-directed, uses Workspace sandbox)
    ├── Publisher Agent (self-directed, uses background task offloading)
    ├── Analyst Agent (self-directed, writes to ReMe)
    ├── Engager Agent (self-directed, uses Playwright sandbox)
    └── Monetizer Agent (self-directed, API calls)
```

**Key improvement:** In CrewAI, tasks are explicitly sequenced (`context=[task_X]`). In AgentScope Team, the leader dynamically decides what to do next based on intermediate results — no static DAG.

**Files affected:**
- `scripts/crew/agents.py` → `scripts/agentscope/agents/` (7 agents)
- `scripts/crew/pipeline_crew.py` → `scripts/agentscope/pipeline.py` (team orchestration)
- `scripts/crew/tools.py` → `scripts/agentscope/tools/` (24 tools)
- `scripts/crew/__init__.py` → `scripts/agentscope/__init__.py`

**Effort:** High (1-2 weeks — port all tools, rewire orchestration)
**Risk:** Medium — CrewAI pipeline is core to Phase 3 operations
**Priority:** Medium — adopt after ReMe; run in parallel with CrewAI during transition

---

### 4. Background Task Offloading → Solve Video Rendering & Upload Timeouts

**Problem statement:** Remotion renders and TikTok uploads take 30-180 seconds. In the current sequential pipeline, they block the entire flow. n8n has timeout issues with long-running steps.

**AgentScope solution:** "A long-running tool moves to the background; its result later wakes the agent up and the conversation resumes."

**How it works in AgentScope:**
```python
# Long-running tool is registered as a background-capable tool
toolkit = Toolkit(tools=[
    Bash(),                          # short commands run inline
    RenderVideo(background=True),    # Remotion render → offloaded
    UploadToTikTok(background=True), # Upload → offloaded
    UploadToYouTube(background=True),# Upload → offloaded
])

# Agent issues the tool call, continues working on other tasks
# When the render/upload completes, the agent is woken up with the result
```

**Impact on pipeline:**
```
Current (blocking):
  Download → WAIT → Render → WAIT → Upload TikTok → WAIT → Upload YouTube → WAIT → Report

With background offloading:
  Download → Render (background) ─┐
           → Upload TikTok (bg) ──┤ all run concurrently
           → Upload YouTube (bg) ─┘
           → Agent works on next item
           ← Wakes when all complete → Report
```

**Files to create/modify:**
- `scripts/agentscope/tools/render_tools.py` — wrap Remotion render as background tool
- `scripts/agentscope/tools/upload_tools.py` — wrap TikTok/YouTube upload as background tool
- `docker-compose.yml` — no change needed (tools run in existing containers)

**Effort:** Low (wrap existing functions with AgentScope tool interface)
**Risk:** Low — additive change, doesn't break existing flow
**Priority: HIGH — adopt immediately**

---

### 5. Workspace / Sandbox Execution → Replace Raw Docker Exec

**Current state:** Python worker runs ffmpeg, Playwright, and yt-dlp directly in its container. The V2 TikTok uploader (`tiktok_v2.py`) is isolated by convention (separate file), not by sandbox.

**AgentScope solution:** Three sandbox backends:
- **Local** — subprocess isolation (lightweight)
- **Docker** — container-per-tool (matches current Docker Compose architecture)
- **E2B** — cloud sandbox (for production scale)

**Use in manga-automation:**
| Operation | Risk Level | Recommended Sandbox |
|-----------|-----------|-------------------|
| ffmpeg video mutation (V2 uploader) | Medium — arbitrary codec params | Docker (ephemeral container) |
| Playwright browser automation (engage) | High — executes JS on remote pages | Docker (network-isolated) |
| yt-dlp download | Low — URL fetching | Local |
| TikTok upload API calls | Low — HTTP requests | Local |

**Benefit:** The V2 uploader's isolation strategy ("isolated file, never touches `tiktok.py`") becomes enforced by the framework rather than developer discipline.

**Effort:** Low (AgentScope handles sandbox lifecycle)
**Risk:** Low — opt-in per tool
**Priority:** Medium — adopt with background tasks

---

### 6. Permission System → Content Publishing Guardrails

**Current state:** Publishing decisions are made by the Operator agent's LLM judgment. There is no programmatic guardrail — if the LLM hallucinates, content can be published un-reviewed.

**AgentScope solution:** Fine-grained permission control with a bypass mode:
- **Permission mode:** Agent pauses before every tool call, waits for human approval
- **Bypass mode:** Agent runs end-to-end without pausing (for trusted workflows)

**Use in manga-automation:**

```
Production pipeline:
  Scout → Bypass (trend discovery is safe)
  Harvester → Bypass (sourcing is safe)
  Render → Bypass (video generation is safe)
  Operator (upload) → PERMISSION REQUIRED (publishing is irreversible)
  Engager → Partial (auto-like bypass, auto-comment requires permission)
  Monetizer → Bypass (read-only marketplace scanning)
```

**Implementation:**
```python
publisher_agent = Agent(
    name="Publisher",
    system_prompt="You publish content to TikTok and YouTube.",
    model=chat_model,
    toolkit=upload_toolkit,
    permission="confirm",  # Human must approve each upload
)

scout_agent = Agent(
    name="TrendScout",
    system_prompt="You find trending content.",
    model=chat_model,
    toolkit=trend_toolkit,
    permission="bypass",  # Safe — read-only operations
)
```

**Effort:** Low (configuration-level, not code-level)
**Risk:** None — purely additive guard
**Priority:** Medium — adopt before production publishing scale-up

---

### 7. OpenJudge (Evaluation Framework) → Automated Content Quality Scoring

**Current state:** Content quality is assessed manually or through heuristic rules. No automated feedback loop to improve caption quality, video engagement, or hashtag effectiveness.

**AgentScope solution:** 50+ judges measuring tool use, code, math, and multimodal output.

**Potential judges for manga-automation:**

| Judge | What It Scores | Integration Point |
|-------|---------------|-------------------|
| Caption Quality Judge | Viral potential, hook strength, call-to-action effectiveness | After caption generation, before publishing |
| Video Engagement Judge | Pacing, visual interest, Ken Burns effect quality | After Remotion render, before upload |
| Hashtag Strategy Judge | Reach vs. competition, tier balance, trend alignment | After hashtag selection |
| Content Originality Judge | Duplicate detection, transformative use score | After asset sourcing |
| Shadow-Ban Risk Judge | Account health, content pattern, upload frequency | Before publishing |

**Feedback loop:**
```
Generate captions → OpenJudge scores → Below threshold → Regenerate → Score again → Publish
Render video → OpenJudge scores → Below threshold → Re-render with adjustments → Publish
```

**Effort:** Medium (define judges, integrate into pipeline stages)
**Risk:** Low — read-only evaluation, doesn't block publishing
**Priority:** Low-Medium — quality-of-life improvement, not blocking

---

### 8. AgentScope Runtime → Production-Grade Multi-Tenant Serving

**Current state:** Phase 2 SaaS transformation added multi-tenancy (users, organizations, proxies, video_variants) via custom PostgreSQL schema. Each deployment is single-instance Docker Compose.

**AgentScope solution:** FastAPI-based runtime with:
- Multi-tenancy and multi-session isolation out of the box
- Pre-built Web UI (React frontend)
- Streaming responses via WebSocket/SSE

**Relevance:** If manga-automation evolves into a SaaS platform (multiple users, each with their own agents, accounts, and pipelines), Runtime provides the isolation layer without custom schema work.

**Fit assessment:**
- **Now (Phase 3, single-user):** Overkill — Docker Compose is sufficient
- **Future (Phase 4+, multi-tenant SaaS):** Strong fit — replaces custom multi-tenancy plumbing

**Effort:** High (migrate Docker Compose to Runtime deployment)
**Risk:** High if done prematurely
**Priority:** Low — revisit after Phase 3 stabilizes and multi-tenant demand is validated

---

### 9. MCP (Model Context Protocol) Support → Standardized External API Tooling

**Status:** Confirmed in AgentScope documentation. Not detailed in the GitHub README but present in the doc navigation under "Tool > MCP."

**Use in manga-automation:**
- **MangaDex MCP Server:** Standardized chapter/panel API access (currently: custom `mangadex.ts` tool)
- **TikTok MCP Server:** Upload, stats, trend discovery (currently: `TiktokAutoUploader` + Apify)
- **YouTube MCP Server:** Search, download, upload (currently: `youtube_tools.py`)

**Benefit:** Tools become reusable MCP servers that any agent (not just AgentScope) can connect to. This enables the hybrid architecture where Mastra agents (Node) and AgentScope agents (Python) share the same tool servers.

**Effort:** Medium (wrap existing tools as MCP servers)
**Risk:** Low — incremental change, doesn't break existing tool calls
**Priority:** Medium — aligns with the project's multi-stack nature

---

### 10. AgentScope Studio → Agent Run Visualization & Debugging

**Current state:** Dashboard has 7 pages (Overview, Manga, Publisher, Workflows, TikTok, Calendar, Analytics) but no agent-specific debugging view. Debugging multi-agent runs involves reading logs.

**AgentScope solution:** "Development-oriented visualization toolkit for agent runs" — traces, event timelines, tool call inspection.

**Potential dashboard enhancement:**
```
New dashboard page: "Agent Observatory"
├── Live agent run timeline (event stream from AgentScope)
├── Tool call inspector (which tools were called, with what params)
├── Token usage tracker (per-agent LLM cost)
├── Error replay (re-run a failed agent step with same context)
└── Team coordination view (leader-worker message graph)
```

**Effort:** Medium (integrate Studio into existing React dashboard)
**Risk:** Low — read-only visualization, doesn't affect pipeline
**Priority:** Low — developer experience improvement

---

### 11. Trinity-RFT (Reinforcement Fine-Tuning) → Optimize Agent Behavior

**Current state:** Agents use off-the-shelf LLMs (Claude Haiku/Sonnet) with prompt engineering. No fine-tuning.

**AgentScope solution:** RL-based fine-tuning framework with Explorer, Trainer, and Buffer components. Used in the samples repo for math reasoning, tool use, environment navigation.

**Potential use in manga-automation:**
- Fine-tune caption generation for higher engagement (reward = view count)
- Fine-tune trend selection for better content predictions (reward = post velocity)
- Fine-tune shadow-ban detection (reward = correct classification)

**Effort:** Very High (requires training data, reward design, compute)
**Risk:** High — experimental, high cost
**Priority:** Not now — revisit post-revenue

---

### 12. AgentScope Samples → Reference Implementations

**Relevant samples for manga-automation:**

| Sample | Relevance |
|--------|-----------|
| `browser_use_agent_pro` | Browser automation pattern for the Engager agent (Playwright-based engagement) |
| `agent_deep_research` | Multi-agent research pipeline — similar to Trend Detection + Content Sourcing |
| `multiagent_conversation` | Agent-to-agent communication pattern |
| `multiagent_debate` | Adversarial content quality review (debate between critic and creator agents) |
| `chatbot_fullstack_runtime` | Full-stack deployment template (React + FastAPI + streaming) — matches dashboard architecture |
| `email_search` (tuner) | Tool-use RL training — applicable to operator agent optimization |

**Effort:** None (reference only)
**Risk:** None
**Priority:** Use as learning resource during adoption

---

## Prioritized Adoption Roadmap

### Phase A: Low-Risk, High-Value (Weeks 1-2)
```
┌─────────────────────────────────────────────────────┐
│ 1. ReMe Memory           Replace ChromaDB plan      │
│    Effort: 1-2 days      Risk: Low                  │
│                                                      │
│ 2. Background Tasks      Wrap Remotion + uploads     │
│    Effort: 2-3 days      Risk: Low                  │
│                                                      │
│ 3. Permission System     Add publishing guardrails   │
│    Effort: 1 day         Risk: None                  │
└─────────────────────────────────────────────────────┘
```

### Phase B: Structural Changes (Weeks 3-6)
```
┌─────────────────────────────────────────────────────┐
│ 4. Agent Team            Replace CrewAI pipeline     │
│    Effort: 1-2 weeks     Risk: Medium               │
│                                                      │
│ 5. Workspace Sandbox     Sandbox ffmpeg + Playwright │
│    Effort: 2-3 days      Risk: Low                  │
│                                                      │
│ 6. MCP Tool Servers      Standardize external APIs   │
│    Effort: 1 week        Risk: Low                  │
└─────────────────────────────────────────────────────┘
```

### Phase C: Enhancement (Weeks 7-10)
```
┌─────────────────────────────────────────────────────┐
│ 7. OpenJudge             Content quality scoring     │
│    Effort: 3-5 days      Risk: Low                  │
│                                                      │
│ 8. AgentScope Core       Port Mastra agents → Python │
│    Effort: 2-3 weeks     Risk: Medium               │
│                                                      │
│ 9. Studio Integration    Agent observability in dash │
│    Effort: 1 week        Risk: Low                  │
└─────────────────────────────────────────────────────┘
```

### Phase D: Future (Post-Revenue)
```
┌─────────────────────────────────────────────────────┐
│ 10. Runtime Multi-Tenant  SaaS isolation layer       │
│ 11. Trinity-RFT           RL fine-tuning pipeline    │
└─────────────────────────────────────────────────────┘
```

---

## Dependency Graph

```
ReMe Memory ─────────────────────────────────────────────┐
    ↓                                                     │
Background Tasks ────────────────────────────────────────┤
    ↓                                                     │
Permission System ───────────────────────────────────────┤
    ↓                                                     │
Workspace Sandbox ──┐                                     │
    ↓               ↓                                     │
Agent Team ────────→ MCP Tool Servers                     │
    ↓                   ↓                                 │
OpenJudge ←────────────┘                                  │
    ↓                                                     │
AgentScope Core (port Mastra agents) ←────────────────────┘
    ↓
Studio Integration
    ↓
Runtime Multi-Tenant (deferred)
    ↓
Trinity-RFT (deferred)
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| AgentScope is Alibaba Cloud-centric (DashScope models) | Medium | Medium | The framework supports arbitrary models — use `AnthropicChatModel` / OpenAI-compatible adapters. Verify before committing. |
| AgentScope 2.0 is new (June 2026) — bugs, API changes | Medium | Medium | Phase A items are low-risk surface area. Defer Core migration until 2.x stabilizes. |
| CrewAI pipeline is mission-critical | High (if migrated poorly) | High | Run AgentScope Team in parallel with CrewAI; switch via feature flag (`SUMMON_BACKEND` env var already exists) |
| Mastra agents depend on Node.js ecosystem (Anthropic SDK, Zod) | Medium | Medium | Keep Mastra for Node-specific agents; use MCP to bridge Python ↔ Node tool access |
| Learning curve — team knows Mastra + CrewAI | Medium | Low | AgentScope's API is intuitive; samples repo provides templates |

---

## Key Decision Points

1. **Python-only or hybrid?** If AgentScope Core is adopted for all agents, the Node.js Mastra layer is retired. If hybrid, MCP bridges the two. Recommendation: start hybrid, evaluate Python-only after Phase B.

2. **ReMe vs. ChromaDB?** ReMe is purpose-built for agents and integrates natively. ChromaDB is general-purpose. Since ChromaDB is not yet live in production, ReMe is the clear choice.

3. **n8n vs. AgentScope Pipeline?** n8n provides visual editing, webhooks, and cron. AgentScope Pipeline provides programmatic orchestration. Recommendation: keep n8n for top-level scheduling; use AgentScope Pipeline for intra-agent workflow.

4. **CrewAI vs. AgentScope Team?** AgentScope Team provides dynamic worker spawning (not static DAG). CrewAI provides explicit sequential execution. For content arbitrage, dynamic is better (trends change mid-run). Switch after Phase A validation.

---

## Sources

- [AgentScope Official Site](https://agentscope.io/)
- [AgentScope GitHub](https://github.com/agentscope-ai/agentscope)
- [AgentScope Documentation](https://doc.agentscope.io/)
- [AgentScope Samples (DeepWiki)](https://deepwiki.com/agentscope-ai/agentscope-samples)
- [AgentScope PyPI](https://pypi.org/project/agentscope/)
- [AgentScope 1.0 Paper (arXiv:2508.16279)](https://arxiv.org/abs/2508.16279)
- [AgentScope Runtime Quick Start](https://runtime.agentscope.io/en/quickstart.html)
- Current manga-automation codebase: `D:\Code\startup\manga-automation\`
  - `scripts/crew/agents.py` — CrewAI agent definitions
  - `scripts/crew/pipeline_crew.py` — CrewAI pipeline orchestration
  - `scripts/crew/tools.py` — CrewAI tool wrappers
  - `mastra-agents/src/agents/` — Mastra Node.js agents
  - `mastra-agents/src/server.ts` — API server with 68KB of endpoints
  - `docker-compose.yml` — 10-service Docker architecture
  - Obsidian vault: `D:\Code\startup\free-claude-code-vault\`
