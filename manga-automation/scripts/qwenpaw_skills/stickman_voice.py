"""Skill: Stickman voiceover — DeepSeek clean narration + TTS (tutorial step 5)."""
from __future__ import annotations

from typing import Any

from ._stickman_flow import run_flow_body


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stage": "voice",
        "render": False,
        "voice": True,
        "optimize_audio": args.get("optimize_audio", True),
    }
    for key in (
        "scenes",
        "narration_text",
        "job_id",
        "assets_dir",
        "voice_id",
        "provider",
        "skip_clean_narration",
        "voiceover_path",
    ):
        if key in args and args[key] is not None:
            body[key] = args[key]

    if args.get("scenes"):
        body["stages"] = ["voice"]
        body.pop("stage", None)
        body["script_result"] = {"success": True, "scenes": args["scenes"]}
        from scripts.stickman_flow_pipeline import (
            _job_dir,
            stage_animate_plan,
            stage_clean_narration,
            stage_voice_flow,
        )

        animate = stage_animate_plan(body, {"scenes": args["scenes"]})
        clean = stage_clean_narration(animate.get("scenes") or [], body)
        if not clean.get("success"):
            return {
                "success": False,
                "error": clean.get("error"),
                "agent_id": agent_context.get("agent_id"),
            }
        voice = stage_voice_flow(body, clean["narration"])
        job = _job_dir(body)
        return {
            "success": bool(voice.get("success")),
            "pipeline": "stickman_flow",
            "job_id": job.name,
            "narration": clean.get("narration"),
            "voiceover_path": voice.get("output_path"),
            "stages": {"narration": clean, "voice": voice, "animate": animate},
            "agent_id": agent_context.get("agent_id", "stickman-voice"),
            "error": voice.get("error"),
        }

    payload = run_flow_body(body)
    return {
        **payload,
        "success": bool(payload.get("success", False)),
        "agent_id": agent_context.get("agent_id", "stickman-voice"),
    }
