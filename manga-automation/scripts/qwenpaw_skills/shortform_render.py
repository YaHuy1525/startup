"""Skill: Remotion MemeStory render for short-form Reddit videos."""
from __future__ import annotations

from typing import Any

from scripts import shortform_pipeline


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    payload = shortform_pipeline.stage_render(args)
    return {**payload, "success": bool(payload.get("ok")), "agent_id": agent_context.get("agent_id")}
