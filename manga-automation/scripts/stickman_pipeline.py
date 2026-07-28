#!/usr/bin/env python3
"""
Stickman / Canva-style viral animation pipeline.

Workflow (from https://youtu.be/b2k4xoXv3S4):
  1. ElevenLabs voiceover (optional voice_id — tutorial uses "Mark")
  2. Audacity-style pacing via ffmpeg (truncate silence + normalize)
  3. Storyboard beats + Canva element search hints (@zidansasc)
  4. Optional Remotion render when stick-figure PNGs are exported to assets_dir

Canva scene assembly is manual (no public API); this pipeline automates audio +
storyboard and renders when assets are provided.
"""
from __future__ import annotations

import json
import os
import base64
from pathlib import Path
from typing import Any

import requests

from scripts import voiceover_service
from scripts.stickman_audio import optimize_voiceover, probe_duration_secs
from scripts.stickman_storyboard import (
    allocate_scene_durations,
    plan_storyboard,
    resolve_scene_images,
)
from scripts.utils.logger import setup_logger

logger = setup_logger("stickman_pipeline")

OUTPUT_DIR = Path(os.environ.get("STICKMAN_OUTPUT_DIR", "/data/videos"))
ASSETS_DIR = Path(os.environ.get("STICKMAN_ASSETS_DIR", "/data/stickman-assets"))
FPS = int(os.environ.get("STICKMAN_FPS", "30"))
MASTRA_URL = os.environ.get("MASTRA_API_URL", "http://manga-agents:3001").rstrip("/")

_MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


def _image_path_to_data_uri(file_path: str) -> str:
    """Embed local panel PNGs so Remotion headless can load them without /data HTTP serving."""
    if file_path.startswith("data:"):
        return file_path
    path = Path(file_path)
    if not path.is_file():
        return file_path
    ext = path.suffix.lower().lstrip(".")
    mime = _MIME_BY_EXT.get(ext, "image/jpeg")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _default_voice_id() -> str | None:
    return (
        os.environ.get("STICKMAN_VOICE_ID")
        or os.environ.get("ELEVENLABS_STICKMAN_VOICE_ID")
        or os.environ.get("ELEVENLABS_VOICE_ID")
        or None
    )


def stage_voice(script: str, body: dict[str, Any]) -> dict[str, Any]:
    voice_id = body.get("voice_id") or _default_voice_id()
    output_path = body.get("voice_output_path")
    if not output_path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = str(OUTPUT_DIR / "voiceover_raw.mp3")

    return voiceover_service.synthesize(
        text=script,
        provider=body.get("provider"),
        voice_id=voice_id,
        model_id=body.get("model_id"),
        output_path=output_path,
    )


def stage_optimize(audio_path: str, body: dict[str, Any]) -> dict[str, Any]:
    if body.get("skip_optimize"):
        return {"success": True, "skipped": True, "output_path": audio_path}
    out = body.get("optimized_output_path")
    if not out:
        p = Path(audio_path)
        out = str(p.with_name(f"{p.stem}_optimized{p.suffix or '.mp3'}"))
    return optimize_voiceover(
        audio_path,
        out,
        silence_threshold_db=body.get("silence_threshold_db"),
        min_silence_sec=body.get("min_silence_sec"),
        keep_silence_sec=body.get("keep_silence_sec"),
    )


def stage_storyboard(script: str, body: dict[str, Any]) -> dict[str, Any]:
    return plan_storyboard(script, max_scenes=int(body.get("max_scenes", 24)))


def build_render_props(
    storyboard: dict[str, Any],
    voiceover_path: str | None,
    body: dict[str, Any],
) -> dict[str, Any]:
    scenes_raw = body.get("scenes") or storyboard.get("scenes") or []
    assets_dir = body.get("assets_dir") or str(ASSETS_DIR)
    resolved = resolve_scene_images(scenes_raw, assets_dir)

    duration_secs = body.get("audio_duration_secs")
    if not duration_secs and voiceover_path:
        duration_secs = probe_duration_secs(voiceover_path)
    duration_secs = float(duration_secs or 30.0)

    frame_durations = allocate_scene_durations(
        len(resolved),
        duration_secs,
        fps=FPS,
        min_scene_secs=float(body.get("min_scene_secs", 1.5)),
    )

    scenes = []
    for i, scene in enumerate(resolved):
        image_path = scene.get("imagePath") or scene.get("image_path")
        if not image_path:
            continue
        scenes.append(
            {
                "imagePath": _image_path_to_data_uri(str(image_path)),
                "caption": scene.get("caption") or scene.get("narration"),
                "durationInFrames": int(
                    scene.get("durationInFrames")
                    or scene.get("duration_in_frames")
                    or frame_durations[i],
                ),
                "elementDelayFrames": int(scene.get("elementDelayFrames", scene.get("element_delay_frames", 6))),
            },
        )

    if not scenes:
        raise ValueError(
            "no_scene_images: export stick figures from Canva to assets_dir "
            f"({assets_dir}) as scene-01.png, scene-02.png, ... or pass scenes[].imagePath",
        )

    return {
        "scenes": scenes,
        "voiceoverSrc": voiceover_path,
        "titleText": body.get("title") or body.get("titleText") or "",
        "paperBackgroundOpacity": float(body.get("paper_background_opacity", 0.12)),
        "aspectLabel": body.get("aspect") or body.get("aspectLabel") or "9:16",
    }


def stage_render(props: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = body.get("filename") or f"stickman-{int(__import__('time').time())}.mp4"
    output_path = body.get("output_path") or str(OUTPUT_DIR / filename)

    payload = {
        "compositionId": "StickFigureStory",
        "props": props,
        "filename": Path(output_path).name,
        "outputPath": output_path,
    }

    try:
        resp = requests.post(
            f"{MASTRA_URL}/pipeline/render-video-custom",
            json=payload,
            timeout=int(os.environ.get("STICKMAN_RENDER_TIMEOUT", "900")),
        )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"success": False, "error": "render_failed", "detail": data, "status": resp.status_code}
        data.setdefault("success", True)
        return data
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def run_stickman_workflow(body: dict[str, Any]) -> dict[str, Any]:
    script = str(body.get("script") or body.get("text") or "").strip()
    if not script and not body.get("voiceover_path") and not body.get("audio_path"):
        return {"success": False, "error": "script or voiceover_path is required"}

    stages: dict[str, Any] = {}
    voiceover_path = body.get("voiceover_path") or body.get("audio_path")

    if script and body.get("voice", True) and not voiceover_path:
        voice = stage_voice(script, body)
        stages["voice"] = voice
        if not voice.get("success"):
            return {"success": False, "pipeline": "stickman", "stages": stages, "error": voice.get("error")}
        voiceover_path = voice.get("output_path")

    if voiceover_path and body.get("optimize_audio", True):
        opt = stage_optimize(voiceover_path, body)
        stages["audio"] = opt
        if not opt.get("success") and not opt.get("skipped"):
            return {"success": False, "pipeline": "stickman", "stages": stages, "error": opt.get("error")}
        if opt.get("output_path"):
            voiceover_path = opt["output_path"]

    storyboard: dict[str, Any] = {}
    if script and body.get("plan", True):
        storyboard = stage_storyboard(script, body)
        stages["storyboard"] = storyboard

    result: dict[str, Any] = {
        "ok": True,
        "success": True,
        "pipeline": "stickman",
        "voiceover_path": voiceover_path,
        "stages": stages,
        "tutorial": "https://youtu.be/b2k4xoXv3S4",
        "canva_next_steps": (storyboard.get("canva_setup") if storyboard else None),
    }

    if body.get("render"):
        try:
            props = build_render_props(storyboard, voiceover_path, body)
            stages["render_props"] = props
            render = stage_render(props, body)
            stages["render"] = render
            result["filePath"] = render.get("filePath")
            result["durationSecs"] = render.get("durationSecs")
            result["fileSizeMb"] = render.get("fileSizeMb")
            if not render.get("success", True):
                result["ok"] = False
                result["success"] = False
                result["error"] = render.get("error") or render.get("detail")
        except Exception as exc:
            result["ok"] = False
            result["success"] = False
            result["error"] = str(exc)

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stickman viral video pipeline")
    parser.add_argument("--body-json", default="")
    parser.add_argument("--script", default="")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--no-voice", action="store_true")
    args = parser.parse_args()

    if args.body_json:
        req = json.loads(Path(args.body_json).read_text(encoding="utf-8"))
    else:
        req = {"script": args.script, "render": args.render, "voice": not args.no_voice}

    print(json.dumps(run_stickman_workflow(req), ensure_ascii=False, indent=2))
