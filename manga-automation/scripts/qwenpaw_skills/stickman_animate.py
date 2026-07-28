"""Skill: Stickman Remotion motion plan from video_prompt (tutorial step 4)."""
from __future__ import annotations

from typing import Any

from ._stickman_flow import run_flow_body


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stage": "animate",
        "render": False,
        "voice": False,
    }
    for key in ("scenes", "job_id", "assets_dir"):
        if key in args and args[key] is not None:
            body[key] = args[key]

    if args.get("scenes"):
        # Bypass image stage: feed scenes into animate via images_result path
        # Orchestrator uses body scenes when animate-only — set script_result + skip images
        body["stages"] = ["animate"]
        body.pop("stage", None)
        # Inject as if images already done
        from scripts.stickman_flow_pipeline import stage_animate_plan

        animate = stage_animate_plan(body, {"scenes": args["scenes"]})
        return {
            "success": bool(animate.get("success")),
            "pipeline": "stickman_flow",
            "stages": {"animate": animate},
            "scenes": animate.get("scenes"),
            "agent_id": agent_context.get("agent_id", "stickman-animator"),
        }

    payload = run_flow_body(body)
    return {
        **payload,
        "success": bool(payload.get("success", False)),
        "agent_id": agent_context.get("agent_id", "stickman-animator"),
    }
