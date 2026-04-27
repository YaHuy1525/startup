#!/usr/bin/env python3
"""
Gig Copilot — Rubric scoring and quality guard.

Calls Mastra rubricScoringAgent + qualityGuardAgent, stores the score and
risk flags in gig_outputs, and marks the task status as 'reviewed'.

Called by:
  POST /gig/task/score  { task_id: int }
"""
from __future__ import annotations

import os
import requests
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("gig_score")

MASTRA_URL = os.getenv("TELEGRAM_MASTRA_URL", "http://manga-agents:3001").rstrip("/")


def _format_score_reply(task_id: int, score: float, risk_flags: list, min_pass: float) -> str:
    """Build a human-readable summary for the Telegram reply."""
    passed = score >= min_pass
    flag_lines = "\n".join(f"  ⚠️ {f}" for f in risk_flags) if risk_flags else "  ✅ None"
    status_icon = "✅" if passed else "❌"
    return (
        f"{status_icon} Task #{task_id} — Score: {score:.2f} / 1.00 "
        f"(pass ≥ {min_pass:.2f})\n\n"
        f"Risk flags:\n{flag_lines}\n\n"
        + (
            "Ready to submit manually." if passed
            else "Revise the draft before submitting."
        )
    )


def score_task(task_id: int) -> dict:
    task = db.execute_one("SELECT * FROM gig_tasks WHERE id = %s", (task_id,))
    if not task:
        return {"error": f"task_id {task_id} not found"}

    output = db.execute_one(
        """
        SELECT * FROM gig_outputs
        WHERE task_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (task_id,),
    )
    if not output:
        return {
            "error": f"No draft found for task_id {task_id}. Run /gig_draft {task_id} first."
        }

    rubric = db.execute_one(
        """
        SELECT rubric_json
        FROM gig_rubrics
        WHERE platform = %s AND task_type = %s AND active = TRUE
        LIMIT 1
        """,
        (task["platform"], task["task_type"]),
    )

    rubric_data = {}
    min_pass    = 0.70
    if rubric and rubric.get("rubric_json"):
        rj = rubric["rubric_json"]
        if isinstance(rj, dict):
            rubric_data = rj
            min_pass    = float(rj.get("min_pass_score", 0.70))

    payload = {
        "taskPrompt":  task["task_prompt"],
        "draftOutput": output.get("draft_output") or output.get("final_output") or "",
        "platform":    task["platform"],
        "taskType":    task["task_type"],
        "rubric":      rubric_data,
    }

    try:
        resp = requests.post(
            f"{MASTRA_URL}/gig/task/score",
            json=payload,
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error(f"Score agent error for task {task_id}: {exc}")
        return {"error": str(exc), "task_id": task_id}

    score      = float(data.get("score", 0.0))
    risk_flags = data.get("risk_flags", [])

    db.execute(
        """
        UPDATE gig_outputs
        SET quality_score = %s, risk_flags_json = %s
        WHERE id = %s
        """,
        (score, risk_flags, output["id"]),
    )
    db.execute(
        "UPDATE gig_tasks SET status = 'reviewed', updated_at = NOW() WHERE id = %s",
        (task_id,),
    )
    logger.info(f"Scored task_id={task_id} score={score:.2f} flags={len(risk_flags)}")

    return {
        "task_id":    task_id,
        "score":      score,
        "min_pass":   min_pass,
        "passed":     score >= min_pass,
        "risk_flags": risk_flags,
        "status":     "reviewed",
        "summary":    _format_score_reply(task_id, score, risk_flags, min_pass),
    }


def main(body: dict) -> dict:
    if "task_id" not in body:
        return {"error": "task_id is required"}
    return score_task(int(body["task_id"]))
