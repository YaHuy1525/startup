"""Edit / pacing / visual style memory — Hermes-trained for Remotion AnimeTheory.

Captures competitor beat density, Ken Burns habits, VO pace, and trim rules.
Separate from script wording (style_memory) and poster CTR (thumbnail_memory).
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, style_memory, youtube_transcript

DEFAULT_CHANNEL = style_memory.DEFAULT_CHANNEL

# Remotion AnimeTheory Ken Burns cycle (must stay in sync with AnimeTheory.tsx)
KEN_BURNS_CYCLE = ("zoom_in", "pan_left", "zoom_out", "pan_right")


def playbook_dir(channel: str | None = None) -> Path:
    handle = youtube_transcript._normalize_channel_handle(channel or DEFAULT_CHANNEL)
    d = config.PIPELINE_ROOT / "data" / "edit-memory" / handle.lstrip("@").lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def playbook_path(channel: str | None = None) -> Path:
    return playbook_dir(channel) / "playbook.json"


def load_playbook(channel: str | None = None) -> dict[str, Any] | None:
    path = playbook_path(channel)
    if not path.is_file():
        root = config.PIPELINE_ROOT / "data" / "edit-memory"
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


def build_playbook(
    *,
    channel: str = DEFAULT_CHANNEL,
    style_playbook: dict[str, Any] | None = None,
) -> dict[str, Any]:
    handle = youtube_transcript._normalize_channel_handle(channel)
    style = style_playbook or style_memory.load_playbook(handle) or {}
    vb = style.get("video_building") or {}
    med = int(style.get("median_words") or vb.get("median_words") or 267)
    wps = float(vb.get("spoken_wps") or 2.8)
    words_per_scene = int(vb.get("words_per_scene") or 32)
    target_scenes = int(vb.get("target_scenes") or max(8, round(med / words_per_scene)))
    est_s = float(vb.get("estimated_duration_s") or round(med / wps, 1))

    # Per-scene spoken length from exemplars (opening/closing density proxy)
    cue_rates: list[float] = []
    scripts_dir = style_memory.channel_scripts_dir(handle)
    for scraped in youtube_transcript.list_english_scraped_scripts(scripts_dir):
        words = len(scraped.body.split()) or 1
        cues = scraped.body.lower().count("[music]")
        cue_rates.append(cues / max(words / 100.0, 1.0))
    median_music_cues_per_100w = (
        statistics.median(cue_rates) if cue_rates else 1.5
    )

    style_brief = (
        f"Match @{handle.lstrip('@')} Remotion edit / pacing for anime-lore Shorts.\n"
        f"- Target runtime ~{est_s}s spoken (~{med} words @ {wps} wps).\n"
        f"- ~{target_scenes} scenes, ~{words_per_scene} words each; one face/panel per beat.\n"
        f"- VO: fast TikTok narrator, almost no pauses; bright not deep.\n"
        f"- Visuals: stills with Ken Burns cycle {list(KEN_BURNS_CYCLE)}; "
        "prefer character close-ups over series banners once a face is used.\n"
        f"- Music sting density proxy: ~{median_music_cues_per_100w:.1f} [music] cues / 100 words "
        "(cut on lore beats, not every sentence).\n"
        "- Structure on timeline: hook face → lore proof faces → payoff face.\n"
        "- If over duration budget, trim middle lore — keep hook + closer.\n"
        "- Captions: large, bottom-safe; no burned-in title unless requested.\n"
        f"- Max Short budget: {getattr(config, 'MAX_ANIME_THEORY_SECONDS', 90)}s "
        f"(long form {getattr(config, 'MAX_ANIME_THEORY_LONG_SECONDS', 180)}s).\n"
    )

    return {
        "channel": handle,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "owner_agent": "hermes",
        "sample_count": int(style.get("sample_count") or 0),
        "pacing": {
            "median_words": med,
            "spoken_wps": wps,
            "target_scenes": target_scenes,
            "words_per_scene": words_per_scene,
            "estimated_duration_s": est_s,
            "word_count_p25": style.get("word_count_p25"),
            "word_count_p75": style.get("word_count_p75"),
            "max_seconds_short": float(
                getattr(config, "MAX_ANIME_THEORY_SECONDS", 90) or 90
            ),
        },
        "visuals": {
            "ken_burns_cycle": list(KEN_BURNS_CYCLE),
            "prefer_character_stills": True,
            "one_panel_per_beat": True,
            "hook_face_scene_1": True,
            "payoff_face_closer": True,
            "notes": vb.get("visual_style_notes")
            or "One character-led panel per beat; rotate cast searchTerms.",
        },
        "voice": {
            "provider_hint": "noiz",
            "speed_hint": float(getattr(config, "NOIZ_SPEED", 1.35) or 1.35),
            "instructions": (
                "Speak like a fast TikTok anime Shorts narrator — bright, punchy, urgent. "
                "Keep moving; almost no pauses between sentences. Not deep, not slow."
            ),
        },
        "music_edit": {
            "volume": float(getattr(config, "ANIME_MUSIC_VOLUME", 0.22) or 0.22),
            "median_music_cues_per_100w": round(median_music_cues_per_100w, 2),
        },
        "trim_policy": "keep_hook_and_closer",
        "style_brief": style_brief,
        "title_shapes": vb.get("title_shapes") or style.get("title_shapes"),
        "series_mix": vb.get("series_mix") or style.get("series_mix"),
    }


def save_playbook(playbook: dict[str, Any], *, channel: str | None = None) -> Path:
    ch = channel or str(playbook.get("channel") or DEFAULT_CHANNEL)
    path = playbook_path(ch)
    path.write_text(json.dumps(playbook, indent=2, ensure_ascii=False), encoding="utf-8")
    md = playbook_dir(ch) / "EDIT_BRIEF.md"
    md.write_text(
        f"# Edit / pacing brief — {playbook.get('channel')}\n\n"
        f"Owner: Hermes\n"
        f"Trained: {playbook.get('trained_at')}\n\n"
        f"{playbook.get('style_brief')}\n",
        encoding="utf-8",
    )
    return path


def format_edit_block(playbook: dict[str, Any] | None) -> str:
    if not playbook:
        return ""
    return (
        "=== EDIT / PACING MEMORY (Hermes-trained) ===\n"
        f"{playbook.get('style_brief') or ''}\n"
        f"Trim policy: {playbook.get('trim_policy')}\n"
        "=== END EDIT / PACING MEMORY ==="
    )


def train_edit(
    channel: str = DEFAULT_CHANNEL,
    *,
    style_playbook: dict[str, Any] | None = None,
) -> dict[str, Any]:
    handle = youtube_transcript._normalize_channel_handle(channel)
    playbook = build_playbook(channel=handle, style_playbook=style_playbook)
    path = save_playbook(playbook, channel=handle)
    print(f"Edit playbook saved -> {path}", flush=True)
    return {
        "ok": True,
        "channel": handle,
        "playbook_path": str(path),
        "target_scenes": (playbook.get("pacing") or {}).get("target_scenes"),
        "estimated_duration_s": (playbook.get("pacing") or {}).get("estimated_duration_s"),
        "sample_count": playbook.get("sample_count"),
        "playbook": playbook,
    }
