"""Assemble a meme-story video from scenes (text + searchTerms).

For each scene: OpenAI TTS -> mp3, OpenAI transcription -> word timings +
duration, and Giphy/Pexels -> background clip. Then a global TikTok-style
captions.json is written and Remotion renders the ``MemeStory`` composition.

Assets live in public/assets/<job_id>/ so Remotion's staticFile() can load them.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from . import config, footage, tts

# Must match src/short/theme.ts (FPS).
FPS = 30


@dataclass
class SceneInput:
    text: str
    search_terms: list[str]


def _caption_tokens(words: list[tts.Word], offset_s: float) -> list[dict]:
    """Convert scene-relative words to absolute-timed @remotion/captions tokens."""
    tokens: list[dict] = []
    for w in words:
        text = w.word.strip()
        if not text:
            continue
        start_ms = round((w.start + offset_s) * 1000)
        end_ms = round((w.end + offset_s) * 1000)
        tokens.append(
            {
                "text": f" {text}",
                "startMs": start_ms,
                "endMs": max(end_ms, start_ms + 1),
                "timestampMs": start_ms,
                "confidence": 1,
            }
        )
    return tokens


def _mp4_duration_seconds(path: Path) -> float:
    """Read an MP4's duration from its `mvhd` atom (no ffprobe needed).

    Returns 0.0 if the atom can't be parsed (caller falls back to a default).
    """
    try:
        data = path.read_bytes()
    except OSError:
        return 0.0
    idx = data.find(b"mvhd")
    if idx == -1:
        return 0.0
    p = idx + 4
    try:
        version = data[p]
        if version == 1:
            # version(1)+flags(3)+created(8)+modified(8) then timescale(4)+duration(8)
            timescale = int.from_bytes(data[p + 20 : p + 24], "big")
            duration = int.from_bytes(data[p + 24 : p + 32], "big")
        else:
            # version(1)+flags(3)+created(4)+modified(4) then timescale(4)+duration(4)
            timescale = int.from_bytes(data[p + 12 : p + 16], "big")
            duration = int.from_bytes(data[p + 16 : p + 20], "big")
        if timescale:
            return duration / timescale
    except (IndexError, ValueError):
        return 0.0
    return 0.0


def _download(url: str, out_path: Path, *, timeout: int = 60) -> Path:
    """Download a remote clip to a local file (Remotion renders local assets more reliably)."""
    resp = requests.get(url, stream=True, timeout=timeout)
    if not resp.ok:
        raise RuntimeError(f"Failed to download clip ({resp.status_code}): {url}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as fh:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            fh.write(chunk)
    return out_path


def build_assets(scenes: list[SceneInput], job_id: str) -> dict:
    """Produce audio + captions + footage, returning Remotion inputProps."""
    job_dir = config.ASSETS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    scene_props: list[dict] = []
    captions: list[dict] = []
    offset_s = 0.0
    used_meme_ids: set[str] = set()

    for i, scene in enumerate(scenes, start=1):
        audio_path = job_dir / f"scene-{i:02d}.mp3"
        print(f"  [{i}/{len(scenes)}] voicing + footage...", flush=True)
        sa = tts.voice_scene(scene.text, audio_path)
        clip = footage.resolve_clip(
            scene.search_terms,
            scene_text=scene.text,
            used_ids=used_meme_ids,
        )
        if clip.giphy_id:
            used_meme_ids.add(clip.giphy_id)
        clip_path = job_dir / f"scene-{i:02d}.mp4"
        _download(clip.url, clip_path)

        frames = max(1, math.ceil(sa.duration * FPS))
        clip_seconds = _mp4_duration_seconds(clip_path)
        clip_frames = max(1, round(clip_seconds * FPS)) if clip_seconds > 0 else 2 * FPS
        print(
            f"      footage={clip.source} query={clip.query_used!r} "
            f"reason={clip.reason[:60]!r}",
            flush=True,
        )
        scene_props.append(
            {
                "audioSrc": f"assets/{job_id}/scene-{i:02d}.mp3",
                "videoSrc": f"assets/{job_id}/scene-{i:02d}.mp4",
                "source": clip.source,
                "durationInFrames": frames,
                "clipDurationInFrames": clip_frames,
            }
        )
        captions.extend(_caption_tokens(sa.words, offset_s))
        offset_s += frames / FPS  # keep captions aligned to rounded scene lengths

    captions_path = job_dir / "captions.json"
    captions_path.write_text(json.dumps(captions, indent=2), encoding="utf-8")

    return {
        "scenes": scene_props,
        "captionsSrc": f"assets/{job_id}/captions.json",
        "tailFrames": 30,
    }


def _render_via_http(props: dict, out_name: str, render_url: str, *, timeout: int) -> Path:
    """Ask a host Remotion Express server to render (avoids Windows→Linux native binding issues)."""
    config.MEME_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.MEME_OUT_DIR / out_name
    payload = {
        "id": config.REMOTION_COMPOSITION,
        "inputProps": props,
        "filename": out_name,
        "download": False,
    }
    print(f"  rendering via {render_url} -> {out_name} ...", flush=True)
    resp = requests.post(render_url, json=payload, timeout=timeout)
    if not resp.ok:
        raise RuntimeError(f"Host Remotion render failed {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"Host Remotion render error: {body.get('error') or body}")
    # Server writes into short-form-pipeline/out (shared mount).
    if not out_path.exists():
        # Prefer reported path if present.
        reported = body.get("file")
        if reported and Path(reported).exists():
            return Path(reported)
        raise RuntimeError(f"Host render succeeded but {out_path} is missing.")
    return out_path


def render(props: dict, out_name: str, *, timeout: int = 1800) -> Path:
    """Render MemeStory via host HTTP (preferred in Docker) or local Remotion CLI."""
    import os

    config.MEME_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.MEME_OUT_DIR / out_name

    props_path = config.ASSETS_DIR / "_last_props.json"
    props_path.parent.mkdir(parents=True, exist_ok=True)
    props_path.write_text(json.dumps(props), encoding="utf-8")

    render_url = (
        os.getenv("SHORTFORM_RENDER_URL")
        or os.getenv("SHORTFORM_HOST_RENDER_URL")
        or ""
    ).strip()
    # Auto-detect Docker → prefer host Remotion server on the Windows host.
    if not render_url and Path("/.dockerenv").exists():
        render_url = "http://shortform-render:3333/render"

    if render_url:
        try:
            return _render_via_http(props, out_name, render_url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            print(f"  host render failed ({exc}); falling back to local CLI...", flush=True)

    cmd = (
        f'npx remotion render "{config.REMOTION_ENTRY}" {config.REMOTION_COMPOSITION} '
        f'"{out_path}" --props="{props_path}" --concurrency=1'
    )
    print(f"  rendering (local CLI) -> {out_path.name} ...", flush=True)
    result = subprocess.run(
        cmd, cwd=str(config.PIPELINE_ROOT), shell=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"Remotion render failed (exit {result.returncode}).")
    if not out_path.exists():
        raise RuntimeError(f"Render reported success but {out_path} is missing.")
    return out_path


def make_video(scenes: list[SceneInput], *, out_name: str | None = None) -> Path:
    """Full pipeline: scenes -> assets -> rendered MP4."""
    from . import compress_video

    job_id = f"job-{int(time.time())}"
    props = build_assets(scenes, job_id)
    out_name = out_name or f"meme-{job_id}.mp4"
    mp4 = render(props, out_name)
    mp4 = compress_video.ensure_under_max_mb(mp4)
    print(f"DONE -> {mp4} ({mp4.stat().st_size / 1_048_576:.2f} MB)", flush=True)
    return mp4
