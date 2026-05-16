#!/usr/bin/env python3
"""
Merchant-facing API for creating and managing promotion tasks.
Provides endpoints for: task creation, budget management, performance reporting.

Usage (via worker HTTP routes):
    POST /monetize/tasks — create a new promotion task
    GET /monetize/tasks — list merchant's tasks
    GET /monetize/tasks/:id/performance — view task performance
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.monetize.marketplace import create_merchant, create_task

logger = setup_logger("merchant_api")


def handle_create_task(body: dict[str, Any]) -> dict[str, Any]:
    required = ["merchant_name", "title", "description", "model", "reward"]
    missing = [f for f in required if f not in body]
    if missing:
        return {"error": f"Missing fields: {missing}", "status": 400}

    merchant_id = create_merchant(
        body["merchant_name"],
        body.get("category", "general"),
        body.get("contact_email", ""),
    )
    task_id = create_task(
        merchant_id=merchant_id,
        title=body["title"],
        description=body["description"],
        model=body["model"],
        reward=float(body.get("reward", 0)),
        budget=float(body.get("budget", 0)),
        target_platforms=body.get("target_platforms"),
    )
    return {"task_id": task_id, "merchant_id": merchant_id, "status": "created"}


def handle_list_tasks(merchant_name: str = "") -> dict[str, Any]:
    if merchant_name:
        tasks = db.execute(
            """SELECT pt.*, m.name AS merchant_name
               FROM promotion_tasks pt
               JOIN merchants m ON m.id = pt.merchant_id
               WHERE m.name = %s
               ORDER BY pt.created_at DESC""",
            (merchant_name,),
        )
    else:
        tasks = db.execute(
            """SELECT pt.*, m.name AS merchant_name
               FROM promotion_tasks pt
               JOIN merchants m ON m.id = pt.merchant_id
               ORDER BY pt.created_at DESC""",
        )
    return {"count": len(tasks), "tasks": [dict(t) for t in tasks]}


def handle_task_performance(task_id: int) -> dict[str, Any]:
    task = db.execute_one(
        """SELECT pt.*, m.name AS merchant_name
           FROM promotion_tasks pt
           JOIN merchants m ON m.id = pt.merchant_id
           WHERE pt.id = %s""",
        (task_id,),
    )
    if not task:
        return {"error": "Task not found", "status": 404}

    earnings = db.execute(
        """SELECT SUM(e.amount) AS total_earned, SUM(e.views) AS total_views,
                  SUM(e.engagements) AS total_engagements, COUNT(*) AS settlement_count
           FROM earnings e
           JOIN task_assignments ta ON ta.id = e.assignment_id
           WHERE ta.task_id = %s""",
        (task_id,),
    )
    perf = dict(earnings[0]) if earnings else {}
    return {
        "task": dict(task),
        "performance": {
            "total_earned": float(perf.get("total_earned") or 0),
            "total_views": int(perf.get("total_views") or 0),
            "total_engagements": int(perf.get("total_engagements") or 0),
            "settlements": int(perf.get("settlement_count") or 0),
        },
    }
