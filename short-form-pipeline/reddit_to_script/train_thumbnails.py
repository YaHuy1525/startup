"""Train the thumbnail agent from competitor YouTube posters.

Uses video IDs already scraped for script learning — downloads maxres thumbnails
and builds a separate playbook (NOT mixed into script style memory).

Examples:
  python -m reddit_to_script.train_thumbnails --channel @animeinsider64
  python -m reddit_to_script.train_thumbnails --channel @animeinsider64 --no-vision
"""

from __future__ import annotations

import argparse
import json

from . import thumbnail_memory


def run(args: argparse.Namespace) -> int:
    result = thumbnail_memory.train_thumbnails(
        args.channel,
        limit=args.limit,
        run_vision=not args.no_vision,
    )
    summary = {
        "ok": result.get("ok"),
        "channel": result.get("channel"),
        "playbook_path": result.get("playbook_path"),
        "owner_agent": result.get("owner_agent"),
        "thumbs_downloaded": result.get("thumbs_downloaded"),
        "sample_count": result.get("sample_count"),
        "median_overlay_words": (result.get("playbook") or {}).get("median_overlay_words"),
        "title_shapes": (result.get("playbook") or {}).get("title_shapes"),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if result.get("ok") else 1


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Learn YouTube thumbnail/poster style from a channel (separate agent)."
    )
    parser.add_argument(
        "--channel",
        default=thumbnail_memory.DEFAULT_CHANNEL,
        help="Channel handle (default @animeinsider64)",
    )
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="Skip OpenAI vision distillation of poster look",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(_main())
