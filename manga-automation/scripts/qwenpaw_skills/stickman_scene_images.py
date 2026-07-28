"""Skill: Stickman scene stills (tutorial step 3)."""
from __future__ import annotations

from typing import Any

from ._stickman_flow import run_flow_body


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stage": "scene_images",
        "render": False,
        "voice": False,
    }
    for key in (
        "scenes",
        "script_result",
        "character_ref_result",
        "character_ref_path",
        "character_ref_url",
        "job_id",
        "assets_dir",
        "topic",
        "duration_secs",
    ):
        if key in args and args[key] is not None:
            body[key] = args[key]

    # Need script scenes: if only scenes list passed, wrap for script_result skip path
    if args.get("scenes") and not args.get("script_result"):
        body["scenes"] = args["scenes"]
        body["stages"] = ["scene_images"]
        body.pop("stage", None)
        # Provide minimal script_result so animate path has scenes after images
        body["script_result"] = {"success": True, "scenes": args["scenes"]}

    payload = run_flow_body(body)
    return {
        **payload,
        "success": bool(payload.get("success", False)),
        "agent_id": agent_context.get("agent_id", "stickman-scene-artist"),
    }
