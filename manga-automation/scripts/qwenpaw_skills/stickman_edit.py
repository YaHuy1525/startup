"""Skill: Stickman edit/sync — Remotion StickFigureStory final render (tutorial step 6)."""
from __future__ import annotations

from typing import Any

from ._stickman_flow import run_flow_body


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stages": ["edit"],
        "render": args.get("render", True),
        "voice": False,
    }
    for key in (
        "scenes",
        "voiceover_path",
        "audio_path",
        "job_id",
        "assets_dir",
        "filename",
        "title",
        "titleText",
        "aspect",
        "paper_background_opacity",
        "audio_duration_secs",
        "duration_secs",
        "min_scene_secs",
    ):
        if key in args and args[key] is not None:
            body[key] = args[key]

    if args.get("scenes"):
        from scripts.stickman_flow_pipeline import (
            _job_dir,
            stage_animate_plan,
            stage_edit,
        )

        animate = stage_animate_plan(body, {"scenes": args["scenes"]})
        voiceover_path = body.get("voiceover_path") or body.get("audio_path")
        if not body.get("render"):
            from scripts.stickman_flow_pipeline import build_flow_render_props

            props = build_flow_render_props(animate, voiceover_path, body)
            return {
                "success": True,
                "pipeline": "stickman_flow",
                "skipped_render": True,
                "props_preview": {
                    "scene_count": len(props.get("scenes") or []),
                    "has_voiceover": bool(props.get("voiceoverSrc")),
                },
                "stages": {"animate": animate},
                "agent_id": agent_context.get("agent_id", "stickman-editor"),
            }

        edit = stage_edit(body, animate, voiceover_path)
        render = edit.get("render") or {}
        job = _job_dir(body)
        return {
            "success": bool(render.get("success", False)),
            "pipeline": "stickman_flow",
            "job_id": job.name,
            "filePath": render.get("filePath"),
            "durationSecs": render.get("durationSecs"),
            "fileSizeMb": render.get("fileSizeMb"),
            "stages": {"animate": animate, "edit": edit},
            "agent_id": agent_context.get("agent_id", "stickman-editor"),
            "error": render.get("error") or render.get("detail"),
        }

    payload = run_flow_body(body)
    return {
        **payload,
        "success": bool(payload.get("success", False)),
        "agent_id": agent_context.get("agent_id", "stickman-editor"),
    }
