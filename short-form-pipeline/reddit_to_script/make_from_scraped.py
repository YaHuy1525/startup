"""Batch-render anime-theory videos from English scraped Short scripts.

Examples:
  python -m reddit_to_script.make_from_scraped --dry-run
  python -m reddit_to_script.make_from_scraped --long
  python -m reddit_to_script.make_from_scraped --file data/reference-scripts/dq1bn03512E-*.txt
"""

from __future__ import annotations

import argparse
import re
import time

from . import config, generate_script, make_anime_theory_video, youtube_transcript


def _topic_from_scraped(scraped: youtube_transcript.ScrapedScript) -> str:
    title = scraped.title.strip()
    for tag in ("#shorts", "#short", "#anime", "#jjk", "#ytshorts"):
        title = title.replace(tag, "")
    return re.sub(r"\s+", " ", title).strip(" -|")


def _render_one(
    scraped: youtube_transcript.ScrapedScript,
    *,
    long_form: bool,
    dry_run: bool,
) -> int:
    topic = _topic_from_scraped(scraped)
    anime = youtube_transcript.infer_anime_series(scraped.title, scraped.body)
    if not anime:
        print(f"  skip: could not infer anime series for {scraped.path.name}", flush=True)
        return 2  # skipped, not a hard failure

    reference = scraped.body
    context = (
        "Source viral Short script (English). Stay faithful to these facts and pacing. "
        "Expand into a full narration arc but do NOT change the core theory.\n\n"
        f"{reference}"
    )

    print(f"\n=== {topic!r} | {anime!r} ===", flush=True)
    print(f"  reference: {scraped.path.name} ({len(reference.split())} words, en)", flush=True)

    scripted = generate_script.build_anime_theory_scenes(
        topic,
        anime=anime,
        context=context,
        long=long_form,
        reference_transcript=reference,
    )
    title = scripted.get("title") or topic
    scenes = scripted["scenes"]
    print(f"  scenes={len(scenes)}", flush=True)

    inputs = [
        make_anime_theory_video.SceneInput(
            text=s["text"],
            search_terms=s.get("searchTerms") or [],
            anime=str(s.get("anime") or anime),
        )
        for s in scenes
    ]

    if dry_run:
        for i, s in enumerate(inputs, 1):
            print(f"  {i}. {s.text}")
        return 0

    slug = generate_script.slugify(title)
    vid = scraped.video_id or slug[:8]
    out_name = f"scraped-{vid}-{slug}.mp4"
    max_seconds = (
        config.MAX_ANIME_THEORY_LONG_SECONDS if long_form else config.MAX_ANIME_THEORY_SECONDS
    )
    mp4 = make_anime_theory_video.make_video(
        inputs,
        out_name=out_name,
        anime_hint=anime,
        max_seconds=max_seconds,
        render_timeout=3600 if long_form else 1800,
    )
    print(f"  video -> {mp4}", flush=True)
    return 0


def run(args: argparse.Namespace) -> int:
    if args.file:
        paths = args.file
        scripts: list[youtube_transcript.ScrapedScript] = []
        for p in paths:
            scraped = youtube_transcript.parse_scraped_file(p)
            if scraped.language and not youtube_transcript.is_english_lang(scraped.language):
                print(f"skip non-English: {p}", flush=True)
                continue
            if not youtube_transcript.looks_english(scraped.body):
                print(f"skip non-English text: {p}", flush=True)
                continue
            scripts.append(scraped)
    else:
        scripts = youtube_transcript.list_english_scraped_scripts(args.dir)

    if not scripts:
        print("No English scraped scripts found.", flush=True)
        return 1

    print(f"English scripts to render: {len(scripts)}", flush=True)
    long_form = bool(args.long)
    rendered = 0
    skipped = 0
    for scraped in scripts:
        code = _render_one(scraped, long_form=long_form, dry_run=args.dry_run)
        if code == 0:
            rendered += 1
        elif code == 2:
            skipped += 1
        else:
            return 1
    if rendered == 0:
        print("No videos rendered.", flush=True)
        return 1
    print(f"\nRendered {rendered} video(s), skipped {skipped}.", flush=True)
    return 0


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Render videos from English scraped YouTube Short scripts."
    )
    parser.add_argument(
        "--dir",
        default="",
        help="Scraped scripts folder (default: data/reference-scripts/)",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Specific scraped .txt file(s); only English accepted",
    )
    parser.add_argument("--long", action="store_true", help="Long-form (~14-22 scenes)")
    parser.add_argument("--dry-run", action="store_true", help="Script preview only")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(_main())
