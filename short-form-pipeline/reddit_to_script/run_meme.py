"""End-to-end: Reddit story -> AI script -> meme video (OpenAI voice + Giphy).

Uses OpenAI TTS for a human voiceover, Giphy memes (with Pexels fallback) for
footage, and Remotion for rendering — a fully custom path that replaces
short-video-maker (which supports neither custom footage nor custom voices).

Examples:
    python -m reddit_to_script.run_meme --subreddit tifu --time week --count 1
    python -m reddit_to_script.run_meme --subreddit AmItheAsshole --count 2 --dry-run
"""

from __future__ import annotations

import argparse
import json
import time

from . import config, fetch_reddit, generate_script, make_meme_video


def run(args: argparse.Namespace) -> int:
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    seen_path = config.WORK_DIR / "processed_meme_ids.json"
    seen = set(json.loads(seen_path.read_text(encoding="utf-8"))) if seen_path.exists() else set()

    print(f"Fetching top /r/{args.subreddit} ({args.time})...", flush=True)
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
        if story.url in seen and not args.allow_repeat:
            print(f"skip (already processed): {story.title[:60]}")
            continue

        print(f"\n=== Story: {story.title[:70]} ===", flush=True)
        try:
            scenes = generate_script.build_scenes(story, style="meme")
        except Exception as exc:  # noqa: BLE001
            print(f"  script generation failed: {exc}")
            continue

        inputs = [
            make_meme_video.SceneInput(text=s["text"], search_terms=s["searchTerms"])
            for s in scenes
        ]
        print(f"  {len(inputs)} scenes generated.")

        if args.dry_run:
            for j, s in enumerate(inputs, 1):
                print(f"    {j}. {s.text[:60]}  [{', '.join(s.search_terms)}]")
            made += 1
            continue

        slug = generate_script.slugify(story.title)
        out_name = f"meme-{args.subreddit}-{time.strftime('%Y%m%d')}-{slug}.mp4"
        try:
            make_meme_video.make_video(inputs, out_name=out_name)
        except Exception as exc:  # noqa: BLE001
            print(f"  render failed: {exc}")
            continue

        seen.add(story.url)
        seen_path.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")
        made += 1

    print(f"\nDone. {made} {'script(s)' if args.dry_run else 'video(s)'} produced.")
    return 0 if made else 1


def _main() -> int:
    parser = argparse.ArgumentParser(description="Reddit -> meme video (OpenAI voice + Giphy).")
    parser.add_argument("--subreddit", default="tifu")
    parser.add_argument("--time", default="week", choices=["hour", "day", "week", "month", "year", "all"])
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true", help="Fetch + script only; no assets/render.")
    parser.add_argument("--allow-repeat", action="store_true")
    parser.add_argument("--skip-buffer", type=int, default=5)
    args = parser.parse_args()

    try:
        return run(args)
    except config.ConfigError as exc:
        print(f"Config error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
