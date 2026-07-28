"""Thumbnail / poster style memory — separate from script style learning.

Owned by the **shortform-thumbnail** agent (Hermes refreshes the playbook).
Scriptwriter must NOT own poster design — different skill, different memory.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from . import config, style_memory, youtube_transcript

DEFAULT_CHANNEL = style_memory.DEFAULT_CHANNEL
_UA = {"User-Agent": "Mozilla/5.0 (compatible; anime-theory-pipeline/1.0)"}


def thumb_dir(channel: str | None = None) -> Path:
    handle = youtube_transcript._normalize_channel_handle(channel or DEFAULT_CHANNEL)
    d = (
        config.PIPELINE_ROOT
        / "data"
        / "thumbnail-memory"
        / handle.lstrip("@").lower()
        / "thumbs"
    )
    d.mkdir(parents=True, exist_ok=True)
    return d


def playbook_dir(channel: str | None = None) -> Path:
    handle = youtube_transcript._normalize_channel_handle(channel or DEFAULT_CHANNEL)
    d = config.PIPELINE_ROOT / "data" / "thumbnail-memory" / handle.lstrip("@").lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def playbook_path(channel: str | None = None) -> Path:
    return playbook_dir(channel) / "playbook.json"


def load_playbook(channel: str | None = None) -> dict[str, Any] | None:
    path = playbook_path(channel)
    if not path.is_file():
        root = config.PIPELINE_ROOT / "data" / "thumbnail-memory"
        if root.is_dir():
            for alt in sorted(root.glob("*/playbook.json")):
                try:
                    return json.loads(alt.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _thumb_urls(video_id: str) -> list[str]:
    # Prefer highest quality; fall through if 404
    return [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    ]


def download_thumbnail(video_id: str, *, channel: str | None = None) -> Path | None:
    """Download YouTube poster frame for a video id (no transcript API)."""
    out = thumb_dir(channel) / f"{video_id}.jpg"
    if out.exists() and out.stat().st_size > 5_000:
        return out
    for url in _thumb_urls(video_id):
        try:
            resp = requests.get(url, headers=_UA, timeout=30)
        except requests.RequestException:
            continue
        if not resp.ok or len(resp.content) < 5_000:
            continue
        # YouTube placeholder gray thumbs are tiny / fixed
        if len(resp.content) < 8_000 and b"hqdefault" in url.encode():
            continue
        out.write_bytes(resp.content)
        return out
    return None


def harvest_thumbnails_from_script_catalog(
    channel: str | None = None,
    *,
    limit: int = 80,
) -> list[dict[str, Any]]:
    """Pull posters for videos already in the script style catalog."""
    script_pb = style_memory.load_playbook(channel)
    catalog = list((script_pb or {}).get("catalog") or [])
    if not catalog:
        # Fall back to scraped txt headers
        scripts_dir = style_memory.channel_scripts_dir(channel)
        for scraped in youtube_transcript.list_english_scraped_scripts(scripts_dir):
            if scraped.video_id:
                catalog.append(
                    {
                        "video_id": scraped.video_id,
                        "title": scraped.title,
                        "anime": youtube_transcript.infer_anime_series(
                            scraped.title, scraped.body
                        ),
                        "url": scraped.url,
                        "words": len(scraped.body.split()),
                    }
                )

    rows: list[dict[str, Any]] = []
    for item in catalog[:limit]:
        vid = str(item.get("video_id") or "").strip()
        if not vid:
            continue
        path = download_thumbnail(vid, channel=channel)
        rows.append(
            {
                "video_id": vid,
                "title": item.get("title"),
                "anime": item.get("anime"),
                "url": item.get("url"),
                "words": item.get("words"),
                "thumb_path": str(path) if path else None,
                "ok": bool(path),
            }
        )
        time.sleep(0.15)
    return rows


def _title_overlay_guess(title: str) -> dict[str, Any]:
    """Heuristic: what short text would appear on a lore Short poster."""
    raw = re.sub(r"#\w+", "", title or "")
    raw = re.sub(r"\s+", " ", raw).strip()
    # Drop trailing emoji spam / pipes
    raw = re.split(r"\|\||\|", raw)[0].strip()
    words = raw.split()
    # Short overlay: first 3–5 punchy words, prefer question / WHY / VS
    overlay_words = words[:5]
    if len(words) > 5 and words[0].lower() in {"the", "a", "an"}:
        overlay_words = words[1:6]
    overlay = " ".join(overlay_words)
    if len(overlay) > 42:
        overlay = " ".join(overlay_words[:4])
    shape = "statement"
    low = raw.lower()
    if "?" in raw:
        shape = "question"
    elif re.search(r"\bvs\.?\b", low):
        shape = "versus"
    elif re.search(r"\bwhy\b", low):
        shape = "why"
    elif re.search(r"\bsecret\b|\btruth\b|\breal reason\b", low):
        shape = "reveal"
    elif re.search(r"\btop\b|\brank|\bstrongest\b|\bfinal\b", low):
        shape = "ranking"
    return {
        "full_title": raw,
        "overlay_text": overlay,
        "overlay_word_count": len(overlay.split()),
        "shape": shape,
    }


def _vision_style_notes(thumb_paths: list[Path], *, max_n: int = 4) -> str:
    """Optional OpenAI vision pass to distill poster look (faces, text, colors)."""
    api_key = getattr(config, "OPENAI_API_KEY", "") or ""
    if not api_key:
        return ""
    samples = [p for p in thumb_paths if p.is_file()][:max_n]
    if not samples:
        return ""
    import base64

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "These are YouTube Short thumbnails from a viral anime-lore channel. "
                "In 8-12 bullet points, describe the SHARED poster style for an agent "
                "to recreate: face framing, expression, text placement/size, colors, "
                "borders, character count, vs-layout, and what to avoid. Be concrete."
            ),
        }
    ]
    for path in samples:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )
    try:
        resp = requests.post(
            f"{config.OPENAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.resolved_llm_model()
                if "gpt-4" in (config.LLM_MODEL or "")
                else "gpt-4o-mini",
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 700,
                "temperature": 0.3,
            },
            timeout=120,
        )
        if not resp.ok:
            print(f"  [thumb] vision failed {resp.status_code}", flush=True)
            return ""
        return str(resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"  [thumb] vision error: {exc}", flush=True)
        return ""


def build_playbook(
    harvested: list[dict[str, Any]],
    *,
    channel: str = DEFAULT_CHANNEL,
    run_vision: bool = True,
) -> dict[str, Any]:
    ok_rows = [r for r in harvested if r.get("ok")]
    overlays = [_title_overlay_guess(str(r.get("title") or "")) for r in harvested]
    shape_counts = Counter(o["shape"] for o in overlays)
    series_counts = Counter(str(r.get("anime") or "Unknown") for r in harvested)
    overlay_lens = [o["overlay_word_count"] for o in overlays if o["overlay_word_count"]]

    thumb_paths = [
        Path(r["thumb_path"]) for r in ok_rows if r.get("thumb_path")
    ]
    vision_notes = _vision_style_notes(thumb_paths) if run_vision else ""

    med_overlay = (
        sorted(overlay_lens)[len(overlay_lens) // 2] if overlay_lens else 4
    )

    style_brief = (
        f"Match @{channel.lstrip('@')} YouTube Short POSTER / thumbnail style.\n"
        f"- Ratio: 16:9 YouTube (1280x720) primary; also export 9:16 crop for Shorts cover.\n"
        f"- Overlay text: ~{med_overlay} words, huge bold, high contrast, max 1 line if possible.\n"
        f"- Dominant title shapes: "
        + ", ".join(f"{k}({v})" for k, v in shape_counts.most_common(4))
        + ".\n"
        "- Usually 1–2 character faces, extreme close-up, shocked/intense expression.\n"
        "- High saturation, dark vignette, optional VS split or big contrast color.\n"
        "- Text away from bottom-right (YouTube timestamp). Never tiny captions.\n"
        "- Subject from the script's lead cast; do not invent off-series characters.\n"
    )
    if vision_notes:
        style_brief += f"\nVision notes from real channel thumbs:\n{vision_notes}\n"

    playbook = {
        "channel": youtube_transcript._normalize_channel_handle(channel),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "owner_agent": "shortform-thumbnail",
        "refreshed_by": "hermes",
        "sample_count": len(harvested),
        "thumbs_downloaded": len(ok_rows),
        "median_overlay_words": med_overlay,
        "title_shapes": [{"shape": k, "count": v} for k, v in shape_counts.most_common()],
        "series_mix": [{"anime": k, "count": v} for k, v in series_counts.most_common()],
        "style_brief": style_brief,
        "vision_notes": vision_notes,
        "specs": {
            "youtube_px": [1280, 720],
            "shorts_cover_px": [1080, 1920],
            "max_overlay_words": 5,
            "faces": "1-2 close-up",
        },
        "examples": [
            {
                "video_id": r.get("video_id"),
                "title": r.get("title"),
                "anime": r.get("anime"),
                "thumb_path": r.get("thumb_path"),
                "overlay": _title_overlay_guess(str(r.get("title") or "")),
            }
            for r in ok_rows[:30]
        ],
        "thumbs_dir": str(thumb_dir(channel)),
    }
    return playbook


def save_playbook(playbook: dict[str, Any], *, channel: str | None = None) -> Path:
    ch = channel or str(playbook.get("channel") or DEFAULT_CHANNEL)
    path = playbook_path(ch)
    path.write_text(json.dumps(playbook, indent=2, ensure_ascii=False), encoding="utf-8")
    md = playbook_dir(ch) / "THUMBNAIL_BRIEF.md"
    md.write_text(
        f"# Thumbnail brief — {playbook.get('channel')}\n\n"
        f"Owner agent: **shortform-thumbnail** (Hermes refreshes)\n"
        f"Trained: {playbook.get('trained_at')}\n"
        f"Samples: {playbook.get('sample_count')} "
        f"({playbook.get('thumbs_downloaded')} images)\n\n"
        f"{playbook.get('style_brief')}\n",
        encoding="utf-8",
    )
    return path


def format_thumb_brief(playbook: dict[str, Any] | None) -> str:
    if not playbook:
        return ""
    return (
        "=== THUMBNAIL STYLE MEMORY (shortform-thumbnail agent) ===\n"
        f"{playbook.get('style_brief') or ''}\n"
        f"Specs: {json.dumps(playbook.get('specs') or {})}\n"
        "=== END THUMBNAIL STYLE MEMORY ==="
    )


def propose_thumbnail(
    topic: str,
    *,
    anime: str = "",
    scene_hook: str = "",
    channel: str | None = None,
) -> dict[str, Any]:
    """Return thumbnail concepts matching the learned channel poster style."""
    playbook = load_playbook(channel)
    brief = format_thumb_brief(playbook)
    hook = (scene_hook or topic).strip()
    overlay = _title_overlay_guess(hook)
    # Prefer shorter punchier overlay for posters
    concepts = [
        {
            "id": "A",
            "overlay_text": overlay["overlay_text"],
            "layout": "single_face_closeup",
            "notes": "Lead character extreme close-up, shocked eyes, text top-left",
        },
        {
            "id": "B",
            "overlay_text": overlay["overlay_text"],
            "layout": "versus_split",
            "notes": "Two faces left/right if topic is a matchup; bold VS center",
        },
        {
            "id": "C",
            "overlay_text": " ".join(overlay["overlay_text"].split()[:3]),
            "layout": "face_plus_prop",
            "notes": "Character + one lore prop/symbol; max 3-word text",
        },
    ]
    return {
        "ok": True,
        "agent": "shortform-thumbnail",
        "topic": topic,
        "anime": anime,
        "style_channel": (playbook or {}).get("channel"),
        "style_brief": brief,
        "concepts": concepts,
        "recommended": "A",
        "specs": (playbook or {}).get("specs")
        or {"youtube_px": [1280, 720], "max_overlay_words": 5},
    }


def render_thumbnail_still(
    *,
    image_src: str,
    overlay_text: str,
    layout: str = "single_face_closeup",
    out_name: str | None = None,
    accent_color: str = "#FFCC00",
) -> Path:
    """Render AnimeTheoryThumbnail via Remotion still (1280×720 JPEG)."""
    import os
    import subprocess

    config.MEME_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.MEME_OUT_DIR / (out_name or f"thumb-{int(time.time())}.jpg")
    props = {
        "imageSrc": image_src,
        "overlayText": overlay_text[:48],
        "layout": layout,
        "accentColor": accent_color,
        "vignette": True,
    }
    props_path = config.ASSETS_DIR / "_last_thumbnail_props.json"
    props_path.parent.mkdir(parents=True, exist_ok=True)
    props_path.write_text(json.dumps(props), encoding="utf-8")
    cmd = (
        f'npx remotion still "{config.REMOTION_ENTRY}" AnimeTheoryThumbnail '
        f'"{out_path}" --props="{props_path}" --frame=0 --image-format=jpeg --jpeg-quality=92'
    )
    print(f"  rendering thumbnail still -> {out_path.name} ...", flush=True)
    result = subprocess.run(
        cmd, cwd=str(config.PIPELINE_ROOT), shell=True, timeout=600
    )
    if result.returncode != 0:
        raise RuntimeError(f"Remotion still failed (exit {result.returncode})")
    if not out_path.exists():
        raise RuntimeError(f"Thumbnail missing: {out_path}")
    return out_path


def train_thumbnails(
    channel: str = DEFAULT_CHANNEL,
    *,
    limit: int = 80,
    run_vision: bool = True,
) -> dict[str, Any]:
    handle = youtube_transcript._normalize_channel_handle(channel)
    print(f"Harvesting thumbnails for {handle} (limit {limit})...", flush=True)
    harvested = harvest_thumbnails_from_script_catalog(handle, limit=limit)
    ok = sum(1 for r in harvested if r.get("ok"))
    print(f"  downloaded {ok}/{len(harvested)} posters", flush=True)
    playbook = build_playbook(harvested, channel=handle, run_vision=run_vision)
    path = save_playbook(playbook, channel=handle)
    print(f"Thumbnail playbook saved -> {path}", flush=True)
    return {
        "ok": True,
        "channel": handle,
        "playbook_path": str(path),
        "thumbs_downloaded": ok,
        "sample_count": len(harvested),
        "owner_agent": "shortform-thumbnail",
        "playbook": playbook,
    }
