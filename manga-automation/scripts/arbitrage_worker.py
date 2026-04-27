#!/usr/bin/env python3
"""
Phase 4: Download Worker.
Processes arbitrage_assets with status='pending', downloads via yt-dlp.

Usage:
    python3 scripts/arbitrage_worker.py [--batch 10]
"""
import os, sys, json, argparse
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("arbitrage_worker")

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    logger.warning("yt-dlp not installed. Run: pip install yt-dlp")
    YT_DLP_AVAILABLE = False

DOWNLOAD_DIR = os.environ.get("ARBITRAGE_VIDEOS_DIR", "/data/arbitrage_videos")


def download_asset(asset: dict) -> dict:
    """Download a YouTube video. Returns updated fields."""
    if not YT_DLP_AVAILABLE:
        return {"status": "failed", "error_message": "yt-dlp not installed in container"}

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    output_path = os.path.join(DOWNLOAD_DIR, f"asset_{asset['id']}.mp4")

    # Skip if already downloaded
    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        return {"local_path": output_path, "file_size_mb": round(size_mb, 2), "status": "downloaded"}

    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": output_path,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    logger.info(f"Downloading asset {asset['id']}: {asset['youtube_url']}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(asset["youtube_url"], download=True)
            duration = info.get("duration") if info else None

        # yt-dlp may add .mp4 extension
        final_path = output_path if os.path.exists(output_path) else output_path
        size_mb = os.path.getsize(final_path) / (1024 * 1024) if os.path.exists(final_path) else 0

        return {
            "local_path": final_path,
            "file_size_mb": round(size_mb, 2),
            "duration_secs": duration,
            "status": "downloaded",
        }
    except Exception as e:
        logger.error(f"Download failed for asset {asset['id']}: {e}")
        return {"status": "failed", "error_message": str(e)[:500]}


def process_pending(batch: int = 10) -> dict:
    """Download up to `batch` pending assets."""
    assets = db.execute(
        "SELECT * FROM arbitrage_assets WHERE status='pending' ORDER BY created_at DESC LIMIT %s",
        (batch,),
    )

    if not assets:
        logger.info("No pending assets to download")
        return {"processed": 0, "downloaded": 0, "failed": 0}

    downloaded = 0
    failed = 0
    downloaded_asset_ids = []
    downloaded_paths = []

    for asset in assets:
        result = download_asset(asset)

        if result["status"] == "downloaded":
            db.execute(
                """
                UPDATE arbitrage_assets
                SET status='downloaded', local_path=%s, file_size_mb=%s,
                    duration_secs=COALESCE(%s, duration_secs), updated_at=NOW()
                WHERE id=%s
                """,
                (result["local_path"], result["file_size_mb"],
                 result.get("duration_secs"), asset["id"]),
            )
            downloaded += 1
            downloaded_asset_ids.append(asset["id"])
            if result.get("local_path"):
                downloaded_paths.append(result["local_path"])
        else:
            db.execute(
                "UPDATE arbitrage_assets SET status='failed', error_message=%s, updated_at=NOW() WHERE id=%s",
                (result.get("error_message", "unknown error"), asset["id"]),
            )
            failed += 1

    return {
        "processed": len(assets),
        "downloaded": downloaded,
        "failed": failed,
        "downloaded_asset_ids": downloaded_asset_ids,
        "local_paths": downloaded_paths,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=10)
    args = parser.parse_args()
    result = process_pending(args.batch)
    print(json.dumps(result))
