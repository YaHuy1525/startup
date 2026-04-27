# Obsidian Integration Guide

> How Obsidian acts as the **second brain** for your automation system — connecting gig tasks, manga research, content ideas, rejection patterns, and winning templates into a searchable knowledge graph.

---

## Why Obsidian Fits This Project

Your system already generates a lot of valuable data that disappears into the database and never gets revisited:

- Gig task drafts and what made them get accepted or rejected
- Research notes from `/research_topic`
- Campaign plans from `/plan_campaign`
- Manga series performance patterns
- Winning prompt templates

Obsidian turns all of that into a **linked, searchable, visual knowledge base** you can actually learn from. The system writes notes automatically — you just open the vault to review.

```
Telegram command
      ↓
Worker script (Python)
      ↓
Writes .md file → Obsidian vault (local folder)
      ↓
Obsidian auto-detects new note → links it to related notes
```

---

## The 5 Areas Obsidian Helps Most

### 1. Gig Task Intelligence
Every task becomes a note. Over time you build a searchable library of:
- What briefs produced accepted vs. rejected submissions
- Which platforms reward which writing styles
- Rejection clustering — spot repeating failure patterns visually

### 2. Winning Prompt Templates
When a task is accepted at high quality score → the draft is automatically saved as a reusable template note. The system learns which templates perform best.

### 3. Research & Content Ideas
Every `/research_topic` and `/plan_campaign` output gets saved as a note. Ideas link back to the manga series and TikTok accounts they belong to.

### 4. Daily Session Logs
Each `/gig_today` run saves a dated log note. You can see your hourly rate improving (or declining) over time without opening a spreadsheet.

### 5. Rejection Analysis Journal
Rejected tasks get tagged and linked. Obsidian's graph view shows you patterns — e.g. "all my Outlier rejections link to `shallow_reasoning`".

---

## Vault Structure

```
obsidian-vault/
├── gig-tasks/
│   ├── 2026-04-19_task-42_dataannotation_accepted.md
│   ├── 2026-04-19_task-43_outlier_rejected.md
│   └── ...
├── templates/
│   ├── dataannotation_prompt-writing_template_01.md
│   ├── outlier_factual-eval_template_01.md
│   └── ...
├── research/
│   ├── 2026-04-19_research_best-anime-channels.md
│   ├── 2026-04-19_campaign_romance-manga-series.md
│   └── ...
├── session-logs/
│   ├── 2026-04-19_session.md
│   ├── 2026-04-20_session.md
│   └── ...
├── rejection-analysis/
│   ├── shallow_reasoning.md
│   ├── hallucination_risk.md
│   └── ...
├── manga-series/
│   ├── One Piece.md
│   ├── Jujutsu Kaisen.md
│   └── ...
└── _index.md
```

---

## Implementation Plan

### Phase 1 — Vault Setup (no code needed)

1. Install [Obsidian](https://obsidian.md) (free desktop app)
2. Create a vault folder: `d:\Code\startup\manga-automation\obsidian-vault\`
3. Open Obsidian → Open folder as vault → point to that folder
4. Install these community plugins (Settings → Community plugins):
   - **Dataview** — lets you query notes like a database (show all accepted tasks, sort by payout)
   - **Templater** — auto-fills note templates when created
   - **Calendar** — visual session log calendar
   - **Tag Wrangler** — manage tags across all notes

---

### Phase 2 — Auto-write Notes from the System

Create `scripts/obsidian_sync.py` — the bridge between your DB and the vault:

```python
#!/usr/bin/env python3
"""
Obsidian Sync — Writes structured markdown notes to the Obsidian vault
for gig tasks, session logs, research output, and rejected patterns.

Called by worker routes or directly after key events.
"""
import os
import json
from datetime import datetime, date
from pathlib import Path
from scripts.utils.logger import setup_logger

logger = setup_logger("obsidian_sync")

VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "./obsidian-vault"))


def _ensure_dir(subdir: str) -> Path:
    p = VAULT_PATH / subdir
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_gig_task_note(task: dict, output: dict | None = None) -> str:
    """Write a gig task note with frontmatter for Dataview queries."""
    today     = date.today().isoformat()
    status    = task.get("status", "drafted")
    platform  = task.get("platform", "unknown")
    task_type = task.get("task_type", "unknown")
    task_id   = task.get("id")
    score     = output.get("quality_score") if output else None
    flags     = output.get("risk_flags_json", []) if output else []
    draft     = output.get("final_output") or output.get("draft_output", "") if output else ""
    payout    = task.get("estimated_payout", 0)
    minutes   = task.get("time_spent_minutes", 0)

    slug = f"{today}_task-{task_id}_{platform}_{status}"
    path = _ensure_dir("gig-tasks") / f"{slug}.md"

    # Tags for filtering in Obsidian
    tags = [f"gig/{platform}", f"type/{task_type}", f"status/{status}"]
    if flags:
        tags += [f"flag/{f}" for f in flags]

    frontmatter = f"""---
task_id: {task_id}
platform: {platform}
task_type: {task_type}
status: {status}
date: {today}
quality_score: {score if score is not None else "null"}
payout_usd: {payout or 0}
minutes_spent: {minutes or 0}
hourly_rate: {round((float(payout or 0) / (int(minutes or 0) / 60)), 2) if minutes and payout else 0}
risk_flags: {json.dumps(flags)}
tags: {json.dumps(tags)}
---
"""
    links = ""
    if flags:
        links = "\n\n## Linked Risk Patterns\n" + "\n".join(
            f"- [[rejection-analysis/{f}]]" for f in flags
        )

    body = f"""# Task #{task_id} — {platform} / {task_type}

**Status:** {status.upper()}  
**Date:** {today}  
**Payout:** ${payout or 0}  
**Time:** {minutes or 0} min  
**Quality score:** {score if score is not None else "—"}  

## Brief
{task.get("task_prompt", "")}

## Draft Used
{draft or "_(draft not saved)_"}
{links}
"""
    path.write_text(frontmatter + body, encoding="utf-8")
    logger.info(f"Obsidian note written: {path.name}")
    return str(path)


def write_session_log(summary: dict) -> str:
    """Write a daily session log note."""
    today = date.today().isoformat()
    path  = _ensure_dir("session-logs") / f"{today}_session.md"

    frontmatter = f"""---
date: {today}
tasks_today: {summary.get("tasks_today", 0)}
tasks_completed: {summary.get("tasks_completed", 0)}
acceptance_rate: {summary.get("acceptance_rate_pct", 0)}
payout_usd: {summary.get("estimated_payout_usd", 0)}
hourly_rate: {summary.get("effective_hourly_rate", 0)}
avg_quality: {summary.get("avg_quality_score", 0)}
tags: ["session-log"]
---
"""
    body = summary.get("formatted", str(summary))
    path.write_text(frontmatter + "\n" + body, encoding="utf-8")
    logger.info(f"Obsidian session log written: {path.name}")
    return str(path)


def write_research_note(query: str, result: dict) -> str:
    """Write a research/campaign note from /research_topic or /plan_campaign."""
    today = date.today().isoformat()
    slug  = query[:40].replace(" ", "-").lower()
    path  = _ensure_dir("research") / f"{today}_{slug}.md"

    frontmatter = f"""---
date: {today}
query: "{query}"
tags: ["research"]
---
"""
    body = f"# Research: {query}\n\n" + json.dumps(result, indent=2, ensure_ascii=False)
    path.write_text(frontmatter + "\n" + body, encoding="utf-8")
    logger.info(f"Obsidian research note written: {path.name}")
    return str(path)


def write_template_note(platform: str, task_type: str, template_text: str,
                        win_rate: float = 0.0, note: str = "") -> str:
    """Save a winning draft as a reusable template note."""
    slug = f"{platform}_{task_type}_template_{datetime.now().strftime('%Y%m%d_%H%M')}"
    path = _ensure_dir("templates") / f"{slug}.md"

    frontmatter = f"""---
platform: {platform}
task_type: {task_type}
win_rate: {win_rate}
date_created: {date.today().isoformat()}
tags: ["template", "gig/{platform}", "type/{task_type}"]
---
"""
    body = f"""# Template: {platform} / {task_type}

**Win rate:** {win_rate:.0%}  
{f"**Note:** {note}" if note else ""}

## Template Text
{template_text}
"""
    path.write_text(frontmatter + body, encoding="utf-8")
    logger.info(f"Obsidian template written: {path.name}")
    return str(path)


def write_rejection_pattern(flag: str, task_ids: list[int], examples: list[str]) -> str:
    """Update or create a rejection pattern note."""
    path = _ensure_dir("rejection-analysis") / f"{flag}.md"

    frontmatter = f"""---
flag: {flag}
linked_tasks: {json.dumps(task_ids)}
tags: ["rejection-pattern", "flag/{flag}"]
---
"""
    examples_text = "\n\n".join(
        f"### Example {i+1}\n{ex}" for i, ex in enumerate(examples[:5])
    )
    body = f"""# Rejection Pattern: `{flag}`

## What it means
See the [User Guide](../GIG_COPILOT_USER_GUIDE.md) for fix instructions.

## Linked Tasks
{" · ".join(f"[[gig-tasks/task-{t}]]" for t in task_ids[-10:])}

## Recent Examples
{examples_text}
"""
    path.write_text(frontmatter + body, encoding="utf-8")
    return str(path)


def main(body: dict) -> dict:
    action = body.get("action", "")
    try:
        if action == "task":
            path = write_gig_task_note(body.get("task", {}), body.get("output"))
            return {"written": path}
        if action == "session":
            path = write_session_log(body.get("summary", {}))
            return {"written": path}
        if action == "research":
            path = write_research_note(body.get("query", ""), body.get("result", {}))
            return {"written": path}
        if action == "template":
            path = write_template_note(
                body.get("platform", ""), body.get("task_type", ""),
                body.get("template_text", ""), body.get("win_rate", 0.0),
                body.get("note", "")
            )
            return {"written": path}
        return {"error": f"Unknown action: {action}"}
    except Exception as exc:
        logger.error(f"Obsidian sync error: {exc}")
        return {"error": str(exc)}
```

---

### Phase 3 — Register Obsidian Routes in `worker.py`

Add to the `ROUTES` dict:

```python
import scripts.obsidian_sync as obsidian_sync

# ── Obsidian Vault Sync ───────────────────────────────────────────────────────
"/obsidian/task":     lambda body: obsidian_sync.main({**body, "action": "task"}),
"/obsidian/session":  lambda body: obsidian_sync.main({**body, "action": "session"}),
"/obsidian/research": lambda body: obsidian_sync.main({**body, "action": "research"}),
"/obsidian/template": lambda body: obsidian_sync.main({**body, "action": "template"}),
```

---

### Phase 4 — Auto-sync Obsidian After Key Events

**Hook into `gig_prepare.py`** — after a task is finalized, call Obsidian sync:

```python
# At the end of create_task():
import requests, os
WORKER_URL = os.getenv("TELEGRAM_WORKER_URL", "http://python-worker:8080")
try:
    requests.post(f"{WORKER_URL}/obsidian/task", json={"action": "task", "task": row}, timeout=5)
except Exception:
    pass  # Non-blocking — don't fail the task if Obsidian sync fails
```

**Hook into `gig_session_report.py`** — auto-write session log on `/gig_today`:

```python
# At the end of today_summary(), add:
try:
    requests.post(f"{WORKER_URL}/obsidian/session", json={"action": "session", "summary": result}, timeout=5)
except Exception:
    pass
```

---

### Phase 5 — Add `.env` Variable

```env
# Path to your Obsidian vault folder (can be absolute or relative to app root)
OBSIDIAN_VAULT_PATH=./obsidian-vault
```

---

### Phase 6 — Telegram Commands

Add these to `telegram_bot.py`:

```python
# /ob_save <task_id>  — Save a specific task to Obsidian
# /ob_log             — Write today's session log to Obsidian
# /ob_template <task_id> <note>  — Save a task's draft as a reusable template

def _cmd_ob_save(parts: List[str]) -> str:
    if len(parts) < 2:
        return "Usage: /ob_save <task_id>"
    task_id = int(parts[1])
    task = _get_json(f"{WORKER_URL}/gig/task/{task_id}")  # add this route too
    return _cmd_worker_route("/obsidian/task", {"action": "task", "task_id": task_id})

def _cmd_ob_log(chat_id: str) -> str:
    return _cmd_worker_route("/obsidian/session", {
        "action": "session",
        "user_id": chat_id
    })
```

---

## Obsidian Dataview Queries (Paste Into Notes)

Once notes are flowing in, these queries give you live dashboards inside Obsidian:

### All accepted tasks this week
```dataview
TABLE platform, task_type, payout_usd, quality_score, minutes_spent
FROM "gig-tasks"
WHERE status = "accepted"
AND date >= date(today) - dur(7 days)
SORT payout_usd DESC
```

### Rejection pattern frequency
```dataview
TABLE length(rows) AS count
FROM "gig-tasks"
WHERE status = "rejected"
FLATTEN risk_flags AS flag
GROUP BY flag
SORT count DESC
```

### Best performing templates
```dataview
TABLE platform, task_type, win_rate, date_created
FROM "templates"
SORT win_rate DESC
```

### Daily payout trend
```dataview
TABLE tasks_today, payout_usd, hourly_rate, acceptance_rate
FROM "session-logs"
SORT date DESC
LIMIT 14
```

### Tasks needing attention (drafted but not scored)
```dataview
TABLE platform, task_type, date
FROM "gig-tasks"
WHERE status = "drafted"
SORT date DESC
```

---

## What This Looks Like in Practice

**Morning:**
Open Obsidian. The Calendar plugin shows yesterday's session log. The graph view shows which `shallow_reasoning` notes link to Outlier tasks → you know to go deeper on your next Outlier submission.

**During work:**
Every `/gig_new` → a note appears in `gig-tasks/`. Every `/gig_submit_done` → the note updates with outcome and payout.

**End of day:**
`/gig_today` → report goes to Telegram **and** auto-writes to `session-logs/2026-04-19_session.md`. You see the day's payout, acceptance rate, and hourly rate in your vault calendar.

**Weekly:**
The Dataview "rejection pattern frequency" table shows you which flag is costing you the most money. You focus on fixing that one thing.

---

## Summary: What Obsidian Adds vs. What the DB Already Does

| | PostgreSQL (already working) | Obsidian vault |
|---|---|---|
| Store task data | ✅ | ✅ (as readable notes) |
| Query by status/date | ✅ (SQL) | ✅ (Dataview) |
| Visual pattern spotting | ❌ | ✅ (Graph view, links) |
| Reusable template library | ⚠️ (table only) | ✅ (notes + search) |
| Research/campaign notes | ❌ | ✅ |
| Daily learning journal | ❌ | ✅ |
| Works offline | ❌ (needs DB connection) | ✅ (local files) |
| Portable / Git-syncable | ❌ | ✅ |

---

## Quick Start Checklist

- [ ] Install Obsidian → open `obsidian-vault/` as vault
- [ ] Install plugins: Dataview · Templater · Calendar · Tag Wrangler
- [ ] Add `OBSIDIAN_VAULT_PATH=./obsidian-vault` to `.env`
- [ ] Create `scripts/obsidian_sync.py` (code above)
- [ ] Add Obsidian routes to `scripts/worker.py`
- [ ] Rebuild Docker: `docker-compose build python-worker && docker-compose up -d python-worker`
- [ ] Test: `/gig_new dataannotation prompt-writing Test brief` → check vault for new note
- [ ] Paste Dataview queries into an `_index.md` note in the vault root
