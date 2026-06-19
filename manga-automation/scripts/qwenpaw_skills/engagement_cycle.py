"""
Skill: Engagement Cycle
Triggers: "run engagement", "auto-engage", "like and comment", "boost reach"
Description: Runs automated engagement across platforms — AI-powered commenting,
             auto-like, auto-follow, comment mining for signals.
Wraps: scripts/engage/engine.py (orchestrator with light/medium/full modes)
       scripts/engage/browser.py (Playwright stealth browser)
       scripts/engage/commenter.py (AI comment generation)
       scripts/engage/liker.py (auto-like)
       scripts/engage/follower.py (auto-follow)
       scripts/engage/comment_miner.py (signal detection)
       scripts/engage/brand_monitor.py (mention tracking)
"""
from __future__ import annotations

import os
from typing import Any

from . import TIMEOUT_ENGAGE
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """
    Run automated engagement on recently published content.

    Args:
        args:
            platform (str): Target platform (default "tiktok")
            mode (str): "light" | "medium" | "full" (default "light")
            max_likes (int): Max likes to perform
            max_follows (int): Max follows to perform
            target_niche (str): Niche/hashtag to target for engagement
            dry_run (bool): If true, simulate only
        agent_context: QwenPaw agent context

    Returns:
        {"success": True, "actions_taken": N, "platforms_engaged": [...],
         "signals_found": N, "details": {...}}
    """
    platform = str(args.get("platform", "tiktok") or "tiktok")
    mode = str(args.get("mode", "light") or "light")

    cmd = [
        "uv", "run", "python",
        "-c",
        f"from scripts.engage.engine import run_engage_cycle; "
        f"import json; "
        f"result = run_engage_cycle(platform='{platform}', mode='{mode}'); "
        f"print(json.dumps(result, default=str))",
    ]

    extra_env = {}
    for key in ("DATABASE_URL", "ENGAGE_HEADLESS", "ENGAGE_MAX_LIKES",
                 "ENGAGE_MAX_FOLLOWS", "ENGAGE_PROXY_URL", "ENGAGE_AI_MODEL",
                 "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
        if key in os.environ:
            extra_env[key] = os.environ[key]

    result = _run(cmd, timeout=TIMEOUT_ENGAGE, env=extra_env)
    return result
