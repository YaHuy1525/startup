#!/usr/bin/env python3
"""
Pinterest Video Pin Uploader — uses Pinterest API v5.

Implements the 4-step video upload flow:
  1. Register media → get upload_url + upload_parameters
  2. Upload video to AWS (multipart/form-data)
  3. Poll for processing completion
  4. Create Pin with the media_id

Usage:
    python scripts/upload_pinterest.py --video /path/to/video.mp4 --title "..."
"""
from __future__ import annotations

import json
import os
import sys
import time
import argparse
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("upload_pinterest")

# ─── Configuration ───────────────────────────────────────────────────────────
PINTEREST_ACCESS_TOKEN = os.environ.get("PINTEREST_ACCESS_TOKEN")
PINTEREST_BOARD_ID = os.environ.get("PINTEREST_BOARD_ID")
PINTEREST_API = "https://api.pinterest.com/v5"
MAX_POLL_ATTEMPTS = 12  # 12 x 10s = 2 min max
POLL_INTERVAL = 10


def _headers():
    return {
        "Authorization": f"Bearer {PINTEREST_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def register_media() -> dict | None:
    """Step 1: Register media upload intent."""
    resp = requests.post(
        f"{PINTEREST_API}/media",
        headers=_headers(),
        json={"media_type": "video"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info(f"Media registered: media_id={data.get('media_id')}")
    return data


def upload_to_aws(upload_url: str, upload_parameters: dict, video_path: str) -> bool:
    """Step 2: Upload video file to AWS using parameters from Step 1."""
    with open(video_path, "rb") as f:
        files = {"file": (os.path.basename(video_path), f, "video/mp4")}
        resp = requests.post(
            upload_url,
            data=upload_parameters,
            files=files,
            timeout=120,
        )
    success = resp.status_code == 204
    if success:
        logger.info("Video uploaded to AWS successfully")
    else:
        logger.error(f"AWS upload failed: {resp.status_code} {resp.text[:200]}")
    return success


def poll_media_status(media_id: str) -> str:
    """Step 3: Poll until video processing is complete."""
    for attempt in range(MAX_POLL_ATTEMPTS):
        resp = requests.get(
            f"{PINTEREST_API}/media/{media_id}",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        status = resp.json().get("status", "")
        logger.info(f"Media {media_id} status: {status} (attempt {attempt + 1})")

        if status == "succeeded":
            return "succeeded"
        elif status in ("failed", "error"):
            return "failed"

        time.sleep(POLL_INTERVAL)

    return "timeout"


def create_pin(
    media_id: str,
    board_id: str,
    title: str = "",
    description: str = "",
    link: str = "",
) -> dict:
    """Step 4: Create the actual Pin with the processed media."""
    payload = {
        "board_id": board_id,
        "media_source": {
            "source_type": "video_id",
            "media_id": media_id,
        },
    }
    if title:
        payload["title"] = title[:100]
    if description:
        payload["description"] = description[:500]
    if link:
        payload["link"] = link

    resp = requests.post(
        f"{PINTEREST_API}/pins",
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def upload_video_pin(
    video_path: str,
    title: str = "",
    description: str = "",
    board_id: str | None = None,
    link: str = "",
) -> dict[str, Any]:
    """
    Full 4-step Pinterest video pin upload.
    Returns { success, pin_id, pin_url, error }
    """
    if not PINTEREST_ACCESS_TOKEN:
        return {"success": False, "error": "PINTEREST_ACCESS_TOKEN not set", "platform": "pinterest"}

    target_board = board_id or PINTEREST_BOARD_ID
    if not target_board:
        return {"success": False, "error": "PINTEREST_BOARD_ID not set", "platform": "pinterest"}

    if not video_path or not os.path.exists(video_path):
        return {"success": False, "error": f"Video not found: {video_path}", "platform": "pinterest"}

    try:
        # Step 1: Register
        media_data = register_media()
        if not media_data:
            return {"success": False, "error": "Media registration failed", "platform": "pinterest"}

        media_id = media_data["media_id"]
        upload_url = media_data["upload_url"]
        upload_params = media_data.get("upload_parameters", {})

        # Step 2: Upload to AWS
        if not upload_to_aws(upload_url, upload_params, video_path):
            return {"success": False, "error": "AWS upload failed", "platform": "pinterest"}

        # Step 3: Poll
        status = poll_media_status(media_id)
        if status != "succeeded":
            return {"success": False, "error": f"Media processing {status}", "platform": "pinterest"}

        # Step 4: Create Pin
        pin = create_pin(media_id, target_board, title, description, link)
        pin_id = pin.get("id")

        logger.info(f"Pin created: {pin_id}")
        return {
            "success": True,
            "platform": "pinterest",
            "pin_id": pin_id,
            "pin_url": f"https://www.pinterest.com/pin/{pin_id}/",
        }

    except Exception as e:
        logger.error(f"Pinterest upload failed: {e}")
        return {"success": False, "error": str(e), "platform": "pinterest"}


def main(body: dict | None = None, **kwargs) -> dict:
    """Entry point for worker.py integration."""
    if body is None:
        body = kwargs
    return upload_video_pin(
        video_path=body.get("video_path", ""),
        title=body.get("title", ""),
        description=body.get("description", ""),
        board_id=body.get("board_id"),
        link=body.get("link", ""),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pinterest Video Pin Uploader")
    parser.add_argument("--video", type=str, required=True)
    parser.add_argument("--title", type=str, default="")
    parser.add_argument("--description", type=str, default="")
    parser.add_argument("--board-id", type=str, default=None)
    args = parser.parse_args()

    result = upload_video_pin(args.video, args.title, args.description, args.board_id)
    print(json.dumps(result, indent=2))
