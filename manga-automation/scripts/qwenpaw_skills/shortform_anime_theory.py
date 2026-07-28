"""Skill: Anime theory Short — full E2E or render-only."""
from __future__ import annotations

from typing import Any

from scripts import shortform_pipeline


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """Run anime-theory pipeline.

    Default: full E2E (script → Remotion → caption → thumb → AiToEarn).
    Pass ``pipeline:false`` or ``render_only:true`` for render stage only.
    Pass ``publish:false`` to generate MP4 without posting.
    """
    render_only = bool(
        args.get("render_only")
        or args.get("renderOnly")
        or (args.get("pipeline") is False)
        or str(args.get("pipeline") or "").strip().lower() in {"false", "0", "no"}
    )
    if render_only:
        payload = shortform_pipeline.stage_anime_theory(args)
    else:
        # Full pipeline defaults publish=True unless caller overrides
        payload = shortform_pipeline.run_anime_theory_pipeline(args)
    return {
        **payload,
        "success": bool(payload.get("ok") or payload.get("success")),
        "agent_id": agent_context.get("agent_id"),
    }
