#!/usr/bin/env python3
"""
CPS/CPE/CPM settlement tracking engine.
Tracks earnings from merchant tasks based on engagement metrics and sales.

Usage:
    python3 scripts/monetize/settlement.py [--action calculate] [--task-id 1]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("settlement")

MODEL_CPS = "cps"
MODEL_CPE = "cpe"
MODEL_CPM = "cpm"


def calculate_earnings(assignment_id: int) -> dict[str, Any]:
    """Calculate earnings for a task assignment based on engagement metrics."""
    assignment = db.execute_one(
        """SELECT ta.*, pt.model, pt.reward, pt.budget
           FROM task_assignments ta
           JOIN promotion_tasks pt ON pt.id = ta.task_id
           WHERE ta.id = %s""",
        (assignment_id,),
    )
    if not assignment:
        return {"error": "Assignment not found"}

    model = assignment["model"]
    reward = float(assignment["reward"])

    # Get published content metrics for this assignment
    metrics = db.execute(
        """SELECT SUM(va.views) AS total_views,
                  SUM(va.likes) AS total_likes,
                  SUM(va.comments) AS total_comments,
                  SUM(va.shares) AS total_shares
           FROM video_analytics va
           JOIN published_videos pv ON pv.id = va.published_video_id
           WHERE va.scraped_at > %s""",
        (assignment["assigned_at"],),
    )

    if not metrics:
        return {"assignment_id": assignment_id, "earnings": 0.0, "model": model}

    m = metrics[0]
    views = int(m.get("total_views") or 0)
    likes = int(m.get("total_likes") or 0)
    comments = int(m.get("total_comments") or 0)
    shares = int(m.get("total_shares") or 0)
    engagements = likes + comments + shares

    earnings = 0.0
    if model == MODEL_CPM:
        earnings = (views / 1000) * reward
    elif model == MODEL_CPE:
        earnings = engagements * reward
    elif model == MODEL_CPS:
        earnings = engagements * reward * 0.05  # Estimated 5% conversion

    # Cap at budget
    budget = float(assignment.get("budget") or 0)
    if budget > 0:
        earnings = min(earnings, budget)

    result = {
        "assignment_id": assignment_id,
        "model": model,
        "reward_rate": reward,
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "engagements": engagements,
        "earnings": round(earnings, 4),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Save earnings record
    try:
        db.execute(
            """INSERT INTO earnings (assignment_id, model, views, engagements, amount, calculated_at)
               VALUES (%s, %s, %s, %s, %s, NOW())
               ON CONFLICT (assignment_id, calculated_at) DO NOTHING""",
            (assignment_id, model, views, engagements, result["earnings"]),
        )
    except Exception as exc:
        logger.warning(f"Failed to save earnings: {exc}")

    return result


def get_creator_earnings(creator_id: int, days: int = 30) -> dict[str, Any]:
    rows = db.execute(
        """SELECT ta.id AS assignment_id, pt.model, pt.reward,
                  e.amount, e.views, e.engagements, e.calculated_at,
                  m.name AS merchant_name, pt.title AS task_title
           FROM earnings e
           JOIN task_assignments ta ON ta.id = e.assignment_id
           JOIN promotion_tasks pt ON pt.id = ta.task_id
           JOIN merchants m ON m.id = pt.merchant_id
           WHERE ta.creator_id = %s
             AND e.calculated_at > NOW() - INTERVAL '%s days'
           ORDER BY e.calculated_at DESC""",
        (creator_id, days),
    )
    earnings = [dict(r) for r in rows]
    total = sum(float(r["amount"] or 0) for r in earnings)
    return {
        "creator_id": creator_id,
        "period_days": days,
        "total_earnings": round(total, 4),
        "transactions": len(earnings),
        "details": earnings,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["calculate", "summary"], default="summary")
    parser.add_argument("--assignment-id", type=int)
    parser.add_argument("--creator-id", type=int, default=1)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    if args.action == "calculate" and args.assignment_id:
        result = calculate_earnings(args.assignment_id)
    else:
        result = get_creator_earnings(args.creator_id, args.days)
    print(json.dumps(result, ensure_ascii=False, default=str))
