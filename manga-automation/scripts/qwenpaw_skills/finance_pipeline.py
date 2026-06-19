"""
Skill: Finance Pipeline
Triggers: "finance video", "earnings proof", "brainrot video", "money content",
          "side hustle video", "mini money matters"
Description: Runs the full finance/side-hustle content pipeline:
             1. Scan earnings screenshots → index payouts
             2. Generate AI video (Revid/Creatify/HeyGen brainrot style)
             3. Publish via AiToEarn to TikTok, YouTube, Instagram, Threads, Pinterest
             4. Report results
Wraps: scripts/finance_video_ai.py (Revid AI video generation)
       scripts/finance_video_generator.py (orchestrator)
       scripts/earnings_proof_ingest.py (screenshot scanning)
"""
from __future__ import annotations

import os
from typing import Any

from . import TIMEOUT_FINANCE
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """
    Run the finance video pipeline.

    Args:
        args:
            provider (str): "revid" | "creatify" | "heygen" (default "revid")
            background (str): "subway_surfers" | "minecraft" | "temple_run" | "gta"
            week_iso (str): ISO week e.g. "2026-W23" (default: current week)
            profile (str): Distribution profile "minimal" | "full"
            channels (list[str]): Target platforms
            title (str): Custom video title
            execute (bool): Must be True to actually run (safety guardrail)
        agent_context: QwenPaw agent context

    Returns:
        {"success": True, "pipeline": "finance_video_pipeline",
         "steps": [{...per-step results...}], "video_url": "..."}
    """
    provider = str(args.get("provider", "revid") or "revid")
    background = str(args.get("background", "subway_surfers") or "subway_surfers")
    execute_flag = bool(args.get("execute", False))

    if not execute_flag:
        return {
            "success": True,
            "dry_run": True,
            "planned_actions": [
                "Scan earnings screenshots for new payouts",
                f"Generate {provider} brainrot video (bg={background})",
                "Publish via AiToEarn to TikTok, YouTube, Instagram",
                "Report results with links",
            ],
            "hint": "Set execute=True to run the pipeline",
        }

    cmd = [
        "uv", "run", "python",
        "scripts/hermes_agent.py",
        "--pipeline", "finance",
        "--provider", provider,
        "--background", background,
    ]

    week_iso = str(args.get("week_iso", "") or "")
    if week_iso:
        cmd.extend(["--week-iso", week_iso])

    extra_env = {}
    for key in os.environ:
        if key.startswith(("AITOEARN_", "REVID_", "CREATIFY_", "HEYGEN_",
                           "INVIDEO_", "FINANCE_", "YOUTUBE_", "EARNINGS_")):
            extra_env[key] = os.environ[key]
    extra_env["HERMES_AUTO_ACTIONS"] = "1"

    result = _run(cmd, timeout=TIMEOUT_FINANCE, env=extra_env)
    return result
