#!/usr/bin/env python3
"""
Check local panel images for duplicates using SHA-256 hashing.
Filters out panels already used >= DUPLICATE_MAX_USES times.

Usage:
    python3 scripts/check_duplicates.py --chapter-id <db_chapter_id>

Output:
    JSON with list of unique panel paths that pass the dedup check.
    Exit 0 on success, 1 on failure.
"""
import sys
import json
import argparse
import os
from dotenv import load_dotenv

load_dotenv()

from scripts.utils import database as db
from scripts.utils.image_hash import check_and_register
from scripts.utils.logger import setup_logger

logger = setup_logger("check_duplicates")

MAX_USES = int(os.environ.get("DUPLICATE_MAX_USES", 5))


def main(chapter_id: int) -> dict:
    row = db.execute_one(
        """
        SELECT mc.id, mc.manga_id, mc.local_paths
        FROM manga_chapters mc
        WHERE mc.id = %s
        """,
        (chapter_id,),
    )
    if not row:
        logger.error(f"Chapter id={chapter_id} not found")
        return {}

    local_paths: list[str] = (
        json.loads(row["local_paths"])
        if isinstance(row["local_paths"], str)
        else (row["local_paths"] or [])
    )

    if not local_paths:
        logger.warning("No local panel paths found for chapter")
        return {"unique": [], "duplicates": [], "total": 0}

    unique_paths = []
    duplicate_paths = []

    for i, path in enumerate(local_paths):
        if not os.path.exists(path):
            logger.warning(f"Panel file not found: {path}")
            continue

        is_dup, uses = check_and_register(
            image_path=path,
            manga_id=row["manga_id"],
            chapter_id=chapter_id,
            panel_index=i,
            max_uses=MAX_USES,
        )

        if is_dup:
            logger.info(f"Panel {i+1} is duplicate (used {uses} times), skipping")
            duplicate_paths.append(path)
        else:
            unique_paths.append(path)

    logger.info(
        f"Dedup: {len(unique_paths)} unique, {len(duplicate_paths)} duplicates "
        f"out of {len(local_paths)} panels"
    )

    return {
        "chapter_id": chapter_id,
        "total": len(local_paths),
        "unique": unique_paths,
        "duplicates": duplicate_paths,
        "unique_count": len(unique_paths),
        "duplicate_count": len(duplicate_paths),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter-id", type=int, required=True)
    args = parser.parse_args()

    result = main(args.chapter_id)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result else 1)
