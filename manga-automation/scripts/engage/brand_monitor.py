#!/usr/bin/env python3
"""
Real-time brand mention tracking across social platforms.
Monitors configured keywords/accounts and alerts on mention spikes.
"""
from __future__ import annotations

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

logger = setup_logger("brand_monitor")

MONITOR_PLATFORMS = ["twitter", "reddit", "tiktok", "youtube"]


def _get_monitor_keywords() -> list[str]:
    rows = db.execute(
        "SELECT display_name, slug FROM genesis_categories WHERE is_active = true"
    )
    keywords: list[str] = []
    for r in rows:
        keywords.append(r["display_name"])
        keywords.append(r["slug"])
    return keywords


def check_mentions(platform: str, keyword: str) -> dict[str, Any]:
    """Check mentions for a keyword on a platform. Returns mention count and samples."""
    try:
        rows = db.execute(
            """SELECT COUNT(*) as cnt FROM genesis_signals
               WHERE source_platform = %s
                 AND title ILIKE %s
                 AND scraped_at > NOW() - INTERVAL '24 hours'""",
            (platform, f"%{keyword}%"),
        )
        count = rows[0]["cnt"] if rows else 0
        return {"platform": platform, "keyword": keyword, "mention_count": count, "checked_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        logger.warning(f"Mention check failed [{platform}][{keyword}]: {exc}")
        return {"platform": platform, "keyword": keyword, "mention_count": 0, "error": str(exc)}


def run_monitor() -> list[dict[str, Any]]:
    """Run brand monitoring across all platforms and keywords."""
    keywords = _get_monitor_keywords()
    results: list[dict[str, Any]] = []
    for platform in MONITOR_PLATFORMS:
        for kw in keywords[:5]:  # Limit to top keywords
            result = check_mentions(platform, kw)
            if result["mention_count"] > 0:
                results.append(result)
                logger.info(f"[{platform}] '{kw}': {result['mention_count']} mentions")

    # Alert on spikes (>10 mentions in 24h)
    spikes = [r for r in results if r.get("mention_count", 0) > 10]
    if spikes:
        logger.info(f"ALERT: {len(spikes)} keyword spikes detected")
    return results


if __name__ == "__main__":
    results = run_monitor()
    print(json.dumps(results, ensure_ascii=False, default=str))
