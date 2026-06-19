"""
Skill: Publish Content
Triggers: "publish", "upload", "post to TikTok", "distribute", "push to YouTube"
Description: Publishes content via AiToEarn (MCP-based fanout to 12 platforms:
             TikTok, YouTube, Instagram, Facebook, Threads, Pinterest, Bilibili,
             Douyin, Kwai, Twitter) with local TikTok uploader as fallback.
Wraps: scripts/aitoearn_pipeline.py --stage publish
       scripts/adapters/aitoearn_client.py (MCP fanout — PRESERVED)
       scripts/upload_tiktok.py (local fallback)
"""
from __future__ import annotations

import os
from typing import Any

from . import TIMEOUT_PUBLISH
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """
    Publish content via AiToEarn-first routing with local fallback.

    The publish routing logic is PRESERVED from scripts/aitoearn_pipeline.py:
      1. If AiToEarn is enabled (AITOEARN_PRIMARY=true + API key set):
         → MCP fanout to all connected accounts across 12 platforms
         → Status polling to verify publishes
      2. Fallback: local TikTok uploader (TiktokAutoUploader v1)

    Args:
        args:
            video_url (str): Public URL of the video to publish
            video_id (int): Database video ID
            title (str): Video title/caption
            desc (str): Description
            hashtags (list[str]): Hashtags for the post
            topics (list[str]): Content topics
            channels (list[str]): Target platforms (tiktok, youtube, instagram, etc.)
            platform (str): Single platform override
            profile (str): "minimal" or "full" distribution profile
            mode (str): "light" or "full"
            selected_accounts (dict): platform → [account_ids] for targeted publishing
            account_ids (list[str]): Specific account IDs to use
            publish_time (str): UTC ISO timestamp for scheduled publish
            dry_run (bool): If true, plan only — don't actually publish
        agent_context: QwenPaw agent context

    Returns:
        {"success": True, "published_count": N, "failed_count": N,
         "channels": {"tiktok": {"success": N, "failed": N}, ...},
         "results": [{...per-platform result...}], "uploader": "aitoearn_mcp_fanout"}
    """
    import json

    dry_run = bool(args.get("dry_run", False))
    video_url = str(args.get("video_url") or args.get("videoUrl") or "")
    video_id = args.get("video_id")
    title = str(args.get("title") or args.get("caption") or "")
    desc = str(args.get("desc") or args.get("description") or title)
    profile = str(args.get("profile", "minimal") or "minimal")

    # Build the publish payload as JSON — passed via stdin to avoid shell escaping
    publish_body = {
        "video_url": video_url,
        "title": title,
        "desc": desc,
        "profile": profile,
        "mode": str(args.get("mode", "full") or "full"),
        "force_local": dry_run,
    }

    if video_id:
        publish_body["video_id"] = int(video_id)

    for key in ("channels", "hashtags", "topics", "selected_accounts",
                 "account_ids", "platform", "cover_url", "publish_time"):
        val = args.get(key)
        if val is not None:
            publish_body[key] = val

    # Pass publish body as environment variable (avoid shell quoting issues)
    extra_env = {}
    for key in os.environ:
        if key.startswith("AITOEARN_") or key in (
            "DATABASE_URL", "TIKTOK_EMAIL", "TIKTOK_PASSWORD",
            "YOUTUBE_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
            "YOUTUBE_REFRESH_TOKEN", "VIDEOS_DIR", "ARBITRAGE_VIDEOS_DIR",
            "USE_NEW_TIKTOK_UPLOADER", "MAX_UPLOADS_PER_ACCOUNT_DAY",
            "ANTHROPIC_API_KEY",
        ):
            extra_env[key] = os.environ[key]
    extra_env["AITOEARN_PUBLISH_BODY"] = json.dumps(publish_body)

    cmd = [
        "uv", "run", "python",
        "scripts/aitoearn_pipeline.py",
        "--stage", "publish",
    ]

    result = _run(cmd, timeout=TIMEOUT_PUBLISH, env=extra_env)
    return result
