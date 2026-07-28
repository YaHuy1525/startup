"""Train Hermes on ALL quality perspectives for a competitor channel.

Rebuilds from existing scraped data by default (YouTube transcript IP bans safe):
  - style-memory   (script writing + length)
  - edit-memory    (pacing, Ken Burns, VO, trim)
  - music-memory   (BGM mood priors)
  - thumbnail-memory (poster CTR; Remotion still specs)

Examples:
  python -m reddit_to_script.train_channel_quality --channel @animeinsider64
  python -m reddit_to_script.train_channel_quality --channel @animeinsider64 --scrape
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from . import edit_memory, music_memory, style_memory, thumbnail_memory, youtube_transcript


def train_all(
    channel: str = style_memory.DEFAULT_CHANNEL,
    *,
    limit: int = 80,
    max_duration_s: float = 180.0,
    scrape: bool = False,
    run_vision: bool = True,
) -> dict[str, Any]:
    handle = youtube_transcript._normalize_channel_handle(channel)
    print(f"=== Hermes channel quality train: {handle} ===", flush=True)
    print(f"  scrape={scrape} limit={limit} vision={run_vision}", flush=True)

    style = style_memory.train_channel(
        handle,
        limit=limit,
        max_duration_s=max_duration_s,
        scrape=scrape,
    )
    edit = edit_memory.train_edit(
        handle, style_playbook=style.get("playbook")
    )
    music = music_memory.train_music(handle)
    thumbs = thumbnail_memory.train_thumbnails(
        handle, limit=limit, run_vision=run_vision
    )

    summary = {
        "ok": all(
            bool(x.get("ok")) for x in (style, edit, music, thumbs)
        ),
        "channel": handle,
        "owner_agent": "hermes",
        "perspectives": {
            "script_style": {
                "path": style.get("playbook_path"),
                "sample_count": (style.get("playbook") or {}).get("sample_count"),
                "median_words": (style.get("playbook") or {}).get("median_words"),
            },
            "edit_pacing": {
                "path": edit.get("playbook_path"),
                "target_scenes": edit.get("target_scenes"),
                "estimated_duration_s": edit.get("estimated_duration_s"),
            },
            "music": {
                "path": music.get("playbook_path"),
                "default_mood": music.get("default_mood"),
                "sample_count": music.get("sample_count"),
            },
            "thumbnail": {
                "path": thumbs.get("playbook_path"),
                "thumbs_downloaded": thumbs.get("thumbs_downloaded"),
                "sample_count": thumbs.get("sample_count"),
            },
        },
    }
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Train Hermes on script + pacing + music + thumbnails for a channel."
    )
    parser.add_argument("--channel", default=style_memory.DEFAULT_CHANNEL)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--max-duration", type=float, default=180.0)
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="Also scrape new YouTube transcripts (may hit IP bans).",
    )
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="Skip OpenAI vision on thumbnail samples.",
    )
    args = parser.parse_args()
    result = train_all(
        args.channel,
        limit=args.limit,
        max_duration_s=args.max_duration,
        scrape=args.scrape,
        run_vision=not args.no_vision,
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_main())
