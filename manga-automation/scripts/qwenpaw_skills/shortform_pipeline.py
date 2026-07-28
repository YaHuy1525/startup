"""
Skill: Shortform Pipeline (Reddit → meme video → AiToEarn)
Triggers: "reddit meme video", "shortform pipeline", "reddit to shorts", "meme story video"
Wraps: scripts/shortform_pipeline.py
"""
from __future__ import annotations

from typing import Any

from scripts import shortform_pipeline


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body = {
        "stage": args.get("stage") or "pipeline",
        "subreddit": args.get("subreddit") or "tifu",
        "time": args.get("time") or args.get("time_filter") or "week",
        "count": args.get("count") or 1,
        "style": args.get("style") or "meme",
        "dry_run": bool(args.get("dry_run", False)),
        "publish": bool(args.get("publish", False)),
    }
    for key in (
        "story",
        "scenes",
        "file",
        "local_path",
        "video_path",
        "title",
        "desc",
        "caption",
        "channels",
        "hashtags",
        "topics",
        "selected_accounts",
        "account_ids",
        "filename",
        "skip_buffer",
        "publish_time",
        "profile",
        "mode",
    ):
        if key in args and args[key] is not None:
            body[key] = args[key]

    payload = shortform_pipeline.main(body)
    return {
        **payload,
        "success": bool(payload.get("ok", False)),
        "agent_id": agent_context.get("agent_id", "shortform-director"),
    }
