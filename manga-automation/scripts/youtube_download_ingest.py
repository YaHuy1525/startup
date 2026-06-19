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
from scripts.utils.ytdlp_config import build_ytdlp_opts, get_ytdlp_format

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


def extract_youtube_id(url: str | None = None, *, video_id: str | None = None) -> str | None:
    """Return 11-char YouTube video id from URL or explicit id."""
    if video_id:
        vid = str(video_id).strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return vid
    if not url:
        return None
    try:
        canonical = normalize_youtube_url(url)
        m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", canonical)
        if m:
            return m.group(1)
    except Exception:
        pass
    m = re.search(
        r"(?:youtube\.com/(?:shorts/|watch\?v=)|youtu\.be/)([A-Za-z0-9_-]{11})",
        url,
        flags=re.IGNORECASE,
    )
    return m.group(1) if m else None


def load_used_youtube_id_set() -> set[str]:
    """Load known YouTube video IDs from DB (fast batch check for discovery loops)."""
    used: set[str] = set()
    try:
        for row in db.execute("SELECT youtube_url FROM arbitrage_assets") or []:
            vid = extract_youtube_id(str(row.get("youtube_url") or ""))
            if vid:
                used.add(vid)
        for row in db.execute(
            "SELECT file_path FROM videos WHERE file_path LIKE '%yt_%'"
        ) or []:
            m = re.search(r"yt_([A-Za-z0-9_-]{11})", str(row.get("file_path") or ""))
            if m:
                used.add(m.group(1))
    except Exception as exc:
        logger.warning(f"load_used_youtube_id_set failed: {exc}")
    return used


def is_youtube_video_already_used(
    *,
    url: str | None = None,
    video_id: str | None = None,
    use_chroma: bool = False,
    used_ids: set[str] | None = None,
) -> dict[str, Any]:
    """
    Check whether this YouTube video was already ingested or published in this system.
    Used to avoid re-downloading/re-posting the same source clip.
    """
    yt_id = extract_youtube_id(url, video_id=video_id)
    if not yt_id:
        return {"is_duplicate": False, "youtube_id": None, "canonical_url": None, "reasons": []}

    if used_ids is not None and yt_id in used_ids:
        return {
            "is_duplicate": True,
            "youtube_id": yt_id,
            "canonical_url": f"https://www.youtube.com/watch?v={yt_id}",
            "reasons": ["cached_used_id_set"],
        }

    canonical = f"https://www.youtube.com/watch?v={yt_id}"
    reasons: list[str] = []

    asset = db.execute_one(
        "SELECT id, status FROM arbitrage_assets WHERE youtube_url = %s LIMIT 1",
        (canonical,),
    )
    if asset:
        reasons.append(f"arbitrage_assets:{asset['id']}:{asset.get('status')}")

    video = db.execute_one(
        """
        SELECT id, status FROM videos
        WHERE file_path LIKE %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (f"%yt_{yt_id}.%",),
    )
    if video:
        reasons.append(f"videos:{video['id']}:{video.get('status')}")

    published = db.execute_one(
        """
        SELECT pv.id, pv.platform, pv.status
        FROM published_videos pv
        JOIN videos v ON v.id = pv.video_id
        WHERE v.file_path LIKE %s
        ORDER BY pv.id DESC
        LIMIT 1
        """,
        (f"%yt_{yt_id}.%",),
    )
    if published:
        reasons.append(
            f"published_videos:{published['id']}:{published.get('platform')}:{published.get('status')}"
        )

    local_path = os.path.join(DOWNLOAD_DIR, f"yt_{yt_id}.mp4")
    if os.path.exists(local_path):
        reasons.append(f"local_file:{local_path}")

    if use_chroma or os.environ.get("DEDUP_USE_CHROMA", "").strip().lower() in {"1", "true", "yes"}:
        try:
            from scripts.memory_manager import is_duplicate

            if is_duplicate(url=canonical):
                reasons.append("chromadb_content_fingerprint")
        except Exception as exc:
            logger.debug(f"Chroma duplicate check skipped: {exc}")

    return {
        "is_duplicate": len(reasons) > 0,
        "youtube_id": yt_id,
        "canonical_url": canonical,
        "reasons": reasons,
    }


def _chapter_id_for_ingest() -> int:
    row = db.execute_one("SELECT id FROM manga_chapters ORDER BY id ASC LIMIT 1")
    if not row:
        raise RuntimeError("No manga_chapters row — run schema seed or fetch_chapter first")
    return int(row["id"])


def _extract_public_media_url(info: dict[str, Any] | None) -> str:
    info = info or {}
    def _has_media_codec(codec: Any) -> bool:
        c = str(codec or "").strip().lower()
        return c not in ("", "none")

    formats = info.get("formats")
    if isinstance(formats, list):
        # Prefer progressive formats that include both video + audio.
        candidates: list[tuple[int, float, str]] = []
        for fmt in formats:
            if not isinstance(fmt, dict):
                continue
            u = fmt.get("url")
            ext = str(fmt.get("ext") or "").lower()
            if not isinstance(u, str) or not u.startswith(("http://", "https://")):
                continue
            if ext != "mp4":
                continue
            if not _has_media_codec(fmt.get("acodec")):
                continue
            if not _has_media_codec(fmt.get("vcodec")):
                continue
            height = int(fmt.get("height") or 0)
            tbr = float(fmt.get("tbr") or 0.0)
            candidates.append((height, tbr, u))
        if candidates:
            candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return candidates[0][2]

    # Fallback only when top-level stream is known to include both audio + video.
    direct = info.get("url")
    if (
        isinstance(direct, str)
        and direct.startswith(("http://", "https://"))
        and _has_media_codec(info.get("acodec"))
        and _has_media_codec(info.get("vcodec"))
    ):
        return direct
    return ""


def _extract_thumbnail_url(info: dict[str, Any] | None) -> str:
    info = info or {}
    thumb = info.get("thumbnail")
    if isinstance(thumb, str) and thumb.startswith(("http://", "https://")):
        return thumb
    thumbs = info.get("thumbnails")
    if isinstance(thumbs, list):
        for item in reversed(thumbs):
            if isinstance(item, dict):
                u = item.get("url")
                if isinstance(u, str) and u.startswith(("http://", "https://")):
                    return u
    return ""


def _extract_hashtags_from_text(text: str) -> list[str]:
    tags: list[str] = []
    for m in re.finditer(r"#([A-Za-z0-9_]{2,40})", text or ""):
        tag = m.group(1).strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _normalize_hashtag_list(values: list[str] | None, limit: int = 12) -> list[str]:
    out: list[str] = []
    for v in values or []:
        tag = str(v).strip().lstrip("#").lower()
        tag = re.sub(r"[^a-z0-9_]", "", tag)
        if len(tag) < 2:
            continue
        if tag in out:
            continue
        out.append(tag)
        if len(out) >= max(1, limit):
            break
    return out


def download_youtube_to_file(url: str, output_path: str) -> dict[str, Any]:
    if not YT_DLP_AVAILABLE:
        return {"success": False, "error": "yt-dlp is not installed"}

    os.makedirs(os.path.dirname(output_path) or DOWNLOAD_DIR, exist_ok=True)
    base, _ = os.path.splitext(output_path)
    outtmpl = base + ".%(ext)s"

    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        probe_info: dict[str, Any] = {}
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "format": get_ytdlp_format()}) as ydl:
                probe_info = ydl.extract_info(url, download=False) or {}
        except Exception:
            probe_info = {}
        return {
            "success": True,
            "local_path": output_path,
            "file_size_mb": round(size_mb, 2),
            "skipped_download": True,
            "stream_url": _extract_public_media_url(probe_info),
            "thumbnail_url": _extract_thumbnail_url(probe_info),
        }

    ydl_opts = build_ytdlp_opts(outtmpl=outtmpl)

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
            "stream_url": _extract_public_media_url(info),
            "thumbnail_url": _extract_thumbnail_url(info),
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
    reject_if_used: bool = False,
) -> dict[str, Any]:
    """
    Download URL, register arbitrage_assets + videos (ready) for TikTok upload.
    """
    canonical = normalize_youtube_url(url)
    if reject_if_used:
        used = is_youtube_video_already_used(url=canonical)
        if used.get("is_duplicate"):
            return {
                "success": False,
                "error": "video_already_used",
                "message": "This YouTube video was already downloaded or published.",
                **used,
            }

    provided_tags = _normalize_hashtag_list(hashtags)

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
    source_description = (meta.get("description") or "").strip()
    source_tags = _normalize_hashtag_list((meta.get("tags") or []))
    desc_tags = _extract_hashtags_from_text(source_description)
    merged_source_tags = _normalize_hashtag_list(source_tags + desc_tags)
    final_tags = provided_tags or merged_source_tags or list(DEFAULT_HASHTAGS)
    hashtag_arr = "{" + ",".join(final_tags) + "}"
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    local_path = os.path.join(DOWNLOAD_DIR, f"yt_{yt_id}.mp4")

    dl = download_youtube_to_file(canonical, local_path)
    if not dl.get("success"):
        return {"success": False, "error": dl.get("error", "download failed"), "url": canonical}

    local_path = dl["local_path"]
    duration = dl.get("duration_secs") or meta.get("duration")
    size_mb = dl.get("file_size_mb")
    final_caption = (caption or source_description or title)[:2200]

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
        "description": source_description[:5000],
        "hashtags": [f"#{t}" for t in final_tags],
        "public_video_url": dl.get("stream_url") or _extract_public_media_url(meta),
        "cover_url": dl.get("thumbnail_url") or _extract_thumbnail_url(meta),
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
        reject_if_used=bool(body.get("reject_if_used", False)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download YouTube URL into content library")
    parser.add_argument("--url", required=True, help="YouTube or YouTube Shorts URL")
    parser.add_argument("--caption", default="", help="Optional caption override")
    args = parser.parse_args()
    result = ingest_youtube_url(args.url, caption=args.caption or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success") else 1)
