#!/usr/bin/env python3
"""
Phase 3: YouTube Asset Sourcing.
For each 'new' trend in trend_intel, searches YouTube for relevant videos
and queues them in arbitrage_assets for download.
Uses YouTube Data API v3 directly (key already in .env).
"""
import os, sys, json, argparse, requests
import re
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("source_youtube_assets")

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
MAX_ASSETS_PER_TREND = int(os.environ.get("MAX_ASSETS_PER_TREND", "3"))
MAX_DURATION_SECS = 180  # keep Shorts-compatible


def extract_channel_id(text: str) -> str | None:
    """
    Extract channel ID from URLs like:
    - https://www.youtube.com/channel/UCxxxx
    - youtube.com/channel/UCxxxx
    """
    if not text:
        return None
    match = re.search(r"(?:youtube\.com/)?channel/(UC[a-zA-Z0-9_-]{20,})", text)
    return match.group(1) if match else None


def search_youtube(query: str, max_results: int = 5) -> list:
    """Search YouTube using Data API v3."""
    if not YOUTUBE_API_KEY:
        logger.error("YOUTUBE_API_KEY not set in .env")
        return []

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "videoDuration": "short",   # under 4 minutes
        "order": "relevance",
        "publishedAfter": "2024-01-01T00:00:00Z",
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }

    logger.info(f"Searching YouTube: '{query}'")
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        items = r.json().get("items", [])
        logger.info(f"YouTube returned {len(items)} results for '{query}'")
        return items
    except Exception as e:
        logger.error(f"YouTube search failed for '{query}': {e}")
        return []


def search_youtube_channel(channel_id: str, max_results: int = 5) -> list:
    """Fetch latest short videos from a specific YouTube channel."""
    if not YOUTUBE_API_KEY:
        logger.error("YOUTUBE_API_KEY not set in .env")
        return []

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "videoDuration": "short",
        "order": "date",
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }

    logger.info(f"Searching YouTube channel shorts: '{channel_id}'")
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        items = r.json().get("items", [])
        logger.info(f"YouTube channel {channel_id} returned {len(items)} results")
        return items
    except Exception as e:
        logger.error(f"YouTube channel search failed for '{channel_id}': {e}")
        return []


def get_video_details(video_ids: list) -> dict:
    """Fetch duration and view count for a list of video IDs."""
    if not video_ids or not YOUTUBE_API_KEY:
        return {}

    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "contentDetails,statistics",
        "id": ",".join(video_ids),
        "key": YOUTUBE_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        result = {}
        for item in r.json().get("items", []):
            vid_id = item["id"]
            # Parse ISO 8601 duration e.g. PT1M30S
            duration_str = item["contentDetails"]["duration"]
            duration = parse_iso_duration(duration_str)
            views = int(item["statistics"].get("viewCount", 0))
            result[vid_id] = {"duration_secs": duration, "views": views}
        return result
    except Exception as e:
        logger.error(f"Failed to get video details: {e}")
        return {}


def parse_iso_duration(duration: str) -> int:
    """Parse PT1H2M3S → seconds."""
    import re
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def build_search_query(hashtag: str) -> str:
    tag = hashtag.lstrip("#").lower()
    query_map = {
        "manga": "best manga recommendations 2025",
        "anime": "best anime 2025 must watch",
        "manhwa": "best manhwa to read 2025",
        "manhua": "best manhua recommendations 2025",
        "isekai": "best isekai manga anime 2025",
        "otaku": "anime manga recommendations otaku 2025",
    }
    # If it's a known manga/anime tag, use the map. 
    # Otherwise, just use the tag directly to avoid pollution (e.g. for Family Guy).
    return query_map.get(tag, f"{tag} viral clips 2025")


def _pick_research_source(trend: dict) -> dict:
    channels = trend.get("channel_candidates") or []
    hashtags = trend.get("hashtag_candidates") or []
    if isinstance(channels, str):
        try:
            channels = json.loads(channels)
        except Exception:
            channels = []

    if channels:
        primary = channels[0] if isinstance(channels[0], dict) else {}
        channel_id = primary.get("channel_id")
        if channel_id:
            return {
                "mode": "channel",
                "channel_id": channel_id,
                "query": primary.get("url") or channel_id,
                "selection_reason": "research_channel_candidate",
            }

    if hashtags:
        tag = hashtags[0]
        return {
            "mode": "query",
            "channel_id": None,
            "query": build_search_query(tag),
            "selection_reason": "research_hashtag_candidate",
        }

    return {
        "mode": "query",
        "channel_id": None,
        "query": build_search_query(trend["hashtag"]),
        "selection_reason": "fallback_trend_hashtag",
    }


def queue_assets(trend_id: int, videos: list, selection: dict, research_run_id: int | None = None) -> int:
    inserted = 0
    for v in videos[:MAX_ASSETS_PER_TREND]:
        try:
            row = db.execute_one(
                """
                INSERT INTO arbitrage_assets
                    (trend_id, youtube_url, youtube_title, youtube_views, duration_secs,
                     source_query, source_channel_id, source_hashtags, selection_reason, research_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (youtube_url) DO UPDATE SET
                    trend_id = EXCLUDED.trend_id,
                    youtube_title = EXCLUDED.youtube_title,
                    youtube_views = EXCLUDED.youtube_views,
                    duration_secs = COALESCE(EXCLUDED.duration_secs, arbitrage_assets.duration_secs),
                    source_query = EXCLUDED.source_query,
                    source_channel_id = EXCLUDED.source_channel_id,
                    source_hashtags = EXCLUDED.source_hashtags,
                    selection_reason = EXCLUDED.selection_reason,
                    research_run_id = EXCLUDED.research_run_id,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    trend_id,
                    v["url"],
                    v["title"],
                    v["views"],
                    v["duration_secs"],
                    selection.get("query"),
                    selection.get("channel_id"),
                    selection.get("hashtags", []),
                    selection.get("selection_reason"),
                    research_run_id,
                ),
            )
            if row and row.get("id"):
                inserted += 1
        except Exception as e:
            logger.error(f"Failed to queue asset {v['url']}: {e}")
    return inserted


def main(limit: int = 5, query_override: str = None) -> dict:
    if query_override:
        # If a direct query is provided, we use a 'default' trend or create a temporary one.
        # For simplicity in this arbitrage flow, we'll look for a 'topic' trend.
        trend = db.execute_one("SELECT id FROM trend_intel WHERE hashtag = %s LIMIT 1", (query_override,))
        if not trend:
            trend = db.execute_one(
                "INSERT INTO trend_intel (hashtag, status) VALUES (%s, 'sourcing') RETURNING id",
                (query_override,)
            )
        else:
            db.execute("UPDATE trend_intel SET status='sourcing' WHERE id=%s", (trend["id"],))
            
        trends = [{"id": trend["id"], "hashtag": query_override}]
    else:
        trends = db.execute(
            """
            SELECT id, hashtag, channel_candidates, hashtag_candidates,
                   research_summary, raw_research_ref
            FROM trend_intel
            WHERE status IN ('new','sourcing') AND hashtag NOT LIKE '%% %%'
            ORDER BY COALESCE(confidence, 0) DESC, trend_velocity DESC
            LIMIT %s
            """,
            (limit,),
        )

    if not trends:
        logger.info("No trends to source")
        return {"processed": 0, "assets_queued": 0}

    total_assets = 0
    for trend in trends:
        if query_override:
            selection = {
                "mode": "channel" if extract_channel_id(query_override) else "query",
                "channel_id": extract_channel_id(query_override),
                "query": query_override,
                "hashtags": [],
                "selection_reason": "direct_query_override",
            }
        else:
            selection = _pick_research_source(trend)
            selection["hashtags"] = trend.get("hashtag_candidates") or []

        query = selection["query"]
        channel_id = selection.get("channel_id")
        if channel_id:
            raw = search_youtube_channel(channel_id, max_results=MAX_ASSETS_PER_TREND + 5)
        else:
            raw = search_youtube(query, max_results=MAX_ASSETS_PER_TREND + 3)

        if not raw:
            logger.warning(f"No YouTube results for trend: {trend['hashtag']}")
            db.execute("UPDATE trend_intel SET status='skipped' WHERE id=%s", (trend["id"],))
            continue

        # Get durations + views in one batch call
        video_ids = [item["id"]["videoId"] for item in raw if item.get("id", {}).get("videoId")]
        details = get_video_details(video_ids)

        videos = []
        for item in raw:
            vid_id = item.get("id", {}).get("videoId")
            if not vid_id:
                continue
            info = details.get(vid_id, {})
            duration = info.get("duration_secs", 0)
            views = info.get("views", 0)
            if duration > MAX_DURATION_SECS and duration != 0:
                continue
            videos.append({
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "title": item["snippet"]["title"][:500],
                "views": views,
                "duration_secs": duration or None,
            })

        if not videos:
            logger.warning(f"All videos filtered out for trend: {trend['hashtag']}")
            db.execute("UPDATE trend_intel SET status='skipped' WHERE id=%s", (trend["id"],))
            continue

        count = queue_assets(
            trend["id"],
            videos,
            selection=selection,
            research_run_id=trend.get("research_run_id"),
        )
        total_assets += count
        if count > 0:
            db.execute("UPDATE trend_intel SET status='sourcing' WHERE id=%s", (trend["id"],))
            logger.info(f"Trend '{trend['hashtag']}': queued {count} assets")
        else:
            # Keep as 'new' so future runs can retry with a different query / API results.
            db.execute("UPDATE trend_intel SET status='new' WHERE id=%s", (trend["id"],))
            logger.info(f"Trend '{trend['hashtag']}': queued 0 assets (will retry later)")

    return {"processed": len(trends), "assets_queued": total_assets}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    result = main(args.limit)
    print(json.dumps(result))
