#!/usr/bin/env python3
"""
Pod 4 — Podcast RSS Feed Generator.

Generates an iTunes-compatible RSS XML feed from content briefs and audio files.
Uses `feedgen` for standards-compliant feed generation.

Usage:
    python scripts/podcast_rss_generator.py [--output data/podcast/feed.xml]
"""
from __future__ import annotations

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("podcast_rss_generator")

# ─── Configuration ───────────────────────────────────────────────────────────
PODCAST_TITLE = os.environ.get("PODCAST_TITLE", "Trend Pulse — AI-Powered Insights")
PODCAST_DESC = os.environ.get(
    "PODCAST_DESC",
    "Daily breakdowns of the hottest trends in tech, fiction, movies, and culture — "
    "powered by AI, delivered by voice.",
)
PODCAST_AUTHOR = os.environ.get("PODCAST_AUTHOR", "Trend Pulse")
PODCAST_EMAIL = os.environ.get("PODCAST_EMAIL", "podcast@example.com")
PODCAST_WEBSITE = os.environ.get("PODCAST_WEBSITE", "https://example.com/podcast")
PODCAST_IMAGE = os.environ.get("PODCAST_IMAGE", "https://example.com/podcast-cover.jpg")
PODCAST_LANGUAGE = os.environ.get("PODCAST_LANGUAGE", "en")
PODCAST_CATEGORY = os.environ.get("PODCAST_CATEGORY", "Technology")
AUDIO_BASE_URL = os.environ.get("PODCAST_AUDIO_BASE_URL", "https://example.com/audio")
OUTPUT_DIR = os.environ.get("PODCAST_OUTPUT_DIR", "data/podcast")


def _ensure_feedgen():
    """Import feedgen, installing it if necessary."""
    try:
        from feedgen.feed import FeedGenerator
        return FeedGenerator
    except ImportError:
        logger.error("feedgen not installed. Run: pip install feedgen")
        raise


def get_podcast_episodes(limit: int = 50) -> list[dict]:
    """
    Fetch master_assets that have audio files, ordered by creation date.
    These become podcast episodes.
    """
    return db.execute(
        """
        SELECT ma.id, ma.title, ma.base_script, ma.base_audio_path,
               ma.category, ma.created_at,
               cb.viral_hook, cb.target_audience
        FROM master_assets ma
        LEFT JOIN content_briefs cb ON ma.brief_id = cb.id
        WHERE ma.base_audio_path IS NOT NULL
          AND ma.status IN ('ready', 'archived')
        ORDER BY ma.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def generate_feed(episodes: list[dict] | None = None, output_path: str | None = None) -> str:
    """
    Generate a podcast RSS XML feed.
    Returns the XML string and writes to file.
    """
    FeedGenerator = _ensure_feedgen()
    fg = FeedGenerator()

    # ── Channel metadata ──
    fg.load_extension("podcast")
    fg.title(PODCAST_TITLE)
    fg.link(href=PODCAST_WEBSITE, rel="alternate")
    fg.description(PODCAST_DESC)
    fg.language(PODCAST_LANGUAGE)
    fg.author({"name": PODCAST_AUTHOR, "email": PODCAST_EMAIL})
    fg.logo(PODCAST_IMAGE)
    fg.podcast.itunes_author(PODCAST_AUTHOR)
    fg.podcast.itunes_category(PODCAST_CATEGORY)
    fg.podcast.itunes_image(PODCAST_IMAGE)
    fg.podcast.itunes_owner(name=PODCAST_AUTHOR, email=PODCAST_EMAIL)
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_type("episodic")

    # ── Episodes ──
    if episodes is None:
        episodes = get_podcast_episodes()

    for ep in episodes:
        fe = fg.add_entry()
        title = ep.get("title") or f"Episode {ep['id']}"
        fe.id(f"episode-{ep['id']}")
        fe.title(title)

        # Description: use viral_hook + script preview
        hook = ep.get("viral_hook") or ""
        script_preview = (ep.get("base_script") or "")[:500]
        description = f"{hook}\n\n{script_preview}..." if hook else script_preview
        fe.description(description)

        fe.published(ep.get("created_at", datetime.now(timezone.utc)))

        # Audio enclosure
        audio_path = ep.get("base_audio_path", "")
        audio_filename = os.path.basename(audio_path) if audio_path else f"episode_{ep['id']}.mp3"
        audio_url = f"{AUDIO_BASE_URL.rstrip('/')}/{audio_filename}"

        # Get file size if local file exists
        file_size = 0
        if audio_path and os.path.exists(audio_path):
            file_size = os.path.getsize(audio_path)

        fe.enclosure(audio_url, str(file_size), "audio/mpeg")

        # iTunes extensions
        fe.podcast.itunes_author(PODCAST_AUTHOR)
        fe.podcast.itunes_summary(description[:255])
        category = ep.get("category") or "general"
        fe.podcast.itunes_subtitle(f"{category.title()} — {title[:100]}")

    # ── Write to file ──
    out_path = output_path or os.path.join(OUTPUT_DIR, "feed.xml")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fg.rss_file(out_path, pretty=True)

    xml_str = fg.rss_str(pretty=True).decode("utf-8")
    logger.info(f"Generated podcast RSS with {len(episodes)} episodes → {out_path}")
    return xml_str


def main(body: dict | None = None, **kwargs) -> dict:
    """Entry point for worker.py integration."""
    if body is None:
        body = kwargs
    limit = int(body.get("limit", 50))
    output_path = body.get("output_path")

    episodes = get_podcast_episodes(limit=limit)
    xml = generate_feed(episodes=episodes, output_path=output_path)

    return {
        "episodes": len(episodes),
        "output_path": output_path or os.path.join(OUTPUT_DIR, "feed.xml"),
        "xml_length": len(xml),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Podcast RSS Feed Generator")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    result = main({"limit": args.limit, "output_path": args.output})
    print(json.dumps(result, indent=2))
