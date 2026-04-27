#!/usr/bin/env python3
"""
Gig Copilot — Task intake and draft generation.

Actions:
  create  — Insert new gig_task row from a user-submitted brief.
  draft   — Call Mastra draftGeneratorAgent and store result in gig_outputs.

Called by:
  POST /gig/task/create  { action: "create", user_id, platform, task_type, brief }
  POST /gig/task/draft   { action: "draft",  task_id }
"""
from __future__ import annotations

import os
import requests
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("gig_prepare")

MASTRA_URL  = os.getenv("TELEGRAM_MASTRA_URL",  "http://manga-agents:3001").rstrip("/")
WORKER_URL  = os.getenv("TELEGRAM_WORKER_URL",  "http://python-worker:8080").rstrip("/")


import threading

def _sync_obsidian(payload: dict) -> None:
    """Fire-and-forget — never raises; vault failures must not break gig flow."""
    def _run():
        try:
            from scripts import obsidian_sync
            obsidian_sync.main(payload)
        except Exception as exc:
            logger.debug(f"Obsidian sync skipped: {exc}")
    threading.Thread(target=_run, daemon=True).start()

VALID_PLATFORMS  = {"dataannotation", "outlier", "babel"}
VALID_TASK_TYPES = {"prompt-writing", "response-rating", "factual-eval", "voice-script"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_rubric(platform: str, task_type: str) -> dict:
    row = db.execute_one(
        """
        SELECT rubric_json
        FROM gig_rubrics
        WHERE platform = %s AND task_type = %s AND active = TRUE
        LIMIT 1
        """,
        (platform, task_type),
    )
    if row and row.get("rubric_json"):
        rj = row["rubric_json"]
        return rj if isinstance(rj, dict) else {}
    return {}


def _get_best_template(platform: str, task_type: str) -> str | None:
    row = db.execute_one(
        """
        SELECT template_text
        FROM prompt_templates
        WHERE platform = %s AND task_type = %s
        ORDER BY win_rate DESC, use_count DESC
        LIMIT 1
        """,
        (platform, task_type),
    )
    return row["template_text"] if row else None


# ── Actions ───────────────────────────────────────────────────────────────────

def create_task(user_id: str, platform: str, task_type: str, brief: str) -> dict:
    """Insert a new gig_task row and return the new row."""
    platform  = platform.strip().lower()
    task_type = task_type.strip().lower()

    if platform not in VALID_PLATFORMS:
        return {"error": f"Invalid platform '{platform}'. Valid: {sorted(VALID_PLATFORMS)}"}
    if task_type not in VALID_TASK_TYPES:
        return {"error": f"Invalid task_type '{task_type}'. Valid: {sorted(VALID_TASK_TYPES)}"}
    if not brief.strip():
        return {"error": "brief cannot be empty"}

    row = db.execute_one(
        """
        INSERT INTO gig_tasks (user_id, platform, task_type, task_prompt, status)
        VALUES (%s, %s, %s, %s, 'drafted')
        RETURNING id, platform, task_type, task_prompt, status, created_at
        """,
        (user_id, platform, task_type, brief.strip()),
    )
    logger.info(f"Created gig_task id={row['id']} platform={platform} type={task_type}")
    result = {
        "task_id":   row["id"],
        "platform":  row["platform"],
        "task_type": row["task_type"],
        "status":    row["status"],
        "message":   f"Task #{row['id']} created. Run /gig_draft {row['id']} to generate drafts.",
    }
    # Non-blocking Obsidian note
    _sync_obsidian({"action": "task", "task": {**row, "brief": brief.strip()}})
    return result


def generate_draft(task_id: int) -> dict:
    """Call Mastra draftGeneratorAgent and write output to gig_outputs."""
    task = db.execute_one("SELECT * FROM gig_tasks WHERE id = %s", (task_id,))
    if not task:
        return {"error": f"task_id {task_id} not found"}

    rubric   = _get_rubric(task["platform"], task["task_type"])
    template = _get_best_template(task["platform"], task["task_type"])

    payload: dict = {
        "taskPrompt": task["task_prompt"],
        "taskType":   task["task_type"],
        "platform":   task["platform"],
        "rubric":     rubric,
    }
    if template:
        payload["templateHint"] = template

    try:
        resp = requests.post(
            f"{MASTRA_URL}/gig/task/draft",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error(f"Draft agent error for task {task_id}: {exc}")
        return {"error": str(exc), "task_id": task_id}

    draft_text = data.get("draft", "")

    db.execute(
        "INSERT INTO gig_outputs (task_id, draft_output) VALUES (%s, %s)",
        (task_id, draft_text),
    )
    logger.info(f"Draft saved for task_id={task_id} ({len(draft_text)} chars)")

    result = {
        "task_id":   task_id,
        "platform":  task["platform"],
        "task_type": task["task_type"],
        "draft":     draft_text,
        "message":   f"Draft ready. Run /gig_score {task_id} to review quality.",
    }
    # Update Obsidian note with the draft text
    _sync_obsidian({
        "action": "task",
        "task":   dict(task),
        "output": {"draft_output": draft_text},
    })
    return result


# ── Entry point ───────────────────────────────────────────────────────────────

def main(body: dict) -> dict:
    action = body.get("action", "create")

    if action == "create":
        return create_task(
            user_id   = str(body.get("user_id", "default")),
            platform  = str(body.get("platform", "")),
            task_type = str(body.get("task_type", "")),
            brief     = str(body.get("brief", "")),
        )

    if action == "draft":
        if "task_id" not in body:
            return {"error": "task_id is required for action=draft"}
        return generate_draft(int(body["task_id"]))

    return {"error": f"Unknown action: {action}. Use 'create' or 'draft'."}
