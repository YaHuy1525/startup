"""
SHA-256 image hashing for duplicate panel detection.
"""
import hashlib
from pathlib import Path
from typing import Tuple

from scripts.utils import database as db


def hash_image(image_path: str) -> str:
    """Generate SHA-256 hash of raw image bytes."""
    with open(image_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_and_register(
    image_path: str,
    manga_id: int,
    chapter_id: int,
    panel_index: int,
    max_uses: int = 5,
) -> Tuple[bool, int]:
    """
    Check if a panel image is a duplicate (used >= max_uses times).

    Returns:
        (is_duplicate, current_use_count)
        If not a duplicate, registers/increments the hash in DB.
    """
    panel_hash = hash_image(image_path)

    row = db.execute_one(
        "SELECT times_used FROM panel_hashes WHERE panel_hash = %s",
        (panel_hash,),
    )

    current_uses = row["times_used"] if row else 0

    if current_uses >= max_uses:
        return True, current_uses

    db.execute(
        """
        INSERT INTO panel_hashes (panel_hash, manga_id, chapter_id, panel_index, first_used_at, times_used)
        VALUES (%s, %s, %s, %s, NOW(), 1)
        ON CONFLICT (panel_hash) DO UPDATE
            SET times_used = panel_hashes.times_used + 1
        """,
        (panel_hash, manga_id, chapter_id, panel_index),
    )

    return False, current_uses + 1
