#!/usr/bin/env python3
"""
YouTube trending videos fetcher.
Discovers trending video topics/categories for content sourcing.

Usage:
    python3 scripts/fetch_youtube_trends.py [--region US] [--limit 20] [--category gaming]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("fetch_youtube_trends")

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
DEFAULT_LIMIT = int(os.environ.get("YOUTUBE_TREND_LIMIT", "20"))
API_BASE = "https://www.googleapis.com/youtube/v3"

# Category mapping: YouTube videoCategoryId → genesis_category slug
CATEGORY_MAP = {
    "1": "movies", "2": "tech", "10": "audio",
    "20": "gaming", "22": "tech", "23": "art",
    "24": "fiction", "25": "finance", "26": "tech",
    "27": "tech", "28": "tech",
}


def _match_category(tags: list[str], title: str) -> int | None:
    combined = f"{' '.join(tags)} {title}".lower()
    cats = db.execute("SELECT id, slug, display_name FROM genesis_categories WHERE is_active = true")
    for c in cats:
        slug = c["slug"].lower()
        display = c["display_name"].lower()
        if slug in combined or display in combined:
            return c["id"]
    return None


def fetch_trending(region: str = "US", limit: int = DEFAULT_LIMIT,
                   category_id: str | None = None) -> list[dict]:
    if not YOUTUBE_API_KEY:
        logger.warning("YOUTUBE_API_KEY not set — skipping YouTube trends")
        return []

    params: dict = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": limit,
        "key": YOUTUBE_API_KEY,
    }
    if category_id:
        params["videoCategoryId"] = category_id

    try:
        r = __import__("requests").get(f"{API_BASE}/videos", params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as exc:
        logger.error(f"YouTube API request failed: {exc}")
        return []

    results: list[dict] = []
    for v in items:
        snip = v.get("snippet", {})
        stats = v.get("statistics", {})
        title = snip.get("title", "")
        tags = snip.get("tags", [])
        view_count = int(stats.get("viewCount", 0))
        results.append({
            "hashtag": f"#{title.split()[0] if title else 'trending'}",
            "region": region,
            "source": "youtube_trending",
            "confidence": min(0.90, view_count / 1_000_000) if view_count else 0.3,
            "trend_velocity": min(1.0, view_count / 5_000_000) if view_count else 0.1,
            "post_count": int(stats.get("commentCount", 0)),
            "avg_views": view_count,
            "raw_title": title,
        })
    return results


def save_trends(trends: list[dict]) -> int:
    saved = 0
    for t in trends:
        title = t.pop("raw_title", "")
        category_id = _match_category([], title)
        try:
            db.execute(
                """INSERT INTO trend_intel
                   (hashtag, region, confidence, trend_velocity, post_count, avg_views,
                    source, source_engine, status, discovered_at, category_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'youtube_trending', 'new', NOW(), %s)
                   ON CONFLICT (hashtag, region) DO UPDATE SET
                     confidence = EXCLUDED.confidence,
                     trend_velocity = EXCLUDED.trend_velocity,
                     avg_views = EXCLUDED.avg_views,
                     last_researched_at = NOW()""",
                (t["hashtag"], t["region"], t["confidence"], t["trend_velocity"],
                 t["post_count"], t["avg_views"], t["source"], category_id),
            )
            saved += 1
        except Exception as exc:
            logger.warning(f"Failed to save trend {t['hashtag']}: {exc}")
    return saved


def main(region: str = "US", limit: int = DEFAULT_LIMIT, category: str = ""):
    cat_id = None
    if category:
        for k, v in CATEGORY_MAP.items():
            if category.lower() in v:
                cat_id = v
                break
    trends = fetch_trending(region=region, limit=limit)
    if not trends:
        return {"source": "youtube", "region": region, "count": 0}
    saved = save_trends(trends)
    logger.info(f"Saved {saved}/{len(trends)} YouTube trends")
    return {"source": "youtube", "region": region, "count": saved}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="US")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--category", default="")
    args = parser.parse_args()
    result = main(region=args.region, limit=args.limit, category=args.category)
    print(json.dumps(result, ensure_ascii=False, default=str))
