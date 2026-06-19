"""
Skill: Video Render
Triggers: "render video", "generate clip", "create video", "make recap"
Description: Triggers Remotion-based video rendering with Ken Burns effects,
             music overlay, and captions. This is a long-running task — QwenPaw
             should use spawn_subagent with background=True to offload it.
Wraps: scripts/generate_video.py (calls Remotion renderer via HTTP)
       mastra-agents/ (Remotion compositions)
"""
from __future__ import annotations

import os
from typing import Any

import requests

from . import TIMEOUT_RENDER


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """
    Render a video from downloaded panels/assets.

    This skill is DESIGNED for background execution. The agent should call:
        spawn_subagent(instruction="render video ...", background=True)
    so the render runs offloaded while the agent continues other work.

    Args:
        args:
            video_id (int): Database video ID to render
            chapter (str): Chapter reference (e.g. "261")
            manga_title (str): Manga title for the video overlay
            music_track (str): Background music filename
            captions (list[str]): Caption lines for the video
        agent_context: QwenPaw agent context

    Returns:
        {"success": True, "video_path": "...", "duration_seconds": N, ...}
    """
    mastra_url = os.environ.get("MASTRA_API_URL", "http://manga-agents:3001").rstrip("/")
    route = "/pipeline/render-video-custom" if args.get("props") else "/pipeline/render-video"

    body: dict[str, Any] = {}
    for key in (
        "queueId",
        "queue_id",
        "templateId",
        "template_id",
        "randomTemplate",
        "random_template",
        "compositionId",
        "composition_id",
        "chapterId",
        "chapter_id",
        "filename",
        "outputPath",
        "output_path",
    ):
        if key in args:
            body[key] = args[key]

    # Normalize snake_case aliases to API camelCase.
    if "queue_id" in body and "queueId" not in body:
        body["queueId"] = body.pop("queue_id")
    if "template_id" in body and "templateId" not in body:
        body["templateId"] = body.pop("template_id")
    if "random_template" in body and "randomTemplate" not in body:
        body["randomTemplate"] = body.pop("random_template")
    if "composition_id" in body and "compositionId" not in body:
        body["compositionId"] = body.pop("composition_id")
    if "chapter_id" in body and "chapterId" not in body:
        body["chapterId"] = body.pop("chapter_id")
    if "output_path" in body and "outputPath" not in body:
        body["outputPath"] = body.pop("output_path")

    if args.get("props"):
        body["props"] = args["props"]

    timeout_sec = min(TIMEOUT_RENDER, 900)
    try:
        resp = requests.post(
            f"{mastra_url}{route}",
            json=body,
            timeout=timeout_sec,
        )
        payload = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {
                "success": False,
                "error": f"mastra_http_{resp.status_code}",
                "detail": payload,
            }
        payload.setdefault("success", True)
        payload.setdefault("route", route)
        return payload
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "route": route,
        }
