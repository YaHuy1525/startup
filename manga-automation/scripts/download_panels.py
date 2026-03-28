#!/usr/bin/env python3
"""
Download manga panel images locally for a given chapter.

Usage:
    python3 scripts/download_panels.py --chapter-id <db_chapter_id>

Output:
    JSON with local file paths.
    Exit 0 on success, 1 on failure.
"""
import sys
import json
import argparse
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import requests
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("download_panels")

PANELS_DIR = os.environ.get("PANELS_DIR", "data/panels")
HEADERS = {"User-Agent": "Mozilla/5.0 MangaBot/1.0"}


def sanitise(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def download_image(url: str, dest: Path, retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                url,
                headers={**HEADERS, "Referer": url.split("/", 3)[:3].__add__([""])[2] + "/"},
                timeout=20,
                stream=True,
            )
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            logger.warning(f"Attempt {attempt} failed for {url}: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return False


def main(chapter_id: int) -> dict:
    row = db.execute_one(
        """
        SELECT mc.id, mc.chapter_number, mc.panel_urls, m.title
        FROM manga_chapters mc
        JOIN manga m ON mc.manga_id = m.id
        WHERE mc.id = %s
        """,
        (chapter_id,),
    )
    if not row:
        logger.error(f"Chapter id={chapter_id} not found in DB")
        return {}

    panel_urls: list[str] = (
        json.loads(row["panel_urls"])
        if isinstance(row["panel_urls"], str)
        else (row["panel_urls"] or [])
    )
    if not panel_urls:
        logger.warning("No panel URLs found for chapter")
        return {}

    safe_title = sanitise(row["title"])
    safe_chapter = sanitise(row["chapter_number"])
    chapter_dir = Path(PANELS_DIR) / safe_title / f"ch_{safe_chapter}"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    local_paths = []
    for i, url in enumerate(panel_urls):
        ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        filename = f"panel_{i+1:03d}.{ext}"
        dest = chapter_dir / filename

        if dest.exists():
            logger.info(f"Panel {i+1} already downloaded, skipping")
            local_paths.append(str(dest))
            continue

        ok = download_image(url, dest)
        if ok:
            local_paths.append(str(dest))
            logger.info(f"Downloaded panel {i+1}/{len(panel_urls)}")
        else:
            logger.error(f"Failed to download panel {i+1}: {url}")

        time.sleep(0.3)

    db.execute(
        "UPDATE manga_chapters SET local_paths = %s WHERE id = %s",
        (json.dumps(local_paths), chapter_id),
    )
    logger.info(f"Downloaded {len(local_paths)}/{len(panel_urls)} panels to {chapter_dir}")

    return {
        "chapter_id": chapter_id,
        "downloaded": len(local_paths),
        "total": len(panel_urls),
        "local_paths": local_paths,
        "chapter_dir": str(chapter_dir),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter-id", type=int, required=True)
    args = parser.parse_args()

    result = main(args.chapter_id)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result else 1)
