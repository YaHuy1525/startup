"""Skill: Stickman video-prompting agent (story/premise -> scene-by-scene video plan)."""
from __future__ import annotations

import json
from typing import Any

from ._base import _run
from . import TIMEOUT_TREND


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for key in ("story", "premise", "topic", "scene_count", "duration_secs", "duration"):
        if key in args and args[key] is not None:
            body[key] = args[key]

    cmd = [
        "uv",
        "run",
        "python",
        "-c",
        (
            "import json, os; "
            "from scripts.stickman_video_prompter import run_video_prompter; "
            "body=json.loads(os.environ['STICKMAN_PROMPT_REQUEST_JSON']); "
            "print(json.dumps(run_video_prompter(body), ensure_ascii=False, default=str))"
        ),
    ]
    result = _run(
        cmd,
        timeout=TIMEOUT_TREND,
        env={"STICKMAN_PROMPT_REQUEST_JSON": json.dumps(body)},
    )
    payload = result if isinstance(result, dict) else {"success": False, "raw": result}
    return {
        **payload,
        "success": bool(payload.get("success", False)),
        "agent_id": agent_context.get("agent_id", "stickman-prompter"),
    }
