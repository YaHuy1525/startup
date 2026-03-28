#!/usr/bin/env python3
"""
Fetch trending manga from MangaDex API and upsert into the database.

Usage:
    python3 scripts/fetch_trending_manga.py [--limit 20]

Output:
    JSON list of manga dicts to stdout.
    Exit 0 on success, 1 on failure.
"""
import sys
import json
import argparse
import time
from dotenv import load_dotenv

load_dotenv()

import requests
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("fetch_trending_manga")

MANGADEX_BASE = "https://api.mangadex.org"
ANILIST_URL = "https://graphql.anilist.co"


def fetch_mangadex_trending(limit: int) -> list[dict]:
    try:
        resp = requests.get(
            f"{MANGADEX_BASE}/manga",
            params={
                "limit": limit,
                "order[followedCount]": "desc",
                "includes[]": ["cover_art", "author"],
                "contentRating[]": ["safe", "suggestive"],
                "availableTranslatedLanguage[]": ["en"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        results = []
        for m in data:
            attr = m.get("attributes", {})
            cover_rel = next(
                (r for r in m.get("relationships", []) if r["type"] == "cover_art"), None
            )
            cover_url = ""
            if cover_rel and cover_rel.get("attributes", {}).get("fileName"):
                cover_url = (
                    f"https://uploads.mangadex.org/covers/{m['id']}/"
                    f"{cover_rel['attributes']['fileName']}.256.jpg"
                )
            title_map = attr.get("title", {})
            title = title_map.get("en") or next(iter(title_map.values()), "Unknown")
            results.append(
                {
                    "mangadex_id": m["id"],
                    "title": title,
                    "genre": ", ".join(
                        t["attributes"]["name"].get("en", "")
                        for t in attr.get("tags", [])
                        if t["attributes"]["group"] == "genre"
                    ),
                    "tags": [
                        t["attributes"]["name"].get("en", "")
                        for t in attr.get("tags", [])
                        if t["attributes"]["name"].get("en")
                    ],
                    "status": attr.get("status", ""),
                    "cover_url": cover_url,
                    "source": "mangadex",
                }
            )
        logger.info(f"MangaDex returned {len(results)} manga")
        return results
    except Exception as e:
        logger.error(f"MangaDex fetch failed: {e}")
        return []


def fetch_anilist_trending(per_page: int) -> list[dict]:
    query = """
    query ($perPage: Int) {
      Page(page: 1, perPage: $perPage) {
        media(type: MANGA, sort: TRENDING_DESC, isAdult: false) {
          id title { english romaji } genres trending popularity
        }
      }
    }"""
    try:
        resp = requests.post(
            ANILIST_URL,
            json={"query": query, "variables": {"perPage": per_page}},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json()["data"]["Page"]["media"]
        return [
            {
                "anilist_id": m["id"],
                "title": m["title"]["english"] or m["title"]["romaji"],
                "genre": ", ".join(m.get("genres", [])),
                "tags": m.get("genres", []),
                "trending": m.get("trending", 0),
                "source": "anilist",
            }
            for m in items
            if m["title"]["english"] or m["title"]["romaji"]
        ]
    except Exception as e:
        logger.error(f"AniList fetch failed: {e}")
        return []


def merge_and_score(mangadex: list[dict], anilist: list[dict]) -> list[dict]:
    """Merge both lists; normalise a trending_score 0-100."""
    combined: dict[str, dict] = {}

    for i, m in enumerate(mangadex):
        key = m["title"].lower()
        score = max(0.0, 100.0 - i * (100.0 / max(len(mangadex), 1)))
        combined[key] = {**m, "trending_score": round(score, 2)}

    for i, m in enumerate(anilist):
        key = m["title"].lower()
        bonus = max(0.0, 30.0 - i * (30.0 / max(len(anilist), 1)))
        if key in combined:
            combined[key]["trending_score"] = min(
                100.0, combined[key]["trending_score"] + bonus
            )
            combined[key]["anilist_id"] = m.get("anilist_id")
        else:
            combined[key] = {**m, "trending_score": round(bonus, 2)}

    return sorted(combined.values(), key=lambda x: x["trending_score"], reverse=True)


def upsert_to_db(manga_list: list[dict]) -> int:
    saved = 0
    for m in manga_list:
        try:
            db.execute(
                """
                INSERT INTO manga (title, mangadex_id, anilist_id, genre, tags, trending_score, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (title) DO UPDATE SET
                    mangadex_id    = COALESCE(EXCLUDED.mangadex_id, manga.mangadex_id),
                    anilist_id     = COALESCE(EXCLUDED.anilist_id,  manga.anilist_id),
                    trending_score = EXCLUDED.trending_score,
                    updated_at     = NOW()
                """,
                (
                    m["title"],
                    m.get("mangadex_id"),
                    m.get("anilist_id"),
                    m.get("genre", ""),
                    m.get("tags", []),
                    m["trending_score"],
                ),
            )
            saved += 1
        except Exception as e:
            logger.warning(f"Failed to upsert '{m['title']}': {e}")
    return saved


def main(limit: int = 20) -> list[dict]:
    logger.info(f"Fetching trending manga (limit={limit})")

    mangadex = fetch_mangadex_trending(limit)
    time.sleep(1)
    anilist = fetch_anilist_trending(min(limit, 50))

    merged = merge_and_score(mangadex, anilist)[:limit]
    saved = upsert_to_db(merged)
    logger.info(f"Upserted {saved}/{len(merged)} manga to DB")
    return merged


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    results = main(args.limit)
    print(json.dumps(results, ensure_ascii=False))
    sys.exit(0 if results else 1)
