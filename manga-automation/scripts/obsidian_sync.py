#!/usr/bin/env python3
"""
Obsidian Sync — Writes structured markdown notes to the Obsidian vault.

Handles:
  task     — gig task note (created on /gig_new, updated on /gig_submit_done)
  session  — daily session log (auto-written on /gig_today)
  research — research/campaign note (from /research_topic, /plan_campaign)
  template — winning draft saved as a reusable template

Vault path is controlled by OBSIDIAN_VAULT_PATH env var.
All writes are non-blocking fire-and-forget — failures are logged but never
propagate back to the calling function.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from scripts.utils.logger import setup_logger

logger = setup_logger("obsidian_sync")

VAULT_PATH = Path(
    os.getenv("OBSIDIAN_VAULT_PATH", "/data/obsidian-vault")
).resolve()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _dir(subdir: str) -> Path:
    p = VAULT_PATH / subdir
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8")
    logger.info(f"Obsidian note written: {path.name}")
    return str(path)


def _safe_float(v) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _safe_int(v) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


# ── Note writers ──────────────────────────────────────────────────────────────

def write_gig_task_note(task: dict, output: dict | None = None) -> str:
    """
    One note per gig task. Called on create and again on finalize so the
    note reflects the latest outcome. Uses YAML frontmatter so Dataview
    can query across all task notes.
    """
    today     = date.today().isoformat()
    task_id   = task.get("id") or task.get("task_id", "?")
    status    = task.get("status", "drafted")
    platform  = task.get("platform", "unknown")
    task_type = task.get("task_type", "unknown")
    payout    = _safe_float(task.get("estimated_payout"))
    minutes   = _safe_int(task.get("time_spent_minutes"))
    brief     = task.get("task_prompt", task.get("brief", ""))
    hourly    = round(payout / (minutes / 60), 2) if minutes > 0 and payout > 0 else 0.0

    score = None
    flags: list = []
    draft = ""
    if output:
        score = output.get("quality_score")
        raw_flags = output.get("risk_flags_json", output.get("risk_flags", []))
        flags = raw_flags if isinstance(raw_flags, list) else []
        draft = output.get("final_output") or output.get("draft_output", "")

    tags = [f"gig/{platform}", f"type/{task_type}", f"status/{status}"]
    tags += [f"flag/{f}" for f in flags]

    flag_links = (
        "\n\n## Risk Pattern Links\n"
        + "\n".join(f"- [[rejection-analysis/{f}]]" for f in flags)
    ) if flags else ""

    frontmatter = f"""\
---
task_id: {task_id}
platform: {platform}
task_type: {task_type}
status: {status}
date: {today}
quality_score: {score if score is not None else "null"}
payout_usd: {payout}
minutes_spent: {minutes}
hourly_rate: {hourly}
risk_flags: {json.dumps(flags)}
tags: {json.dumps(tags)}
---
"""
    body = f"""\
# Task #{task_id} — {platform} / {task_type}

**Status:** {status.upper()}
**Date:** {today}
**Payout:** ${payout:.2f}
**Time:** {minutes} min
**Effective rate:** ${hourly:.2f}/hr
**Quality score:** {f"{score:.2f}" if score is not None else "—"}

## Brief
{brief}

## Draft Used
{draft or "_(not yet generated)_"}
{flag_links}
"""
    slug = f"{today}_task-{task_id}_{platform}_{status}"
    path = _dir("gig-tasks") / f"{slug}.md"
    return _write(path, frontmatter + body)


def write_session_log(summary: dict) -> str:
    """Daily session log — overwrites same file if called multiple times today."""
    today = date.today().isoformat()
    path  = _dir("session-logs") / f"{today}_session.md"

    frontmatter = f"""\
---
date: {today}
tasks_today: {summary.get("tasks_today", 0)}
tasks_completed: {summary.get("tasks_completed", 0)}
tasks_rejected: {summary.get("tasks_rejected", 0)}
acceptance_rate: {summary.get("acceptance_rate_pct", 0)}
payout_usd: {summary.get("estimated_payout_usd", 0)}
hourly_rate: {summary.get("effective_hourly_rate", 0)}
avg_quality: {summary.get("avg_quality_score", 0)}
tags: ["session-log"]
---
"""
    body = f"# Session Log — {today}\n\n" + summary.get("formatted", str(summary))
    return _write(path, frontmatter + "\n" + body)


def write_research_note(query: str, result: dict) -> str:
    """Research or campaign plan note from /research_topic or /plan_campaign."""
    today = date.today().isoformat()
    slug  = query[:50].strip().replace(" ", "-").lower()
    # Remove chars unsafe for filenames
    slug  = "".join(c for c in slug if c.isalnum() or c in "-_")
    path  = _dir("research") / f"{today}_{slug}.md"

    frontmatter = f"""\
---
date: {today}
query: "{query}"
tags: ["research"]
---
"""
    body = (
        f"# Research: {query}\n\n"
        + "## Results\n\n"
        + json.dumps(result, indent=2, ensure_ascii=False)
    )
    return _write(path, frontmatter + "\n" + body)


def write_template_note(
    platform: str,
    task_type: str,
    template_text: str,
    win_rate: float = 0.0,
    note: str = "",
) -> str:
    """Save a high-scoring draft as a reusable template."""
    ts   = datetime.now().strftime("%Y%m%d_%H%M")
    slug = f"{platform}_{task_type}_{ts}"
    path = _dir("templates") / f"{slug}.md"

    frontmatter = f"""\
---
platform: {platform}
task_type: {task_type}
win_rate: {win_rate}
date_created: {date.today().isoformat()}
tags: ["template", "gig/{platform}", "type/{task_type}"]
---
"""
    body = f"""\
# Template: {platform} / {task_type}

**Win rate:** {win_rate:.0%}
{f"**Note:** {note}" if note else ""}

## Template Text

{template_text}
"""
    return _write(path, frontmatter + body)


def write_rejection_pattern(flag: str, task_ids: list[int], examples: list[str]) -> str:
    """Create/update a rejection pattern note. Each flag gets one persistent note."""
    path = _dir("rejection-analysis") / f"{flag}.md"

    # Preserve existing task links if the note already exists
    existing_ids: list[int] = []
    if path.exists():
        try:
            existing_text = path.read_text(encoding="utf-8")
            import re
            existing_ids = [int(m) for m in re.findall(r"task-(\d+)", existing_text)]
        except Exception:
            pass

    all_ids = list(dict.fromkeys(existing_ids + task_ids))[-20:]  # keep last 20

    examples_text = "\n\n".join(
        f"### Example {i + 1}\n{ex}" for i, ex in enumerate(examples[:5])
    )

    frontmatter = f"""\
---
flag: {flag}
linked_task_count: {len(all_ids)}
tags: ["rejection-pattern", "flag/{flag}"]
---
"""
    body = f"""\
# Rejection Pattern: `{flag}`

## What it means
See [[GIG_COPILOT_USER_GUIDE]] for the fix for this flag.

## Linked Tasks ({len(all_ids)} total)
{" · ".join(f"[[gig-tasks/task-{t}]]" for t in all_ids)}

## Recent Examples
{examples_text or "_(none recorded yet)_"}
"""
    return _write(path, frontmatter + body)


def ensure_index() -> None:
    """Write a root _index.md with Dataview dashboards if it doesn't exist."""
    path = VAULT_PATH / "_index.md"
    if path.exists():
        return

    content = """\
# Gig Copilot — Obsidian Index

All notes are auto-generated by the manga-automation system.
Use the Dataview queries below as live dashboards.

---

## ✅ Accepted Tasks This Week

```dataview
TABLE platform, task_type, payout_usd, quality_score, minutes_spent
FROM "gig-tasks"
WHERE status = "accepted"
AND date >= date(today) - dur(7 days)
SORT payout_usd DESC
```

---

## ❌ Rejection Pattern Frequency

```dataview
TABLE length(rows) AS total_hits
FROM "gig-tasks"
WHERE status = "rejected"
FLATTEN risk_flags AS flag
GROUP BY flag
SORT total_hits DESC
```

---

## 📈 Daily Payout Trend (Last 14 Days)

```dataview
TABLE tasks_today, payout_usd, hourly_rate, acceptance_rate
FROM "session-logs"
SORT date DESC
LIMIT 14
```

---

## 🏆 Best Templates

```dataview
TABLE platform, task_type, win_rate, date_created
FROM "templates"
SORT win_rate DESC
```

---

## ⏳ Tasks Needing Attention (Not Yet Scored)

```dataview
TABLE platform, task_type, date
FROM "gig-tasks"
WHERE status = "drafted"
SORT date DESC
```
"""
    _write(path, content)


# ── Entry point ───────────────────────────────────────────────────────────────

def main(body: dict) -> dict:
    action = body.get("action", "")
    try:
        ensure_index()

        if action == "task":
            path = write_gig_task_note(
                task   = body.get("task", {}),
                output = body.get("output"),
            )
            return {"written": path, "action": "task"}

        if action == "session":
            path = write_session_log(body.get("summary", {}))
            return {"written": path, "action": "session"}

        if action == "research":
            path = write_research_note(
                query  = body.get("query", ""),
                result = body.get("result", {}),
            )
            return {"written": path, "action": "research"}

        if action == "template":
            path = write_template_note(
                platform      = body.get("platform", ""),
                task_type     = body.get("task_type", ""),
                template_text = body.get("template_text", ""),
                win_rate      = _safe_float(body.get("win_rate", 0.0)),
                note          = body.get("note", ""),
            )
            return {"written": path, "action": "template"}

        if action == "rejection":
            path = write_rejection_pattern(
                flag     = body.get("flag", "unknown"),
                task_ids = body.get("task_ids", []),
                examples = body.get("examples", []),
            )
            return {"written": path, "action": "rejection"}

        return {"error": f"Unknown action '{action}'. Use: task|session|research|template|rejection"}

    except Exception as exc:
        logger.error(f"Obsidian sync error (action={action}): {exc}")
        return {"error": str(exc)}
