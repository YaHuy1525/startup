"""Shared yt-dlp format and options for YouTube downloads."""
from __future__ import annotations

import os


def get_max_height() -> int | None:
    """Max video height; None = no cap. Set YOUTUBE_DOWNLOAD_MAX_HEIGHT=0 to disable."""
    raw = os.environ.get("YOUTUBE_DOWNLOAD_MAX_HEIGHT", "1080").strip()
    if not raw or raw.lower() in {"0", "none", "unlimited"}:
        return None
    try:
        height = int(raw)
        return height if height > 0 else None
    except ValueError:
        return 1080


def get_ytdlp_format() -> str:
    """
    Best available video+audio, merged to mp4.

    Avoids ext=mp4 filters — YouTube's highest quality is usually webm (vp9/av1),
    and forcing mp4 progressive streams often yields 360p–720p only.
    """
    override = os.environ.get("YOUTUBE_DOWNLOAD_FORMAT", "").strip()
    if override:
        return override

    height_filter = ""
    max_height = get_max_height()
    if max_height:
        height_filter = f"[height<={max_height}]"

    return (
        f"bestvideo{height_filter}+bestaudio/"
        f"bestvideo{height_filter}+bestaudio/best"
    )


def build_ytdlp_opts(
    *,
    outtmpl: str,
    quiet: bool = True,
    no_warnings: bool = True,
) -> dict:
    return {
        "format": get_ytdlp_format(),
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": quiet,
        "no_warnings": no_warnings,
    }
