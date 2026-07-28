#!/usr/bin/env python3
"""
Storyboard planner for viral stickman / Canva animations.

Splits a script into scene beats (split on sentence boundaries when context shifts)
and emits Canva search hints matching the tutorial workflow (@zidansasc library).
"""
from __future__ import annotations

import re
from typing import Any

# Tutorial: search @zidansasc in Canva Elements for consistent stick figures
CANVA_ARTIST_TAG = "@zidansasc"

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_script_to_beats(script: str, max_scenes: int = 24) -> list[str]:
    text = " ".join(script.strip().split())
    if not text:
        return []

    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    if not sentences:
        return [text]

    # Merge very short fragments
    beats: list[str] = []
    buffer = ""
    for sentence in sentences:
        if not buffer:
            buffer = sentence
            continue
        if len(buffer) < 40 and len(beats) < max_scenes - 1:
            buffer = f"{buffer} {sentence}"
        else:
            beats.append(buffer)
            buffer = sentence
    if buffer:
        beats.append(buffer)

    return beats[:max_scenes]


def _canva_search_hint(beat: str) -> str:
    lower = beat.lower()
    hints = [
        ("sad", "unhappy stick figure"),
        ("happy", "happy stick figure"),
        ("question", "stick figure question"),
        ("computer", "stick figure computer"),
        ("money", "stick figure money"),
        ("angry", "angry stick figure"),
        ("think", "stick figure thinking"),
        ("love", "stick figure heart"),
        ("run", "stick figure running"),
        ("win", "stick figure celebration"),
    ]
    for keyword, hint in hints:
        if keyword in lower:
            return f"{CANVA_ARTIST_TAG} {hint}"
    return f"{CANVA_ARTIST_TAG} stick figure"


def plan_storyboard(script: str, *, max_scenes: int = 24) -> dict[str, Any]:
    beats = split_script_to_beats(script, max_scenes=max_scenes)
    scenes = []
    for index, beat in enumerate(beats):
        scenes.append(
            {
                "index": index,
                "narration": beat,
                "caption": beat if len(beat) <= 120 else beat[:117] + "...",
                "canva_element_search": _canva_search_hint(beat),
                "canva_timing_tip": "Right-click → Show element timing; stagger purple bar to match words",
            },
        )

    return {
        "scene_count": len(scenes),
        "scenes": scenes,
        "canva_setup": {
            "canvas": "9:16 for Shorts/TikTok or 16:9 for YouTube",
            "background": "Search Images → paper background → lower transparency",
            "elements": f"Elements tab → search {CANVA_ARTIST_TAG} for consistent stick figures",
            "split_scenes": "Play audio; press S when the sentence context changes",
            "fonts": "Handwritten fonts e.g. Chewy for emphasis text",
            "tutorial": "https://youtu.be/b2k4xoXv3S4",
        },
    }


def allocate_scene_durations(
    scene_count: int,
    total_duration_secs: float,
    fps: int = 30,
    min_scene_secs: float = 1.5,
) -> list[int]:
    if scene_count <= 0:
        return []
    min_frames = max(int(min_scene_secs * fps), 15)
    total_frames = max(int(total_duration_secs * fps), scene_count * min_frames)
    per_scene = max(min_frames, total_frames // scene_count)
    durations = [per_scene] * scene_count
    remainder = total_frames - per_scene * scene_count
    for i in range(remainder):
        durations[i % scene_count] += 1
    return durations


def resolve_scene_images(
    scenes: list[dict[str, Any]],
    assets_dir: str,
) -> list[dict[str, Any]]:
    """
    Map storyboard scenes to PNG/JPG files in assets_dir (scene-01.png, 02, ... or listed paths).
    """
    from pathlib import Path

    root = Path(assets_dir)
    if not root.is_dir():
        return scenes

    files = sorted(
        [
            p
            for p in root.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ],
    )
    resolved: list[dict[str, Any]] = []
    for i, scene in enumerate(scenes):
        item = dict(scene)
        if scene.get("imagePath") or scene.get("image_path"):
            item["imagePath"] = scene.get("imagePath") or scene.get("image_path")
        elif i < len(files):
            item["imagePath"] = str(files[i].resolve())
        resolved.append(item)
    return resolved
