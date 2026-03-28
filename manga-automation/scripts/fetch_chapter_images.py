#!/usr/bin/env python3
"""
Fetch the latest chapter for a given manga and save panel URLs to the database.

Usage:
    python3 scripts/fetch_chapter_images.py --manga-id <db_manga_id>
    python3 scripts/fetch_chapter_images.py --manga-id 1

Output:
    JSON with chapter info and panel URLs.
    Exit 0 on success, 1 on failure.
"""
import sys
import json
import argparse
from dotenv import load_dotenv

load_dotenv()

import requests
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("fetch_chapter_images")

MANGADEX_BASE = "https://api.mangadex.org"


def get_latest_chapter(mangadex_id: str) -> dict | None:
    try:
        resp = requests.get(
            f"{MANGADEX_BASE}/manga/{mangadex_id}/feed",
            params={
                "limit": 1,
                "order[chapter]": "desc",
                "translatedLanguage[]": ["en"],
                "contentRating[]": ["safe", "suggestive"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        ch = data[0]
        attr = ch.get("attributes", {})
        return {
            "id": ch["id"],
            "chapter_number": attr.get("chapter", "?"),
            "chapter_title": attr.get("title", ""),
            "published_at": attr.get("publishAt", ""),
        }
    except Exception as e:
        logger.error(f"Failed to fetch chapter for manga {mangadex_id}: {e}")
        return None


def get_chapter_pages(chapter_id: str) -> list[str]:
    """Fetch page URLs from MangaDex@Home. Falls back to dataSaver quality if full-res is empty."""
    try:
        resp = requests.get(
            f"{MANGADEX_BASE}/at-home/server/{chapter_id}",
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        base_url = body["baseUrl"]
        chapter = body["chapter"]
        img_hash = chapter["hash"]

        pages = chapter.get("data", [])
        quality = "data"

        if not pages:
            pages = chapter.get("dataSaver", [])
            quality = "data-saver"

        if not pages:
            logger.warning(f"Chapter {chapter_id} has no pages in either data or dataSaver")
            return []

        logger.info(f"Chapter {chapter_id}: {len(pages)} pages ({quality} quality)")
        return [f"{base_url}/{quality}/{img_hash}/{img}" for img in pages]
    except Exception as e:
        logger.error(f"Failed to fetch pages for chapter {chapter_id}: {e}")
        return []


def get_recent_chapters(mangadex_id: str, limit: int = 10) -> list[dict]:
    """Fetch recent English chapters that are hosted on MangaDex (not external/licensed)."""
    try:
        resp = requests.get(
            f"{MANGADEX_BASE}/manga/{mangadex_id}/feed",
            params={
                "limit": limit,
                "order[chapter]": "desc",
                "translatedLanguage[]": ["en"],
                "contentRating[]": ["safe", "suggestive"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        all_chapters = resp.json().get("data", [])
        # Filter out licensed/external chapters that MangaDex doesn't host
        hosted = [
            ch for ch in all_chapters
            if ch["attributes"].get("externalUrl") is None
            and ch["attributes"].get("pages", 0) > 0
        ]
        if len(all_chapters) > 0 and len(hosted) == 0:
            logger.warning(
                f"All {len(all_chapters)} chapters for {mangadex_id} are externally licensed "
                "(Viz/Shonen Jump). Cannot scrape."
            )
        return hosted
    except Exception as e:
        logger.error(f"Failed to fetch chapter list for {mangadex_id}: {e}")
        return []


def already_scraped(mangadex_chapter_id: str) -> bool:
    row = db.execute_one(
        "SELECT id FROM manga_chapters WHERE mangadex_id = %s",
        (mangadex_chapter_id,),
    )
    return row is not None


def save_chapter(manga_id: int, chapter: dict, pages: list[str]) -> int:
    chapter_id = db.execute_returning(
        """
        INSERT INTO manga_chapters
            (manga_id, chapter_number, chapter_title, mangadex_id, panel_urls)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (mangadex_id) DO UPDATE SET
            panel_urls = EXCLUDED.panel_urls
        RETURNING id
        """,
        (
            manga_id,
            chapter["chapter_number"],
            chapter["chapter_title"],
            chapter["id"],
            json.dumps(pages),
        ),
    )
    return chapter_id


def main(manga_db_id: int) -> dict:
    manga = db.execute_one(
        "SELECT id, title, mangadex_id FROM manga WHERE id = %s",
        (manga_db_id,),
    )
    if not manga:
        logger.error(f"Manga id={manga_db_id} not found in DB")
        return {}

    if not manga.get("mangadex_id"):
        logger.warning(f"Manga '{manga['title']}' has no mangadex_id, skipping")
        return {}

    logger.info(f"Fetching recent chapters for: {manga['title']}")

    # Try up to 5 recent chapters to find one with available pages
    recent = get_recent_chapters(manga["mangadex_id"], limit=5)
    if not recent:
        logger.warning(f"No English chapters found for {manga['title']}")
        return {}

    chapter = None
    pages = []
    for raw in recent:
        attr = raw.get("attributes", {})
        candidate = {
            "id": raw["id"],
            "chapter_number": attr.get("chapter", "?"),
            "chapter_title": attr.get("title", ""),
            "published_at": attr.get("publishAt", ""),
        }

        if already_scraped(candidate["id"]):
            logger.info(f"Chapter {candidate['chapter_number']} already in DB, skipping")
            existing = db.execute_one(
                "SELECT id FROM manga_chapters WHERE mangadex_id = %s",
                (candidate["id"],),
            )
            return {"status": "already_processed", "chapter_id": existing["id"]}

        pages = get_chapter_pages(candidate["id"])
        if pages:
            chapter = candidate
            logger.info(f"Using chapter {chapter['chapter_number']} with {len(pages)} pages")
            break
        else:
            logger.warning(f"Chapter {candidate['chapter_number']} has no pages, trying older one...")

    if not chapter or not pages:
        logger.error(f"No accessible chapters with pages found for {manga['title']}")
        return {}

    chapter_id = save_chapter(manga["id"], chapter, pages)
    logger.info(
        f"Saved chapter {chapter['chapter_number']} ({len(pages)} pages) → chapter_id={chapter_id}"
    )

    return {
        "status": "fetched",
        "manga_id": manga["id"],
        "manga_title": manga["title"],
        "chapter_id": chapter_id,
        "chapter_number": chapter["chapter_number"],
        "panel_count": len(pages),
        "panel_urls": pages,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manga-id", type=int, required=True, help="DB manga id")
    args = parser.parse_args()

    result = main(args.manga_id)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result else 1)
