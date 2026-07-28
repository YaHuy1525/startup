"""Assemble an anime-theory Short from scenes (text + anime searchTerms).

Flow per scene:
  OpenAI TTS → mp3 + Whisper words
  AniList still (or Giphy anime clip) → downloaded under public/assets/<job>/
  Remotion ``AnimeTheory`` composition → MP4
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from . import anime_footage, config, tts
from .make_meme_video import _caption_tokens, _download, _mp4_duration_seconds

FPS = 30
COMPOSITION = "AnimeTheory"

_THEORY_VOICE_INSTRUCTIONS = (
    "Speak like a fast TikTok anime Shorts narrator — bright, punchy, urgent. "
    "Keep moving; almost no pauses between sentences. Speak quickly — denser than "
    "normal conversation. Not deep, not slow, not documentary. Clear emphasis on "
    "names and twists. Never laugh."
)


@dataclass
class SceneInput:
    text: str
    search_terms: list[str]
    anime: str = ""


def _ext_for(url: str, kind: str) -> str:
    if kind == "video":
        return ".mp4"
    lower = url.lower().split("?", 1)[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if lower.endswith(ext):
            return ext if ext != ".jpeg" else ".jpg"
    return ".jpg"


def build_assets(
    scenes: list[SceneInput],
    job_id: str,
    *,
    anime_hint: str = "",
    title: str | None = None,
    max_seconds: float | None = None,
    music_mood: str | None = None,
) -> dict:
    job_dir = config.ASSETS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    prev_instr = config.OPENAI_TTS_INSTRUCTIONS
    prev_provider = config.TTS_PROVIDER
    prev_auto_emo = config.NOIZ_AUTO_EMOTION
    config.OPENAI_TTS_INSTRUCTIONS = _THEORY_VOICE_INSTRUCTIONS
    # Prefer configured provider; only force Noiz when explicitly set
    if (config.TTS_PROVIDER or "").strip().lower() not in {"openai", "noiz"}:
        config.TTS_PROVIDER = "openai"
    # Auto emotion tags often add laughs/smiles — use manual emo for theory shorts.
    config.NOIZ_AUTO_EMOTION = False

    scene_props: list[dict] = []
    captions: list[dict] = []
    offset_s = 0.0
    used_ids: set[str] = set()
    used_urls: set[str] = set()
    cast_pool: list[str] = []
    for sc in scenes:
        for t in sc.search_terms or []:
            if t and t not in cast_pool:
                cast_pool.append(t)

    try:
        for i, scene in enumerate(scenes, start=1):
            audio_path = job_dir / f"scene-{i:02d}.mp3"
            print(f"  [{i}/{len(scenes)}] voicing ({config.TTS_PROVIDER}) + anime asset...", flush=True)
            sa = tts.voice_scene(scene.text, audio_path)
            hint = scene.anime or anime_hint
            asset = anime_footage.resolve_anime_asset(
                scene.search_terms,
                scene_text=scene.text,
                anime_hint=hint,
                used_ids=used_ids,
                used_urls=used_urls,
                prefer_video=False,
                scene_index=i - 1,
                cast_pool=cast_pool,
            )
            if asset.asset_id:
                used_ids.add(asset.asset_id)
                base = anime_footage._char_base_id(asset.asset_id)
                if base:
                    used_ids.add(base)
            if asset.url:
                used_urls.add(asset.url)

            ext = _ext_for(asset.url, asset.kind)
            media_path = job_dir / f"scene-{i:02d}{ext}"
            _download(asset.url, media_path)

            frames = max(1, math.ceil(sa.duration * FPS))
            clip_frames = 2 * FPS
            if asset.kind == "video":
                clip_seconds = _mp4_duration_seconds(media_path)
                clip_frames = max(1, round(clip_seconds * FPS)) if clip_seconds > 0 else 2 * FPS

            print(
                f"      {asset.source}/{asset.kind} query={asset.query_used!r} "
                f"title={asset.title[:40]!r}",
                flush=True,
            )
            prop: dict = {
                "audioSrc": f"assets/{job_id}/scene-{i:02d}.mp3",
                "mediaSrc": f"assets/{job_id}/scene-{i:02d}{ext}",
                "kind": asset.kind,
                "source": asset.source,
                "durationInFrames": frames,
            }
            if asset.kind == "video":
                prop["clipDurationInFrames"] = clip_frames
            scene_props.append(prop)
            captions.extend(_caption_tokens(sa.words, offset_s))
            offset_s += frames / FPS
    finally:
        config.OPENAI_TTS_INSTRUCTIONS = prev_instr
        config.TTS_PROVIDER = prev_provider
        config.NOIZ_AUTO_EMOTION = prev_auto_emo

    captions_path = job_dir / "captions.json"
    captions_path.write_text(json.dumps(captions, indent=2), encoding="utf-8")

    # Enforce duration budget (Hermes edit-memory: keep hook + closer when trimming).
    max_s = float(
        max_seconds
        if max_seconds is not None
        else getattr(config, "MAX_ANIME_THEORY_SECONDS", 90) or 90
    )
    max_frames = int(max_s * FPS)
    total = sum(s["durationInFrames"] for s in scene_props) + 12
    if total > max_frames and len(scene_props) > 3:
        print(f"  trimming scenes to fit under {max_s:g}s ({total/FPS:.1f}s raw)...", flush=True)
        trim_policy = "keep_hook_and_closer"
        try:
            from . import edit_memory

            ep = edit_memory.load_playbook()
            if ep and ep.get("trim_policy"):
                trim_policy = str(ep["trim_policy"])
        except Exception:  # noqa: BLE001
            pass

        if trim_policy == "keep_hook_and_closer" and len(scene_props) >= 4:
            hook = scene_props[0]
            closer = scene_props[-1]
            middle = scene_props[1:-1]
            kept = [hook]
            acc = hook["durationInFrames"]
            closer_frames = closer["durationInFrames"]
            for s in middle:
                if acc + s["durationInFrames"] + closer_frames + 12 > max_frames:
                    break
                kept.append(s)
                acc += s["durationInFrames"]
            kept.append(closer)
            acc += closer_frames
        else:
            kept = []
            acc = 0
            for s in scene_props:
                if acc + s["durationInFrames"] + 12 > max_frames and kept:
                    break
                kept.append(s)
                acc += s["durationInFrames"]
        end_ms = int((acc / FPS) * 1000)
        captions = [c for c in captions if int(c.get("startMs") or 0) < end_ms]
        captions_path.write_text(json.dumps(captions, indent=2), encoding="utf-8")
        scene_props = kept
        print(f"  kept {len(scene_props)} scenes (~{acc/FPS:.1f}s) policy={trim_policy}", flush=True)

    from . import bg_music

    music_src = bg_music.resolve_music_src(music_mood, title=title or "")
    if music_src:
        print(f"  bg music mood={music_mood or 'dark'!r} -> {music_src}", flush=True)
    else:
        print("  bg music: NONE (no track resolved)", flush=True)

    vol = float(getattr(config, "ANIME_MUSIC_VOLUME", 0.22) or 0.22)
    try:
        from . import edit_memory

        ep = edit_memory.load_playbook()
        if ep and (ep.get("music_edit") or {}).get("volume") is not None:
            vol = float(ep["music_edit"]["volume"])
    except Exception:  # noqa: BLE001
        pass
    return {
        "scenes": scene_props,
        "captionsSrc": f"assets/{job_id}/captions.json",
        "tailFrames": 12,
        "title": None,  # never burn-in title overlay
        "musicSrc": music_src,
        "musicVolume": vol,
    }


def render(props: dict, out_name: str, *, timeout: int = 1800) -> Path:
    config.MEME_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.MEME_OUT_DIR / out_name

    props_path = config.ASSETS_DIR / "_last_anime_theory_props.json"
    props_path.parent.mkdir(parents=True, exist_ok=True)
    props_path.write_text(json.dumps(props), encoding="utf-8")

    render_url = (
        os.getenv("SHORTFORM_RENDER_URL")
        or os.getenv("SHORTFORM_HOST_RENDER_URL")
        or ""
    ).strip()
    if not render_url and Path("/.dockerenv").exists():
        render_url = "http://shortform-render:3333/render"

    if render_url:
        try:
            payload = {
                "id": COMPOSITION,
                "inputProps": props,
                "filename": out_name,
                "download": False,
            }
            print(f"  rendering via {render_url} ({COMPOSITION}) -> {out_name} ...", flush=True)
            resp = requests.post(render_url, json=payload, timeout=timeout)
            if not resp.ok:
                raise RuntimeError(f"Host Remotion render failed {resp.status_code}: {resp.text[:300]}")
            body = resp.json()
            if not body.get("success"):
                raise RuntimeError(f"Host Remotion render error: {body.get('error') or body}")
            if out_path.exists():
                return out_path
            reported = body.get("file")
            if reported and Path(reported).exists():
                return Path(reported)
            raise RuntimeError(f"Host render succeeded but {out_path} is missing.")
        except Exception as exc:  # noqa: BLE001
            print(f"  host render failed ({exc}); falling back to local CLI...", flush=True)

    cmd = (
        f'npx remotion render "{config.REMOTION_ENTRY}" {COMPOSITION} '
        f'"{out_path}" --props="{props_path}" --concurrency=1 '
        f'--crf={int(getattr(config, "REMOTION_CRF", 23))} '
        f'--x264-preset={getattr(config, "REMOTION_X264_PRESET", "medium")} '
        f'--jpeg-quality={int(getattr(config, "REMOTION_JPEG_QUALITY", 80))}'
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


def make_video(
    scenes: list[SceneInput],
    *,
    out_name: str | None = None,
    anime_hint: str = "",
    title: str | None = None,
    max_seconds: float | None = None,
    render_timeout: int = 1800,
    music_mood: str | None = None,
) -> Path:
    from . import compress_video

    job_id = f"anime-{int(time.time())}"
    props = build_assets(
        scenes,
        job_id,
        anime_hint=anime_hint,
        title=title,
        max_seconds=max_seconds,
        music_mood=music_mood,
    )
    out_name = out_name or f"anime-theory-{job_id}.mp4"
    mp4 = render(props, out_name, timeout=render_timeout)
    # Keep Shorts under budget (default ~45MB) for upload + disk.
    max_mb = float(getattr(config, "MAX_VIDEO_MB", 45) or 45)
    mp4 = compress_video.ensure_under_max_mb(mp4, max_mb=max_mb)
    print(f"DONE -> {mp4} ({mp4.stat().st_size / 1_048_576:.2f} MB)", flush=True)
    return mp4
