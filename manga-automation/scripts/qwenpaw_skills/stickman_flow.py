"""
Skill: Stickman Flow orchestrator (DeepSeek + Remotion)
Triggers: "stickman flow", "deepseek stickman", "remotion stickman", "full stickman pipeline"
Wraps: scripts/stickman_flow_pipeline.py
"""
from __future__ import annotations

from typing import Any

from ._stickman_flow import run_flow_body


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "duration_secs": args.get("duration_secs") or args.get("duration") or 60,
        "auto_pick_topic": args.get("auto_pick_topic", True),
        "render": bool(args.get("render", False)),
        "voice": args.get("voice", True),
        "optimize_audio": args.get("optimize_audio", True),
    }
    for key in (
        "topic_hint",
        "niche",
        "topic",
        "topics",
        "scenes",
        "character_ref_url",
        "character_ref_path",
        "character_ref",
        "job_id",
        "assets_dir",
        "stages",
        "stage",
        "voice_id",
        "provider",
        "filename",
        "title",
        "titleText",
        "narration_text",
        "voiceover_path",
        "audio_path",
        "clip_secs",
        "aspect",
        "paper_background_opacity",
        "skip_clean_narration",
    ):
        if key in args and args[key] is not None:
            body[key] = args[key]

    payload = run_flow_body(body)
    return {
        **payload,
        "success": bool(payload.get("success", payload.get("ok", False))),
        "agent_id": agent_context.get("agent_id", "stickman-director"),
    }
