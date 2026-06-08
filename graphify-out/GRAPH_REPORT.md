# Graph Report - startup  (2026-06-08)

## Corpus Check
- 2841 files · ~2,585,232 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 570 nodes · 963 edges · 37 communities (30 shown, 7 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 9 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `8b11fa46`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]

## God Nodes (most connected - your core abstractions)
1. `_dispatch_command()` - 56 edges
2. `_cmd_worker_route()` - 53 edges
3. `Any` - 32 edges
4. `AiToEarnClient` - 29 edges
5. `Any` - 26 edges
6. `Tool-by-Tool Analysis` - 13 edges
7. `AI Gig Copilot — Telegram Bot Integration Guide` - 13 edges
8. `run_link_publish_pipeline()` - 13 edges
9. `ingest_youtube_url()` - 12 edges
10. `/graphify` - 11 edges

## Surprising Connections (you probably didn't know these)
- `_video_usage_check()` --calls--> `is_youtube_video_already_used()`  [INFERRED]
  manga-automation/scripts/hermes_agent.py → manga-automation/scripts/youtube_download_ingest.py
- `discover_video_from_objective()` --calls--> `load_used_youtube_id_set()`  [INFERRED]
  manga-automation/scripts/hermes_agent.py → manga-automation/scripts/youtube_download_ingest.py
- `run_link_publish_pipeline()` --calls--> `load_used_youtube_id_set()`  [INFERRED]
  manga-automation/scripts/hermes_agent.py → manga-automation/scripts/youtube_download_ingest.py
- `Props` --references--> `Clip`  [EXTRACTED]
  manga-automation/dashboard/src/components/PublishComposer.tsx → manga-automation/dashboard/src/types.ts

## Import Cycles
- 1-file cycle: `manga-automation/scripts/stripe_billing.py -> manga-automation/scripts/stripe_billing.py`

## Communities (37 total, 7 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.11
Nodes (19): AiToEarnClient, AiToEarnConfig, _bool_env(), enabled(), get_publish_restrictions(), get_publishing_task_status(), health(), _join_url() (+11 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (29): BaseHTTPRequestHandler, _agent_dbg_upload(), build_caption(), do_tiktok_upload(), do_tiktok_upload_v2(), get_available_account(), get_video(), main() (+21 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (46): _cmd_aito_accounts(), _cmd_aito_post_json(), _cmd_aito_publish_status(), _cmd_check_duplicates(), _cmd_deerflow(), _cmd_download_panels(), _cmd_fetch_chapter(), _cmd_finance_ai_video() (+38 more)

### Community 3 - "Community 3"
Cohesion: 0.13
Nodes (44): Any, RuntimeError, _anthropic_base_url(), _anthropic_client(), _candidate_is_blocked(), _claude_diagnose(), _claude_json_call(), collect_status_snapshot() (+36 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (19): Props, AgentConsole(), extractPublishSummary(), PlatformStats, PublishRow, PublishSummary, toInt(), PIPELINES (+11 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (31): 8 Concrete Integration Paths for AiToEarn, Action Plan for PawFriends, Core Architecture, Current Status: Pre-Launch / Placeholder, Effort Estimate, Installation for manga-automation, Key Features Relevant to AiToEarn, Month 2: Agent-per-Stage (+23 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (29): 1.1 Run the migration, 30-Day Milestone Checklist, 5.1 Add command handlers to `telegram_bot.py`, 5.2 Register commands in `_dispatch_command`, 5.3 Update `_help_text()`, Agent files to create, AI Gig Copilot — Telegram Bot Integration Guide, API routes to expose in Mastra (`src/index.ts` or equivalent) (+21 more)

### Community 7 - "Community 7"
Cohesion: 0.07
Nodes (27): 0.1 Register on AiToEarn, 0.2 Seed the Database with AiToEarn Tasks, 0.3 Configure the Pipeline, 1.1 Content Plan (per product, per week), 1.2 Automation Flow, 1.3 Using the Telegram Bot, 2.1 Engagement Engine — Run Daily, 2.2 Content Cadence (+19 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (25): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+17 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (25): 10. AgentScope Studio → Agent Run Visualization & Debugging, 11. Trinity-RFT (Reinforcement Fine-Tuning) → Optimize Agent Behavior, 12. AgentScope Samples → Reference Implementations, 1. AgentScope Core → Replace/Consolidate Mastra + CrewAI, 2. ReMe (Memory Management Kit) → Replace Planned ChromaDB, 3. Agent Team (Leader-Worker Pattern) → Replace CrewAI Sequential Pipeline, 4. Background Task Offloading → Solve Video Rendering & Upload Timeouts, 5. Workspace / Sandbox Execution → Replace Raw Docker Exec (+17 more)

### Community 10 - "Community 10"
Cohesion: 0.16
Nodes (20): datetime, create_checkout_session(), create_customer_portal_session(), _db(), get_subscription_status(), _handle_checkout_completed(), _handle_subscription_created(), _handle_subscription_deleted() (+12 more)

### Community 11 - "Community 11"
Cohesion: 0.18
Nodes (17): Any, build_search_query(), discover_short_videos(), extract_channel_id(), get_video_details(), main(), parse_iso_duration(), _pick_research_source() (+9 more)

### Community 12 - "Community 12"
Cohesion: 0.25
Nodes (16): Any, _chapter_id_for_ingest(), download_youtube_to_file(), _extract_hashtags_from_text(), _extract_public_media_url(), _extract_thumbnail_url(), extract_youtube_id(), ingest_youtube_url() (+8 more)

### Community 13 - "Community 13"
Cohesion: 0.19
Nodes (15): Any, _cmd_download_youtube(), _cmd_finance_post(), _cmd_mastra(), _cmd_status(), _extract_text(), _extract_youtube_url(), _get_json() (+7 more)

### Community 14 - "Community 14"
Cohesion: 0.25
Nodes (13): _create_bucket(), ensure_public_url(), is_configured(), is_public_http_url(), is_stable_public_url(), tmpfiles.org JSON API returns e.g. {"data":{"url":"https://tmpfiles.org/123/file, Heuristic guard for URLs that often expire quickly (e.g. googlevideo links)., Ensure a stable public URL exists for a media input.      Returns:         {" (+5 more)

### Community 15 - "Community 15"
Cohesion: 0.28
Nodes (12): _as_float(), _as_int(), _cmd_arb_discover(), _cmd_arb_distribute(), _cmd_arb_download(), _cmd_arb_source(), _cmd_fetch_trending(), _cmd_finance_briefs() (+4 more)

### Community 16 - "Community 16"
Cohesion: 0.22
Nodes (8): Dashboard (React + Vite), Database Schema (PostgreSQL), For future Claude, manga-automation — System Architecture, Mastra Agents (Node.js), Python Workers (scripts/), Remotion Renderer, Service Topology

### Community 17 - "Community 17"
Cohesion: 0.28
Nodes (9): _clean_telegram_error_noise(), _cmd_aito_hermes(), _cmd_hermes_order(), _extract_first_url(), _extract_platforms_from_text(), _parse_account_selection_map(), Format:       tiktok=tiktok_id1|tiktok_id2;youtube=youtube_id1;instagram=instag, Natural language orchestrator:     /hermes_order i want to post this on all my (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.25
Nodes (9): _cmd_aito_link_publish(), _cmd_aito_post_accounts(), _cmd_aito_post_all(), _cmd_aito_restrictions(), _parse_platform_csv(), /aito_post_all <video_url> [platform_csv] [title|desc], /aito_post_accounts <video_url> <platform=id1|id2;platform2=id3> [title|desc], /aito_link_publish <video_or_channel_url> [platform_csv] [title|desc] (+1 more)

### Community 19 - "Community 19"
Cohesion: 0.25
Nodes (7): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 20 - "Community 20"
Cohesion: 0.29
Nodes (6): env, OBSIDIAN_VAULT_PATH, hooks, PreToolUse, permissions, defaultMode

### Community 21 - "Community 21"
Cohesion: 0.38
Nodes (7): _check_keyword_trigger(), _is_authorized(), Check if a non-command message contains a keyword trigger.     Returns the repl, run_bot(), _send_message(), TelegramBotError, _tg_api()

### Community 22 - "Community 22"
Cohesion: 0.29
Nodes (3): app, PORT, REMOTION_DIR

### Community 23 - "Community 23"
Cohesion: 0.33
Nodes (5): AGENTIC DIRECTIVE — manga-automation (AiToEarn), ARCHITECTURE, CODING ENVIRONMENT, graphify, PROJECT MEMORY (Obsidian vault at D:\Code\startup\free-claude-code-vault)

### Community 24 - "Community 24"
Cohesion: 0.60
Nodes (5): Any, _load_jobs(), main(), _run_job(), _worker_base()

### Community 25 - "Community 25"
Cohesion: 0.20
Nodes (6): _cmd_finance_pipeline(), _cmd_list_avatars(), _cmd_ob_template(), /list_avatars [provider]     List available AI avatars for video generation., /finance_pipeline [provider] [background] [week_iso] [profile]     🚀 FULL AUTON, /ob_template <task_id> [note about why this is a winning template]     Save a t

### Community 26 - "Community 26"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 27 - "Community 27"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 28 - "Community 28"
Cohesion: 0.50
Nodes (3): For /graphify explain, For /graphify path, graphify reference: query, path, explain

### Community 29 - "Community 29"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

## Knowledge Gaps
- **156 isolated node(s):** `For future Claude`, `Service Topology`, `Database Schema (PostgreSQL)`, `Mastra Agents (Node.js)`, `Python Workers (scripts/)` (+151 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TelegramBotError` connect `Community 21` to `Community 3`, `Community 15`?**
  _High betweenness centrality (0.132) - this node is a cross-community bridge._
- **Why does `datetime` connect `Community 10` to `Community 0`, `Community 3`?**
  _High betweenness centrality (0.106) - this node is a cross-community bridge._
- **What connects `For future Claude`, `Service Topology`, `Database Schema (PostgreSQL)` to the rest of the system?**
  _227 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.11081560283687943 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05230496453900709 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.07053140096618357 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.1303030303030303 - nodes in this community are weakly interconnected._