"""Competitor style memory — learned from channel transcripts (e.g. AnimeInsider64).

Hermes (adaptive ops agent) owns refreshing this playbook. The anime-theory
scriptwriter loads it on every run so pacing/hooks match viral Shorts.
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, youtube_transcript

DEFAULT_CHANNEL = "@animeinsider64"

_HOOK_STARTERS = (
    "what if",
    "did you know",
    "everyone thinks",
    "most people",
    "here's why",
    "the real reason",
    "nobody talks",
    "wait",
    "so basically",
    "you think",
    "why does",
    "the truth",
)


def playbook_dir(channel: str | None = None) -> Path:
    handle = youtube_transcript._normalize_channel_handle(channel or DEFAULT_CHANNEL)
    d = config.PIPELINE_ROOT / "data" / "style-memory" / handle.lstrip("@").lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def playbook_path(channel: str | None = None) -> Path:
    return playbook_dir(channel) / "playbook.json"


def channel_scripts_dir(channel: str | None = None) -> Path:
    handle = youtube_transcript._normalize_channel_handle(channel or DEFAULT_CHANNEL)
    return (
        config.PIPELINE_ROOT
        / "data"
        / "reference-scripts"
        / "channels"
        / handle.lstrip("@").lower()
    )


def load_playbook(channel: str | None = None) -> dict[str, Any] | None:
    path = playbook_path(channel)
    if not path.is_file():
        # Fallback: any trained playbook
        root = config.PIPELINE_ROOT / "data" / "style-memory"
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


def build_playbook_from_dir(
    scripts_dir: Path | str,
    *,
    channel: str = DEFAULT_CHANNEL,
) -> dict[str, Any]:
    """Distill scraped .txt transcripts into a reusable style playbook."""
    base = Path(scripts_dir)
    scripts = youtube_transcript.list_english_scraped_scripts(base)
    if not scripts:
        raise youtube_transcript.TranscriptError(
            f"No English transcripts in {base} — scrape the channel first."
        )

    word_counts = [len(s.body.split()) for s in scripts]
    durations = [s.duration_s for s in scripts if s.duration_s]
    hooks: list[str] = []
    closers: list[str] = []
    exemplars: list[dict[str, Any]] = []

    for s in scripts:
        words = s.body.split()
        opening = " ".join(words[:18]).lower()
        closing = " ".join(words[-16:]).lower()
        for starter in _HOOK_STARTERS:
            if starter in opening:
                hooks.append(starter)
                break
        if closing:
            closers.append(closing[:80])
        exemplars.append(
            {
                "title": s.title,
                "url": s.url,
                "video_id": s.video_id,
                "words": len(words),
                "duration_s": s.duration_s,
                "anime": youtube_transcript.infer_anime_series(s.title, s.body),
                "path": str(s.path),
                "transcript": s.body,
                "opening": " ".join(words[:40]),
                "closing": " ".join(words[-30:]),
            }
        )

    # Keep a wide exemplar bank so topic matching has more JJK/Bleach/etc. options
    exemplars.sort(key=lambda e: abs(e["words"] - statistics.median(word_counts)))
    top = exemplars[:24]

    avg_words = round(statistics.mean(word_counts))
    med_words = round(statistics.median(word_counts))
    avg_dur = round(statistics.mean(durations), 1) if durations else None

    # Estimated Shorts build: ~2.6–3.0 spoken words/sec; ~28–36 words per visual beat
    wps = 2.8
    words_per_beat = 32
    est_seconds = round(med_words / wps, 1)
    est_scenes = max(8, min(16, round(med_words / words_per_beat)))

    series_counts: dict[str, int] = {}
    for e in exemplars:
        series = str(e.get("anime") or "Unknown")
        series_counts[series] = series_counts.get(series, 0) + 1

    title_shapes: dict[str, int] = {}
    for s in scripts:
        t = s.title.lower()
        shape = "other"
        if "?" in s.title:
            shape = "question_hook"
        elif re.search(r"\bwhy\b", t):
            shape = "why_explainer"
        elif re.search(r"\bvs\.?\b|versus", t):
            shape = "versus"
        elif re.search(r"\bsecret\b|\breal reason\b|\btruth\b", t):
            shape = "secret_reveal"
        elif re.search(r"\btop\b|\brank|\bstrongest\b|\bfinal\b", t):
            shape = "ranking"
        title_shapes[shape] = title_shapes.get(shape, 0) + 1

    hook_freq: dict[str, int] = {}
    for h in hooks:
        hook_freq[h] = hook_freq.get(h, 0) + 1
    top_hooks = sorted(hook_freq.items(), key=lambda x: -x[1])[:8]

    video_building = {
        "target_scenes": est_scenes,
        "words_per_scene": words_per_beat,
        "estimated_duration_s": est_seconds,
        "spoken_wps": wps,
        "title_shapes": [
            {"shape": k, "count": v}
            for k, v in sorted(title_shapes.items(), key=lambda x: -x[1])
        ],
        "series_mix": [
            {"anime": k, "count": v}
            for k, v in sorted(series_counts.items(), key=lambda x: -x[1])
        ],
        "visual_style_notes": (
            "One character-led panel per beat; rotate cast searchTerms; "
            "hook face on scene 1; lore proof faces in the middle; payoff face on closer."
        ),
    }

    style_brief = (
        f"Match @{channel.lstrip('@')} anime-lore Shorts exactly in PACING, not wording.\n"
        f"- Target spoken length: ~{med_words} words (avg {avg_words}"
        + (f", ~{avg_dur}s" if avg_dur else f", ~{est_seconds}s at {wps} wps")
        + ").\n"
        f"- Build ~{est_scenes} scenes (~{words_per_beat} words each).\n"
        f"- Hook in the first sentence (common openers: "
        + ", ".join(f"'{h}'" for h, _ in top_hooks[:4])
        + ").\n"
        f"- Common title shapes on this channel: "
        + ", ".join(f"{x['shape']}({x['count']})" for x in video_building["title_shapes"][:4])
        + ".\n"
        "- Fast TikTok cadence: short clauses, dense facts, almost no filler.\n"
        "- Structure: false assumption -> surprising answer early -> bust wrong reason "
        "-> stack lore proof -> emotional closer that fully answers the hook.\n"
        f"- Visual build: {video_building['visual_style_notes']}\n"
        "- Mirror the REFERENCE exemplar beat count and energy; write ORIGINAL lines "
        "for the new topic/series — never copy sentences.\n"
    )

    playbook = {
        "channel": youtube_transcript._normalize_channel_handle(channel),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "owner_agent": "hermes",
        "sample_count": len(scripts),
        "avg_words": avg_words,
        "median_words": med_words,
        "avg_duration_s": avg_dur,
        "word_count_p25": round(statistics.quantiles(word_counts, n=4)[0])
        if len(word_counts) >= 4
        else min(word_counts),
        "word_count_p75": round(statistics.quantiles(word_counts, n=4)[2])
        if len(word_counts) >= 4
        else max(word_counts),
        "top_hook_starters": [{"phrase": h, "count": c} for h, c in top_hooks],
        "video_building": video_building,
        "style_brief": style_brief,
        "exemplars": [
            {
                **{k: v for k, v in e.items() if k != "transcript"},
                "transcript_excerpt": e["transcript"][:1400],
            }
            for e in top
        ],
        "catalog": [
            {
                "title": e["title"],
                "video_id": e["video_id"],
                "words": e["words"],
                "anime": e["anime"],
                "path": e["path"],
                "url": e["url"],
            }
            for e in exemplars
        ],
        "scripts_dir": str(base),
    }
    return playbook


def save_playbook(playbook: dict[str, Any], *, channel: str | None = None) -> Path:
    ch = channel or str(playbook.get("channel") or DEFAULT_CHANNEL)
    path = playbook_path(ch)
    path.write_text(json.dumps(playbook, indent=2, ensure_ascii=False), encoding="utf-8")
    # Human-readable brief for agents
    md = playbook_dir(ch) / "STYLE_BRIEF.md"
    md.write_text(
        f"# Style brief — {playbook.get('channel')}\n\n"
        f"Trained: {playbook.get('trained_at')}\n"
        f"Owner agent: Hermes (adaptive)\n"
        f"Samples: {playbook.get('sample_count')}\n\n"
        f"{playbook.get('style_brief')}\n\n"
        "## Exemplar openings\n\n"
        + "\n".join(
            f"- **{e.get('title', '')[:60]}** ({e.get('words')}w): {e.get('opening', '')}"
            for e in (playbook.get("exemplars") or [])[:5]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def pick_reference_transcript(
    topic: str,
    *,
    anime: str = "",
    channel: str | None = None,
    max_chars: int = 3500,
) -> tuple[str, dict[str, Any] | None]:
    """Pick the best exemplar transcript for this topic (same series preferred)."""
    playbook = load_playbook(channel)
    if not playbook:
        return "", None

    needle = f"{topic} {anime}".lower()
    # Prefer full catalog (all scraped videos); fall back to exemplars bank
    pool = list(playbook.get("catalog") or []) or list(playbook.get("exemplars") or [])
    if not pool:
        return "", playbook

    def score(ex: dict[str, Any]) -> tuple:
        series = str(ex.get("anime") or "").lower()
        title = str(ex.get("title") or "").lower()
        series_hit = 2 if series and (
            series in needle or any(tok in needle for tok in series.split() if len(tok) > 3)
        ) else 0
        if anime and series and anime.lower() in series:
            series_hit = 3
        title_overlap = sum(
            1 for tok in re.findall(r"[a-z0-9]{4,}", title) if tok in needle
        )
        med = int(playbook.get("median_words") or 160)
        length_pen = abs(int(ex.get("words") or med) - med)
        return (series_hit, title_overlap, -length_pen)

    pool.sort(key=score, reverse=True)
    best = pool[0]
    path = best.get("path")
    text = ""
    if path and Path(path).is_file():
        try:
            text = youtube_transcript.load_reference(path, english_only=True)
        except Exception:  # noqa: BLE001
            text = str(best.get("transcript_excerpt") or "")
    else:
        text = str(best.get("transcript_excerpt") or "")
    if len(text) > max_chars:
        text = text[: max_chars - 3].rsplit(" ", 1)[0] + "..."
    meta = {
        "title": best.get("title"),
        "url": best.get("url"),
        "words": best.get("words"),
        "anime": best.get("anime"),
        "channel": playbook.get("channel"),
    }
    enriched = {**playbook, "selected_exemplar": meta}
    vb = playbook.get("video_building") or {}
    if vb.get("target_scenes"):
        enriched["target_scenes"] = vb["target_scenes"]
    return text, enriched


def format_style_block(playbook: dict[str, Any] | None) -> str:
    if not playbook:
        return ""
    ex = playbook.get("selected_exemplar") or {}
    vb = playbook.get("video_building") or {}
    lines = [
        "=== COMPETITOR STYLE MEMORY (Hermes-trained) ===",
        str(playbook.get("style_brief") or "").strip(),
    ]
    if vb:
        lines.append(
            f"VIDEO BUILD: ~{vb.get('target_scenes')} scenes, "
            f"~{vb.get('words_per_scene')} words/scene, "
            f"~{vb.get('estimated_duration_s')}s runtime. "
            f"{vb.get('visual_style_notes') or ''}"
        )
    if ex:
        lines.append(
            f"Selected exemplar: {ex.get('title')} ({ex.get('words')} words) "
            f"[{ex.get('url')}]"
        )
    lines.append("=== END STYLE MEMORY ===")
    return "\n".join(lines)


def train_channel(
    channel: str = DEFAULT_CHANNEL,
    *,
    limit: int = 25,
    max_duration_s: float = 180.0,
    scrape: bool = True,
) -> dict[str, Any]:
    """Scrape channel transcripts (optional) and rebuild the style playbook."""
    handle = youtube_transcript._normalize_channel_handle(channel)
    scripts_dir = channel_scripts_dir(handle)
    scrape_result = None
    if scrape:
        scrape_result = youtube_transcript.scrape_channel_scripts(
            handle,
            limit=limit,
            max_duration_s=max_duration_s,
            out_dir=scripts_dir,
            english_only=True,
        )
    playbook = build_playbook_from_dir(scripts_dir, channel=handle)
    path = save_playbook(playbook, channel=handle)
    print(f"Style playbook saved -> {path}", flush=True)
    print(
        f"  samples={playbook['sample_count']} median_words={playbook['median_words']} "
        f"avg_duration={playbook.get('avg_duration_s')}",
        flush=True,
    )
    return {
        "ok": True,
        "channel": handle,
        "playbook_path": str(path),
        "playbook": playbook,
        "scrape": scrape_result.to_dict() if scrape_result else None,
        "owner_agent": "hermes",
    }
