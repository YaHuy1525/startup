#!/usr/bin/env python3
"""
Upload a video to TikTok via TiktokAutoUploader (requests-based, no Playwright).
Picks the next available active account from the DB, uploads, and records the result.

Initial setup (one-time per account):
    cd D:\\Code\\startup\\TiktokAutoUploader
    python cli.py login -n <session_name>
    Then insert the account into tiktok_accounts with cookies_file = <session_name>

Usage:
    python3 scripts/upload_tiktok.py --video-id <db_video_id>

Output:
    JSON with upload result.
    Exit 0 on success, 1 on failure.
"""
import sys
import json
import time
import argparse
import os

# Ensure the root 'manga-automation' directory is in PYTHONPATH so 'scripts.utils' resolves properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

load_dotenv()

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("upload_tiktok")


def _agent_dbg_upload(data: dict) -> None:
    # #region agent log
    try:
        _p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "debug-0f0c72.log"))
        payload = {
            "sessionId": "0f0c72",
            "timestamp": int(time.time() * 1000),
            "location": "upload_tiktok.py:main",
            "message": "upload_tiktok main exit shape",
            "data": data,
            "hypothesisId": "H3",
        }
        with open(_p, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass

    # #endregion


MAX_UPLOADS_PER_DAY = int(os.environ.get("MAX_UPLOADS_PER_ACCOUNT_DAY", 3))

UPLOADER_DIR = os.path.abspath(
    os.environ.get(
        "TIKTOK_UPLOADER_DIR",
        os.path.join(os.path.dirname(__file__), "..", "..", "TiktokAutoUploader"),
    )
)


def get_available_account() -> dict | None:
    forced_username = os.environ.get("DIRECT_TIKTOK_ACCOUNT", "").strip()
    if forced_username:
        return db.execute_one(
            """
            SELECT t.id, t.username, t.cookies_file, t.email, t.tiktok_password,
                   p.ip_address, p.port, p.username as proxy_user, p.password as proxy_pass
            FROM tiktok_accounts t
            LEFT JOIN proxies p ON t.proxy_id = p.id
            WHERE t.username = %s
              AND t.account_status = 'active'
              AND t.shadow_banned = false
              AND t.cookies_file IS NOT NULL
            LIMIT 1
            """,
            (forced_username,),
        )

    return db.execute_one(
        """
        SELECT t.id, t.username, t.cookies_file, t.email, t.tiktok_password,
               p.ip_address, p.port, p.username as proxy_user, p.password as proxy_pass
        FROM tiktok_accounts t
        LEFT JOIN proxies p ON t.proxy_id = p.id
        WHERE t.account_status = 'active'
          AND t.shadow_banned = false
          AND t.cookies_file IS NOT NULL
          AND (
              t.last_post_at IS NULL
              OR DATE(t.last_post_at) < CURRENT_DATE
              OR (
                  DATE(t.last_post_at) = CURRENT_DATE
                  AND (
                      SELECT COUNT(*) FROM upload_results ur
                      WHERE ur.account_id = t.id
                        AND DATE(ur.uploaded_at) = CURRENT_DATE
                        AND ur.success = true
                  ) < %s
              )
          )
        ORDER BY t.last_post_at ASC NULLS FIRST
        LIMIT 1
        """,
        (MAX_UPLOADS_PER_DAY,),
    )


def get_video(video_id: int) -> dict | None:
    return db.execute_one(
        """
        SELECT v.id, v.file_path, v.caption, v.hashtags,
               m.title AS manga_title,
               sp.tiktok_sound_id, sp.tiktok_sound_title
        FROM videos v
        JOIN manga_chapters mc ON v.chapter_id = mc.id
        JOIN manga m ON mc.manga_id = m.id
        LEFT JOIN selected_panels sp ON sp.chapter_id = mc.id
        WHERE v.id = %s AND v.status IN ('ready', 'publishing')
        ORDER BY sp.selected_at DESC
        LIMIT 1
        """,
        (video_id,),
    )


def build_caption(video: dict) -> str:
    caption = video.get("caption") or "Must watch moment! 🔥"
    hashtags: list[str] = video.get("hashtags") or ["#fyp", "#shorts", "#viral"]
    hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    full = f"{caption}\n\n{hashtag_str}"
    return full[:2200]


def do_tiktok_upload(video_path: str, caption_text: str, session_name: str, music_id: str | None = None, proxy: str | None = None) -> dict:
    """
    Upload using TiktokAutoUploader library (requests-based, no browser needed).
    session_name is the name used with `python cli.py login -n <session_name>`.
    Cookies are loaded from TiktokAutoUploader/CookiesDir/tiktok_session-<session_name>.
    music_id, if provided, is passed to TikTok's publish API to overlay a native sound.
    """
    if not session_name:
        return {
            "success": False,
            "tiktok_url": None,
            "error": "No session_name set. Set cookies_file = <login_name> in tiktok_accounts table.",
        }

    if not os.path.isdir(UPLOADER_DIR):
        return {
            "success": False,
            "tiktok_url": None,
            "error": f"TiktokAutoUploader not found at: {UPLOADER_DIR}. Set TIKTOK_UPLOADER_DIR in .env",
        }

    cookie_file = os.path.join(UPLOADER_DIR, "CookiesDir", f"tiktok_session-{session_name}.cookie")
    if not os.path.exists(cookie_file):
        return {
            "success": False,
            "tiktok_url": None,
            "error": (
                f"No cookies found for '{session_name}'. "
                f"Run first: cd {UPLOADER_DIR} && python cli.py login -n {session_name}"
            ),
        }

    abs_video_path = os.path.abspath(video_path)
    if not os.path.exists(abs_video_path):
        return {"success": False, "tiktok_url": None, "error": f"Video file not found: {abs_video_path}"}

    original_dir = os.getcwd()
    try:
        os.chdir(UPLOADER_DIR)
        if UPLOADER_DIR not in sys.path:
            sys.path.insert(0, UPLOADER_DIR)

        from tiktok_uploader.tiktok import upload_video

        # Apply proxy to environment for the requests library underneath
        if proxy:
            logger.info(f"Using proxy: {proxy}")
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy

        if music_id:
            logger.info(f"Using TikTok native sound id={music_id}")
        logger.info(f"Uploading via TiktokAutoUploader: session={session_name}, video={abs_video_path}")
        result = upload_video(
            session_user=session_name,
            video=abs_video_path,
            title=caption_text[:150],
            music_id=music_id or None,
        )

        success = result is not False
        logger.info(f"Upload result: {'success' if success else 'failed'}")
        return {
            "success": success,
            "tiktok_url": None,
            "error": None if success else "Upload returned False — check TikTok session cookies",
        }

    except Exception as e:
        logger.error(f"TiktokAutoUploader error: {e}")
        return {"success": False, "tiktok_url": None, "error": str(e)}
    finally:
        os.chdir(original_dir)
        if proxy:
            os.environ.pop("HTTP_PROXY", None)
            os.environ.pop("HTTPS_PROXY", None)

def do_tiktok_upload_v2(video_path: str, caption_text: str, session_name: str, music_id: str | None = None, proxy: str | None = None) -> dict:
    """
    Upload using the NEW tiktokautouploader (phantomwright based).
    """
    if not session_name:
        return {
            "success": False,
            "tiktok_url": None,
            "error": "No session_name set.",
        }

    NEW_UPLOADER_DIR = os.path.abspath(
        os.environ.get(
            "TIKTOK_UPLOADER_V2_DIR",
            os.path.join(os.path.dirname(__file__), "..", "..", "TiktokUploader"),
        )
    )

    if not os.path.isdir(NEW_UPLOADER_DIR):
        return {
            "success": False,
            "tiktok_url": None,
            "error": f"TiktokUploader v2 not found at: {NEW_UPLOADER_DIR}",
        }

    abs_video_path = os.path.abspath(video_path)
    if not os.path.exists(abs_video_path):
        return {"success": False, "tiktok_url": None, "error": f"Video file not found: {abs_video_path}"}

    original_dir = os.getcwd()
    try:
        os.chdir(NEW_UPLOADER_DIR)
        if NEW_UPLOADER_DIR not in sys.path:
            sys.path.insert(0, NEW_UPLOADER_DIR)

        from tiktokautouploader import upload_tiktok

        proxy_dict = None
        if proxy:
            from urllib.parse import urlparse
            p = urlparse(proxy)
            proxy_dict = {
                'server': f"{p.scheme}://{p.hostname}:{p.port}",
            }
            if p.username:
                proxy_dict['username'] = p.username
                proxy_dict['password'] = p.password

        cookie_file = f"TK_cookies_{session_name}.json"
        if not os.path.exists(cookie_file):
            logger.warning(f"No cookies {cookie_file} found in {NEW_UPLOADER_DIR}. The uploader may fail or prompt for login.")

        logger.info(f"Uploading via NEW tiktokautouploader: session={session_name}, video={abs_video_path}")
        
        import re
        hashtags = re.findall(r'#\w+', caption_text)
        clean_description = re.sub(r'#\w+', '', caption_text).strip()

        # Use non-headless when a virtual display is available (avoids TikTok bot detection)
        use_headless = os.environ.get("DISPLAY") is None

        result = upload_tiktok(
            video=abs_video_path,
            description=clean_description,
            accountname=session_name,
            hashtags=hashtags if hashtags else None,
            sound_name=music_id,
            headless=use_headless,
            stealth=True,
            proxy=proxy_dict
        )

        success = (result == 'Completed')
        logger.info(f"Upload result: {result}")
        return {
            "success": success,
            "tiktok_url": None,
            "error": None if success else f"Upload returned: {result}",
        }

    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        logger.error(f"tiktokautouploader error: {err_msg}")
        return {"success": False, "tiktok_url": None, "error": err_msg}
    finally:
        os.chdir(original_dir)


def record_result(video_id: int, account_id: int, result: dict):
    db.execute(
        """
        INSERT INTO upload_results
            (video_id, account_id, platform, success, error_message, tiktok_url)
        VALUES (%s, %s, 'tiktok', %s, %s, %s)
        """,
        (
            video_id,
            account_id,
            result["success"],
            result.get("error"),
            result.get("tiktok_url"),
        ),
    )

    if result["success"]:
        db.execute(
            """
            UPDATE tiktok_accounts
            SET last_post_at = NOW(), total_posts = total_posts + 1,
                upload_failures = 0
            WHERE id = %s
            """,
            (account_id,),
        )
        db.execute(
            "UPDATE videos SET status = 'published' WHERE id = %s",
            (video_id,),
        )
        db.execute(
            """
            INSERT INTO published_videos
                (video_id, account_id, platform, platform_url, status)
            VALUES (%s, %s, 'tiktok', %s, 'published')
            """,
            (video_id, account_id, result.get("tiktok_url")),
        )
    else:
        db.execute(
            """
            UPDATE tiktok_accounts
            SET upload_failures = upload_failures + 1
            WHERE id = %s
            """,
            (account_id,),
        )
        db.execute(
            "UPDATE videos SET status = 'failed' WHERE id = %s",
            (video_id,),
        )


_HOST_VIDEOS_DIR = os.path.abspath(
    os.environ.get("HOST_VIDEOS_DIR") or os.path.join(os.path.dirname(__file__), "..", "data", "videos")
)
_ARBITRAGE_VIDEOS_DIR = os.path.abspath(
    os.environ.get("ARBITRAGE_VIDEOS_DIR") or os.path.join(os.path.dirname(__file__), "..", "data", "arbitrage_videos")
)


def resolve_video_path(file_path: str) -> str:
    """Map container paths (/data/...) to host paths when running outside Docker."""
    if os.path.exists(file_path):
        return file_path
    filename = os.path.basename(file_path)
    for base in (_HOST_VIDEOS_DIR, _ARBITRAGE_VIDEOS_DIR):
        candidate = os.path.join(base, filename)
        if os.path.exists(candidate):
            return candidate
    return file_path


def main(video_id: int) -> dict:
    video = get_video(video_id)
    if not video:
        logger.error(f"Video id={video_id} not found or not ready")
        _agent_dbg_upload({"video_id": video_id, "success": None, "reason": "no_video_or_not_ready"})
        return {}

    account = get_available_account()
    if not account:
        logger.error("No available TikTok account (all at daily limit or banned)")
        _agent_dbg_upload({"video_id": video_id, "success": False, "reason": "no_available_account"})
        return {"error": "no_available_account"}

    session_name = account.get("cookies_file") or account["username"]
    music_id = video.get("tiktok_sound_id")
    sound_title = video.get("tiktok_sound_title")
    if music_id:
        logger.info(f"TikTok sound: '{sound_title}' (id={music_id})")
    else:
        logger.info("No TikTok sound selected — uploading with original audio")

    logger.info(f"Uploading video_id={video_id} via account={account['username']} (session={session_name})")

    caption = build_caption(video)
    video_path = resolve_video_path(video["file_path"])
    
    proxy_url = None
    if account.get("ip_address"):
        auth = f"{account['proxy_user']}:{account['proxy_pass']}@" if account.get("proxy_user") else ""
        proxy_url = f"http://{auth}{account['ip_address']}:{account['port']}"

    use_v2 = os.environ.get("USE_NEW_TIKTOK_UPLOADER", "false").lower() in ("true", "1", "yes")
    logger.info(f"TikTok upload path: {'v2 (TiktokUploader)' if use_v2 else 'v1 (TiktokAutoUploader)'}")

    if use_v2:
        result = do_tiktok_upload_v2(
            video_path=video_path,
            caption_text=caption,
            session_name=session_name,
            music_id=music_id,
            proxy=proxy_url
        )
    else:
        result = do_tiktok_upload(
            video_path=video_path,
            caption_text=caption,
            session_name=session_name,
            music_id=music_id,
            proxy=proxy_url
        )

    record_result(video_id, account["id"], result)

    _agent_dbg_upload(
        {
            "video_id": video_id,
            "success": result.get("success"),
            "error_prefix": (str(result.get("error") or ""))[:160],
        }
    )
    return {
        "video_id": video_id,
        "account": account["username"],
        "success": result["success"],
        "tiktok_url": result.get("tiktok_url"),
        "error": result.get("error"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", type=int, required=True)
    args = parser.parse_args()

    result = main(args.video_id)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("success") else 1)
