"""Background-music style memory — Hermes-trained from competitor scripts/titles.

Infers mood priors from channel titles + transcript cues (no audio download needed).
Consumed by generate_script + bg_music.resolve_music_src.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, style_memory, youtube_transcript

DEFAULT_CHANNEL = style_memory.DEFAULT_CHANNEL

# Title / body keywords → MUSIC_TAGS
_MOOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dark": (
        "dark", "death", "kill", "curse", "sukuna", "kenjaku", "hollow", "hell",
        "betray", "secret", "truth", "horror", "demon", "evil", "sacrifice",
    ),
    "uneasy": (
        "twist", "wrong", "never", "actually", "wait", "shock", "theory", "hidden",
        "lie", "fake", "copy",
    ),
    "sad": (
        "tragic", "tragedy", "die", "died", "death", "cry", "sad", "loss", "goodbye",
        "alone", "hurt",
    ),
    "melancholic": ("bittersweet", "memory", "past", "regret", "forgotten"),
    "hopeful": ("hope", "save", "power", "awaken", "rise", "win", "strongest"),
    "angry": ("rage", "angry", "brutal", "fight", "vs", "versus", "war", "destroy"),
    "excited": ("insane", "crazy", "buff", "op", "god", "final", "arc", "hype"),
    "contemplative": ("reason", "why", "philosophy", "name", "meaning", "real"),
}


def playbook_dir(channel: str | None = None) -> Path:
    handle = youtube_transcript._normalize_channel_handle(channel or DEFAULT_CHANNEL)
    d = config.PIPELINE_ROOT / "data" / "music-memory" / handle.lstrip("@").lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def playbook_path(channel: str | None = None) -> Path:
    return playbook_dir(channel) / "playbook.json"


def load_playbook(channel: str | None = None) -> dict[str, Any] | None:
    path = playbook_path(channel)
    if not path.is_file():
        root = config.PIPELINE_ROOT / "data" / "music-memory"
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


def infer_mood_from_text(title: str, body: str = "") -> str:
    blob = f"{title}\n{body}".lower()
    scores: Counter[str] = Counter()
    for mood, words in _MOOD_KEYWORDS.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", blob):
                scores[mood] += 1
    # Caption music markers often sit on lore beats → dark/uneasy beds
    music_cues = len(re.findall(r"\[music\]", body, flags=re.I))
    if music_cues >= 3:
        scores["dark"] += 2
        scores["uneasy"] += 1
    if not scores:
        return "dark"
    return scores.most_common(1)[0][0]


def build_playbook_from_scraped(
    scripts_dir: Path | str | None = None,
    *,
    channel: str = DEFAULT_CHANNEL,
) -> dict[str, Any]:
    handle = youtube_transcript._normalize_channel_handle(channel)
    scripts_dir = Path(scripts_dir or style_memory.channel_scripts_dir(handle))
    mood_counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

    for scraped in youtube_transcript.list_english_scraped_scripts(scripts_dir):
        mood = infer_mood_from_text(scraped.title, scraped.body)
        mood_counts[mood] += 1
        examples.append(
            {
                "video_id": scraped.video_id,
                "title": scraped.title,
                "mood": mood,
                "music_cues": len(re.findall(r"\[music\]", scraped.body, flags=re.I)),
                "anime": youtube_transcript.infer_anime_series(scraped.title, scraped.body),
            }
        )

    # Also fold style catalog titles if scripts_dir empty
    if not examples:
        pb = style_memory.load_playbook(handle) or {}
        for item in pb.get("catalog") or []:
            mood = infer_mood_from_text(str(item.get("title") or ""))
            mood_counts[mood] += 1
            examples.append(
                {
                    "video_id": item.get("video_id"),
                    "title": item.get("title"),
                    "mood": mood,
                    "music_cues": 0,
                    "anime": item.get("anime"),
                }
            )

    top = mood_counts.most_common()
    default_mood = top[0][0] if top else "dark"
    style_brief = (
        f"Match @{handle.lstrip('@')} lore-Short BGM taste.\n"
        f"- Default mood: {default_mood} (most common on channel).\n"
        f"- Mood mix: "
        + ", ".join(f"{m}({c})" for m, c in top[:6])
        + ".\n"
        "- Keep music under VO (~0.22–0.24 volume); cinematic ambient, not lyrical pop.\n"
        "- Prefer dark/uneasy/contemplative for theory twists; sad/melancholic for tragedy; "
        "angry/excited for VS / fight hooks.\n"
        "- Never drown narration; no comedy beds on death theories.\n"
    )

    return {
        "channel": handle,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "owner_agent": "hermes",
        "sample_count": len(examples),
        "default_mood": default_mood,
        "mood_priors": [{"mood": m, "count": c} for m, c in top],
        "allowed_tags": list(config.MUSIC_TAGS),
        "volume_target": float(getattr(config, "ANIME_MUSIC_VOLUME", 0.22) or 0.22),
        "style_brief": style_brief,
        "examples": examples[:40],
    }


def save_playbook(playbook: dict[str, Any], *, channel: str | None = None) -> Path:
    ch = channel or str(playbook.get("channel") or DEFAULT_CHANNEL)
    path = playbook_path(ch)
    path.write_text(json.dumps(playbook, indent=2, ensure_ascii=False), encoding="utf-8")
    md = playbook_dir(ch) / "MUSIC_BRIEF.md"
    md.write_text(
        f"# Music brief — {playbook.get('channel')}\n\n"
        f"Owner: Hermes\n"
        f"Trained: {playbook.get('trained_at')}\n"
        f"Samples: {playbook.get('sample_count')}\n"
        f"Default mood: **{playbook.get('default_mood')}**\n\n"
        f"{playbook.get('style_brief')}\n",
        encoding="utf-8",
    )
    return path


def pick_mood(
    topic: str,
    *,
    anime: str = "",
    script_music: str | None = None,
    channel: str | None = None,
) -> str:
    """Pick a MUSIC_TAGS mood: validate LLM choice, else score topic vs priors."""
    allowed = {t.lower() for t in config.MUSIC_TAGS}
    if script_music:
        key = script_music.strip().lower()
        if key in allowed:
            return key
    playbook = load_playbook(channel)
    inferred = infer_mood_from_text(topic, anime)
    if playbook:
        priors = {
            str(x["mood"]): int(x["count"])
            for x in (playbook.get("mood_priors") or [])
            if x.get("mood")
        }
        # Soft bias toward channel priors
        if inferred in priors:
            return inferred
        default = str(playbook.get("default_mood") or "dark")
        if default in allowed:
            # Prefer inferred if it's a valid tag; else channel default
            return inferred if inferred in allowed else default
    return inferred if inferred in allowed else "dark"


def format_music_block(playbook: dict[str, Any] | None) -> str:
    if not playbook:
        return ""
    return (
        "=== MUSIC STYLE MEMORY (Hermes-trained) ===\n"
        f"{playbook.get('style_brief') or ''}\n"
        f"Prefer mood tag from: {', '.join(playbook.get('allowed_tags') or config.MUSIC_TAGS)}\n"
        "=== END MUSIC STYLE MEMORY ==="
    )


def train_music(
    channel: str = DEFAULT_CHANNEL,
) -> dict[str, Any]:
    handle = youtube_transcript._normalize_channel_handle(channel)
    playbook = build_playbook_from_scraped(channel=handle)
    path = save_playbook(playbook, channel=handle)
    print(f"Music playbook saved -> {path}", flush=True)
    return {
        "ok": True,
        "channel": handle,
        "playbook_path": str(path),
        "default_mood": playbook.get("default_mood"),
        "sample_count": playbook.get("sample_count"),
        "playbook": playbook,
    }
