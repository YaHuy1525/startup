"""End-to-end orchestrator: Reddit -> AI script -> short-video-maker -> MP4.

Examples:
    # Full run: 3 videos from r/tifu top-of-day
    python -m reddit_to_script.run --subreddit tifu --time day --count 3

    # Dry run: fetch + generate payloads, but don't render
    python -m reddit_to_script.run --subreddit AmItheAsshole --count 2 --dry-run
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import config
from . import fetch_reddit, generate_script, submit_video


def _save(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_seen(path: Path) -> set[str]:
    if path.exists():
        return set(json.loads(path.read_text(encoding="utf-8")))
    return set()


def run(args: argparse.Namespace) -> int:
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    seen_path = config.WORK_DIR / "processed_ids.json"
    seen = _load_seen(seen_path)

    print(f"Fetching top /r/{args.subreddit} ({args.time})...", flush=True)
    # Over-fetch so we can skip duplicates/short posts and still hit --count.
    stories = fetch_reddit.fetch_stories(
        args.subreddit, args.time, limit=args.count + args.skip_buffer
    )
    if not stories:
        print("No usable stories found.")
        return 1

    made = 0
    for story in stories:
        if made >= args.count:
            break
        key = story.url
        if key in seen and not args.allow_repeat:
            print(f"skip (already processed): {story.title[:60]}")
            continue

        print(f"\n=== Story: {story.title[:70]} ({story.upvotes} upvotes) ===", flush=True)
        try:
            payload = generate_script.build_payload(story, voice=args.voice)
        except Exception as exc:  # noqa: BLE001 - surface per-story failures, keep going
            print(f"  script generation failed: {exc}")
            continue

        stamp = time.strftime("%Y%m%d")
        slug = generate_script.slugify(story.title)
        payload_path = config.PAYLOAD_DIR / f"reddit-{args.subreddit}-{stamp}-{slug}.json"
        _save(payload, payload_path)
        print(f"  payload -> {payload_path.name} ({len(payload['scenes'])} scenes, "
              f"music={payload['config']['music']})")

        if args.dry_run:
            made += 1
            continue

        try:
            submit_video.render(payload, max_wait=args.max_wait)
        except Exception as exc:  # noqa: BLE001
            print(f"  render failed: {exc}")
            continue

        seen.add(key)
        _save(sorted(seen), seen_path)
        made += 1

    print(f"\nDone. {made} {'payload(s)' if args.dry_run else 'video(s)'} produced.")
    return 0 if made else 1


def _main() -> int:
    parser = argparse.ArgumentParser(description="Reddit -> AI script -> short video pipeline.")
    parser.add_argument("--subreddit", default="tifu")
    parser.add_argument("--time", default="day", choices=["hour", "day", "week", "month", "year", "all"])
    parser.add_argument("--count", type=int, default=1, help="How many videos to produce.")
    parser.add_argument("--voice", default=None, help=f"Override voice (default {config.DEFAULT_VOICE}).")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + generate payloads only.")
    parser.add_argument("--allow-repeat", action="store_true", help="Ignore the processed-ids dedupe list.")
    parser.add_argument("--skip-buffer", type=int, default=5, help="Extra posts to fetch for filtering.")
    parser.add_argument("--max-wait", type=int, default=900)
    args = parser.parse_args()

    try:
        return run(args)
    except config.ConfigError as exc:
        print(f"Config error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
