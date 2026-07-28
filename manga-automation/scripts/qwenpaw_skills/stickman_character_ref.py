"""Skill: Stickman character reference (tutorial step 1)."""
from __future__ import annotations

from typing import Any

from ._stickman_flow import run_flow_body


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {"stage": "character_ref", "render": False, "voice": False}
    for key in ("character_ref_url", "character_ref_path", "character_ref", "job_id", "assets_dir"):
        if key in args and args[key] is not None:
            body[key] = args[key]
    payload = run_flow_body(body)
    return {
        **payload,
        "success": bool(payload.get("success", False)),
        "agent_id": agent_context.get("agent_id", "stickman-character-ref"),
    }
