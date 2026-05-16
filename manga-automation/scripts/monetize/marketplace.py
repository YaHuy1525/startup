#!/usr/bin/env python3
"""
Merchant task matching engine.
Matches creator content niches with merchant promotion tasks using CPS/CPE/CPM models.

Usage:
    python3 scripts/monetize/marketplace.py [--action match] [--creator-id 1]
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

logger = setup_logger("marketplace")

# Settlement models
MODEL_CPS = "cps"  # Cost Per Sale — % of transaction
MODEL_CPE = "cpe"  # Cost Per Engagement — per like/comment/share
MODEL_CPM = "cpm"  # Cost Per Mille — per 1000 views

DEFAULT_COMMISSION_RATE = float(os.environ.get("MARKETPLACE_DEFAULT_COMMISSION", "0.10"))


def create_merchant(name: str, category: str, contact_email: str = "") -> int:
    merchant_id = db.execute_returning(
        """INSERT INTO merchants (name, category, contact_email, status, created_at)
           VALUES (%s, %s, %s, 'active', NOW())
           ON CONFLICT (name) DO UPDATE SET category = EXCLUDED.category
           RETURNING id""",
        (name, category, contact_email),
    )
    return merchant_id or 0


def create_task(merchant_id: int, title: str, description: str,
                model: str = MODEL_CPS, reward: float = 0.0,
                budget: float = 0.0, target_platforms: list[str] | None = None) -> int:
    platforms = target_platforms or ["tiktok", "youtube"]
    task_id = db.execute_returning(
        """INSERT INTO promotion_tasks
           (merchant_id, title, description, model, reward, budget,
            target_platforms, status, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', NOW())
           RETURNING id""",
        (merchant_id, title, description, model, reward, budget, json.dumps(platforms)),
    )
    return task_id or 0


def match_creator(creator_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """Match open promotion tasks to a creator based on their content niches."""
    # Get creator's published content categories
    niches = db.execute(
        """SELECT DISTINCT gs.category_id, gc.slug, gc.display_name
           FROM published_videos pv
           JOIN genesis_signals gs ON gs.source_url = pv.platform_url
           JOIN genesis_categories gc ON gc.id = gs.category_id
           WHERE pv.status = 'published'
           LIMIT %s""",
        (limit,),
    )
    niche_slugs = [n["slug"] for n in niches] if niches else []

    # Find matching tasks
    if niche_slugs:
        tasks = db.execute(
            """SELECT pt.*, m.name AS merchant_name, m.contact_email
               FROM promotion_tasks pt
               JOIN merchants m ON m.id = pt.merchant_id
               WHERE pt.status = 'open'
               ORDER BY pt.budget DESC, pt.created_at DESC
               LIMIT %s""",
            (limit,),
        )
    else:
        tasks = db.execute(
            """SELECT pt.*, m.name AS merchant_name
               FROM promotion_tasks pt
               JOIN merchants m ON m.id = pt.merchant_id
               WHERE pt.status = 'open'
               ORDER BY pt.budget DESC
               LIMIT %s""",
            (limit,),
        )

    return [dict(t) for t in tasks]


def assign_task(task_id: int, creator_id: int) -> int:
    assignment_id = db.execute_returning(
        """INSERT INTO task_assignments (task_id, creator_id, status, assigned_at)
           VALUES (%s, %s, 'accepted', NOW())
           RETURNING id""",
        (task_id, creator_id),
    )
    # Mark task as assigned
    db.execute("UPDATE promotion_tasks SET status = 'assigned' WHERE id = %s", (task_id,))
    return assignment_id or 0


def list_open_tasks() -> list[dict[str, Any]]:
    rows = db.execute(
        """SELECT pt.*, m.name AS merchant_name
           FROM promotion_tasks pt
           JOIN merchants m ON m.id = pt.merchant_id
           WHERE pt.status = 'open'
           ORDER BY pt.budget DESC"""
    )
    return [dict(r) for r in rows]


def main(action: str = "list", creator_id: int = 1):
    if action == "list":
        tasks = list_open_tasks()
        return {"action": "list", "count": len(tasks), "tasks": tasks}

    if action == "match":
        matches = match_creator(creator_id)
        return {"action": "match", "creator_id": creator_id, "count": len(matches), "matches": matches}

    return {"error": f"Unknown action: {action}"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["list", "match"], default="list")
    parser.add_argument("--creator-id", type=int, default=1)
    args = parser.parse_args()
    result = main(action=args.action, creator_id=args.creator_id)
    print(json.dumps(result, ensure_ascii=False, default=str))
