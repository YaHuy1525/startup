"""CLI: manga chapter → vision summary → commentary video.

Examples:
  python -m reddit_to_script.run_chapter_commentary --series Baki --chapter 65
  python -m reddit_to_script.run_chapter_commentary --series "Baki Rahen" --latest --dry-run
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import config, generate_script, make_anime_theory_video, manga_chapter

_CHAPTER_VOICE = (
    "You are a hype manga YouTube commentator. Energetic, shocked, analytical. "
    "React to fight scenes and plot twists like you're watching with a friend. "
    "English only. Never sound bored or robotic."
)


def run(args: argparse.Namespace) -> int:
    series = (args.series or "Baki").strip()
    print(f"Fetching chapter from MangaDex: {series!r}...", flush=True)

    chapter = manga_chapter.fetch_chapter(
        series,
        chapter_number=args.chapter,
        use_latest=bool(args.latest),
    )
    label = manga_chapter.chapter_label(chapter)
    print(
        f"  {label} | {chapter.page_count} pages | id={chapter.chapter_id[:8]}...",
        flush=True,
    )

    job_dir = config.ASSETS_DIR / f"chapter-{chapter.chapter_id[:8]}"
    print(f"  sampling panels for vision summary...", flush=True)
    panels = manga_chapter.download_panel_samples(
        chapter, job_dir, sample_count=args.panel_samples
    )
    print(f"  downloaded {len(panels)} panel samples", flush=True)

    summary_data = manga_chapter.summarize_chapter_panels(chapter, panels)
    summary_path = job_dir / "chapter-summary.json"
    summary_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
    print(f"  vision summary saved -> {summary_path.name}", flush=True)
    print(f"  summary: {summary_data.get('summary', '')[:200]}...", flush=True)

    scripted = generate_script.build_chapter_commentary_scenes(
        manga_title=chapter.manga_title,
        chapter_number=chapter.chapter_number,
        chapter_title=chapter.chapter_title,
        summary=str(summary_data.get("summary") or ""),
        events=summary_data.get("events") or [],
        characters=summary_data.get("characters") or [],
    )
    anime = scripted.get("anime") or chapter.manga_title
    title = scripted.get("title") or label
    scenes = scripted["scenes"]
    print(f"  commentary script: {len(scenes)} scenes | {title!r}", flush=True)

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
    out_name = args.out or (
        f"baki-ch{chapter.chapter_number}-{slug}.mp4"
        if "baki" in series.lower()
        else f"chapter-{chapter.chapter_number}-{slug}.mp4"
    )

    prev_instr = config.OPENAI_TTS_INSTRUCTIONS
    config.OPENAI_TTS_INSTRUCTIONS = _CHAPTER_VOICE

    try:
        mp4 = make_anime_theory_video.make_video(
            inputs,
            out_name=out_name,
            anime_hint=anime,
            max_seconds=args.max_seconds or config.MAX_ANIME_THEORY_LONG_SECONDS,
            render_timeout=3600,
        )
    finally:
        config.OPENAI_TTS_INSTRUCTIONS = prev_instr

    print(f"\nVideo ready: {mp4}")
    return 0


def _main() -> int:
    parser = argparse.ArgumentParser(description="Manga chapter commentary → MP4.")
    parser.add_argument("--series", default="Baki", help="Manga series (default: Baki)")
    parser.add_argument("--chapter", default=None, help="Chapter number (e.g. 65)")
    parser.add_argument("--latest", action="store_true", help="Use latest English chapter")
    parser.add_argument("--panel-samples", type=int, default=8, help="Panels to analyze")
    parser.add_argument("--max-seconds", type=float, default=None, help="Duration cap")
    parser.add_argument("--out", default=None, help="Output filename under out/")
    parser.add_argument("--dry-run", action="store_true", help="Preview script only")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(_main())
