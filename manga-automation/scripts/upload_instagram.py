#!/usr/bin/env python3
"""
Instagram Reels Uploader — uses instagrapi.

Uploads video to Instagram Reels using the unofficial mobile API.
Falls back to reporting the upload as "queued" if instagrapi is not installed.

Usage:
    python scripts/upload_instagram.py --video /path/to/video.mp4 --caption "..." --account user
"""
from __future__ import annotations

import json
import os
import sys
import argparse
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("upload_instagram")

# ─── Configuration ───────────────────────────────────────────────────────────
IG_SESSION_DIR = os.environ.get("IG_SESSION_DIR", "data/ig_sessions")
MAX_CAPTION_LEN = 2200


def _get_credentials(account: str) -> dict | None:
    """Fetch Instagram account credentials from DB."""
    return db.execute_one(
        """
        SELECT username, ig_user_id, access_token
        FROM instagram_accounts
        WHERE username = %s AND account_status = 'active'
        """,
        (account,),
    )


def _load_or_login(username: str, password: str | None = None):
    """
    Load saved session or perform fresh login.
    Returns an instagrapi Client instance.
    """
    from instagrapi import Client

    cl = Client()
    session_file = os.path.join(IG_SESSION_DIR, f"{username}.json")
    os.makedirs(IG_SESSION_DIR, exist_ok=True)

    # Try loading saved session
    if os.path.exists(session_file):
        try:
            cl.load_settings(session_file)
            cl.login(username, password or "")
            cl.get_timeline_feed()  # Verify session is valid
            logger.info(f"Loaded saved session for @{username}")
            return cl
        except Exception as e:
            logger.warning(f"Saved session invalid for @{username}: {e}")

    # Fresh login
    if not password:
        password = os.environ.get(f"IG_PASS_{username.upper()}")
    if not password:
        raise ValueError(f"No password for @{username}. Set IG_PASS_{username.upper()} in .env")

    cl.login(username, password)
    cl.dump_settings(session_file)
    logger.info(f"Fresh login for @{username}, session saved")
    return cl


def upload_reel(
    video_path: str,
    caption: str = "",
    account: str | None = None,
    hashtags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Upload a video as an Instagram Reel.
    Returns { success, platform_url, error }
    """
    if not video_path or not os.path.exists(video_path):
        return {"success": False, "error": f"Video not found: {video_path}", "platform": "instagram"}

    # Build caption
    if hashtags:
        tag_str = " ".join(f"#{t.lstrip('#')}" for t in hashtags[:30])
        caption = f"{caption}\n\n{tag_str}"
    caption = caption[:MAX_CAPTION_LEN]

    # Determine account
    if not account:
        account = os.environ.get("IG_DEFAULT_ACCOUNT")
    if not account:
        return {"success": False, "error": "No Instagram account specified", "platform": "instagram"}

    try:
        from instagrapi import Client
    except ImportError:
        logger.warning("instagrapi not installed — queuing upload for manual processing")
        return {
            "success": False,
            "error": "instagrapi not installed. Run: pip install instagrapi",
            "platform": "instagram",
            "status": "queued",
        }

    try:
        cl = _load_or_login(account)
        media = cl.clip_upload(video_path, caption)

        # Update DB
        db.execute(
            """
            UPDATE instagram_accounts
            SET last_post_at = NOW(), total_posts = total_posts + 1
            WHERE username = %s
            """,
            (account,),
        )

        return {
            "success": True,
            "platform": "instagram",
            "media_id": str(media.pk),
            "platform_url": f"https://www.instagram.com/reel/{media.code}/",
            "account": account,
        }
    except Exception as e:
        logger.error(f"Instagram upload failed for @{account}: {e}")
        return {"success": False, "error": str(e), "platform": "instagram", "account": account}


def main(body: dict | None = None, **kwargs) -> dict:
    """Entry point for worker.py integration."""
    if body is None:
        body = kwargs

    return upload_reel(
        video_path=body.get("video_path", ""),
        caption=body.get("caption", ""),
        account=body.get("account"),
        hashtags=body.get("hashtags"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram Reels Uploader")
    parser.add_argument("--video", type=str, required=True)
    parser.add_argument("--caption", type=str, default="")
    parser.add_argument("--account", type=str, default=None)
    parser.add_argument("--hashtags", type=str, default=None)
    args = parser.parse_args()

    hashtags = args.hashtags.split(",") if args.hashtags else None
    result = upload_reel(args.video, args.caption, args.account, hashtags)
    print(json.dumps(result, indent=2))
