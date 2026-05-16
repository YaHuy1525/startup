#!/usr/bin/env python3
"""
Phase 5: Multi-Platform Distribution.
Takes downloaded arbitrage assets and uploads to TikTok and/or YouTube Shorts.

Usage:
    python3 scripts/distribute_arbitrage.py [--platforms tiktok youtube] [--batch 5]
"""
import os, sys, json, time, argparse, requests, re
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.adapters import aitoearn_client

logger = setup_logger("distribute_arbitrage")

PYTHON_WORKER_URL = os.environ.get("PYTHON_WORKER_URL", "http://localhost:8080")
MASTRA_API_URL = os.environ.get("MASTRA_API_URL", "http://localhost:3001")
TIKTOK_UPLOADER_DIR = os.environ.get("TIKTOK_UPLOADER_DIR", r"D:\Code\startup\TiktokAutoUploader")
MAX_UPLOAD_RETRIES = int(os.environ.get("ARBITRAGE_UPLOAD_RETRIES", "2"))
RETRY_DELAY_SECONDS = int(os.environ.get("ARBITRAGE_UPLOAD_RETRY_DELAY_SECONDS", "8"))
EDITORIAL_MODEL = os.environ.get("EDITORIAL_MODEL", "claude-sonnet-4-20250514")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_raw_preserve = os.environ.get("CAPTION_PRESERVE_SERIES", "")
CAPTION_PRESERVE_SERIES = [x.strip().lower() for x in _raw_preserve.split(",") if x.strip()]
ARBITRAGE_AITOEARN_PRIMARY = os.environ.get("ARBITRAGE_AITOEARN_PRIMARY", "0").strip().lower() in {"1", "true", "yes"}


def _looks_like_asset_filename(text: str) -> bool:
    return bool(re.search(r"\basset[_\-\s]?\d+\b", (text or "").lower()))


def _extract_title_hashtags(title: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"#([A-Za-z0-9_]+)", title or "")]


def _clean_title(title: str) -> str:
    raw = (title or "").strip()
    raw = re.sub(r"#([A-Za-z0-9_]+)", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" -|")
    if not raw or _looks_like_asset_filename(raw):
        return ""
    return raw


def _should_preserve_caption(clean_title: str) -> bool:
    text = (clean_title or "").lower()
    return any(key in text for key in CAPTION_PRESERVE_SERIES)


def _build_fallback_caption(tag: str, title: str) -> str:
    clean_title = _clean_title(title)
    if clean_title:
        return clean_title
    return f"{tag} short clip".strip()


def _normalize_hashtags(tag: str, hashtags: list) -> list[str]:
    normalized = []
    seen = set()
    for raw in ([f"#{tag}"] + (hashtags or []) + ["#fyp", "#shorts", "#viral", "#trending"]):
        cleaned = "#" + str(raw).lstrip("#").strip().lower()
        cleaned = re.sub(r"[^#a-z0-9_]", "", cleaned)
        if cleaned == "#" or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
        if len(normalized) >= 8:
            break
    return normalized


def _ai_caption_from_source(tag: str, title: str, source_hashtags: list[str]) -> tuple[str, list[str]] | None:
    if not ANTHROPIC_API_KEY:
        return None
    clean_title = _clean_title(title)
    if not clean_title:
        return None

    preserve_mode = _should_preserve_caption(clean_title)
    prompt = (
        "You rewrite social captions for short-form video clips.\n"
        "Return ONLY valid JSON with keys: caption (string), hashtags (array of strings without #).\n"
        f"Source title: {clean_title}\n"
        f"Topic tag: {tag}\n"
        f"Source hashtags: {json.dumps(source_hashtags, ensure_ascii=False)}\n"
        f"Preserve mode: {'true' if preserve_mode else 'false'}\n"
        "Rules:\n"
        "- If preserve mode is true: keep the caption close to source meaning/wording.\n"
        "- If preserve mode is false: paraphrase the source title naturally.\n"
        "- Never output filename-like text such as asset_123.\n"
        "- Generate 4-8 hashtags by paraphrasing/expanding source hashtags + topic.\n"
        "- Do not include # prefix in hashtags array."
    )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=EDITORIAL_MODEL,
            max_tokens=260,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        parsed = json.loads(raw)
        caption = (parsed.get("caption") or "").strip()
        hashtags = [str(x).strip() for x in (parsed.get("hashtags") or []) if str(x).strip()]
        if not caption or _looks_like_asset_filename(caption):
            return None
        return caption, hashtags
    except Exception as e:
        logger.warning(f"AI caption generation failed; using fallback: {e}")
        return None


def generate_caption(hashtag: str, title: str, source_hashtags: list[str] | None = None) -> tuple[str, list[str]]:
    """Generate caption + hashtags from source metadata, preferring AI rewrite."""
    tag = hashtag.lstrip("#").strip().lower() or "viral"
    source_hashtags = source_hashtags or []

    ai_result = _ai_caption_from_source(tag, title, source_hashtags + _extract_title_hashtags(title))
    if ai_result:
        caption, ai_hashtags = ai_result
        hashtags = _normalize_hashtags(tag, ai_hashtags + source_hashtags)
        return caption, hashtags

    # Try the mastra caption API first
    try:
        r = requests.post(
            f"{MASTRA_API_URL}/captions/generate",
            json={"videoId": 0, "mangaTitle": tag, "chapterNumber": "1",
                  "genre": "general", "formulaType": "recommendation"},
            timeout=10,
        )
        if r.ok:
            data = r.json()
            caption = (data.get("caption") or "").strip()
            hashtags = _normalize_hashtags(tag, data.get("hashtags", []))
            if not caption or _looks_like_asset_filename(caption):
                caption = _build_fallback_caption(tag, title)
            return caption, hashtags
    except Exception:
        pass

    # Fallback: simple template
    caption = _build_fallback_caption(tag, title)
    hashtags = _normalize_hashtags(tag, [])
    return caption, hashtags


def upload_to_tiktok(asset: dict, caption: str, hashtags: list) -> dict:
    """Upload to TikTok by calling upload_tiktok.main() directly in-process."""
    try:
        chapter = db.execute_one("SELECT id FROM manga_chapters LIMIT 1")
        if not chapter:
            return {"success": False, "error": "No chapter reference found in DB"}

        hashtag_arr = "{" + ",".join(h.lstrip("#") for h in hashtags) + "}"
        video_row = db.execute_one(
            """
            INSERT INTO videos (chapter_id, file_path, caption, hashtags, status, duration_secs)
            VALUES (%s, %s, %s, %s, 'ready', %s)
            RETURNING id
            """,
            (chapter["id"], asset["local_path"], caption, hashtag_arr,
             asset.get("duration_secs") or 60),
        )
        video_id = video_row["id"]

        import scripts.upload_tiktok as upload_tiktok_module
        result_data = upload_tiktok_module.main(video_id)

        success = result_data.get("success", False)
        if not success:
            db.execute("DELETE FROM videos WHERE id=%s AND status='ready'", (video_id,))

        return {"success": success, "error": result_data.get("error")}
    except Exception as e:
        logger.error(f"TikTok upload failed: {e}")
        return {"success": False, "error": str(e)[:500]}


def upload_to_youtube(asset: dict, caption: str, hashtags: list) -> dict:
    """Upload to YouTube Shorts using google-api-python-client directly."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        import googleapiclient.discovery
        import googleapiclient.http
    except ImportError:
        return {"success": False, "error": "google-api-python-client not installed. Add to requirements.txt"}

    client_id     = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token or refresh_token == "refresh_token":
        return {"success": False, "error": "YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN not set in env"}

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        creds.refresh(Request())
        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
    except Exception as e:
        return {"success": False, "error": f"YouTube auth failed: {e}"}

    video_path = asset.get("local_path")
    if not video_path or not os.path.exists(video_path):
        return {"success": False, "error": f"Video file not found: {video_path}"}

    tag_list = [h.lstrip("#") for h in hashtags]
    description = caption + "\n\n#Shorts"

    body = {
        "snippet": {
            "title": caption[:100],
            "description": description[:5000],
            "tags": tag_list,
            "categoryId": "22",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }

    try:
        media = googleapiclient.http.MediaFileUpload(
            video_path, mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024
        )
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _, response = request.next_chunk()
        video_id = response["id"]
        url = f"https://www.youtube.com/shorts/{video_id}"
        logger.info(f"YouTube upload success: {url}")
        return {"success": True, "platform_url": url, "platform_post_id": video_id}
    except Exception as e:
        return {"success": False, "error": f"YouTube upload error: {e}"}


def _record_social_upload(video_id: int | None, platform: str, result: dict):
    """Persist successful upload into published_videos for analytics consistency."""
    if not result.get("success") or not video_id:
        return
    db.execute(
        """
        INSERT INTO published_videos (video_id, platform, account_name, platform_post_id, platform_url)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (video_id, platform, "arbitrage_pipeline", result.get("platform_post_id"), result.get("platform_url")),
    )


def _video_pin_from_asset(asset: dict, caption: str, hashtags: list) -> dict:
    """
    Fallback Pinterest path when API auth is unavailable:
    create a queue item in DB (for external poster) and return queued state.
    """
    pinterest_board = os.environ.get("PINTEREST_DEFAULT_BOARD", "content-highlights")
    landing_url = os.environ.get("PINTEREST_DEFAULT_LANDING_URL", "")
    db.execute(
        """
        INSERT INTO arbitrage_uploads
            (asset_id, platform, caption, hashtags, status, error_message, platform_url, platform_post_id)
        VALUES (%s, 'pinterest', %s, %s, 'pending', %s, %s, %s)
        """,
        (
            asset["id"],
            caption,
            "{" + ",".join(h.lstrip("#") for h in hashtags) + "}",
            f"queued_for_board:{pinterest_board}",
            landing_url or None,
            None,
        ),
    )
    return {"success": True, "platform_url": landing_url, "platform_post_id": None, "queued": True}


def upload_to_instagram(asset: dict, caption: str, hashtags: list) -> dict:
    """
    Upload via Instagram Graph API if tokens are available, otherwise queue as pending.
    """
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    ig_token = (
        (os.environ.get("META_API_KEY") or os.environ.get("META_ACCESS_TOKEN") or "").strip()
        or (os.environ.get("INSTAGRAM_ACCESS_TOKEN") or "").strip()
        or None
    )
    if not ig_user_id or not ig_token:
        return {"success": True, "queued": True, "platform_url": None, "platform_post_id": None}

    try:
        # Requires a publicly accessible URL; fallback to local-path note.
        video_url = asset.get("public_video_url") or asset.get("local_path")
        if not video_url:
            return {"success": False, "error": "No video URL/path for Instagram upload"}
        create = requests.post(
            f"https://graph.facebook.com/v22.0/{ig_user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": (caption + " " + " ".join(hashtags))[:2100],
                "access_token": ig_token,
            },
            timeout=20,
        )
        create.raise_for_status()
        creation_id = create.json().get("id")
        if not creation_id:
            return {"success": False, "error": "Instagram media creation id missing"}
        publish = requests.post(
            f"https://graph.facebook.com/v22.0/{ig_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": ig_token},
            timeout=20,
        )
        publish.raise_for_status()
        post_id = publish.json().get("id")
        return {"success": True, "platform_post_id": post_id, "platform_url": None}
    except Exception as e:
        return {"success": False, "error": f"Instagram upload error: {e}"}


def upload_to_facebook(asset: dict, caption: str, hashtags: list) -> dict:
    """
    Upload via Facebook Graph API if page credentials exist, otherwise queue as pending.
    """
    page_id = os.environ.get("FACEBOOK_PAGE_ID")
    page_token = (
        (os.environ.get("META_API_KEY") or os.environ.get("META_ACCESS_TOKEN") or "").strip()
        or (os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
        or None
    )
    if not page_id or not page_token:
        return {"success": True, "queued": True, "platform_url": None, "platform_post_id": None}

    try:
        video_url = asset.get("public_video_url") or asset.get("local_path")
        if not video_url:
            return {"success": False, "error": "No video URL/path for Facebook upload"}
        post = requests.post(
            f"https://graph.facebook.com/v22.0/{page_id}/video_reels",
            data={
                "upload_phase": "finish",
                "description": (caption + " " + " ".join(hashtags))[:2200],
                "video_url": video_url,
                "access_token": page_token,
            },
            timeout=20,
        )
        post.raise_for_status()
        post_id = post.json().get("video_id") or post.json().get("id")
        return {"success": True, "platform_post_id": post_id, "platform_url": None}
    except Exception as e:
        return {"success": False, "error": f"Facebook upload error: {e}"}


def log_upload(asset_id: int, platform: str, caption: str, hashtags: list, result: dict):
    """Record upload attempt in arbitrage_uploads."""
    hashtag_arr = "{" + ",".join(h.lstrip("#") for h in hashtags) + "}"
    db.execute(
        """
        INSERT INTO arbitrage_uploads
            (asset_id, platform, caption, hashtags, status, error_message, platform_url, platform_post_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (asset_id, platform, caption, hashtag_arr,
         "success" if result["success"] else "failed",
         result.get("error"),
         result.get("platform_url"),
         result.get("platform_post_id")),
    )


def process_pending(platforms: list = None, batch: int = 5) -> dict:
    """Distribute up to `batch` downloaded assets to specified platforms."""
    if platforms is None:
        platforms = os.environ.get("ARBITRAGE_PLATFORMS", "tiktok").split(",")

    assets = db.execute(
        """
        SELECT a.*, t.hashtag
        FROM arbitrage_assets a
        JOIN trend_intel t ON a.trend_id = t.id
        WHERE a.status = 'downloaded'
        ORDER BY a.created_at ASC
        LIMIT %s
        """,
        (batch,),
    )

    if not assets:
        logger.info("No downloaded assets to distribute")
        # #region agent log
        try:
            _p = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "debug-0f0c72.log")
            )
            with open(_p, "a", encoding="utf-8") as _f:
                _f.write(
                    json.dumps(
                        {
                            "sessionId": "0f0c72",
                            "timestamp": int(time.time() * 1000),
                            "location": "distribute_arbitrage.py:process_pending",
                            "message": "no downloaded assets",
                            "data": {"processed": 0, "uploaded": 0, "failed": 0},
                            "hypothesisId": "H2",
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
        return {"processed": 0, "uploaded": 0, "failed": 0}

    uploaded = 0
    failed = 0

    for asset in assets:
        caption, hashtags = generate_caption(
            asset["hashtag"],
            asset.get("youtube_title", ""),
            asset.get("source_hashtags") or [],
        )
        asset_success = False

        if ARBITRAGE_AITOEARN_PRIMARY and aitoearn_client.enabled():
            remote_publish = aitoearn_client.run_stage(
                "publish",
                {
                    "asset_id": asset["id"],
                    "video_path": asset.get("local_path"),
                    "caption": caption,
                    "hashtags": hashtags,
                    "channels": platforms,
                    "idempotency_key": f"arb-asset-{asset['id']}",
                },
            )
            if remote_publish.get("ok"):
                asset_success = True
                db.execute(
                    "UPDATE arbitrage_assets SET status='distributed', updated_at=NOW() WHERE id=%s",
                    (asset["id"],),
                )
                uploaded += 1
                logger.info(f"Uploaded asset {asset['id']} via AiToEarn primary publish")
                continue
            logger.warning(f"AiToEarn publish failed for asset {asset['id']}; falling back local path")

        for platform in platforms:
            platform = platform.strip()
            logger.info(f"Uploading asset {asset['id']} to {platform}")

            def _perform_upload() -> dict:
                if platform == "tiktok":
                    return upload_to_tiktok(asset, caption, hashtags)
                if platform == "youtube":
                    return upload_to_youtube(asset, caption, hashtags)
                if platform == "instagram":
                    return upload_to_instagram(asset, caption, hashtags)
                if platform == "facebook":
                    return upload_to_facebook(asset, caption, hashtags)
                if platform == "pinterest":
                    return _video_pin_from_asset(asset, caption, hashtags)
                return {"success": False, "error": f"Unknown platform: {platform}"}

            attempt = 0
            result = {"success": False, "error": "not attempted"}
            while attempt <= MAX_UPLOAD_RETRIES:
                result = _perform_upload()
                if result.get("success"):
                    break
                attempt += 1
                if attempt <= MAX_UPLOAD_RETRIES:
                    logger.warning(
                        f"Retrying asset {asset['id']} on {platform} attempt {attempt}/{MAX_UPLOAD_RETRIES}"
                    )
                    time.sleep(RETRY_DELAY_SECONDS)

            log_upload(asset["id"], platform, caption, hashtags, result)

            # #region agent log
            if not result.get("success"):
                try:
                    _p = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), "..", "..", "debug-0f0c72.log")
                    )
                    with open(_p, "a", encoding="utf-8") as _f:
                        _f.write(
                            json.dumps(
                                {
                                    "sessionId": "0f0c72",
                                    "timestamp": int(time.time() * 1000),
                                    "location": "distribute_arbitrage.py:platform_upload",
                                    "message": "per-platform upload failed",
                                    "data": {
                                        "asset_id": asset["id"],
                                        "platform": platform,
                                        "error_prefix": (str(result.get("error") or ""))[:200],
                                    },
                                    "hypothesisId": "H4",
                                }
                            )
                            + "\n"
                        )
                except Exception:
                    pass
            # #endregion

            if result["success"]:
                asset_success = True
                # Best effort: bind upload to a video row if we have one.
                video_row = db.execute_one(
                    "SELECT id FROM videos WHERE file_path = %s ORDER BY id DESC LIMIT 1",
                    (asset.get("local_path"),),
                )
                _record_social_upload(video_row["id"] if video_row else None, platform, result)
                logger.info(f"✅ Uploaded asset {asset['id']} to {platform}")
            else:
                logger.error(f"❌ Failed asset {asset['id']} on {platform}: {result.get('error', 'no error details')}")

        # Mark asset as distributed if at least one platform succeeded
        if asset_success:
            db.execute(
                "UPDATE arbitrage_assets SET status='distributed', updated_at=NOW() WHERE id=%s",
                (asset["id"],),
            )
            # Mark trend as done if all its assets are distributed
            db.execute(
                """
                UPDATE trend_intel SET status='done', processed_at=NOW()
                WHERE id=%s
                AND NOT EXISTS (
                    SELECT 1 FROM arbitrage_assets
                    WHERE trend_id=%s AND status NOT IN ('distributed','failed')
                )
                """,
                (asset["trend_id"], asset["trend_id"]),
            )
            # Register content fingerprint to prevent re-uploads
            try:
                from scripts.memory_manager import register_content, record_upload
                if asset.get("youtube_url"):
                    register_content(url=asset["youtube_url"],
                                     metadata={"trend": asset.get("hashtag", ""),
                                               "platform": ",".join(platforms)})
                record_upload(account_name="pipeline", success=True)
            except Exception as mem_err:
                logger.warning(f"ChromaDB fingerprint write skipped: {mem_err}")
            uploaded += 1
        else:
            db.execute(
                "UPDATE arbitrage_assets SET status='failed', updated_at=NOW() WHERE id=%s",
                (asset["id"],),
            )
            failed += 1

    # #region agent log
    try:
        _p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "debug-0f0c72.log"))
        with open(_p, "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "0f0c72",
                        "timestamp": int(time.time() * 1000),
                        "location": "distribute_arbitrage.py:process_pending",
                        "message": "distribute batch complete",
                        "data": {
                            "processed": len(assets),
                            "uploaded": uploaded,
                            "failed": failed,
                            "platforms": platforms,
                        },
                        "hypothesisId": "H2",
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion

    return {"processed": len(assets), "uploaded": uploaded, "failed": failed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platforms", nargs="+", default=["tiktok"])
    parser.add_argument("--batch", type=int, default=5)
    args = parser.parse_args()
    result = process_pending(args.platforms, args.batch)
    print(json.dumps(result))
