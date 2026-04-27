"""
CrewAI Tool wrappers around existing pipeline functions.
Each tool is a thin adapter so agents can call real pipeline logic.
"""
import os, sys, json, time, re
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from crewai.tools import tool
except ImportError:
    # Fallback decorator if crewai not installed
    def tool(name):
        def decorator(fn):
            return fn
        return decorator


import logging
logger = logging.getLogger("crew_tools")


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_title_hashtags(raw_title: str) -> tuple[str, list[str]]:
    """
    Pull hashtag-like tokens from the original title and keep a cleaned base title.
    Returns (clean_title, hashtags_without_hash_prefix).
    """
    title = _clean_text(raw_title or "")
    if not title:
        return "", []

    found = re.findall(r"#([A-Za-z0-9_]+)", title)
    dedup = []
    seen = set()
    for tag in found:
        low = tag.lower()
        if low not in seen:
            seen.add(low)
            dedup.append(tag)
    clean_title = _clean_text(re.sub(r"#([A-Za-z0-9_]+)", "", title))
    return clean_title, dedup


def _paraphrase_title(raw_title: str) -> str:
    """
    Lightweight deterministic paraphrase to avoid direct title copying.
    """
    base, _ = _extract_title_hashtags(raw_title)
    if not base:
        return "Must watch short clip"

    # Keep intent but reframe wording.
    base = re.sub(r"\b(official|original|video|shorts?)\b", "", base, flags=re.IGNORECASE)
    base = _clean_text(base)
    if not base:
        base = "Must watch clip"
    return f"POV: {base} - remix edit"


def _build_asset_caption(asset_id: int, fallback_title: str = "") -> tuple[str, list[str]]:
    """
    Build caption text + hashtags from arbitrage source metadata.
    Uses:
    - original YouTube title (paraphrased)
    - trend hashtag
    - hashtags found in source title
    """
    default_tags = ["fyp", "shorts", "viral"]
    row = execute_one(
        """
        SELECT aa.youtube_title, ti.hashtag, ti.hashtag_candidates, ti.research_summary
        FROM arbitrage_assets aa
        LEFT JOIN trend_intel ti ON aa.trend_id = ti.id
        WHERE aa.id = %s
        """,
        (asset_id,),
    )
    if not row:
        caption = _paraphrase_title(fallback_title or "viral short")
        return caption, default_tags

    yt_title = row.get("youtube_title") or fallback_title or ""
    trend_tag = (row.get("hashtag") or "").lstrip("#").strip()
    research_tags = row.get("hashtag_candidates") or []
    research_summary = _clean_text(row.get("research_summary") or "")
    _, source_tags = _extract_title_hashtags(yt_title)

    tags = []
    if trend_tag:
        tags.append(trend_tag)
    tags.extend(research_tags[:3])
    tags.extend(source_tags)
    tags.extend(default_tags)

    dedup = []
    seen = set()
    for tag in tags:
        tag = re.sub(r"[^A-Za-z0-9_]", "", (tag or "")).strip()
        if not tag:
            continue
        low = tag.lower()
        if low in seen:
            continue
        seen.add(low)
        dedup.append(tag)
        if len(dedup) >= 6:
            break

    caption = _paraphrase_title(yt_title)
    if research_summary:
        summary_hint = research_summary.split(".")[0][:70].strip()
        if summary_hint:
            caption = f"{caption} | {summary_hint}"
    return caption, dedup

# #region agent log
def _agent_dbg(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        _p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "debug-0f0c72.log"))
        payload = {
            "sessionId": "0f0c72",
            "runId": "crew-tools",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_p, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
# #endregion

# ---------------------------------------------------------------------------
# Database imports
# ---------------------------------------------------------------------------
from scripts.utils.database import execute_one, execute


# ---------------------------------------------------------------------------
# Trend tools
# ---------------------------------------------------------------------------

@tool("fetch_tiktok_trends")
def fetch_tiktok_trends(region: str = "US", limit: int = 10) -> str:
    """
    Fetch trending TikTok hashtags via Apify and save to the database.
    Returns a JSON summary of fetched trends.
    """
    try:
        from scripts.fetch_tiktok_trends_apify import main as fetch_trends
        result = fetch_trends(region=region, limit=limit)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("query_trend_memory")
def query_trend_memory(query: str, n_results: int = 5) -> str:
    """
    Semantic search over ChromaDB trend_memory.
    Returns historically similar trends with performance data.
    Use this to check if a topic has been tried before and how it performed.
    """
    try:
        from scripts.memory_manager import query_similar_trends
        results = query_similar_trends(query, n_results)
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("get_declining_trends")
def get_declining_trends_tool() -> str:
    """
    Returns trends where views have declined >20% over recorded history.
    Use this to identify content to pivot away from.
    """
    try:
        from scripts.memory_manager import get_declining_trends
        results = get_declining_trends()
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# YouTube sourcing tools
# ---------------------------------------------------------------------------

@tool("source_youtube_assets")
def source_youtube_assets(query: str, limit: int = 5) -> str:
    """
    Search YouTube and queue matching videos for a specific topic.
    You MUST provide 'query' as the search topic (e.g. 'Family Guy funny clips').
    Returns count of assets queued.
    """
    try:
        from scripts.source_youtube_assets import main as source_assets
        result = source_assets(limit=limit, query_override=query)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("check_content_duplicate")
def check_content_duplicate(url: str) -> str:
    """
    Check if a YouTube URL has already been uploaded.
    Returns {"is_duplicate": true/false}.
    """
    try:
        from scripts.memory_manager import is_duplicate
        result = is_duplicate(url=url)
        return json.dumps({"is_duplicate": result, "url": url})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Download tools
# ---------------------------------------------------------------------------

@tool("download_pending_assets")
def download_pending_assets(batch: int = 5) -> str:
    """
    Download pending YouTube assets via yt-dlp.
    Returns {processed, downloaded, failed, local_paths} where local_paths
    are the real absolute file paths ready for upload.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from scripts.arbitrage_worker import process_pending
        result = process_pending(batch=batch)
        # process_pending now returns only paths from THIS run.
        if "local_paths" not in result:
            result["local_paths"] = []
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Upload tools
# ---------------------------------------------------------------------------

@tool("upload_to_tiktok_v2")
def upload_to_tiktok_v2(video_path: str, account: str, title: str = None) -> str:
    """
    Upload a video to TikTok using the V2 stealth pipeline.
    video_path must be a real absolute path to an existing .mp4 file.
    Returns {"success": true/false, "error": "..."}.
    """
    if not video_path or "/path/to/" in video_path or not os.path.exists(video_path):
        return json.dumps({
            "success": False,
            "error": f"Video file not found: '{video_path}'. Use download_pending_assets first."
        })

    # Try to extract arbitrage DB info to generate a proper caption + hashtags.
    # e.g., /data/arbitrage_videos/asset_165.mp4
    final_title = title or "Must watch short clip"
    final_hashtags = []
    try:
        m = re.search(r'asset_(\d+)\.', video_path)
        if m:
            asset_id = int(m.group(1))
            c_text, c_tags = _build_asset_caption(asset_id, fallback_title=title or "")
            final_title = c_text
            final_hashtags = [f"#{x}" for x in c_tags]
    except Exception as e:
        logger.error(f"Failed to auto-generate caption for {video_path}: {e}")

    try:
        uploader_dir = os.path.abspath(os.environ.get("TIKTOK_UPLOADER_V2_DIR", "/TiktokUploader"))
        if not os.path.isdir(uploader_dir):
            return json.dumps({"success": False, "error": f"TiktokUploader not found at: {uploader_dir}"})

        original_dir = os.getcwd()
        try:
            os.chdir(uploader_dir)
            if uploader_dir not in sys.path:
                sys.path.insert(0, uploader_dir)

            from tiktokautouploader import upload_tiktok

            _agent_dbg("H5", "crew/tools.py:upload_to_tiktok_v2", "tiktokautouploader call", {
                "account": account,
                "video_exists": os.path.exists(video_path),
                "title_len": len(final_title or ""),
                "uploader_dir": uploader_dir,
            })

            use_headless = os.environ.get("DISPLAY") is None
            result = upload_tiktok(
                video=os.path.abspath(video_path),
                description=(final_title or "")[:150],
                accountname=account,
                hashtags=final_hashtags if final_hashtags else None,
                sound_name=None,
                headless=use_headless,
                stealth=True,
                proxy=None,
            )

            success = (result == "Completed")
            _agent_dbg("H5", "crew/tools.py:upload_to_tiktok_v2", "tiktokautouploader result", {
                "result": str(result)[:120],
                "success_bool": bool(success),
            })
            return json.dumps({"success": bool(success), "error": None if success else f"Upload returned: {result}"})
        finally:
            os.chdir(original_dir)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("upload_to_tiktok_v1")
def upload_to_tiktok_v1(video_path: str, account: str, title: str = None) -> str:
    """
    Upload a video to TikTok using the stable V1 pipeline (fallback).
    video_path must be a real absolute path to an existing .mp4 file.
    Returns {"success": true/false, "status": "published"/"draft", "error": "..."}.
    """
    if not video_path or "/path/to/" in video_path or not os.path.exists(video_path):
        return json.dumps({
            "success": False,
            "error": f"Video file not found: '{video_path}'. Use download_pending_assets first."
        })

    final_title = title or "Must watch short clip"
    final_tags = []
    try:
        m = re.search(r'asset_(\d+)\.', video_path)
        if m:
            asset_id = int(m.group(1))
            c_text, c_tags = _build_asset_caption(asset_id, fallback_title=title or "")
            final_title = c_text
            final_tags = [f"#{x}" for x in c_tags]
    except Exception as e:
        logger.error(f"Failed to auto-generate caption for {video_path}: {e}")

    if final_tags:
        final_title = f"{final_title} {' '.join(final_tags)}".strip()

    try:
        uploader_dir = os.path.abspath(os.environ.get("TIKTOK_UPLOADER_DIR",
                       os.path.join(os.getcwd(), "..", "TiktokAutoUploader")))
        original_dir = os.getcwd()
        os.chdir(uploader_dir)
        sys.path.insert(0, uploader_dir)
        from tiktok_uploader.tiktok import upload_video
        
        # Capture stdout to check for draft status since the function return True for both
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            result = upload_video(session_user=account, video=video_path, title=final_title[:500])
        output = f.getvalue()
        os.chdir(original_dir)
        
        status = "published"
        if "Saved as draft successfully" in output:
            status = "draft"
            
        success = bool(result) and status == "published"
        _agent_dbg("H4", "crew/tools.py:upload_to_tiktok_v1", "v1 upload output parsed", {
            "account": account,
            "success_bool": success,
            "status": status,
            "output_contains_draft": ("Saved as draft successfully" in output),
        })
        return json.dumps({"success": success, "status": status, "output_msg": output.split('\n')[-2] if '\n' in output else output})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("upload_to_youtube")
def upload_to_youtube(video_path: str, video_id: int = None, title: str = None, caption: str = None) -> str:
    """
    Upload a video to YouTube Shorts using the official API.
    video_path must be a real absolute path.
    video_id is optional; if provided, it will try to fetch metadata from the database.
    title and caption are optional overrides.
    Returns {"success": true/false, "url": "...", "error": "..."}.
    """
    if not video_path or not os.path.exists(video_path):
        return json.dumps({"success": False, "error": f"Video file not found: {video_path}"})
        
    try:
        # Reuse the existing uploader path that uses youtube.upload OAuth scope
        # and has proven more stable in this project than the legacy helper module.
        from scripts.distribute_arbitrage import upload_to_youtube as stable_upload_to_youtube
        asset = {"local_path": video_path}
        final_title = title or "Must watch short clip"
        final_caption = caption or ""
        final_tags = []

        m = re.search(r'asset_(\d+)\.', video_path or "")
        if m:
            asset_id = int(m.group(1))
            c_text, c_tags = _build_asset_caption(asset_id, fallback_title=final_title)
            final_title = c_text
            final_caption = final_caption or c_text
            final_tags = [f"#{x}" for x in c_tags]

        result = stable_upload_to_youtube(asset, final_caption, final_tags)
        _agent_dbg("H6", "crew/tools.py:upload_to_youtube", "youtube upload call completed", {
            "video_path_exists": os.path.exists(video_path),
            "has_video_id": bool(video_id),
            "success": bool(result.get("success")),
            "error_prefix": str(result.get("error") or "")[:120],
            "url_prefix": str(result.get("platform_url") or "")[:120],
        })
        if result.get("success"):
            return json.dumps({"success": True, "youtube_url": result.get("platform_url"), "error": None})
        return json.dumps({"success": False, "error": result.get("error") or "youtube upload failed"})
    except Exception as e:
        logger.error(f"YouTube tool failed: {e}")
        return json.dumps({"success": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Account health tools
# ---------------------------------------------------------------------------

@tool("get_account_health")
def get_account_health_tool(account: str) -> str:
    """
    Get health summary for a TikTok account from ChromaDB.
    Returns {total_uploads, success_rate, avg_views, shadow_ban_count, recommendation}.
    recommendation is one of: healthy, monitor, quarantine.
    """
    try:
        from scripts.memory_manager import get_account_health
        result = get_account_health(account)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("record_upload_result")
def record_upload_result(account: str, success: bool, views: int = 0,
                         shadow_banned: bool = False) -> str:
    """
    Record an upload result to ChromaDB account_health collection.
    Also registers the content fingerprint to prevent re-uploads.
    """
    try:
        from scripts.memory_manager import record_upload
        record_upload(account, success, views, shadow_banned)
        return json.dumps({"recorded": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("get_available_tiktok_accounts")
def get_available_tiktok_accounts() -> str:
    """
    Query the database for active TikTok accounts that haven't hit their daily upload limit.
    Falls back to scanning CookiesDir for saved session files if DB has no accounts.
    Returns a list of available account names.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from scripts.utils import database as db
        max_per_day = int(os.environ.get("MAX_UPLOADS_PER_ACCOUNT_DAY", "3"))
        accounts = db.execute(
            """
            SELECT username, cookies_file FROM tiktok_accounts
            WHERE account_status = 'active' AND shadow_banned = false
              AND cookies_file IS NOT NULL
              AND (
                  last_post_at IS NULL OR DATE(last_post_at) < CURRENT_DATE
                  OR (
                      DATE(last_post_at) = CURRENT_DATE AND (
                          SELECT COUNT(*) FROM upload_results ur
                          WHERE ur.account_id = tiktok_accounts.id
                            AND DATE(ur.uploaded_at) = CURRENT_DATE
                            AND ur.success = true
                      ) < %s
                  )
              )
            ORDER BY last_post_at ASC NULLS FIRST
            """,
            (max_per_day,),
        )
        db_accounts = [a["username"] for a in (accounts or [])]

        if db_accounts:
            return json.dumps(db_accounts)

        # Fallback: scan CookiesDir for saved session files
        uploader_dir = os.environ.get("TIKTOK_UPLOADER_DIR",
                       os.path.join(os.getcwd(), "..", "TiktokAutoUploader"))
        sys.path.insert(0, uploader_dir)
        try:
            from tiktok_uploader.tiktok_v2 import list_saved_accounts
            cookie_accounts = list_saved_accounts(
                os.path.join(uploader_dir, "CookiesDir")
            )
            if cookie_accounts:
                return json.dumps(cookie_accounts)
        except Exception:
            pass

        return json.dumps([])
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("quarantine_account")
def quarantine_account(account: str, reason: str = "manager_decision") -> str:
    """
    Mark a TikTok account as shadow_banned in the database so it won't be used.
    Call this when an account fails repeatedly or shows shadow-ban signals.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from scripts.utils import database as db
        db.execute(
            "UPDATE tiktok_accounts SET shadow_banned=true, account_status='quarantined' WHERE username=%s",
            (account,),
        )
        from scripts.memory_manager import record_upload
        record_upload(account, success=False, shadow_banned=True)
        return json.dumps({"quarantined": True, "account": account, "reason": reason})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Reporting tools
# ---------------------------------------------------------------------------

@tool("register_content_fingerprint")
def register_content_fingerprint(url: str, account: str = "", platform: str = "tiktok") -> str:
    """
    Register a YouTube URL as uploaded to prevent future re-uploads.
    Call this after every successful upload.
    """
    try:
        from scripts.memory_manager import register_content
        register_content(url=url, metadata={"account": account, "platform": platform})
        return json.dumps({"registered": True, "url": url})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("record_trend_performance")
def record_trend_performance(hashtag: str, avg_views: int,
                             post_count: int = 0, trend_velocity: float = 0.0,
                             region: str = "US") -> str:
    """
    Record trend performance data to ChromaDB for long-term memory.
    Call this after each pipeline run to build the feedback loop.
    """
    try:
        from scripts.memory_manager import record_trend
        record_trend(hashtag, avg_views, post_count, trend_velocity, region)
        return json.dumps({"recorded": True, "hashtag": hashtag})
    except Exception as e:
        return json.dumps({"error": str(e)})
