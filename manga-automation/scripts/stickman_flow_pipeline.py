#!/usr/bin/env python3
"""
Stickman Flow pipeline — DeepSeek script + Remotion animate/edit.

Automates the Google-Flow-style stickman tutorial without Google Flow / Omni Flash:
  1. Character reference (download/copy)
  2. DeepSeek topics + full script (narration, image_prompt, video_prompt per scene)
  3. Scene stills (OpenRouter image if configured, else programmatic stick figures)
  4. Remotion motion presets from video_prompt
  5. Clean narration → TTS + ffmpeg silence trim
  6. Remotion StickFigureStory sync + export

Usage:
    python scripts/stickman_flow_pipeline.py --body-json body.json
    POST /stickman/flow
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import requests

from scripts.stickman_audio import probe_duration_secs
from scripts.stickman_pipeline import (
    _default_voice_id,
    _image_path_to_data_uri,
    stage_optimize,
    stage_render,
    stage_voice,
)
from scripts.stickman_storyboard import allocate_scene_durations
from scripts.utils import deepseek_client
from scripts.utils.logger import setup_logger

logger = setup_logger("stickman_flow")

ASSETS_DIR = Path(os.environ.get("STICKMAN_ASSETS_DIR", "/data/stickman-assets"))
OUTPUT_DIR = Path(os.environ.get("STICKMAN_OUTPUT_DIR", "/data/videos/stickman"))
FPS = int(os.environ.get("STICKMAN_FPS", "30"))
CLIP_SECS_DEFAULT = float(os.environ.get("STICKMAN_CLIP_SECS", "9"))

MOTION_PRESETS = (
    "zoom_in",
    "zoom_out",
    "bounce",
    "slide_left",
    "slide_right",
    "idle_sway",
    "pop_in",
    "pan_up",
)

_POSE_KEYWORDS: list[tuple[str, str]] = [
    ("run", "running"),
    ("walk", "walking"),
    ("jump", "jumping"),
    ("think", "thinking"),
    ("sad", "sad"),
    ("angry", "angry"),
    ("happy", "happy"),
    ("celebrate", "celebrating"),
    ("computer", "at_computer"),
    ("phone", "on_phone"),
    ("point", "pointing"),
    ("wave", "waving"),
    ("sit", "sitting"),
]


def _job_dir(body: dict[str, Any]) -> Path:
    job_id = str(body.get("job_id") or f"flow-{int(time.time())}")
    root = Path(body.get("assets_dir") or str(ASSETS_DIR)) / job_id
    root.mkdir(parents=True, exist_ok=True)
    return root


# ─── Stage 1: Character reference ─────────────────────────────────────────────


def stage_character_ref(body: dict[str, Any]) -> dict[str, Any]:
    job = _job_dir(body)
    dest = job / "character_ref.png"

    src = body.get("character_ref_path") or body.get("character_ref")
    url = body.get("character_ref_url")

    if src:
        path = Path(str(src))
        if not path.is_file():
            return {"success": False, "error": f"character_ref_path not found: {src}"}
        shutil.copy2(path, dest)
        return {"success": True, "character_ref_path": str(dest), "source": "path"}

    if url:
        try:
            resp = requests.get(str(url), timeout=60)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return {
                "success": True,
                "character_ref_path": str(dest),
                "source": "url",
                "url": str(url),
            }
        except Exception as exc:
            return {"success": False, "error": f"download_failed: {exc}"}

    # Generate a default stick-figure reference so the pipeline always runs
    try:
        _draw_stickman_png(dest, pose="idle", accent="#1a1a1a", label="character ref")
        return {
            "success": True,
            "character_ref_path": str(dest),
            "source": "generated_default",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ─── Stage 2: Topics + script (DeepSeek) ──────────────────────────────────────


def stage_topics(body: dict[str, Any]) -> dict[str, Any]:
    hint = str(body.get("topic_hint") or body.get("niche") or "viral stickman explainer").strip()
    duration = float(body.get("duration_secs") or body.get("duration") or 60)

    if body.get("topics") and isinstance(body["topics"], list):
        return {
            "success": True,
            "topics": body["topics"][:20],
            "skipped_llm": True,
        }

    if not deepseek_client.is_available():
        fallback = [
            f"{hint} — unexpected truth #{i}"
            for i in range(1, 21)
        ]
        return {
            "success": True,
            "topics": fallback,
            "fallback": True,
            "warning": "DeepSeek unavailable — heuristic topics",
        }

    result = deepseek_client.chat_json(
        [
            {
                "role": "system",
                "content": (
                    "You are a viral short-form content strategist. "
                    "Return ONLY valid JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Generate exactly 20 engaging topic ideas for a stick-figure "
                    f"animation video (~{int(duration)}s). Niche/hint: {hint}\n\n"
                    'Return JSON: {"topics": ["idea1", ...]} with exactly 20 strings.'
                ),
            },
        ],
        temperature=0.8,
        max_tokens=2048,
    )
    if not result.get("success"):
        fallback = [f"{hint} — unexpected truth #{i}" for i in range(1, 21)]
        return {
            "success": True,
            "topics": fallback,
            "fallback": True,
            "warning": result.get("error") or result.get("detail"),
        }

    data = result["data"]
    topics = data.get("topics") if isinstance(data, dict) else data
    if not isinstance(topics, list) or not topics:
        fallback = [f"{hint} — unexpected truth #{i}" for i in range(1, 21)]
        return {
            "success": True,
            "topics": fallback,
            "fallback": True,
            "warning": "no_topics_in_response",
            "raw": data,
        }

    clean = [str(t).strip() for t in topics if str(t).strip()][:20]
    return {
        "success": True,
        "topics": clean,
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def stage_script(body: dict[str, Any], topics_result: dict[str, Any] | None = None) -> dict[str, Any]:
    duration = float(body.get("duration_secs") or body.get("duration") or 60)
    clip_secs = float(body.get("clip_secs") or CLIP_SECS_DEFAULT)
    scene_count = max(2, int(round(duration / max(clip_secs, 5.0))))

    topic = str(body.get("topic") or "").strip()
    if not topic:
        topics = (topics_result or {}).get("topics") or body.get("topics") or []
        if body.get("auto_pick_topic") and topics:
            topic = str(topics[0])
        elif not body.get("auto_pick_topic"):
            return {
                "success": True,
                "awaiting_topic": True,
                "topics": topics,
                "message": "Pick a topic and re-submit with topic=... and auto_pick_topic=false",
            }
        else:
            topic = str(body.get("topic_hint") or "Why stick figures go viral")

    if body.get("scenes") and isinstance(body["scenes"], list):
        scenes = body["scenes"]
        return {
            "success": True,
            "topic": topic,
            "scene_count": len(scenes),
            "scenes": scenes,
            "skipped_llm": True,
        }

    if not deepseek_client.is_available():
        return {
            "success": True,
            "topic": topic,
            "scene_count": scene_count,
            "scenes": _fallback_scenes(topic, scene_count),
            "fallback": True,
            "warning": "DeepSeek unavailable — heuristic script",
        }

    result = deepseek_client.chat_json(
        [
            {
                "role": "system",
                "content": (
                    "You write viral Rico Animations–style stick-figure shorts "
                    "(like Beckett AI / Google Flow Nano Banana tutorials). "
                    "Tone: calm philosophical or motivational POV narration. "
                    "Visuals: expressive black-and-white vector storyboard stickmen — "
                    "thick bold outlines, cinematic framing, symbolic props, pure white bg. "
                    "NOT emoji icons or children's scribbles. "
                    "Every scene needs narration, image_prompt, and video_prompt. "
                    "image_prompt must describe SUBJECT + ACTION + COMPOSITION + MOOD. "
                    "video_prompt should prefer slow cinematic zoom / push-in "
                    "(Omni Flash feel), not cartoon bounce. "
                    "Return ONLY valid JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Write a full script for a {int(duration)}-second viral stickman Short "
                    f"in premium Rico Animations / Google Flow quality.\n"
                    f"Topic: {topic}\n"
                    f"Target scenes: {scene_count} (about {clip_secs:.0f}s each).\n\n"
                    "image_prompt RULES:\n"
                    "- Describe the beat as a storyboard still: who, what pose, key prop, camera angle.\n"
                    "- Example: 'Stickman hunched over phone, blue-light addiction pose, medium shot, "
                    "expressive silhouette, pure white background, bold black vector outlines.'\n"
                    "- No photorealism, no color fills, no text in frame, no clutter.\n"
                    "- Make each scene visually distinct and readable on a phone.\n\n"
                    "video_prompt RULES: slow zoom in, subtle pan, or gentle push-in.\n\n"
                    "Return JSON:\n"
                    "{\n"
                    '  "title": "...",\n'
                    '  "topic": "...",\n'
                    '  "scenes": [\n'
                    "    {\n"
                    '      "index": 0,\n'
                    '      "narration": "spoken line",\n'
                    '      "image_prompt": "detailed storyboard still description...",\n'
                    '      "video_prompt": "slow cinematic zoom in",\n'
                    '      "action": "thinking|money|crowd|clock|..."\n'
                    "    }\n"
                    "  ]\n"
                    "}\n"
                    f"Exactly {scene_count} scenes. Narration must fit ~{clip_secs:.0f}s speech each."
                ),
            },
        ],
        temperature=0.6,
        max_tokens=4096,
    )
    if not result.get("success"):
        return {
            "success": True,
            "topic": topic,
            "scene_count": scene_count,
            "scenes": _fallback_scenes(topic, scene_count),
            "fallback": True,
            "warning": result.get("error") or result.get("detail"),
        }

    data = result["data"]
    if not isinstance(data, dict):
        return {
            "success": True,
            "topic": topic,
            "scene_count": scene_count,
            "scenes": _fallback_scenes(topic, scene_count),
            "fallback": True,
            "warning": "script_not_object",
            "raw": data,
        }

    scenes = data.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        return {
            "success": True,
            "topic": topic,
            "scene_count": scene_count,
            "scenes": _fallback_scenes(topic, scene_count),
            "fallback": True,
            "warning": "no_scenes",
            "raw": data,
        }

    normalized = []
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        narration = str(scene.get("narration") or "").strip()
        if not narration:
            continue
        image_prompt = str(scene.get("image_prompt") or narration).strip()
        video_prompt = str(scene.get("video_prompt") or "slow cinematic zoom in").strip()
        from scripts.stickman_panel_library import classify_action

        action = classify_action(
            f"{image_prompt} {narration} {video_prompt}",
            preferred=str(scene.get("action") or scene.get("action_category") or "") or None,
        )
        normalized.append(
            {
                "index": i,
                "narration": narration,
                "caption": narration if len(narration) <= 120 else narration[:117] + "...",
                "image_prompt": image_prompt,
                "video_prompt": video_prompt,
                "action": action,
                "action_category": action,
            },
        )

    if not normalized:
        return {"success": False, "error": "empty_normalized_scenes"}

    return {
        "success": True,
        "topic": data.get("topic") or topic,
        "title": data.get("title") or topic,
        "scene_count": len(normalized),
        "scenes": normalized,
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def _fallback_scenes(topic: str, count: int) -> list[dict[str, Any]]:
    # Motivational POV beats matching Beckett tutorial sample ending
    beats = [
        f"Most people never pause to think about {topic}.",
        "They keep chasing approval that never lasts.",
        "Then one day, they realize something important.",
        "Nobody is watching them as closely as they imagined.",
        "Everyone is busy living their own life.",
        "Time is more valuable than money.",
        "You can earn more money, but you cannot get time back.",
        "So start now — the perfect moment never arrives.",
    ]
    style_lock = (
        "Black stick figure on pure white background, Rico Animation style, "
        "clean vector bold outlines, minimal props"
    )
    scenes = []
    for i in range(count):
        line = beats[i % len(beats)]
        if i == 0 and topic:
            line = beats[0]
        scenes.append(
            {
                "index": i,
                "narration": line,
                "caption": line,
                "image_prompt": f"{style_lock}. Scene: {line}",
                "video_prompt": "slow cinematic zoom in",
                "action": _infer_fallback_action(line),
                "action_category": _infer_fallback_action(line),
            },
        )
    return scenes


def _infer_fallback_action(line: str) -> str:
    from scripts.stickman_panel_library import classify_action

    return classify_action(line)


# ─── Stage 3: Scene images (AI panels + action library) ───────────────────────


def stage_scene_images(
    body: dict[str, Any],
    script: dict[str, Any],
    character_ref: dict[str, Any],
) -> dict[str, Any]:
    from scripts.stickman_panel_library import (
        can_generate_ai,
        classify_action,
        list_library,
        resolve_or_generate_panel,
    )

    job = _job_dir(body)
    scenes_dir = job / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    scenes = list(script.get("scenes") or [])
    ref_path = character_ref.get("character_ref_path")
    force = bool(body.get("force_regenerate_panels") or body.get("force_images"))
    reuse = body.get("reuse_library", True)
    prefer_ai = body.get("prefer_ai_panels", True)

    written: list[dict[str, Any]] = []
    errors: list[str] = []
    actions_used: list[str] = []

    for i, scene in enumerate(scenes):
        out = scenes_dir / f"scene-{i + 1:02d}.png"
        image_prompt = str(scene.get("image_prompt") or scene.get("narration") or "")
        narration = str(scene.get("narration") or "")
        video_prompt = str(scene.get("video_prompt") or "")
        action_hint = scene.get("action") or scene.get("action_category")

        ok = False
        source = "placeholder"
        action = classify_action(
            f"{image_prompt} {narration} {video_prompt}",
            preferred=str(action_hint) if action_hint else None,
        )
        model = None
        library_id = None
        reused = False

        if prefer_ai or can_generate_ai():
            result = resolve_or_generate_panel(
                action=action,
                image_prompt=image_prompt,
                narration=narration,
                video_prompt=video_prompt,
                character_ref_path=str(ref_path) if ref_path else None,
                dest=out,
                force_regenerate=force,
                reuse_library=bool(reuse),
            )
            if result.get("success"):
                ok = True
                source = str(result.get("source") or "ai")
                action = str(result.get("action") or action)
                model = result.get("model")
                library_id = result.get("library_id")
                reused = bool(result.get("reused"))
            else:
                errors.append(
                    f"scene_{i}:{action}:{result.get('error')}",
                )

        if not ok:
            # Last-resort PIL only if AI unavailable / failed
            try:
                _draw_stickman_png(out, pose=_infer_pose(f"{image_prompt} {video_prompt}"), accent="#111111")
                ok = True
                source = "placeholder"
            except Exception as exc:
                errors.append(f"scene_{i}_draw:{exc}")

        item = dict(scene)
        item["imagePath"] = str(out) if ok else None
        item["image_source"] = source if ok else "failed"
        item["action"] = action
        item["action_category"] = action
        item["library_id"] = library_id
        item["reused_from_library"] = reused
        if model:
            item["image_model"] = model
        written.append(item)
        actions_used.append(action)

    ok_count = sum(1 for s in written if s.get("imagePath"))
    lib = list_library()
    return {
        "success": ok_count > 0,
        "scenes_dir": str(scenes_dir),
        "scene_count": ok_count,
        "scenes": written,
        "actions_used": actions_used,
        "library": {
            "dir": lib.get("library_dir"),
            "counts": lib.get("counts"),
            "panel_count": lib.get("panel_count"),
        },
        "errors": errors or None,
        "ai_available": can_generate_ai(),
        "prefer_ai_panels": prefer_ai,
    }


def _infer_pose(text: str) -> str:
    lower = text.lower()
    for keyword, pose in _POSE_KEYWORDS:
        if keyword in lower:
            return pose
    return "idle"


def _draw_stickman_png(
    dest: Path,
    *,
    pose: str = "idle",
    accent: str = "#111111",
    label: str = "",
    size: tuple[int, int] = (1080, 1080),
) -> None:
    from PIL import Image, ImageDraw

    # Solid white canvas — Rico / Beckett viral stickman look
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, size[1] // 2 - 20
    stroke = max(10, size[0] // 90)
    r = size[0] // 14

    draw.ellipse((cx - r, cy - 120 - r, cx + r, cy - 120 + r), outline=accent, width=stroke)
    draw.line((cx, cy - 80, cx, cy + 50), fill=accent, width=stroke)

    if pose in ("running", "walking"):
        draw.line((cx, cy - 30, cx - 100, cy - 5), fill=accent, width=stroke)
        draw.line((cx, cy - 30, cx + 90, cy - 70), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx - 80, cy + 160), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx + 50, cy + 130), fill=accent, width=stroke)
    elif pose == "thinking":
        draw.line((cx, cy - 30, cx - 80, cy - 30), fill=accent, width=stroke)
        draw.line((cx, cy - 30, cx + 60, cy - 110), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx - 55, cy + 150), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx + 55, cy + 150), fill=accent, width=stroke)
        draw.ellipse((cx + 70, cy - 140, cx + 95, cy - 115), outline=accent, width=max(3, stroke // 2))
    elif pose in ("sad",):
        draw.line((cx, cy - 30, cx - 60, cy), fill=accent, width=stroke)
        draw.line((cx, cy - 30, cx + 60, cy), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx - 45, cy + 160), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx + 45, cy + 160), fill=accent, width=stroke)
    elif pose in ("celebrating", "happy", "jumping"):
        draw.line((cx, cy - 30, cx - 90, cy - 110), fill=accent, width=stroke)
        draw.line((cx, cy - 30, cx + 90, cy - 110), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx - 60, cy + 120), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx + 60, cy + 120), fill=accent, width=stroke)
    elif pose == "pointing":
        draw.line((cx, cy - 30, cx - 70, cy - 30), fill=accent, width=stroke)
        draw.line((cx, cy - 30, cx + 120, cy - 80), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx - 55, cy + 150), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx + 55, cy + 150), fill=accent, width=stroke)
    elif pose == "sitting":
        draw.line((cx, cy - 30, cx - 80, cy - 30), fill=accent, width=stroke)
        draw.line((cx, cy - 30, cx + 80, cy - 30), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx - 90, cy + 90), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx + 90, cy + 90), fill=accent, width=stroke)
        draw.line((cx - 90, cy + 90, cx - 90, cy + 160), fill=accent, width=stroke)
        draw.line((cx + 90, cy + 90, cx + 90, cy + 160), fill=accent, width=stroke)
    else:
        draw.line((cx, cy - 30, cx - 80, cy - 30), fill=accent, width=stroke)
        draw.line((cx, cy - 30, cx + 80, cy - 30), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx - 55, cy + 150), fill=accent, width=stroke)
        draw.line((cx, cy + 50, cx + 55, cy + 150), fill=accent, width=stroke)

    # No caption text burned into frame (voice-led like the tutorial)
    _ = label

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG")


def _composite_ref_scene(ref: Path, dest: Path, caption: str = "") -> None:
    from PIL import Image

    canvas = Image.new("RGB", (1080, 1080), (255, 255, 255))
    ref_img = Image.open(ref).convert("RGBA")
    ref_img.thumbnail((900, 900))
    x = (1080 - ref_img.width) // 2
    y = (1080 - ref_img.height) // 2
    canvas.paste(ref_img, (x, y), ref_img if ref_img.mode == "RGBA" else None)
    _ = caption  # voice-led; do not burn caption into image
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, format="PNG")


# ─── Stage 4: Animate plan (Remotion motion presets) ──────────────────────────


def infer_motion_preset(video_prompt: str) -> dict[str, Any]:
    text = (video_prompt or "").lower()
    intensity = 0.7
    if any(w in text for w in ("dramatic", "fast", "intense", "slam")):
        intensity = 1.0
    elif any(w in text for w in ("subtle", "slow", "gentle", "soft")):
        intensity = 0.35

    mapping = [
        (("zoom out", "pull back", "zoom_out"), "zoom_out"),
        (("zoom", "push in", "zoom_in", "close up"), "zoom_in"),
        (("bounce", "hop", "jump"), "bounce"),
        (("slide left", "from right", "slide_left"), "slide_left"),
        (("slide right", "from left", "slide_right"), "slide_right"),
        (("pan up", "rise", "look up"), "pan_up"),
        (("pop", "appear", "snap"), "pop_in"),
        (("sway", "idle", "breathe", "subtle"), "idle_sway"),
    ]
    for keywords, preset in mapping:
        if any(k in text for k in keywords):
            return {"preset": preset, "intensity": intensity}

    # hash-stable default from prompt — prefer cinematic zoom for Rico look
    if not text:
        return {"preset": "zoom_in", "intensity": intensity}
    idx = sum(ord(c) for c in text) % len(MOTION_PRESETS)
    # Bias odd hash toward zoom_in for tutorial-like feel
    preset = MOTION_PRESETS[idx]
    if preset in ("bounce", "pop_in"):
        preset = "zoom_in"
    return {"preset": preset, "intensity": intensity}


def _animate_clips_enabled(body: dict[str, Any]) -> bool:
    if "animate_clips" in body:
        return bool(body.get("animate_clips"))
    provider = str(os.environ.get("STICKMAN_ANIMATE_PROVIDER") or "").strip().lower()
    return provider in ("kie", "kia")


def stage_animate_clips(
    body: dict[str, Any],
    scenes: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Turn each static panel into a short animated clip via Kie image-to-video.
    This is the "AI Frame Sequencing" step: Kie clips → Remotion timeline.
    """
    from scripts.utils import kie_client

    if not kie_client.available():
        return {"success": False, "error": "KIA_API_KEY not set", "scenes": scenes}

    job = _job_dir(body)
    clips_dir = job / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    aspect = str(body.get("aspect") or body.get("aspectLabel") or "9:16")
    resolution = str(body.get("clip_resolution") or os.environ.get("STICKMAN_VIDEO_RESOLUTION") or "720p")
    duration = int(body.get("clip_duration_secs") or os.environ.get("STICKMAN_VIDEO_CLIP_SECS") or 6)
    model = body.get("video_model") or os.environ.get("STICKMAN_VIDEO_MODEL")

    animated = 0
    errors: list[str] = []
    for i, scene in enumerate(scenes):
        image_path = scene.get("imagePath") or scene.get("image_path")
        if not image_path or not Path(str(image_path)).is_file():
            continue
        prompt = str(
            scene.get("video_prompt")
            or scene.get("image_prompt")
            or scene.get("narration")
            or "subtle cinematic motion, slow push-in, stickman animation, pure white background",
        )
        out = clips_dir / f"clip-{i + 1:02d}.mp4"
        # Kie video jobs are occasionally flaky (transient generation_failed); retry a couple times.
        # Failed/timeout tasks are not charged, so retries are credit-safe.
        attempts = max(1, int(body.get("clip_retries") or os.environ.get("STICKMAN_VIDEO_RETRIES") or 3))
        result: dict[str, Any] = {}
        for attempt in range(attempts):
            result = kie_client.generate_video(
                out,
                prompt=prompt,
                image_path=str(image_path),
                model=model,
                duration=duration,
                resolution=resolution,
                aspect_ratio=aspect,
            )
            if result.get("success"):
                break
            logger.warning(
                "Clip gen scene %s attempt %s/%s failed: %s",
                i, attempt + 1, attempts, result.get("error") or result.get("failMsg"),
            )
        if result.get("success"):
            scene["videoPath"] = str(out)
            scene["videoSrc"] = result.get("resultUrl") or str(out)
            scene["video_model"] = result.get("model")
            animated += 1
        else:
            errors.append(f"scene_{i}:{result.get('error') or result.get('failMsg')}")

    return {
        "success": animated > 0,
        "animated": animated,
        "scenes": scenes,
        "errors": errors or None,
        "clips_dir": str(clips_dir),
    }


def stage_animate_plan(body: dict[str, Any], images_result: dict[str, Any]) -> dict[str, Any]:
    scenes = []
    for scene in images_result.get("scenes") or []:
        item = dict(scene)
        motion = item.get("motion")
        if not isinstance(motion, dict) or not motion.get("preset"):
            motion = infer_motion_preset(str(item.get("video_prompt") or ""))
        item["motion"] = {
            "preset": str(motion.get("preset", "idle_sway")),
            "intensity": float(motion.get("intensity", 0.7)),
        }
        scenes.append(item)

    result: dict[str, Any] = {
        "success": True,
        "scene_count": len(scenes),
        "scenes": scenes,
        "engine": "remotion",
        "compositionId": "StickFigureStory",
    }

    if _animate_clips_enabled(body):
        clips = stage_animate_clips(body, scenes)
        result["clips"] = {
            "animated": clips.get("animated"),
            "errors": clips.get("errors"),
            "clips_dir": clips.get("clips_dir"),
        }
        result["scenes"] = clips.get("scenes") or scenes
        result["animation_mode"] = "kie_clips"
    else:
        result["animation_mode"] = "remotion_motion"

    return result


# ─── Stage 5: Voiceover ───────────────────────────────────────────────────────


def stage_clean_narration(scenes: list[dict[str, Any]], body: dict[str, Any]) -> dict[str, Any]:
    if body.get("narration_text"):
        return {"success": True, "narration": str(body["narration_text"]).strip(), "skipped_llm": True}

    lines = [str(s.get("narration") or "").strip() for s in scenes if s.get("narration")]
    joined = "\n\n".join(lines)
    if not joined:
        return {"success": False, "error": "no_narration"}

    if not deepseek_client.is_available() or body.get("skip_clean_narration"):
        return {"success": True, "narration": joined, "skipped_llm": True}

    result = deepseek_client.chat(
        [
            {
                "role": "system",
                "content": (
                    "Rewrite narration for text-to-speech. "
                    "Strip image/video prompts. Keep only spoken lines as clean paragraphs. "
                    "No markdown, no labels, no scene numbers."
                ),
            },
            {
                "role": "user",
                "content": f"Clean this script into paragraphs for voiceover:\n\n{joined}",
            },
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    if not result.get("success"):
        return {"success": True, "narration": joined, "warning": result.get("error")}

    text = str(result.get("content") or "").strip()
    return {
        "success": True,
        "narration": text or joined,
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def _voice_provider(body: dict[str, Any]) -> str:
    pref = str(body.get("voice_provider") or os.environ.get("STICKMAN_VOICE_PROVIDER") or "auto").lower()
    return pref


def stage_voice_kie(body: dict[str, Any], narration: str) -> dict[str, Any]:
    """Voiceover via Kie ElevenLabs (works when direct ElevenLabs has no credits)."""
    from scripts.utils import kie_client

    if not kie_client.available():
        return {"success": False, "error": "KIA_API_KEY not set"}

    job = _job_dir(body)
    dest = Path(body.get("voice_output_path") or str(job / "voiceover_raw.mp3"))
    result = kie_client.generate_speech(
        narration,
        dest,
        voice=body.get("voice_id") or body.get("kie_voice"),
        model=body.get("tts_model"),
    )
    if not result.get("success"):
        return result
    return {
        "success": True,
        "output_path": result.get("path"),
        "provider": "kie",
        "model": result.get("model"),
        "voice": result.get("voice"),
    }


def stage_voice_flow(body: dict[str, Any], narration: str) -> dict[str, Any]:
    job = _job_dir(body)
    provider = _voice_provider(body)

    voice: dict[str, Any] = {}
    if provider in ("kie", "kia"):
        voice = stage_voice_kie(body, narration)
    else:
        voice_body = {
            **body,
            "voice_output_path": body.get("voice_output_path") or str(job / "voiceover_raw.mp3"),
            "voice_id": body.get("voice_id") or _default_voice_id(),
        }
        voice = stage_voice(narration, voice_body)
        # auto: fall back to Kie ElevenLabs if direct ElevenLabs fails (e.g. no credits)
        if not voice.get("success") and provider == "auto":
            logger.warning("Direct TTS failed (%s); falling back to Kie ElevenLabs", voice.get("error"))
            kie_voice = stage_voice_kie(body, narration)
            if kie_voice.get("success"):
                voice = kie_voice

    if not voice.get("success"):
        return voice

    path = voice.get("output_path")
    if path and body.get("optimize_audio", True):
        opt_body = {
            **body,
            "optimized_output_path": body.get("optimized_output_path")
            or str(Path(path).with_name("voiceover_optimized.mp3")),
        }
        opt = stage_optimize(path, opt_body)
        if opt.get("success") or opt.get("skipped"):
            voice["optimized"] = opt
            if opt.get("output_path"):
                voice["output_path"] = opt["output_path"]
        else:
            voice["optimize_warning"] = opt.get("error")
    return voice


# ─── Stage 6: Edit / Remotion render ──────────────────────────────────────────


def _video_path_to_data_uri(path: str) -> str:
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:video/mp4;base64,{encoded}"


def build_flow_render_props(
    animate: dict[str, Any],
    voiceover_path: str | None,
    body: dict[str, Any],
) -> dict[str, Any]:
    scenes_raw = animate.get("scenes") or []
    duration_secs = body.get("audio_duration_secs")
    if not duration_secs and voiceover_path:
        duration_secs = probe_duration_secs(voiceover_path)
    duration_secs = float(duration_secs or body.get("duration_secs") or 30.0)

    frame_durations = allocate_scene_durations(
        len(scenes_raw),
        duration_secs,
        fps=FPS,
        min_scene_secs=float(body.get("min_scene_secs", 1.5)),
    )

    scenes = []
    for i, scene in enumerate(scenes_raw):
        image_path = scene.get("imagePath") or scene.get("image_path")
        if not image_path:
            continue
        motion = scene.get("motion") or infer_motion_preset(str(scene.get("video_prompt") or ""))
        # AI Frame Sequencing: if a Kie clip exists, play it instead of Ken Burns image
        video_src = scene.get("videoSrc") or scene.get("video_src")
        if not video_src and scene.get("videoPath") and Path(str(scene["videoPath"])).is_file():
            video_src = _video_path_to_data_uri(str(scene["videoPath"]))
        scenes.append(
            {
                "imagePath": _image_path_to_data_uri(str(image_path)),
                "videoSrc": video_src,
                "caption": scene.get("caption") or scene.get("narration"),
                "durationInFrames": int(
                    scene.get("durationInFrames")
                    or scene.get("duration_in_frames")
                    or frame_durations[i],
                ),
                "elementDelayFrames": int(
                    scene.get("elementDelayFrames", scene.get("element_delay_frames", 6)),
                ),
                "motion": {
                    "preset": str(motion.get("preset", "zoom_in")),
                    "intensity": float(motion.get("intensity", 0.7)),
                },
            },
        )

    if not scenes:
        raise ValueError("no_scene_images for Remotion render")

    voice_src = None
    if voiceover_path and Path(voiceover_path).is_file():
        # Prefer data URI so headless Remotion can load without /data HTTP
        encoded = base64.b64encode(Path(voiceover_path).read_bytes()).decode("ascii")
        voice_src = f"data:audio/mpeg;base64,{encoded}"

    style = str(body.get("style") or "rico").lower()
    if style not in ("rico", "paper"):
        style = "rico"

    return {
        "scenes": scenes,
        "voiceoverSrc": voice_src,
        "titleText": body.get("title") or body.get("titleText") or "",
        "paperBackgroundOpacity": float(
            body.get("paper_background_opacity", 0 if style == "rico" else 0.12),
        ),
        "aspectLabel": body.get("aspect") or body.get("aspectLabel") or "9:16",
        "style": style,
        "showCaptions": bool(body.get("show_captions", body.get("showCaptions", False))),
        "crossfadeFrames": int(body.get("crossfade_frames", body.get("crossfadeFrames", 12))),
    }


def stage_edit(
    body: dict[str, Any],
    animate: dict[str, Any],
    voiceover_path: str | None,
) -> dict[str, Any]:
    props = build_flow_render_props(animate, voiceover_path, body)
    return {"props": props, "render": stage_render(props, body)}


# ─── Orchestrator ─────────────────────────────────────────────────────────────


def run_stickman_flow(body: dict[str, Any]) -> dict[str, Any]:
    """
    Run all flow stages. Body flags:
      stages: list of stage names to run (default all)
      auto_pick_topic: bool
      render: bool
      voice: bool
      skip_images / skip_animate / etc.
    """
    requested = body.get("stages")
    if isinstance(requested, str):
        requested = [s.strip() for s in requested.split(",") if s.strip()]
    all_stages = (
        "character_ref",
        "topics",
        "script",
        "scene_images",
        "animate",
        "voice",
        "edit",
    )
    stages_to_run = set(requested or all_stages)

    # Convenience: single stage overrides
    if body.get("stage"):
        stages_to_run = {str(body["stage"])}

    stages: dict[str, Any] = {}
    job = _job_dir(body)
    body = {**body, "job_id": job.name, "assets_dir": str(job.parent)}

    # Video-prompting agent: if a story/premise is given (and no explicit scenes),
    # let the prompter build the scene-by-scene plan before the normal stages.
    if (body.get("story") or body.get("premise") or body.get("use_prompter")) and not body.get("scenes"):
        from scripts.stickman_video_prompter import compose_video_prompts

        plan = compose_video_prompts(
            story=str(body.get("story") or ""),
            premise=str(body.get("premise") or ""),
            topic=str(body.get("topic") or body.get("topic_hint") or ""),
            scene_count=int(body.get("scene_count") or 0)
            or max(2, round(float(body.get("duration_secs") or 60) / float(body.get("clip_secs") or CLIP_SECS_DEFAULT))),
            duration_secs=float(body.get("duration_secs") or body.get("duration") or 60),
        )
        stages["prompter"] = {
            "success": plan.get("success"),
            "title": plan.get("title"),
            "logline": plan.get("logline"),
            "scene_count": plan.get("scene_count"),
            "source": plan.get("source"),
            "warning": plan.get("warning"),
        }
        if plan.get("scenes"):
            body["scenes"] = plan["scenes"]
            if plan.get("title") and not body.get("title"):
                body["title"] = plan["title"]
            if not body.get("topic"):
                body["topic"] = plan.get("title") or "Untitled"

    # 1. Character ref
    character_ref: dict[str, Any] = body.get("character_ref_result") or {}
    if "character_ref" in stages_to_run:
        character_ref = stage_character_ref(body)
        stages["character_ref"] = character_ref
        if not character_ref.get("success"):
            return _fail(stages, character_ref.get("error"), job)

    # 2. Topics
    topics_result: dict[str, Any] = {}
    if "topics" in stages_to_run or (
        "script" in stages_to_run and not body.get("topic") and not body.get("scenes")
    ):
        topics_result = stage_topics(body)
        stages["topics"] = topics_result
        if not topics_result.get("success"):
            return _fail(stages, topics_result.get("error"), job)

        if not body.get("auto_pick_topic") and not body.get("topic") and not body.get("scenes"):
            return {
                "ok": True,
                "success": True,
                "pipeline": "stickman_flow",
                "awaiting_topic": True,
                "job_id": job.name,
                "job_dir": str(job),
                "topics": topics_result.get("topics"),
                "stages": stages,
                "message": "Pick a topic, then POST again with topic=... and auto_pick_topic=false",
            }

    # 3. Script
    script: dict[str, Any] = body.get("script_result") or {}
    if "script" in stages_to_run:
        script = stage_script(body, topics_result)
        stages["script"] = script
        if script.get("awaiting_topic"):
            return {
                "ok": True,
                "success": True,
                "pipeline": "stickman_flow",
                "awaiting_topic": True,
                "job_id": job.name,
                "topics": script.get("topics") or topics_result.get("topics"),
                "stages": stages,
            }
        if not script.get("success"):
            return _fail(stages, script.get("error"), job)

    scenes = script.get("scenes") or body.get("scenes") or []

    # 4. Images
    images_result: dict[str, Any] = {"scenes": scenes}
    if "scene_images" in stages_to_run and scenes:
        images_result = stage_scene_images(body, script or {"scenes": scenes}, character_ref)
        stages["scene_images"] = images_result
        if not images_result.get("success"):
            return _fail(stages, images_result.get("error") or "scene_images_failed", job)

    # 5. Animate plan
    animate: dict[str, Any] = images_result
    if "animate" in stages_to_run:
        animate = stage_animate_plan(body, images_result)
        stages["animate"] = animate

    # 6. Voice
    voiceover_path = body.get("voiceover_path") or body.get("audio_path")
    if "voice" in stages_to_run and body.get("voice", True) and not voiceover_path:
        clean = stage_clean_narration(animate.get("scenes") or scenes, body)
        stages["narration"] = clean
        if not clean.get("success"):
            return _fail(stages, clean.get("error"), job)
        voice = stage_voice_flow(body, clean["narration"])
        stages["voice"] = voice
        if not voice.get("success"):
            return _fail(stages, voice.get("error"), job)
        voiceover_path = voice.get("output_path")

    # 7. Edit / render
    result: dict[str, Any] = {
        "ok": True,
        "success": True,
        "pipeline": "stickman_flow",
        "job_id": job.name,
        "job_dir": str(job),
        "voiceover_path": voiceover_path,
        "topic": script.get("topic") if script else body.get("topic"),
        "title": script.get("title") if script else None,
        "stages": stages,
        "engine": "remotion",
    }

    if "edit" in stages_to_run and body.get("render"):
        try:
            edit = stage_edit(body, animate, voiceover_path)
            stages["edit"] = edit
            render = edit.get("render") or {}
            result["filePath"] = render.get("filePath")
            result["durationSecs"] = render.get("durationSecs")
            result["fileSizeMb"] = render.get("fileSizeMb")
            result["render_props_preview"] = {
                "scene_count": len((edit.get("props") or {}).get("scenes") or []),
                "has_voiceover": bool((edit.get("props") or {}).get("voiceoverSrc")),
            }
            if not render.get("success", True):
                result["ok"] = False
                result["success"] = False
                result["error"] = render.get("error") or render.get("detail")
        except Exception as exc:
            result["ok"] = False
            result["success"] = False
            result["error"] = str(exc)
    elif "edit" in stages_to_run and not body.get("render"):
        try:
            props = build_flow_render_props(animate, voiceover_path, body)
            # Drop heavy data URIs from response preview
            preview_scenes = []
            for s in props.get("scenes") or []:
                preview_scenes.append(
                    {
                        "caption": s.get("caption"),
                        "durationInFrames": s.get("durationInFrames"),
                        "motion": s.get("motion"),
                        "hasImage": bool(s.get("imagePath")),
                    },
                )
            stages["edit"] = {
                "skipped_render": True,
                "props_preview": {
                    "scene_count": len(preview_scenes),
                    "scenes": preview_scenes,
                    "titleText": props.get("titleText"),
                },
            }
        except Exception as exc:
            stages["edit"] = {"skipped_render": True, "warning": str(exc)}

    # Persist job manifest for specialists / resume
    try:
        manifest = {
            "job_id": job.name,
            "topic": result.get("topic"),
            "title": result.get("title"),
            "voiceover_path": voiceover_path,
            "scenes": animate.get("scenes") or scenes,
            "character_ref_path": character_ref.get("character_ref_path"),
        }
        (job / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        result["manifest_path"] = str(job / "manifest.json")
    except Exception as exc:
        logger.warning("Could not write manifest: %s", exc)

    return result


def _fail(stages: dict[str, Any], error: Any, job: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "success": False,
        "pipeline": "stickman_flow",
        "job_id": job.name,
        "job_dir": str(job),
        "stages": stages,
        "error": error,
    }


# Thin stage entrypoints for specialist skills
def run_stage(stage: str, body: dict[str, Any]) -> dict[str, Any]:
    return run_stickman_flow({**body, "stage": stage, "stages": [stage]})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stickman Flow (DeepSeek + Remotion)")
    parser.add_argument("--body-json", default="")
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--topic-hint", default="why procrastination is useful")
    parser.add_argument("--topic", default="")
    parser.add_argument("--auto-pick-topic", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--no-voice", action="store_true")
    args = parser.parse_args()

    if args.body_json:
        req = json.loads(Path(args.body_json).read_text(encoding="utf-8"))
    else:
        req = {
            "duration_secs": args.duration,
            "topic_hint": args.topic_hint,
            "topic": args.topic,
            "auto_pick_topic": args.auto_pick_topic or not args.topic,
            "render": args.render,
            "voice": not args.no_voice,
        }

    print(json.dumps(run_stickman_flow(req), ensure_ascii=False, indent=2, default=str))
