"""CLI: anime theory topic → script → AniList visuals → Remotion MP4.

Examples:
  python -m reddit_to_script.run_anime_theory --topic "Why Old Man Yuji NEVER goes OLD" --anime "Jujutsu Kaisen"
  python -m reddit_to_script.run_anime_theory --topic "Who is Orsted really?" --anime "Mushoku Tensei" --long
  python -m reddit_to_script.run_anime_theory --topic "Orsted explained" --reference-url "https://youtube.com/shorts/VIDEO_ID" --long --dry-run
"""

from __future__ import annotations

import argparse
import time

from . import generate_script, make_anime_theory_video
from . import config
from . import youtube_transcript


def run(args: argparse.Namespace) -> int:
    topic = (args.topic or "").strip()
    if not topic:
        print("Provide --topic (e.g. an anime theory title).")
        return 1

    reference = ""
    if args.reference_file:
        print(f"Loading reference script from {args.reference_file!r}...", flush=True)
        reference = youtube_transcript.load_reference(args.reference_file, english_only=True)
    elif args.reference_url:
        print(f"Fetching reference transcript from YouTube...", flush=True)
        reference = youtube_transcript.fetch_transcript(
            args.reference_url, english_only=True
        )
        print(f"  reference transcript: {len(reference.split())} words", flush=True)

    long_form = bool(args.long or args.reference_url or args.reference_file)
    if long_form and not args.long:
        print("  auto-enabling --long (reference script provided)", flush=True)

    print(f"Writing anime-theory script for: {topic}", flush=True)
    scripted = generate_script.build_anime_theory_scenes(
        topic,
        anime=args.anime or "",
        context=args.context or "",
        long=long_form,
        reference_transcript=reference,
    )
    anime = scripted.get("anime") or args.anime or ""
    title = scripted.get("title") or topic
    music = scripted.get("music") or "dark"
    scenes = scripted["scenes"]
    print(f"  title={title!r} anime={anime!r} scenes={len(scenes)} music={music!r}", flush=True)

    inputs = [
        make_anime_theory_video.SceneInput(
            text=s["text"],
            search_terms=s.get("searchTerms") or [],
            anime=str(s.get("anime") or anime),
        )
        for s in scenes
    ]

    if args.dry_run:
        for i, s in enumerate(inputs, 1):
            print(f"  {i}. {s.text}")
            print(f"     visuals: {', '.join(s.search_terms)}")
        return 0

    slug = generate_script.slugify(title)
    out_name = args.out or f"anime-theory-{time.strftime('%Y%m%d-%H%M%S')}-{slug}.mp4"
    max_seconds = args.max_seconds
    if max_seconds is None:
        max_seconds = (
            config.MAX_ANIME_THEORY_LONG_SECONDS
            if long_form
            else config.MAX_ANIME_THEORY_SECONDS
        )
    mp4 = make_anime_theory_video.make_video(
        inputs,
        out_name=out_name,
        anime_hint=anime,
        title=title.upper()[:48] if args.show_title else None,
        max_seconds=max_seconds,
        render_timeout=3600 if long_form else 1800,
        music_mood=music,
    )
    print(f"\nVideo ready: {mp4}")
    return 0


def _main() -> int:
    parser = argparse.ArgumentParser(description="Anime theory topic → Shorts MP4.")
    parser.add_argument("--topic", required=True, help="Theory hook / title")
    parser.add_argument("--anime", default="", help="Series name (e.g. Jujutsu Kaisen)")
    parser.add_argument("--context", default="", help="Optional extra lore notes for the LLM")
    parser.add_argument(
        "--long",
        action="store_true",
        help="Long-form script (~14-22 scenes, up to 3 min)",
    )
    parser.add_argument(
        "--reference-url",
        default="",
        help="YouTube/Shorts URL — pull captions as pacing reference",
    )
    parser.add_argument(
        "--reference-file",
        default="",
        help="Local .txt transcript to use as pacing reference",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Duration cap (default: 90 short / 180 long)",
    )
    parser.add_argument("--out", default=None, help="Output filename under out/")
    parser.add_argument("--show-title", action="store_true", help="Burn series title at top")
    parser.add_argument("--dry-run", action="store_true", help="Script only, no render")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(_main())
