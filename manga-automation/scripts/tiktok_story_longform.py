#!/usr/bin/env python3
"""
TikTok story → long meme video pipeline.

1. Fetch a #storytime (or custom hashtag) TikTok post caption via Apify
2. Expand into a long multi-scene narration script (OpenAI)
3. Render via short-form Remotion MemeStory (TTS + Giphy/Pexels)

Usage:
    python -m scripts.tiktok_story_longform --hashtag storytime
    POST /shortform/tiktok-longform  { "hashtag": "storytime", "publish": false }
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts import shortform_pipeline
from scripts.utils.logger import setup_logger

logger = setup_logger("tiktok_story_longform")

APIFY_TOKEN = os.environ.get("APIFY_API") or os.environ.get("APIFY_DATA_SCRAPING_API")
# Public Apify actor that scrapes hashtag videos + captions
ACTOR_ID = os.environ.get("TIKTOK_STORY_ACTOR", "clockworks~tiktok-scraper")


@dataclass
class TikTokStory:
    title: str
    body: str
    url: str
    author: str = ""
    views: int = 0
    hashtag: str = "storytime"


def _apify_run(payload: dict[str, Any], *, timeout_sec: int = 120) -> list[dict]:
    if not APIFY_TOKEN:
        logger.warning("APIFY_API not set — cannot scrape TikTok")
        return []

    run_url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs"
    r = requests.post(run_url, params={"token": APIFY_TOKEN}, json=payload, timeout=30)
    r.raise_for_status()
    run_id = r.json().get("data", {}).get("id")
    if not run_id:
        return []

    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
    status = ""
    dataset_id = None
    for _ in range(max(1, timeout_sec // 5)):
        time.sleep(5)
        sr = requests.get(status_url, params={"token": APIFY_TOKEN}, timeout=15)
        data = sr.json().get("data", {})
        status = data.get("status", "")
        dataset_id = data.get("defaultDatasetId")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if status != "SUCCEEDED" or not dataset_id:
        logger.warning(f"Apify TikTok scrape ended status={status}")
        return []

    dr = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": APIFY_TOKEN, "limit": 20},
        timeout=30,
    )
    dr.raise_for_status()
    return dr.json() if isinstance(dr.json(), list) else []


def fetch_tiktok_stories(hashtag: str = "storytime", *, limit: int = 10) -> list[TikTokStory]:
    """Scrape TikTok hashtag videos and return caption-based stories."""
    tag = hashtag.lstrip("#").strip() or "storytime"
    payload = {
        "hashtags": [tag],
        "resultsPerPage": max(limit, 5),
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSlideshowImages": False,
    }
    try:
        items = _apify_run(payload, timeout_sec=90)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"TikTok scrape failed: {exc}")
        items = []

    stories: list[TikTokStory] = []
    for item in items:
        text = (
            item.get("text")
            or item.get("desc")
            or item.get("description")
            or item.get("caption")
            or ""
        ).strip()
        # Strip hashtag spam for readability but keep enough story meat.
        cleaned = re.sub(r"#\w+", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned.split()) < 25:
            continue
        author = (
            (item.get("authorMeta") or {}).get("name")
            or (item.get("author") or {}).get("uniqueId")
            or item.get("authorName")
            or "tiktok"
        )
        url = item.get("webVideoUrl") or item.get("url") or ""
        views = int(
            item.get("playCount")
            or (item.get("stats") or {}).get("playCount")
            or item.get("views")
            or 0
        )
        title = cleaned[:80] + ("…" if len(cleaned) > 80 else "")
        stories.append(
            TikTokStory(
                title=title,
                body=cleaned,
                url=str(url),
                author=str(author),
                views=views,
                hashtag=tag,
            )
        )
        if len(stories) >= limit:
            break

    stories.sort(key=lambda s: s.views, reverse=True)
    return stories


def _fallback_story(hashtag: str) -> TikTokStory:
    """If scrape fails, seed a storytime-shaped prompt from the trend tag."""
    tag = hashtag.lstrip("#") or "storytime"
    body = (
        f"TikTok #{tag} story: I found out my best friend had been lying to me for months. "
        "It started with small things I ignored, then one night I saw messages on their phone "
        "that changed everything. I confronted them the next morning and the excuse they gave "
        "was somehow worse than the lie. Now I keep replaying every memory wondering what else "
        "wasn't real. People in the comments said I should cut them off, but it's not that easy "
        "when you grew up together."
    )
    return TikTokStory(
        title=f"#{tag} — the friend who lied for months",
        body=body,
        url=f"https://www.tiktok.com/tag/{tag}",
        author="fallback",
        views=0,
        hashtag=tag,
    )


def run(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    hashtag = str(body.get("hashtag") or body.get("tag") or "storytime")
    dry_run = bool(body.get("dry_run", False))
    publish = bool(body.get("publish", False))
    limit = int(body.get("limit") or 5)

    logger.info(f"Fetching TikTok stories for #{hashtag.lstrip('#')}")
    stories = fetch_tiktok_stories(hashtag, limit=limit)
    source = "apify"
    if not stories:
        logger.warning("No usable TikTok captions — using storytime fallback seed")
        stories = [_fallback_story(hashtag)]
        source = "fallback"

    story = stories[0]
    logger.info(f"Selected story ({source}): {story.title[:70]} ({story.views} views)")

    # Expand into long meme script + render via shortform bridge.
    scripted = shortform_pipeline.stage_script(
        {
            "story": {
                "title": story.title,
                "url": story.url,
                "body": story.body,
                "author": story.author,
                "upvotes": story.views,
            },
            "style": "long_meme",
        }
    )
    if not scripted.get("ok"):
        return {"ok": False, "error": "script_failed", "script": scripted, "story": asdict(story)}

    scenes = scripted["scenes"]
    result: dict[str, Any] = {
        "ok": True,
        "source": source,
        "hashtag": hashtag.lstrip("#"),
        "story": asdict(story),
        "scene_count": len(scenes),
        "scenes": scenes if dry_run else None,
    }

    if dry_run:
        result["dry_run"] = True
        return result

    filename = body.get("filename") or f"tiktok-long-{hashtag.lstrip('#')}-{int(time.time())}.mp4"
    rendered = shortform_pipeline.stage_render(
        {
            "scenes": scenes,
            "story": {"title": story.title},
            "filename": filename,
            "title": story.title,
        }
    )
    result["render"] = rendered
    if not rendered.get("ok"):
        result["ok"] = False
        result["error"] = "render_failed"
        return result

    result["file"] = rendered.get("file")
    result["size_mb"] = rendered.get("size_mb")

    if publish:
        pub = shortform_pipeline.stage_publish(
            {
                **body,
                "file": rendered["file"],
                "title": story.title[:100],
                "desc": scenes[0]["text"] if scenes else story.title,
                "caption": scenes[0]["text"] if scenes else story.title,
                "hashtags": [f"#{hashtag.lstrip('#')}", "#storytime", "#fyp"],
            }
        )
        result["publish"] = pub
        result["ok"] = bool(pub.get("ok"))

    return result


def main(body: dict[str, Any] | None = None) -> dict[str, Any]:
    return run(body or {})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--hashtag", default="storytime")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    out = run(
        {
            "hashtag": args.hashtag,
            "dry_run": args.dry_run,
            "publish": args.publish,
            "limit": args.limit,
        }
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
