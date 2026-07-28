"""
Skill: Seedance Video (AiToEarn Open Platform)
Triggers: "seedance", "ai video", "generate clip with seedance", "aitoearn video"
Description: Submits Seedance video generation via AiToEarn REST API, polls for result,
             optionally publishes to connected social channels via MCP fanout.
Wraps: scripts/aitoearn_seedance_pipeline.py
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import TIMEOUT_SEEDANCE
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    prompt = str(args.get("prompt") or args.get("message") or "").strip()
    if not prompt and not args.get("task_id") and not args.get("status_only"):
        return {"success": False, "error": "prompt or task_id is required"}

    body: dict[str, Any] = {
        "prompt": prompt,
        "publish": bool(args.get("publish", False)),
        "engage": bool(args.get("engage", False)),
        "wait": args.get("wait", True),
        "plan": args.get("plan", True),
    }

    for key in (
        "model",
        "ratio",
        "resolution",
        "duration",
        "group_id",
        "groupId",
        "images",
        "image",
        "videos",
        "video",
        "audios",
        "audio",
        "title",
        "desc",
        "description",
        "caption",
        "channels",
        "platform",
        "hashtags",
        "topics",
        "selected_accounts",
        "account_ids",
        "product",
        "brand",
        "style",
        "audience",
        "task_id",
        "taskId",
        "status_only",
        "skip_plan",
    ):
        if key in args and args[key] is not None:
            body[key] = args[key]

    extra_env = {
        k: os.environ[k]
        for k in os.environ
        if k.startswith("AITOEARN_") or k.startswith("SUPABASE_") or k in ("DATABASE_URL",)
    }
    extra_env["SEEDANCE_REQUEST_JSON"] = json.dumps(body)

    cmd = [
        "uv",
        "run",
        "python",
        "-c",
        (
            "import json, os; "
            "from scripts.aitoearn_seedance_pipeline import run_seedance_workflow; "
            "body=json.loads(os.environ['SEEDANCE_REQUEST_JSON']); "
            "print(json.dumps(run_seedance_workflow(body), ensure_ascii=False, default=str))"
        ),
    ]

    result = _run(cmd, timeout=TIMEOUT_SEEDANCE, env=extra_env)
    if isinstance(result, dict) and result.get("success") is False:
        return result

    payload = result if isinstance(result, dict) and result.get("pipeline") else result.get("result", result)
    if not isinstance(payload, dict):
        return {"success": False, "error": "invalid_seedance_response", "raw": result}

    ok = bool(payload.get("ok", True))
    return {
        "success": ok,
        "pipeline": payload.get("pipeline", "aitoearn_seedance"),
        "task_id": payload.get("task_id"),
        "video_url": payload.get("video_url"),
        "cover_url": payload.get("cover_url"),
        "stages": payload.get("stages"),
        "duration_seconds": payload.get("duration_seconds"),
        "error": payload.get("error"),
        "agent_id": agent_context.get("agent_id", "seedance-director"),
        "raw": payload,
    }
