---
date: 2026-05-12
updated: 2026-05-12
type: project
status: active
tags:
  - project
  - open-source
  - proxy
  - ai
related-people: []
related-projects: []
ai-first: true
---

## For future Claude
free-claude-code is an open-source proxy that routes Claude Code API traffic to multiple providers (NVIDIA NIM, OpenRouter, DeepSeek, LM Studio, Ollama, etc.). Status: active as of 2026-05-12. It enables free/paid/local model usage while maintaining stable Anthropic-compatible client protocol. The Overview explains the architecture; Key Decisions documents major directional choices.

---

# free-claude-code

Anthropic-compatible proxy for Claude Code — route API traffic to NVIDIA NIM, OpenRouter, DeepSeek, LM Studio, llama.cpp, Ollama, and more.

**Repo:** `D:\Code\startup\free-claude-code`
**Stack:** Python 3.14, FastAPI, uv, pytest, ruff, ty, loguru

---

## Architecture

```
Claude Code Client → FastAPI Server → Provider Adapters → Upstream Models
                         ↓
                   Messaging Layer (Discord, Telegram)
```

### Layers

| Layer | Directory | Purpose |
|---|---|---|
| API | `api/` | FastAPI routes, request orchestration, model routing, auth, server lifecycle |
| Providers | `providers/` | Upstream model adapters, request/stream conversion, rate limiting, error mapping |
| Messaging | `messaging/` | Discord/Telegram adapters, command handling, session persistence, voice |
| CLI | `cli/` | Package entrypoints, Claude CLI subprocess management |
| Config | `config/` | Environment-backed settings and logging |
| Core | `core/` | Shared Anthropic protocol helpers and SSE utilities |
| Tests | `tests/` | Unit and contract tests |
| Smoke | `smoke/` | Opt-in product smoke scenarios |

### Dependency direction

```
config → providers → api → cli/messaging
              ↑
           core/ (neutral shared protocol utilities — no provider imports from another provider)
```

---

## Key Features

- Anthropic-compatible API routes (messages, streaming, tool use, thinking blocks)
- Per-model routing with fallback chains (Opus/Sonnet/Haiku)
- Multiple provider support: NVIDIA NIM, OpenRouter, DeepSeek, LM Studio, Ollama, llama.cpp, Kimi
- Message streaming with SSE
- Discord and Telegram bot integrations
- Voice transcription support

---

## Key Decisions

- *No decisions logged yet. Run `/obsidian-decide` after making architectural choices.*

---

## Architecture Decision Records

- *No ADRs yet. Run `/obsidian-adr` after vault structural changes.*

---

## Bugs

- *No bugs tracked yet. Log bugs found during development.*

---

## Related Tasks

```dataview
TABLE WITHOUT ID file.link AS "Task", status AS "Status", priority AS "Priority"
FROM "Tasks"
WHERE contains(file.outlinks, this.file.link)
SORT date DESC
```

---

## Recent Activity

```dataview
LIST FROM "Daily"
WHERE contains(file.outlinks, this.file.link)
SORT date DESC
LIMIT 10
```
