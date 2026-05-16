#!/usr/bin/env python3
"""
Reddit trending posts fetcher.
Discovers hot/rising posts from configured subreddits per genesis_category.

Usage:
    python3 scripts/fetch_reddit_trends.py [--category tech] [--limit 20]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import requests
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("fetch_reddit_trends")

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
DEFAULT_LIMIT = int(os.environ.get("REDDIT_TREND_LIMIT", "20"))


def _get_categories() -> list[dict]:
    return db.execute(
        "SELECT id, slug, display_name, subreddits FROM genesis_categories WHERE is_active = true AND subreddits IS NOT NULL AND array_length(subreddits, 1) > 0"
    )


def fetch_hot(subreddit: str, limit: int = 25) -> list[dict]:
    """Fetch hot posts from a subreddit using Reddit's public JSON API (no auth needed)."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json"
    headers = {"User-Agent": "aitoearn-trend-bot/1.0"}
    try:
        r = requests.get(url, params={"limit": limit}, headers=headers, timeout=10)
        r.raise_for_status()
        children = r.json().get("data", {}).get("children", [])
    except Exception as exc:
        logger.warning(f"Failed to fetch r/{subreddit}: {exc}")
        return []

    results: list[dict] = []
    for child in children:
        data = child.get("data", {})
        title = data.get("title", "")
        score = data.get("score", 0)
        num_comments = data.get("num_comments", 0)
        upvote_ratio = data.get("upvote_ratio", 0.0)
        permalink = data.get("permalink", "")
        created_utc = data.get("created_utc", 0)
        hours_old = max(1, (datetime.now(timezone.utc).timestamp() - created_utc) / 3600)
        velocity = min(1.0, score / max(1, hours_old) / 1000)
        confidence = min(0.95, upvote_ratio * min(1.0, score / 1000))

        results.append({
            "title": title,
            "hashtag": f"#r/{subreddit}",
            "source_url": f"https://reddit.com{permalink}",
            "region": "US",
            "source": "reddit",
            "source_engine": f"r/{subreddit}",
            "confidence": confidence,
            "trend_velocity": velocity,
            "post_count": num_comments,
            "score": score,
            "upvote_ratio": upvote_ratio,
        })
    return results


def save_signals_and_trends(category_id: int, posts: list[dict]) -> int:
    saved = 0
    for p in posts:
        try:
            db.execute(
                """INSERT INTO genesis_signals
                   (category_id, source_platform, source_url, title, score,
                    comment_count, velocity_score, scraped_at)
                   VALUES (%s, 'reddit', %s, %s, %s, %s, %s, NOW())
                   ON CONFLICT (source_platform, source_url) DO UPDATE SET
                     score = EXCLUDED.score,
                     velocity_score = EXCLUDED.velocity_score,
                     scraped_at = NOW()""",
                (category_id, p["source_url"], p["title"], p["score"],
                 p["post_count"], p["trend_velocity"]),
            )
            db.execute(
                """INSERT INTO trend_intel
                   (hashtag, region, confidence, trend_velocity, post_count, source,
                    source_engine, status, discovered_at, category_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'new', NOW(), %s)
                   ON CONFLICT (hashtag, region) DO UPDATE SET
                     trend_velocity = EXCLUDED.trend_velocity,
                     last_researched_at = NOW()""",
                (p["hashtag"], p["region"], p["confidence"], p["trend_velocity"],
                 p["post_count"], p["source"], p["source_engine"], category_id),
            )
            saved += 1
        except Exception as exc:
            logger.warning(f"Failed to save Reddit signal: {exc}")
    return saved


def main(category_slug: str = "", limit: int = DEFAULT_LIMIT) -> dict:
    categories = _get_categories()
    if category_slug:
        categories = [c for c in categories if c["slug"] == category_slug]
    if not categories:
        logger.warning("No categories with subreddits configured")
        return {"source": "reddit", "count": 0}

    total_saved = 0
    for cat in categories:
        subreddits = cat.get("subreddits") or []
        if not isinstance(subreddits, list):
            subreddits = [subreddits]
        for sub in subreddits:
            posts = fetch_hot(sub, limit=min(limit, 10))
            if posts:
                saved = save_signals_and_trends(cat["id"], posts)
                total_saved += saved
                logger.info(f"Saved {saved} from r/{sub} [{cat['slug']}]")

    return {"source": "reddit", "count": total_saved}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()
    result = main(category_slug=args.category, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, default=str))
