#!/usr/bin/env python3
"""
X/Twitter trending topics fetcher.
Discovers trending hashtags and topics from X via API or scraping fallback.

Usage:
    python3 scripts/fetch_twitter_trends.py [--region US] [--limit 20]
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

logger = setup_logger("fetch_twitter_trends")

X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "")
API_BASE = "https://api.twitter.com/2"
DEFAULT_LIMIT = int(os.environ.get("TWITTER_TREND_LIMIT", "20"))


def _match_category(hashtag: str, text: str) -> int | None:
    """Match a trend to a genesis_category by keyword overlap."""
    combined = f"{hashtag} {text}".lower()
    cats = db.execute("SELECT id, slug, display_name FROM genesis_categories WHERE is_active = true")
    for c in cats:
        slug = c["slug"].lower()
        display = c["display_name"].lower()
        if slug in combined or display in combined:
            return c["id"]
    return None


def fetch_trending(region: str = "US", limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Fetch trending topics from X API (WOEID-based or global)."""
    if not X_BEARER_TOKEN:
        logger.warning("X_BEARER_TOKEN not set — skipping Twitter trends")
        return []

    # WOEID for common regions
    woeid_map = {"US": 23424977, "GB": 23424975, "JP": 23424856, "KR": 23424868, "BR": 23424768, "global": 1}
    woeid = woeid_map.get(region, 1)
    url = "https://api.x.com/1.1/trends/place.json"
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

    try:
        r = requests.get(url, params={"id": woeid}, headers=headers, timeout=10)
        r.raise_for_status()
        trends_data = r.json()
        if not trends_data or not trends_data[0].get("trends"):
            logger.warning("X API returned empty trends")
            return []

        trends = trends_data[0]["trends"]
        results: list[dict] = []
        for t in trends[:limit]:
            name = t.get("name", "").strip("#")
            volume = t.get("tweet_volume") or 0
            results.append({
                "hashtag": f"#{name}",
                "region": region,
                "source": "x_trending",
                "confidence": min(0.95, volume / 100_000) if volume else 0.3,
                "trend_velocity": min(1.0, volume / 500_000) if volume else 0.1,
                "post_count": volume,
            })
        return results
    except Exception as exc:
        logger.error(f"X API request failed: {exc}")
        return []


def save_trends(trends: list[dict]) -> int:
    """Upsert trends into trend_intel, linking to genesis_categories."""
    saved = 0
    for t in trends:
        category_id = _match_category(t["hashtag"], "")
        try:
            db.execute(
                """INSERT INTO trend_intel
                   (hashtag, region, confidence, trend_velocity, post_count, source,
                    source_engine, status, discovered_at, category_id)
                   VALUES (%s, %s, %s, %s, %s, %s, 'x_trending', 'new', NOW(), %s)
                   ON CONFLICT (hashtag, region) DO UPDATE SET
                     confidence = EXCLUDED.confidence,
                     trend_velocity = EXCLUDED.trend_velocity,
                     post_count = EXCLUDED.post_count,
                     last_researched_at = NOW()""",
                (t["hashtag"], t["region"], t["confidence"], t["trend_velocity"],
                 t["post_count"], t["source"], category_id),
            )
            saved += 1
        except Exception as exc:
            logger.warning(f"Failed to save trend {t['hashtag']}: {exc}")
    return saved


def main(region: str = "US", limit: int = DEFAULT_LIMIT):
    trends = fetch_trending(region=region, limit=limit)
    if not trends:
        logger.info("No Twitter trends found")
        return {"source": "twitter", "region": region, "count": 0}
    saved = save_trends(trends)
    logger.info(f"Saved {saved}/{len(trends)} Twitter trends")
    return {"source": "twitter", "region": region, "count": saved, "trends": trends}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="US")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()
    result = main(region=args.region, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, default=str))
