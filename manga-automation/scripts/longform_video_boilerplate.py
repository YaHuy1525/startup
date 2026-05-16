#!/usr/bin/env python3
"""
Pod 2 — Long-form video pipeline (authority engine) — BOILERPLATE.

Planned integration points (implement when API keys exist):
  - B-roll generation: KLING_AI_API_KEY or env per vendor
  - Assembly: reuse existing FFmpeg/moviepy stack in repo
  - Ken Burns stills: parameterized pan/zoom presets

This module records the contract omnichannel/worker can call later.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils.logger import setup_logger

logger = setup_logger("longform_video")

KLING_API_KEY = os.environ.get("KLING_API_KEY", "")
RUNWAY_API_KEY = os.environ.get("RUNWAY_API_KEY", "")
PIKA_API_KEY = os.environ.get("PIKA_API_KEY", "")


def queue_longform_job(
    brief_id: int,
    *,
    target_duration_sec: int = 600,
    style: str = "documentary",
) -> dict[str, Any]:
    """
    Placeholder queue step — persist job row or enqueue to Temporal/Celery when added.
    """
    if not any((KLING_API_KEY, RUNWAY_API_KEY, PIKA_API_KEY)):
        logger.warning("No cinematic API key configured — returning dry plan only")
    return {
        "ok": True,
        "brief_id": brief_id,
        "target_duration_sec": target_duration_sec,
        "style": style,
        "status": "planned",
        "note": (
            "Wire generate_video.py / FFmpeg after choosing a vendor; "
            "store outputs in master_assets.base_video_path"
        ),
        "configured_providers": [
            name
            for name, key in (
                ("kling", KLING_API_KEY),
                ("runway", RUNWAY_API_KEY),
                ("pika", PIKA_API_KEY),
            )
            if key
        ],
    }


def main(body: dict | None = None, **kwargs) -> dict[str, Any]:
    if body is None:
        body = kwargs
    brief_id = body.get("brief_id")
    if not brief_id:
        return {"ok": False, "error": "brief_id required"}
    return queue_longform_job(
        int(brief_id),
        target_duration_sec=int(body.get("target_duration_sec", 600)),
        style=str(body.get("style", "documentary")),
    )


if __name__ == "__main__":
    print(json.dumps(main({"brief_id": 1}), indent=2))
