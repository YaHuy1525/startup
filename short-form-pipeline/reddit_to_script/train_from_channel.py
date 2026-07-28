"""Train the anime-theory scriptwriter from a competitor YouTube channel.

Scrapes captions via youtube-transcript-api / yt-dlp, then builds a Hermes-owned
style playbook used by ``generate_script.build_anime_theory_scenes``.

Examples:
  python -m reddit_to_script.train_from_channel --channel @animeinsider64
  python -m reddit_to_script.train_from_channel --channel @animeinsider64 --limit 30
  python -m reddit_to_script.train_from_channel --channel @animeinsider64 --rebuild-only
"""

from __future__ import annotations

import argparse
import json
import sys

from . import style_memory


def run(args: argparse.Namespace) -> int:
    result = style_memory.train_channel(
        args.channel,
        limit=args.limit,
        max_duration_s=args.max_duration,
        scrape=not args.rebuild_only,
    )
    # Compact stdout summary (full playbook on disk)
    summary = {
        "ok": result.get("ok"),
        "channel": result.get("channel"),
        "playbook_path": result.get("playbook_path"),
        "owner_agent": result.get("owner_agent"),
        "sample_count": (result.get("playbook") or {}).get("sample_count"),
        "median_words": (result.get("playbook") or {}).get("median_words"),
        "avg_words": (result.get("playbook") or {}).get("avg_words"),
        "avg_duration_s": (result.get("playbook") or {}).get("avg_duration_s"),
        "top_hooks": (result.get("playbook") or {}).get("top_hook_starters"),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if result.get("ok") else 1


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Learn script pacing from a YouTube channel (competitor reverse-engineer)."
    )
    parser.add_argument(
        "--channel",
        default=style_memory.DEFAULT_CHANNEL,
        help="Channel handle or URL (default: @animeinsider64)",
    )
    parser.add_argument("--limit", type=int, default=25, help="Max transcripts to pull")
    parser.add_argument(
        "--max-duration",
        type=float,
        default=180.0,
        help="Skip videos longer than this (seconds)",
    )
    parser.add_argument(
        "--rebuild-only",
        action="store_true",
        help="Do not re-scrape; rebuild playbook from existing channel .txt files",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(_main())
