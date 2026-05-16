# Claude Operating Manual — Yahuy1525's free-claude-code Brain

> Read this file before doing anything in this vault.
> This is the single source of truth for how Claude operates here.

---

## Section 0 — AI-First Vault Rule (read first, applies to every note)

This vault is designed for **future-Claude** to read and reason over, not for human review. The owner rarely reads notes directly — they call Claude to retrieve, synthesize, and connect dots.

**Every note Claude writes to this vault must follow these rules:**

1. **Self-contained context** — Each note must explain itself. Future-Claude may pull this single note via search with no surrounding context.
2. **"For future Claude" preamble** — Every note begins with a 2-3 sentence summary so Claude can decide relevance in 10 seconds.
3. **Rich, consistent frontmatter** — Filterable metadata (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields from `references/ai-first-rules.md`).
4. **Recency markers per claim** — "Mem0 raised $24M (as of 2026-04)" so future-Claude knows what to verify.
5. **Sources preserved verbatim** — Every external claim has its source URL inline.
6. **Cross-links are mandatory** — Every person, project, idea, decision, concept uses `[[wikilinks]]`.
7. **Confidence levels** — `stated | high | medium | speculation` where applicable.

---

## Vault Identity

- **Owner:** Yahuy1525
- **Primary purpose:** Code project second brain — track architecture decisions, dev sessions, bugs, features, and project knowledge for free-claude-code
- **Preset:** Builder (projects, dev logs, architecture decisions, debugging)
- **Last updated:** 2026-05-12

---

## Folder Map

| Folder | Purpose |
|---|---|
| `Daily/` | One note per day. Named `YYYY-MM-DD.md` |
| `Projects/` | Active and archived projects (one per major initiative) |
| `Tasks/` | Standalone task notes (linked from boards) |
| `Boards/` | Kanban boards: Sprint, Backlog, Done |
| `People/` | One note per person (contributors, collaborators) |
| `Dev Logs/` | Technical work logs — dated, project-tagged |
| `Knowledge/` | Reference material, architecture notes, ADRs |
| `Learning/` | Books, courses, content consumed |
| `Ideas/` | Feature ideas, improvements, experiments |
| `Reviews/` | Sprint/weekly retrospectives and reviews |
| `Templates/` | Note templates (Templater) |
| `Goals/` | Milestones and goals |
| `Health/` | Project health checks, vault health reports |
| `Mentions/` | Recognition and shoutouts |
| `Content/` | Content calendar and post drafts |
| `Finances/` | Not used (builder preset) |
| `Jobs/` | Not used (builder preset) |
| `Businesses/` | Not used (builder preset) |
| `Life Chapters/` | Not used (builder preset) |
| `_trash/` | Soft-deleted notes before permanent removal |

---

## Key Files

- **Dashboard:** `Home.md`
- **Work Board:** `Boards/free-claude-code.md`
- **Personal Board:** `Boards/Personal.md`
- **Index:** `index.md` — catalog of all vault pages (read first when navigating)
- **Log:** `log.md` — chronological audit trail of all vault operations

---

## Active Context

> Update this section at the start of each major project or focus period.

**Current project:** [free-claude-code](https://github.com/anthropics/claude-code) — open-source Claude Code
**Current focus:** Building a second brain for the project
**Key areas:** Provider integrations, API routing, message processing, tool execution

---

## Auto-Save Rules

Claude should auto-save the following **without asking**:
- Decisions made in conversation → relevant project note + daily note
- New people mentioned → People/ (create stub if needed)
- Tasks assigned or committed to → kanban board + Tasks/ note
- Dev work done → Dev Logs/ + project note + daily note
- Bugs found or fixed → project note (Bugs section) + daily note
- Architecture decisions → Knowledge/ADR + project note
- Completed tasks → move on kanban to Done
- New feature ideas → Ideas/ + daily note

Claude should **ask before saving**:
- Anything involving deleting or archiving an existing note
- Major vault restructuring

---

## Naming Conventions

- Daily notes: `YYYY-MM-DD.md`
- Dev logs: `YYYY-MM-DD — Description.md`
- ADRs: `ADR-YYYY-MM-DD — Title.md`
- People: Full name or GitHub handle (e.g. `Jane Smith.md`)
- Projects: Descriptive title, no date prefix
- Archive prefix: `_archived_`

---

## Frontmatter Requirements

Every note must have at minimum:
```yaml
---
date: YYYY-MM-DD
type: <note-type>
tags:
  - <note-type>
ai-first: true
---
```

Note types: `daily` | `project` | `task` | `person` | `devlog` | `idea` | `decision` | `adr` | `review` | `research` | `synthesis`

---

## Kanban Convention

Columns: `📥 Backlog` · `📋 This Week` · `🔨 In Progress` · `⏳ Waiting On` · `✅ Done`

Priority: 🔴 critical · 🟡 important · 🟢 low

Active item:
```
- [ ] 🔴 **Title** · @{YYYY-MM-DD}
	Description. [[Related Project]] [[Person]]
```

Done item:
```
- [x] ~~🔴 **Title**~~ ✅ Date
```

---

## Propagation Rules

| Event | Also update |
|---|---|
| New project | Board (Backlog) + today's daily note |
| Task done | Board (Done) + project note + daily note |
| Dev session | Dev Logs/ + project note (Recent Activity) + daily note |
| Person interaction | Daily note + their People/ note |
| Decision made | Project note (Key Decisions) + daily note |
| Bug found/fixed | Project note (Bugs) + daily note |
| ADR created | Project note (Key Decisions) + index.md + log.md |
| Idea captured | Ideas/ + daily note |
| Vault operation | log.md (append timestamped entry) |
| New note created | index.md (add entry) |

---

## Projects Currently Active

- `[[Projects/free-claude-code]]` — Core platform: provider routing, message processing, tool execution

---

## Do Not Touch

- `Templates/` — Never modify templates during normal vault operations (only when explicitly asked)
- `_trash/` — Soft-delete holding area, review before permanent deletion

---

*Generated by obsidian-second-brain bootstrap + builder tailoring.*
*Regenerate: "Claude, update my _CLAUDE.md"*
