"""
Skill: Account Health Check
Triggers: "check accounts", "account health", "shadow ban status", "FYP ratio"
Description: Checks TikTok account health — FYP ratio, shadow-ban flags,
             upload history, view averages. Flags accounts needing attention.
Wraps: scripts/detect_shadow_ban.py
       scripts/fetch_tiktok_stats.py
"""
from __future__ import annotations

import os
from typing import Any

from . import TIMEOUT_REPORT
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """
    Check health of all or specific TikTok accounts.

    Args:
        args:
            account (str): Specific account username to check (default: all)
            threshold (float): FYP ratio threshold for shadow-ban flag (default 0.10)
        agent_context: QwenPaw agent context

    Returns:
        {"success": True, "accounts": [{"username": ..., "fyp_ratio": ...,
         "shadow_ban_risk": ..., "status": "healthy"|"warning"|"critical"}, ...]}
    """
    threshold = float(args.get("threshold", 0.10))

    cmd = [
        "uv", "run", "python",
        "scripts/detect_shadow_ban.py",
    ]
    account = str(args.get("account", "") or "")
    if account:
        cmd.extend(["--account", account])

    extra_env = {}
    for key in ("DATABASE_URL", "TIKTOK_EMAIL", "TIKTOK_PASSWORD",
                 "SHADOW_BAN_FYP_THRESHOLD", "APIFY_API"):
        if key in os.environ:
            extra_env[key] = os.environ[key]
    extra_env.setdefault("SHADOW_BAN_FYP_THRESHOLD", str(threshold))

    result = _run(cmd, timeout=TIMEOUT_REPORT, env=extra_env)
    return result
