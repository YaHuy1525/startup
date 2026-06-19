"""
Skill: Content Sourcing
Triggers: "source content", "find videos", "harvest content", "download videos"
Description: Finds matching YouTube videos for trending concepts, checks for duplicates,
             downloads high-quality assets to /data/arbitrage_videos/.
Wraps: scripts/arbitrage_worker.py
       scripts/source_youtube_assets.py
       scripts/check_duplicates.py
"""
from __future__ import annotations

import os
from typing import Any

from . import TIMEOUT_SOURCE
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """
    Source content assets for given concepts.

    Args:
        args:
            concepts (list[dict]): Trending concepts from trend_discovery
                [{"concept": "...", "hashtag": "...", "confidence": 0.8}, ...]
            count (int): Max assets to source (default 5)
            youtube_channel_id (str): Optional specific channel to source from
        agent_context: QwenPaw agent context

    Returns:
        {"success": True, "assets_queued": N, "urls": [...], "local_paths": [...]}
    """
    count = int(args.get("count", 5))
    channel_id = str(args.get("youtube_channel_id", "") or "")

    # Call the arbitrage worker which handles sourcing + download
    cmd = [
        "uv", "run", "python",
        "scripts/arbitrage_worker.py",
        "--batch", str(count),
    ]
    if channel_id:
        cmd.extend(["--channel-id", channel_id])

    extra_env = {}
    for key in ("YOUTUBE_API_KEY", "DATABASE_URL", "CHROMADB_URL",
                 "ARBITRAGE_VIDEOS_DIR"):
        if key in os.environ:
            extra_env[key] = os.environ[key]

    result = _run(cmd, timeout=TIMEOUT_SOURCE, env=extra_env)
    return result
