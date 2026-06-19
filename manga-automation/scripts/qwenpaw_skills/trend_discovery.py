"""
Skill: Trend Discovery
Triggers: "find trends", "what's trending", "trend discovery", "trending topics"
Description: Queries TikTok, Reddit, YouTube, and X/Twitter for trending topics
             across all genesis_categories. Returns ranked list with viral_potential scores.
Wraps: scripts/aitoearn_pipeline.py --stage trend
       scripts/fetch_tiktok_trends_apify.py
       scripts/fetch_twitter_trends.py
       scripts/fetch_youtube_trends.py
       scripts/fetch_reddit_trends.py
"""
from __future__ import annotations

from typing import Any

from . import TIMEOUT_TREND
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """
    Run trend discovery across all or a specific category.

    Args:
        args:
            category (str): Target category slug ("" = all categories)
            count (int): Max trends to return (default 20)
            platforms (list[str]): Platforms to query (default all: tiktok,twitter,youtube,reddit)
        agent_context: QwenPaw agent context (agent_id, workspace_path, etc.)

    Returns:
        {"success": True, "total_trends": N, "fetchers": {...}, "timestamp": "..."}
    """
    category = str(args.get("category", "") or "")
    count = int(args.get("count", 20))

    cmd = [
        "uv", "run", "python",
        "scripts/aitoearn_pipeline.py",
        "--stage", "trend",
        "--category", category,
    ]

    # Merge AiToEarn env vars from agent_context if present
    extra_env = {}
    for key in ("AITOEARN_PRIMARY", "AITOEARN_API_KEY", "AITOEARN_BASE_URL",
                 "AITOEARN_MCP_URL", "DATABASE_URL"):
        if key in os.environ:
            extra_env[key] = os.environ[key]

    result = _run(cmd, timeout=TIMEOUT_TREND, env=extra_env)
    return result


import os  # noqa: E402 (used at top but referenced here for clarity)
