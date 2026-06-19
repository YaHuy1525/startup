"""
Skill: Content Plan / Brief Generator
Triggers: "plan content", "content brief", "what should I post", "content strategy",
          "generate briefs", "content calendar"
Description: Generates content plans and briefs based on trending topics.
             Uses genesis_discover for ideation and genesis_brief_generator
             for detailed content briefs with platform-specific instructions.
Wraps: scripts/genesis_discover.py (content ideation)
       scripts/genesis_brief_generator.py (detailed briefs)
"""
from __future__ import annotations

import os
from typing import Any

from . import TIMEOUT_TREND
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """
    Generate content plans and briefs.

    Args:
        args:
            category (str): Category slug (default: discovers best)
            count (int): Number of briefs to generate (default 5)
            mode (str): "discover" | "brief" | "both" (default "both")
            platforms (list[str]): Target platforms for distribution
        agent_context: QwenPaw agent context

    Returns:
        {"success": True, "briefs": [...], "category": "...", "count": N}
    """
    mode = str(args.get("mode", "both") or "both")
    category = str(args.get("category", "") or "")
    count = int(args.get("count", 5))

    extra_env = {}
    for key in ("DATABASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
                 "TREND_PLANNER_LIMIT", "TREND_MIN_CONFIDENCE"):
        if key in os.environ:
            extra_env[key] = os.environ[key]

    if mode in ("discover", "both"):
        cmd = [
            "uv", "run", "python",
            "scripts/genesis_discover.py",
            "--limit", str(count),
        ]
        if category:
            cmd.extend(["--category", category])
        result = _run(cmd, timeout=TIMEOUT_TREND, env=extra_env)
        return result

    if mode == "brief":
        cmd = [
            "uv", "run", "python",
            "scripts/genesis_brief_generator.py",
            "--limit", str(count),
        ]
        if category:
            cmd.extend(["--category", category])
        result = _run(cmd, timeout=TIMEOUT_TREND, env=extra_env)
        return result

    return {"success": True, "mode": mode, "count": count}
