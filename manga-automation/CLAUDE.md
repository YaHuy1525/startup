# AGENTIC DIRECTIVE — manga-automation (AiToEarn)

> AI-powered 5-stage content arbitrage pipeline: Trend → Create → Publish → Engage → Monetize.
> Orchestrated by CrewAI agents across 40+ platforms.

## CODING ENVIRONMENT

- Use `docker compose up -d` to start all services
- Python scripts run inside `python-worker` container (port 8080) or `uv run` for local dev
- Node/TS agents run inside `manga-agents` container (port 3001) or `npm run dev` for local dev
- Read `.env.example` for environment variables
- PostgreSQL on 5434, Redis on 6380, ChromaDB on 8001, n8n on 5679

## ARCHITECTURE

7 Docker services:
| Service | Port | Stack |
|---|---|---|
| PostgreSQL | 5434 | Primary DB |
| Redis | 6380 | API cache |
| manga-agents | 3001 | Mastra AI agents (Node 20) |
| python-worker | 8080 | Python scripts (FFmpeg + Playwright + CrewAI) |
| n8n | 5679 | Workflow orchestrator |
| ChromaDB | 8001 | Vector memory |
| Dashboard | 3000 | React analytics + control panel |

5 pipeline stages: Trend Detection → Content Creation → Publishing → Engagement → Monetization

## PROJECT MEMORY (Obsidian vault at D:\Code\startup\free-claude-code-vault)

This project shares an Obsidian vault at `D:\Code\startup\free-claude-code-vault`. Read `_CLAUDE.md` there first.

Key project files in vault:
- `Projects/manga-automation.md` — main project note with architecture decisions
- `Projects/manga-automation-pipelines.md` — pipeline architecture
- `Projects/manga-automation-architecture.md` — system design
- `Projects/manga-automation-saas-transformation.md` — SaaS conversion plan
- `Projects/manga-automation-agentic-upgrade.md` — agent upgrade plan
- `Boards/free-claude-code.md` — kanban board

Rules:
- After writing code, run `/obsidian-log` to record dev sessions
- Log decisions to the project note with `/obsidian-decide`
- Save conversations with `/obsidian-save` after significant work
- Check `Daily/YYYY-MM-DD.md` at session start for context

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
