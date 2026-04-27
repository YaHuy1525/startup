"""
yt_to_tiktok_manual.py
-----------------------
Agent: Search for a fresh anime YouTube Short and post it to TikTok.

Steps:
  1. Search YouTube for recent anime shorts using yt-dlp.
  2. Pick the first video not already posted today (tracked in DB).
  3. Download it.
  4. Pick a TikTok account that has a valid cookie file in TiktokUploader dir.
  5. Upload via do_tiktok_upload_v2 (Phantomwright).
"""

import os
import sys
import re
import argparse
import subprocess

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── Auto-start Xvfb for bot-detection evasion (needs a display for non-headless mode) ──
_xvfb_proc = None
if not os.environ.get("DISPLAY"):
    try:
        _xvfb_proc = subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", "1280x900x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import time as _t; _t.sleep(1.5)
        os.environ["DISPLAY"] = ":99"
    except FileNotFoundError:
        pass  # Xvfb not available, fall back to headless
from yt_dlp import YoutubeDL
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.upload_tiktok import do_tiktok_upload_v2

logger = setup_logger("yt_to_tiktok_manual")

# ─── Config ──────────────────────────────────────────────────────────────────

TIKTOK_UPLOADER_DIR = os.path.abspath(
    os.environ.get("TIKTOK_UPLOADER_V2_DIR",
                   os.path.join(os.path.dirname(__file__), "..", "..", "TiktokUploader"))
)

SEARCH_QUERIES = [
    "anime shorts 2025",
    "anime edit shorts",
    "best anime moments short",
    "trending anime tiktok short",
]

ANIME_HASHTAGS = ["anime", "fyp", "animeedit", "manga", "viral"]

# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_account_with_valid_cookie() -> dict | None:
    """
    Return a TikTok account whose cookie file physically exists
    in the TiktokUploader directory and hasn't posted today.
    """
    accounts = db.execute(
        """
        SELECT t.id, t.username, t.cookies_file,
               p.ip_address AS proxy_host, p.port AS proxy_port,
               p.username AS proxy_username, p.password AS proxy_password,
               p.protocol AS proxy_protocol
        FROM tiktok_accounts t
        LEFT JOIN proxies p ON t.proxy_id = p.id
        WHERE t.account_status = 'active'
          AND t.shadow_banned = false
          AND t.cookies_file IS NOT NULL
        ORDER BY t.last_post_at ASC NULLS FIRST
        """
    )
    for acc in (accounts or []):
        username = acc["username"]
        # cookies_file column may store the actual session name (e.g. 'nuggerchicken433')
        cookie_session = acc.get("cookies_file") or username
        cookie_path = os.path.join(TIKTOK_UPLOADER_DIR, f"TK_cookies_{cookie_session}.json")
        if os.path.exists(cookie_path):
            logger.info(f"Found valid cookie for account: {username} (session: {cookie_session})")
            acc["_session_name"] = cookie_session  # store resolved session name
            return acc
        # also try username directly
        cookie_path2 = os.path.join(TIKTOK_UPLOADER_DIR, f"TK_cookies_{username}.json")
        if os.path.exists(cookie_path2):
            logger.info(f"Found valid cookie for account: {username}")
            acc["_session_name"] = username
            return acc
        logger.debug(f"No cookie found for {username} (tried: {cookie_session}, {username}), skipping")
    return None


def search_anime_shorts(max_results: int = 20) -> list[dict]:
    """
    Search YouTube for anime shorts, return list of video info dicts.
    """
    all_results = []
    for query in SEARCH_QUERIES:
        logger.info(f"Searching: {query}")
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "playlistend": max_results,
        }
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
                entries = (info or {}).get("entries", [])
                for e in entries:
                    vid_id = e.get("id") or e.get("url", "").split("?v=")[-1]
                    title = e.get("title", "")
                    duration = e.get("duration") or 0
                    # YouTube Shorts are <= 60 seconds
                    if vid_id and duration and duration <= 65:
                        all_results.append({
                            "id": vid_id,
                            "url": f"https://www.youtube.com/shorts/{vid_id}",
                            "title": title,
                            "duration": duration,
                        })
            except Exception as e:
                logger.warning(f"Search failed for '{query}': {e}")
        if all_results:
            break  # stop at first working query

    return all_results


def already_posted(video_id: str) -> bool:
    """Check if we have already posted this YouTube video today."""
    row = db.execute_one(
        """
        SELECT id FROM yt_arbitrage_log
        WHERE youtube_id = %s
          AND DATE(posted_at) = CURRENT_DATE
        LIMIT 1
        """,
        (video_id,),
    )
    return row is not None


def record_upload(video_id: str, title: str, account: dict, result: dict):
    """Record the upload attempt in yt_arbitrage_log."""
    try:
        db.execute(
            """
            INSERT INTO yt_arbitrage_log
                (youtube_id, youtube_title, tiktok_account, success, error_message)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (video_id, title, account["username"], result["success"], result.get("error")),
        )
    except Exception as e:
        logger.warning(f"Could not record upload: {e}")


def download_video(url: str, output_dir: str) -> tuple[str | None, dict | None]:
    """Download video, return (file_path, info_dict)."""
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
        "quiet": False,
        "merge_output_format": "mp4",
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            # If merged to mp4 the extension may differ
            if not os.path.exists(path):
                path = path.rsplit(".", 1)[0] + ".mp4"
            return path, info
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None, None


# ─── Main ────────────────────────────────────────────────────────────────────

def main(url: str | None = None, caption: str | None = None, hashtags: list[str] | None = None) -> dict:

    # 1. Get a TikTok account with a valid local cookie
    account = get_account_with_valid_cookie()
    if not account:
        msg = f"No TikTok accounts with valid cookie files found in {TIKTOK_UPLOADER_DIR}"
        logger.error(msg)
        return {"success": False, "error": msg}

    # 2. Choose video — either manually provided or auto-discovered
    if url:
        video_id = url.split("/")[-1].split("?")[0]
        chosen = {"id": video_id, "url": url, "title": caption or "Anime Short"}
    else:
        logger.info("Auto-discovering anime shorts on YouTube...")
        candidates = search_anime_shorts(max_results=15)
        chosen = None
        for v in candidates:
            if not already_posted(v["id"]):
                chosen = v
                break

        if not chosen:
            return {"success": False, "error": "No fresh anime shorts found to post."}

    logger.info(f"Selected video: [{chosen['id']}] {chosen['title']}")

    # 3. Download
    videos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "videos")
    os.makedirs(videos_dir, exist_ok=True)
    video_path, info = download_video(chosen["url"], videos_dir)

    if not video_path or not os.path.exists(video_path):
        return {"success": False, "error": "Video download failed."}

    # 4. Build caption
    use_caption = caption or chosen["title"]
    use_hashtags = hashtags or ANIME_HASHTAGS
    hashtag_str = " ".join(f"#{h.strip('#')}" for h in use_hashtags)
    full_caption = f"{use_caption}\n\n{hashtag_str}"

    # 5. Build proxy string if account has one
    proxy_str = None
    if account.get("proxy_host"):
        proto = account.get("proxy_protocol") or "http"
        host = account["proxy_host"]
        port = account.get("proxy_port") or "80"
        user = account.get("proxy_username") or ""
        pw = account.get("proxy_password") or ""
        if user and pw:
            proxy_str = f"{proto}://{user}:{pw}@{host}:{port}"
        else:
            proxy_str = f"{proto}://{host}:{port}"

    # 6. Upload to TikTok
    session_name = account.get("_session_name") or account["username"]
    logger.info(f"Uploading to TikTok as @{account['username']} (session: {session_name}) ...")
    result = do_tiktok_upload_v2(
        video_path=video_path,
        caption_text=full_caption,
        session_name=session_name,
        music_id=None,
        proxy=proxy_str,
    )

    logger.info(f"Upload result: {result}")

    # 7. Record result
    record_upload(chosen["id"], chosen["title"], account, result)

    # 8. Clean up downloaded file
    try:
        if os.path.exists(video_path):
            os.remove(video_path)
    except Exception:
        pass

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download a YouTube anime short and post to TikTok.")
    parser.add_argument("--url", default=None, help="Specific YouTube URL (optional; auto-discovers if omitted)")
    parser.add_argument("--caption", default=None, help="TikTok caption (optional)")
    parser.add_argument("--hashtags", nargs="+", default=None, help="Hashtags without #")
    args = parser.parse_args()

    result = main(args.url, args.caption, args.hashtags)
    print("Result:", result)
