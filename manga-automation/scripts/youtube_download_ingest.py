#!/usr/bin/env python3
"""
Download a YouTube / YouTube Shorts URL and add it to the local content library.

Saves MP4 under ARBITRAGE_VIDEOS_DIR, upserts arbitrage_assets, and creates a
videos row (status=ready) for /upload_tiktok.

Usage:
    python3 scripts/youtube_download_ingest.py --url "https://youtube.com/shorts/..."
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("youtube_download_ingest")

try:
    import yt_dlp

    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

DOWNLOAD_DIR = os.path.abspath(
    os.environ.get("ARBITRAGE_VIDEOS_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "arbitrage_videos"))
)
DEFAULT_HASHTAGS = ["fyp", "shorts", "viral"]


def normalize_youtube_url(url: str) -> str:
    """Accept shorts, watch, youtu.be links; return a canonical watch URL."""
    url = (url or "").strip()
    if not url:
        raise ValueError("URL is required")

    m = re.search(
        r"https?://(?:www\.)?(?:youtube\.com/(?:shorts/|watch\?)|youtu\.be/)([A-Za-z0-9_-]{6,})",
        url,
    )
    if not m:
        if "youtube.com" in url or "youtu.be" in url:
            return url.split()[0]
        raise ValueError(f"Not a YouTube URL: {url}")

    video_id = m.group(1)
    parsed = urlparse(url)
    if "youtu.be" in parsed.netloc:
        return f"https://www.youtube.com/watch?v={video_id}"
    if "/shorts/" in parsed.path:
        return f"https://www.youtube.com/watch?v={video_id}"
    if parsed.path.endswith("/watch"):
        qs = parse_qs(parsed.query)
        vid = (qs.get("v") or [video_id])[0]
        return f"https://www.youtube.com/watch?v={vid}"
    return f"https://www.youtube.com/watch?v={video_id}"


def _chapter_id_for_ingest() -> int:
    row = db.execute_one("SELECT id FROM manga_chapters ORDER BY id ASC LIMIT 1")
    if not row:
        raise RuntimeError("No manga_chapters row — run schema seed or fetch_chapter first")
    return int(row["id"])


def download_youtube_to_file(url: str, output_path: str) -> dict[str, Any]:
    if not YT_DLP_AVAILABLE:
        return {"success": False, "error": "yt-dlp is not installed"}

    os.makedirs(os.path.dirname(output_path) or DOWNLOAD_DIR, exist_ok=True)
    base, _ = os.path.splitext(output_path)
    outtmpl = base + ".%(ext)s"

    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        return {
            "success": True,
            "local_path": output_path,
            "file_size_mb": round(size_mb, 2),
            "skipped_download": True,
        }

    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    logger.info(f"Downloading {url} -> {output_path}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        final = output_path
        if not os.path.exists(final) and os.path.exists(base + ".mp4"):
            final = base + ".mp4"
        if not os.path.exists(final):
            return {"success": False, "error": f"Download finished but file missing: {final}"}

        duration = info.get("duration") if info else None
        size_mb = os.path.getsize(final) / (1024 * 1024)
        return {
            "success": True,
            "local_path": final,
            "file_size_mb": round(size_mb, 2),
            "duration_secs": duration,
            "title": (info or {}).get("title"),
            "youtube_id": (info or {}).get("id"),
        }
    except Exception as exc:
        logger.error(f"yt-dlp failed: {exc}")
        return {"success": False, "error": str(exc)[:500]}


def ingest_youtube_url(
    url: str,
    *,
    caption: str | None = None,
    hashtags: list[str] | None = None,
    create_video: bool = True,
) -> dict[str, Any]:
    """
    Download URL, register arbitrage_assets + videos (ready) for TikTok upload.
    """
    canonical = normalize_youtube_url(url)
    tags = hashtags or DEFAULT_HASHTAGS
    hashtag_arr = "{" + ",".join(t.lstrip("#") for t in tags) + "}"

    # Probe metadata first for stable filename
    meta: dict[str, Any] = {}
    if YT_DLP_AVAILABLE:
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                meta = ydl.extract_info(canonical, download=False) or {}
        except Exception as exc:
            logger.warning(f"Metadata probe failed: {exc}")

    yt_id = meta.get("id") or "unknown"
    title = (meta.get("title") or "").strip() or "Must watch moment! 🔥"
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    local_path = os.path.join(DOWNLOAD_DIR, f"yt_{yt_id}.mp4")

    dl = download_youtube_to_file(canonical, local_path)
    if not dl.get("success"):
        return {"success": False, "error": dl.get("error", "download failed"), "url": canonical}

    local_path = dl["local_path"]
    duration = dl.get("duration_secs") or meta.get("duration")
    size_mb = dl.get("file_size_mb")
    final_caption = (caption or title)[:2200]

    asset_row = db.execute_one(
        """
        INSERT INTO arbitrage_assets
            (youtube_url, youtube_title, duration_secs, local_path, file_size_mb, status)
        VALUES (%s, %s, %s, %s, %s, 'downloaded')
        ON CONFLICT (youtube_url) DO UPDATE SET
            youtube_title = EXCLUDED.youtube_title,
            duration_secs = COALESCE(EXCLUDED.duration_secs, arbitrage_assets.duration_secs),
            local_path = EXCLUDED.local_path,
            file_size_mb = COALESCE(EXCLUDED.file_size_mb, arbitrage_assets.file_size_mb),
            status = 'downloaded',
            updated_at = NOW()
        RETURNING id
        """,
        (canonical, title, duration, local_path, size_mb),
    )
    asset_id = asset_row["id"] if asset_row else None

    video_id = None
    if create_video:
        chapter_id = _chapter_id_for_ingest()
        video_row = db.execute_one(
            """
            INSERT INTO videos
                (chapter_id, file_path, caption, hashtags, status, duration_secs, file_size_mb)
            VALUES (%s, %s, %s, %s, 'ready', %s, %s)
            RETURNING id
            """,
            (chapter_id, local_path, final_caption, hashtag_arr, duration, size_mb),
        )
        video_id = video_row["id"] if video_row else None

    return {
        "success": True,
        "url": canonical,
        "youtube_id": yt_id,
        "title": title,
        "local_path": local_path,
        "file_size_mb": size_mb,
        "duration_secs": duration,
        "asset_id": asset_id,
        "video_id": video_id,
        "caption": final_caption,
        "upload_hint": f"/upload_tiktok {video_id}" if video_id else None,
    }


def main(body: dict | None = None) -> dict[str, Any]:
    body = body or {}
    url = body.get("url") or body.get("youtube_url") or ""
    if not url and body.get("args"):
        url = body["args"]
    return ingest_youtube_url(
        url,
        caption=body.get("caption"),
        hashtags=body.get("hashtags"),
        create_video=body.get("create_video", True),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download YouTube URL into content library")
    parser.add_argument("--url", required=True, help="YouTube or YouTube Shorts URL")
    parser.add_argument("--caption", default="", help="Optional caption override")
    args = parser.parse_args()
    result = ingest_youtube_url(args.url, caption=args.caption or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success") else 1)
