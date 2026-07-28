"""CLI: search YouTube Shorts and scrape narration scripts (captions).

Examples:
  python -m reddit_to_script.scrape_shorts --query "anime theory jjk shorts"
  python -m reddit_to_script.scrape_shorts --query "mushoku tensei theory" --limit 8 --max-duration 120
  python -m reddit_to_script.scrape_shorts --url "https://www.youtube.com/shorts/VIDEO_ID"
"""

from __future__ import annotations

import argparse
import json
import sys

from . import youtube_transcript


def run(args: argparse.Namespace) -> int:
    if args.channel:
        max_dur = args.max_duration
        # Channel flag defaulted to 90 in argparse — bump for Shorts+VODs unless user set higher
        if max_dur <= 90:
            max_dur = 180.0
        youtube_transcript.scrape_channel_scripts(
            args.channel,
            limit=args.limit,
            max_duration_s=max_dur,
            out_dir=args.out_dir or None,
            english_only=not args.allow_non_english,
        )
        return 0

    if args.url:
        urls = args.url if isinstance(args.url, list) else [args.url]
        from datetime import datetime, timezone
        from pathlib import Path

        from . import config

        out_dir = Path(args.out_dir) if args.out_dir else config.PIPELINE_ROOT / "data" / "reference-scripts"
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for url in urls:
            vid = youtube_transcript.extract_video_id(url)
            print(f"Fetching transcript: {url}", flush=True)
            try:
                text, lang = youtube_transcript.fetch_transcript_with_lang(
                    vid, english_only=not args.allow_non_english
                )
                path = out_dir / f"{vid}.txt"
                path.write_text(text, encoding="utf-8")
                print(f"  {len(text.split())} words ({lang}) -> {path}", flush=True)
                rows.append({"video_id": vid, "url": url, "language": lang, "words": len(text.split()), "status": "ok"})
            except Exception as exc:  # noqa: BLE001
                print(f"  failed: {exc}", flush=True)
                rows.append({"video_id": vid, "url": url, "status": "error", "error": str(exc)})
        print(json.dumps(rows, indent=2), flush=True)
        return 0 if any(r.get("status") == "ok" for r in rows) else 1

    query = (args.query or "").strip()
    if not query:
        print("Provide --query, --channel, or --url", file=sys.stderr)
        return 1

    youtube_transcript.scrape_short_scripts(
        query,
        limit=args.limit,
        max_duration_s=args.max_duration,
        out_dir=args.out_dir or None,
        english_only=not args.allow_non_english,
    )
    return 0


def _main() -> int:
    parser = argparse.ArgumentParser(description="Scrape scripts from YouTube Shorts captions.")
    parser.add_argument("--query", default="", help="Search query (e.g. 'anime theory shorts')")
    parser.add_argument(
        "--channel",
        default="",
        help="Channel handle/URL (e.g. @animeinsider64) — scrape that channel's uploads",
    )
    parser.add_argument("--url", action="append", default=[], help="Direct Short/video URL (repeatable)")
    parser.add_argument("--limit", type=int, default=5, help="Max Shorts to scrape per query")
    parser.add_argument(
        "--max-duration",
        type=float,
        default=90.0,
        help="Only include videos up to this many seconds (default 90; use 180 for channels)",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="Output folder (default: data/reference-scripts/)",
    )
    parser.add_argument(
        "--allow-non-english",
        action="store_true",
        help="Allow Hindi/other language transcripts (default: English only)",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(_main())
