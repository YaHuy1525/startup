"""Skill: Stickman scriptwriter via DeepSeek (topics + per-scene prompts)."""
from __future__ import annotations

from typing import Any

from ._stickman_flow import run_flow_body


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stages": ["topics", "script"],
        "render": False,
        "voice": False,
        "duration_secs": args.get("duration_secs") or args.get("duration") or 60,
        "auto_pick_topic": args.get("auto_pick_topic", False),
    }
    for key in (
        "topic_hint",
        "niche",
        "topic",
        "topics",
        "scenes",
        "job_id",
        "clip_secs",
    ):
        if key in args and args[key] is not None:
            body[key] = args[key]

    # If only topics requested
    if args.get("topics_only"):
        body["stages"] = ["topics"]

    payload = run_flow_body(body)
    return {
        **payload,
        "success": bool(payload.get("success", False)),
        "agent_id": agent_context.get("agent_id", "stickman-scriptwriter"),
    }
