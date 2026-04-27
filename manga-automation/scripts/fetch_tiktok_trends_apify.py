#!/usr/bin/env python3
"""
Phase 2: TikTok Trend Discovery via Apify.
Fetches trending hashtags from TikTok Creative Center and saves to trend_intel table.

Usage:
    python3 scripts/fetch_tiktok_trends_apify.py [--region US] [--limit 20]
"""
import os, sys, json, argparse, requests
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("fetch_tiktok_trends_apify")

APIFY_TOKEN = os.environ.get("APIFY_API") or os.environ.get("APIFY_DATA_SCRAPING_API")
VELOCITY_THRESHOLD = float(os.environ.get("VELOCITY_THRESHOLD", "0.0"))

# Apify actor for TikTok Creative Center trends
ACTOR_ID = "madoka_trendpulse~tiktok-trends-scraper"


def fetch_from_apify(region: str = "US", limit: int = 20) -> list:
    """Call Apify actor synchronously and return raw results."""
    if not APIFY_TOKEN:
        logger.error("APIFY_API token not set in .env")
        return []

    # Use the async run + dataset fetch pattern (more reliable than run-sync)
    run_url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs"
    params = {"token": APIFY_TOKEN}
    payload = {"region": region, "limit": limit, "type": "hashtag"}

    logger.info(f"Fetching TikTok trends from Apify: region={region}, limit={limit}")
    try:
        # Start the run
        r = requests.post(run_url, params=params, json=payload, timeout=15)
        r.raise_for_status()
        run_id = r.json().get("data", {}).get("id")
        if not run_id:
            logger.error("No run ID returned from Apify")
            return []

        # Poll for completion (max 60s)
        import time
        status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
        for _ in range(12):  # 12 x 5s = 60s max
            time.sleep(5)
            sr = requests.get(status_url, params={"token": APIFY_TOKEN}, timeout=10)
            status = sr.json().get("data", {}).get("status", "")
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break

        if status != "SUCCEEDED":
            logger.warning(f"Apify run ended with status: {status} — using fallback")
            return []

        # Fetch dataset
        dataset_id = sr.json()["data"]["defaultDatasetId"]
        dr = requests.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            params={"token": APIFY_TOKEN, "limit": limit},
            timeout=15,
        )
        dr.raise_for_status()
        data = dr.json()
        logger.info(f"Apify returned {len(data)} trend items")
        return data
    except requests.exceptions.Timeout:
        logger.warning("Apify timed out — using fallback seeds")
        return []
    except Exception as e:
        logger.error(f"Apify request failed: {e}")
        return []


def calculate_velocity(item: dict) -> float:
    """Trend velocity = post_count_change * avg_engagement_rate."""
    change = item.get("postCountChange") or item.get("post_count_change") or 0
    engagement = item.get("avgEngagementRate") or item.get("avg_engagement_rate") or 0
    return float(change) * float(engagement)


def normalize_item(item: dict) -> dict | None:
    """Normalize Apify response fields to our schema."""
    hashtag = (
        item.get("hashtag") or item.get("name") or
        item.get("hashtagName") or item.get("tag") or ""
    ).strip().lstrip("#").strip()

    # Skip blank, spaced, or clearly non-topic hashtags
    if not hashtag or " " in hashtag or len(hashtag) < 2:
        return None

    return {
        "hashtag": f"#{hashtag}",
        "avg_views": item.get("avgViews") or item.get("avg_views") or 0,
        "post_count": item.get("postCount") or item.get("post_count") or 0,
        "trend_velocity": calculate_velocity(item),
    }


def save_trends(trends: list, region: str) -> int:
    """Upsert trends into trend_intel. Returns count of new/updated rows."""
    saved = 0
    for t in trends:
        if t["trend_velocity"] < VELOCITY_THRESHOLD:
            continue
        try:
            db.execute(
                """
                INSERT INTO trend_intel (hashtag, region, avg_views, post_count, trend_velocity)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (hashtag, region) DO UPDATE
                    SET avg_views      = EXCLUDED.avg_views,
                        post_count     = EXCLUDED.post_count,
                        trend_velocity = EXCLUDED.trend_velocity,
                        status         = CASE
                            WHEN trend_intel.status = 'done' THEN 'new'
                            ELSE trend_intel.status
                        END,
                        discovered_at  = NOW()
                """,
                (t["hashtag"], region, t["avg_views"], t["post_count"], t["trend_velocity"]),
            )
            saved += 1
        except Exception as e:
            logger.error(f"Failed to save trend {t['hashtag']}: {e}")
    return saved


def main(region: str = "US", limit: int = 20) -> dict:
    raw = fetch_from_apify(region, limit)

    if not raw:
        # Fallback: seed with known manga/anime trends for testing
        logger.warning("No Apify data — using fallback manga trend seeds")
        raw = [
            {"hashtag": "manga",   "avgViews": 5000000, "postCount": 500000, "postCountChange": 10000, "avgEngagementRate": 0.05},
            {"hashtag": "anime",   "avgViews": 8000000, "postCount": 900000, "postCountChange": 15000, "avgEngagementRate": 0.06},
            {"hashtag": "manhwa",  "avgViews": 2000000, "postCount": 200000, "postCountChange": 8000,  "avgEngagementRate": 0.07},
            {"hashtag": "manhua",  "avgViews": 1000000, "postCount": 100000, "postCountChange": 5000,  "avgEngagementRate": 0.06},
            {"hashtag": "isekai",  "avgViews": 3000000, "postCount": 300000, "postCountChange": 12000, "avgEngagementRate": 0.08},
            {"hashtag": "otaku",   "avgViews": 1500000, "postCount": 150000, "postCountChange": 6000,  "avgEngagementRate": 0.07},
            {"hashtag": "webtoon", "avgViews": 2500000, "postCount": 250000, "postCountChange": 9000,  "avgEngagementRate": 0.07},
        ]

    normalized = [n for item in raw if (n := normalize_item(item)) is not None]
    saved = save_trends(normalized, region)

    logger.info(f"Saved {saved}/{len(normalized)} trends for region={region}")

    # Write to ChromaDB vector memory for long-term trend tracking
    try:
        from scripts.memory_manager import record_trend
        for t in normalized:
            record_trend(
                hashtag=t["hashtag"],
                avg_views=int(t["avg_views"]),
                post_count=int(t["post_count"]),
                trend_velocity=float(t["trend_velocity"]),
                region=region,
            )
        logger.info(f"Recorded {len(normalized)} trends to ChromaDB memory")
    except Exception as e:
        logger.warning(f"ChromaDB memory write skipped: {e}")

    return {"region": region, "fetched": len(raw), "normalized": len(normalized), "saved": saved}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="US")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    result = main(args.region, args.limit)
    print(json.dumps(result))
