"""
Skill: Video Template Research
Triggers: "video template", "react template", "remotion template", "what template",
           "learn templates", "component library for video"
Description: Discovers React/Remotion video templates from the internet (GitHub + Remotion
             resources) and recommends libraries for a brief or composition.
Wraps: scripts/video_template_research.py
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import TIMEOUT_REPORT
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {}

    action = args.get("action") or args.get("mode")
    if action:
        body["action"] = action

    for key in (
        "brief",
        "prompt",
        "message",
        "composition_id",
        "compositionId",
        "category",
        "style",
        "style_tag",
        "fetch_github",
        "fetch_remotion",
    ):
        if key in args and args[key] is not None:
            body[key] = args[key]

    if "composition_id" in body and "compositionId" not in body:
        body["compositionId"] = body.pop("composition_id")

    if not body.get("action") and not body.get("brief") and not body.get("prompt"):
        if body.get("refresh") or body.get("learn"):
            body["action"] = "refresh"
        elif body.get("list"):
            body["action"] = "list"
        elif body.get("compositionId"):
            body["action"] = "recommend"
            body["brief"] = body.get("message") or f"video for {body['compositionId']}"

    extra_env = {"TEMPLATE_RESEARCH_JSON": json.dumps(body)}
    cmd = [
        "uv",
        "run",
        "python",
        "-c",
        (
            "import json, os; "
            "from scripts.video_template_research import run_template_research; "
            "body=json.loads(os.environ['TEMPLATE_RESEARCH_JSON']); "
            "print(json.dumps(run_template_research(body), ensure_ascii=False, default=str))"
        ),
    ]

    result = _run(cmd, timeout=TIMEOUT_REPORT, env=extra_env)
    if isinstance(result, dict) and result.get("success") is False and "recommendations" not in result:
        return result

    payload = result
    if isinstance(result, dict) and not ("templates" in result or "recommendations" in result or result.get("template_count") is not None):
        payload = result.get("result", result)
    if not isinstance(payload, dict):
        return {"success": False, "error": "invalid_template_research_response", "raw": result}

    return {
        "success": bool(payload.get("success", True)),
        "agent_id": agent_context.get("agent_id", "video-template-director"),
        **payload,
    }
