#!/usr/bin/env python3
"""
Engagement Engine — orchestrates auto-engagement across platforms.
Coordinates: liking, commenting, following, comment mining, and brand monitoring.

Usage:
    python3 scripts/engage/engine.py [--platform tiktok] [--mode full]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.engage import liker, commenter, follower, comment_miner, brand_monitor

logger = setup_logger("engage_engine")

DEFAULT_PLATFORM = os.environ.get("ENGAGE_DEFAULT_PLATFORM", "tiktok")


def _get_published_content(platform: str, limit: int = 10) -> list[dict]:
    rows = db.execute(
        """SELECT pv.id, pv.platform, pv.platform_url, pv.caption, pv.published_at
           FROM published_videos pv
           WHERE pv.platform = %s AND pv.status = 'published'
           ORDER BY pv.published_at DESC
           LIMIT %s""",
        (platform, limit),
    )
    return [dict(r) for r in rows]


def _get_engagement_summary() -> dict:
    rows = db.execute(
        """SELECT platform, COUNT(*) as total, MAX(created_at) as last_run
           FROM engagement_runs
           WHERE created_at > NOW() - INTERVAL '7 days'
           GROUP BY platform"""
    )
    return {r["platform"]: {"total": r["total"], "last_run": str(r["last_run"])} for r in rows}


def run_engage_cycle(platform: str = DEFAULT_PLATFORM, mode: str = "light") -> dict:
    """
    Run one engagement cycle for a platform.

    Modes:
      light — likes only (safe, low risk)
      medium — likes + comments (moderate)
      full — likes + comments + follows + mining (aggressive)
    """
    content = _get_published_content(platform, limit=5)
    if not content:
        logger.info(f"No published content for {platform}")
        return {"platform": platform, "mode": mode, "actions": 0}

    results: dict = {"platform": platform, "mode": mode, "actions": 0, "details": []}

    # Always run likes (light mode)
    for item in content[:3]:
        likes = liker.run_likes(platform, item.get("platform_url", ""), count=10)
        results["actions"] += likes
        results["details"].append({"type": "like", "platform": platform, "count": likes})

    if mode in ("medium", "full"):
        for item in content[:2]:
            caption = item.get("caption") or ""
            replies = commenter.run_comment_engagement(
                platform, item.get("platform_url", ""), caption, ["Great content!", "Love this!"]
            )
            results["actions"] += replies
            results["details"].append({"type": "comment", "platform": platform, "count": replies})

    if mode == "full":
        follower.run_follows(platform)
        results["details"].append({"type": "follow", "platform": platform})

        for item in content[:1]:
            signals = comment_miner.mine_from_platform(
                platform, item.get("platform_url", "")
            )
            results["details"].append({"type": "mining", "signals": len(signals)})

    # Log the run
    try:
        db.execute(
            """INSERT INTO engagement_runs (platform, mode, actions_count, created_at)
               VALUES (%s, %s, %s, NOW())""",
            (platform, mode, results["actions"]),
        )
    except Exception:
        pass

    logger.info(f"Engage cycle complete: {platform}/{mode} — {results['actions']} actions")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default=DEFAULT_PLATFORM)
    parser.add_argument("--mode", choices=["light", "medium", "full"], default="light")
    args = parser.parse_args()
    result = run_engage_cycle(platform=args.platform, mode=args.mode)
    print(json.dumps(result, ensure_ascii=False, default=str))
