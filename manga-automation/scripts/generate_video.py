#!/usr/bin/env python3
"""
Generate a TikTok-ready vertical video from selected manga panels.

In production mode (default), calls the manga-agents Remotion renderer endpoint.
In legacy mode (--legacy), falls back to the old FFmpeg bash script.

Usage:
    python3 -m scripts.generate_video --chapter-id <db_chapter_id>
    python3 -m scripts.generate_video --chapter-id <id> --legacy

Output:
    JSON with video_id and file path.
    Exit 0 on success, 1 on failure.
"""
import sys
import json
import argparse
import os
import subprocess
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import requests
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("generate_video")

VIDEOS_DIR = os.environ.get("VIDEOS_DIR", "data/videos")
AGENTS_URL = os.environ.get("MANGA_AGENTS_URL", "http://localhost:3001")
BASH_SCRIPT = os.path.join(os.path.dirname(__file__), "../scripts-bash/generate_manga_video.sh")
MIN_DURATION = float(os.environ.get("VIDEO_MIN_DURATION_SECONDS", 60))


def get_selected_panels(chapter_id: int) -> dict | None:
    return db.execute_one(
        """
        SELECT sp.panels, sp.music_path, m.title, mc.chapter_number
        FROM selected_panels sp
        JOIN manga_chapters mc ON sp.chapter_id = mc.id
        JOIN manga m ON mc.manga_id = m.id
        WHERE sp.chapter_id = %s
        ORDER BY sp.selected_at DESC
        LIMIT 1
        """,
        (chapter_id,),
    )


def sanitise(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


# ─── Remotion Renderer (Default) ──────────────────────────────────────────────

def render_via_remotion(chapter_id: int) -> dict:
    """Call the manga-agents Remotion render endpoint."""
    url = f"{AGENTS_URL}/pipeline/render-video"
    logger.info(f"Calling Remotion renderer at {url} for chapter_id={chapter_id}")

    try:
        resp = requests.post(
            url,
            json={"chapterId": chapter_id},
            timeout=600,  # 10 min timeout for rendering
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success"):
            logger.error(f"Remotion render failed: {data.get('error')}")
            return {}

        logger.info(
            f"Remotion render complete: {data['filePath']} | "
            f"{data['durationSecs']}s | {data['fileSizeMb']}MB"
        )

        if data["durationSecs"] < MIN_DURATION:
            logger.warning(
                f"Video duration {data['durationSecs']}s < minimum {MIN_DURATION}s"
            )

        return {
            "video_id": data["videoId"],
            "file_path": data["filePath"],
            "chapter_id": chapter_id,
            "duration_secs": data["durationSecs"],
            "file_size_mb": data["fileSizeMb"],
        }
    except requests.exceptions.ConnectionError:
        logger.error(f"Cannot connect to manga-agents at {AGENTS_URL}. Is it running?")
        return {}
    except Exception as e:
        logger.error(f"Remotion render error: {e}")
        return {}


# ─── FFmpeg Legacy Renderer ───────────────────────────────────────────────────

def run_ffmpeg_script(
    panel_paths: list[str],
    output_path: str,
    title: str,
    chapter_number: str,
    music_path: str = "",
) -> subprocess.CompletedProcess:
    cmd = [
        "bash",
        BASH_SCRIPT,
        "--panels", ",".join(panel_paths),
        "--output", output_path,
        "--title", title,
        "--chapter", f"Chapter {chapter_number}",
    ]
    if music_path and os.path.exists(music_path):
        cmd += ["--music", music_path]

    logger.info(f"Running legacy FFmpeg script for {len(panel_paths)} panels")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def get_file_info(path: str) -> dict:
    """Get duration and size of the generated video via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        info = json.loads(result.stdout).get("format", {})
        duration = float(info.get("duration", 0))
        size_bytes = int(info.get("size", 0))
        return {
            "duration_secs": round(duration, 2),
            "file_size_mb": round(size_bytes / (1024 * 1024), 2),
        }
    except Exception as e:
        logger.warning(f"ffprobe failed: {e}")
        size = os.path.getsize(path) if os.path.exists(path) else 0
        return {"duration_secs": 0.0, "file_size_mb": round(size / (1024 * 1024), 2)}


def render_via_ffmpeg(chapter_id: int) -> dict:
    """Legacy FFmpeg renderer — kept for fallback."""
    selection = get_selected_panels(chapter_id)
    if not selection:
        logger.error(f"No selected panels found for chapter_id={chapter_id}")
        return {}

    panels: list[dict] = (
        json.loads(selection["panels"])
        if isinstance(selection["panels"], str)
        else (selection["panels"] or [])
    )

    if not panels:
        logger.error("Empty panel selection")
        return {}

    panel_paths = [p["localPath"] for p in panels if p.get("localPath") and os.path.exists(p["localPath"])]
    if not panel_paths:
        logger.error("No valid local panel paths in selection")
        return {}

    os.makedirs(VIDEOS_DIR, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_title = sanitise(selection["title"])
    filename = f"{safe_title}_ch{selection['chapter_number']}_{timestamp}.mp4"
    output_path = os.path.join(VIDEOS_DIR, filename)

    music_path = selection.get("music_path") or ""
    if music_path:
        logger.info(f"Using background music: {music_path}")
    else:
        logger.info("No background music selected — generating silent video")

    proc = run_ffmpeg_script(
        panel_paths=panel_paths,
        output_path=output_path,
        title=selection["title"],
        chapter_number=selection["chapter_number"],
        music_path=music_path,
    )

    if proc.returncode != 0:
        logger.error(f"FFmpeg script failed:\n{proc.stderr}")
        return {}

    if not os.path.exists(output_path):
        logger.error("Video file not created after FFmpeg run")
        return {}

    info = get_file_info(output_path)
    logger.info(f"Video created: {output_path} | {info['duration_secs']}s | {info['file_size_mb']}MB")

    if info["duration_secs"] < MIN_DURATION:
        logger.warning(
            f"Video duration {info['duration_secs']}s < minimum {MIN_DURATION}s"
        )

    video_id = db.execute_returning(
        """
        INSERT INTO videos (chapter_id, file_path, duration_secs, file_size_mb, status)
        VALUES (%s, %s, %s, %s, 'ready')
        RETURNING id
        """,
        (chapter_id, output_path, info["duration_secs"], info["file_size_mb"]),
    )

    logger.info(f"Inserted video_id={video_id}")
    return {
        "video_id": video_id,
        "file_path": output_path,
        "chapter_id": chapter_id,
        **info,
    }


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main(chapter_id: int, legacy: bool = False) -> dict:
    if legacy:
        logger.info("Using legacy FFmpeg renderer")
        return render_via_ffmpeg(chapter_id)
    else:
        logger.info("Using Remotion renderer")
        return render_via_remotion(chapter_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter-id", type=int, required=True)
    parser.add_argument("--legacy", action="store_true", help="Use old FFmpeg renderer instead of Remotion")
    args = parser.parse_args()

    result = main(args.chapter_id, legacy=args.legacy)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result else 1)
