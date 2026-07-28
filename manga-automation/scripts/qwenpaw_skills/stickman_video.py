"""
Skill: Stickman Video (Canva-style viral animation)
Triggers: "stickman", "stick figure video", "canva animation", "viral stickman"
Description: ElevenLabs voiceover → ffmpeg pacing → storyboard with Canva hints →
             optional Remotion StickFigureStory render when PNG assets are ready.
Wraps: scripts/stickman_pipeline.py
Tutorial: https://youtu.be/b2k4xoXv3S4
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import TIMEOUT_RENDER
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    script = str(args.get("script") or args.get("text") or args.get("message") or "").strip()
    if not script and not args.get("voiceover_path") and not args.get("audio_path"):
        return {"success": False, "error": "script or voiceover_path is required"}

    body: dict[str, Any] = {
        "script": script,
        "voice": args.get("voice", True),
        "optimize_audio": args.get("optimize_audio", True),
        "plan": args.get("plan", True),
        "render": bool(args.get("render", False)),
    }

    for key in (
        "voice_id",
        "provider",
        "model_id",
        "assets_dir",
        "scenes",
        "filename",
        "output_path",
        "title",
        "titleText",
        "voiceover_path",
        "audio_path",
        "max_scenes",
        "skip_optimize",
        "paper_background_opacity",
        "aspect",
        "min_scene_secs",
    ):
        if key in args and args[key] is not None:
            body[key] = args[key]

    extra_env = {"STICKMAN_REQUEST_JSON": json.dumps(body)}
    cmd = [
        "uv",
        "run",
        "python",
        "-c",
        (
            "import json, os; "
            "from scripts.stickman_pipeline import run_stickman_workflow; "
            "body=json.loads(os.environ['STICKMAN_REQUEST_JSON']); "
            "print(json.dumps(run_stickman_workflow(body), ensure_ascii=False, default=str))"
        ),
    ]

    result = _run(cmd, timeout=TIMEOUT_RENDER, env=extra_env)
    if isinstance(result, dict) and result.get("success") is False and "pipeline" not in result:
        return result

    payload = result if isinstance(result, dict) and result.get("pipeline") else result.get("result", result)
    if not isinstance(payload, dict):
        return {"success": False, "error": "invalid_stickman_response", "raw": result}

    ok = bool(payload.get("success", payload.get("ok", True)))
    return {
        "success": ok,
        "pipeline": "stickman",
        "voiceover_path": payload.get("voiceover_path"),
        "filePath": payload.get("filePath"),
        "durationSecs": payload.get("durationSecs"),
        "stages": payload.get("stages"),
        "canva_next_steps": payload.get("canva_next_steps"),
        "tutorial": payload.get("tutorial", "https://youtu.be/b2k4xoXv3S4"),
        "error": payload.get("error"),
        "agent_id": agent_context.get("agent_id", "stickman-director"),
        "raw": payload,
    }
