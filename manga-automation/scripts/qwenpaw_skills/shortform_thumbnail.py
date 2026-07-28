"""Skill: Propose anime-theory thumbnails using Hermes thumbnail style memory."""
from __future__ import annotations

import os
import sys
from typing import Any

_scripts = os.path.dirname(os.path.dirname(__file__))
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from scripts import shortform_pipeline  # noqa: E402


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    payload = shortform_pipeline.stage_thumbnail(args)
    return {
        **payload,
        "success": bool(payload.get("ok")),
        "agent_id": agent_context.get("agent_id") or "shortform-thumbnail",
    }
