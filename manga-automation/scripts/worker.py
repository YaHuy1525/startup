#!/usr/bin/env python3
"""
Python worker HTTP server.
n8n / Telegram / external callers use these endpoints.

AiToEarn Pipeline (primary):
    POST /aitoearn/pipeline     body: { category?, mode?: "light"|"full" }
    POST /aitoearn/stage/trend     body: { category?, limit? }
    POST /aitoearn/stage/create    body: { limit? }
    POST /aitoearn/stage/publish   body: {}
    POST /aitoearn/stage/engage    body: { platform? }
    POST /aitoearn/stage/monetize  body: { creator_id? }

CrewAI Agent Pipeline:
    POST /api/summon-agent      body: { prompt, target_count, dry_run, sync }

Arbitrage Pipeline:
    POST /arbitrage/discover-trends  body: { region?, limit? }
    POST /arbitrage/source-assets    body: { limit? }
    POST /arbitrage/download         body: { batch? }
    POST /arbitrage/distribute       body: { platforms?, batch? }

TikTok Uploader (kept as an option):
    POST /upload-tiktok          body: { video_id }

Legacy manga endpoints (deprecated — use AiToEarn pipeline instead):
    POST /fetch-trending         body: { limit: 20 }
    POST /fetch-chapter          body: { manga_id: 1 }
    POST /download-panels        body: { chapter_id: 1 }
    POST /check-duplicates       body: { chapter_id: 1 }
    POST /generate-video         body: { chapter_id: 1 }
    POST /detect-shadow-ban      body: {}
    GET  /health
"""
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dotenv import load_dotenv

load_dotenv()

from scripts.utils.logger import setup_logger

logger = setup_logger("worker")

# #region agent log
_DEBUG_LOG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "debug-0f0c72.log")
)


def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        payload = {
            "sessionId": "0f0c72",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "hypothesisId": hypothesis_id,
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
            _df.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


# #endregion

import scripts.fetch_trending_manga as fetch_trending
import scripts.fetch_chapter_images as fetch_chapter
import scripts.download_panels as download_panels
import scripts.check_duplicates as check_duplicates
import scripts.generate_video as generate_video
import scripts.upload_tiktok as upload_tiktok
import scripts.detect_shadow_ban as detect_shadow_ban
import scripts.upload_arbitrage as upload_arbitrage
import scripts.fetch_tiktok_trends_apify as trend_discovery
import scripts.source_youtube_assets as asset_sourcer
import scripts.arbitrage_worker as arb_downloader
import scripts.distribute_arbitrage as arb_distributor
import scripts.research_ingest_last30days as research_ingest
import scripts.gig_prepare as gig_prepare
import scripts.gig_score as gig_score
import scripts.gig_session_report as gig_report
import scripts.obsidian_sync as obsidian_sync
import scripts.monetization_ops as monetization_ops
import scripts.monetization_activation as monetization_activation
import scripts.weekly_optimizer as weekly_optimizer
import scripts.trend_content_planner as trend_content_planner
import scripts.voiceover_service as voiceover_service
import scripts.genesis_discover as genesis_discover
import scripts.genesis_brief_generator as genesis_briefs
import scripts.omnichannel_distributor as omnichannel
import scripts.editorial_publisher as editorial
import scripts.digital_product_generator as digital_products
import scripts.upload_instagram as upload_instagram
import scripts.meta_graph_publish as meta_graph_publish
import scripts.upload_pinterest as upload_pinterest
import scripts.podcast_rss_generator as podcast_rss
import scripts.adapters.postiz_client as postiz_client
import scripts.adapters.postiz_bridge as postiz_bridge
import scripts.adapters.aitoearn_client as aitoearn_client
import scripts.rpa.playwright_rpa_boilerplate as rpa_pw
import scripts.longform_video_boilerplate as longform_video
import scripts.marketplace_listings_boilerplate as marketplace_listings
import scripts.hermes_agent as hermes_agent
import scripts.earnings_proof_ingest as earnings_ingest
import scripts.finance_video_generator as finance_video
import scripts.finance_video_ai as finance_video_ai
import scripts.youtube_download_ingest as youtube_download_ingest
from scripts.utils import database as db
from scripts.aitoearn_pipeline import (
    stage_trend,
    stage_create,
    stage_publish,
    stage_engage,
    stage_monetize,
    run_full_pipeline,
)


def _run_deerflow(body: dict) -> dict:
    from scripts import deerflow_client

    mode = body.get("mode", "chat")
    prompt = body.get("prompt", "").strip()
    if not prompt and mode != "models":
        return {"error": "prompt is required"}

    if mode == "models":
        return deerflow_client.list_models()
    if mode == "plan":
        return deerflow_client.plan_campaign(prompt)
    if mode == "recover":
        return deerflow_client.recover_last_run(prompt)
    return deerflow_client.run_prompt(
        prompt=prompt,
        thread_id=body.get("thread_id"),
        model_name=body.get("model_name"),
        thinking_enabled=body.get("thinking_enabled", True),
        is_plan_mode=body.get("is_plan_mode", False),
        recursion_limit=int(body.get("recursion_limit", 100)),
    )


def _research_status(body: dict) -> dict:
    return research_ingest.get_research_status(limit=int(body.get("limit", 10)))


def _research_ingest(body: dict) -> dict:
    queries = body.get("queries") or []
    if not queries and body.get("query"):
        queries = [body["query"]]
    region = body.get("region") or os.environ.get("LAST30DAYS_REGION", "US")
    return research_ingest.ingest_queries(queries, region=region)


def _recover_last_run(_: dict) -> dict:
    from scripts import deerflow_client
    from scripts.utils import database as db

    failed_uploads = db.execute(
        """
        SELECT asset_id, platform, error_message, uploaded_at
        FROM arbitrage_uploads
        WHERE status = 'failed'
        ORDER BY uploaded_at DESC
        LIMIT 5
        """
    )
    failed_results = db.execute(
        """
        SELECT video_id, success, error_message, uploaded_at
        FROM upload_results
        WHERE success = false
        ORDER BY uploaded_at DESC
        LIMIT 5
        """
    )
    context = {
        "arbitrage_upload_failures": failed_uploads,
        "classic_upload_failures": failed_results,
    }
    return deerflow_client.recover_last_run(json.dumps(context, ensure_ascii=False))


def _memory_stats() -> dict:
    try:
        from scripts.memory_manager import get_collections
        tm, ah, cf = get_collections()
        return {"trend_memory": tm.count(), "account_health": ah.count(),
                "content_fingerprints": cf.count()}
    except Exception as e:
        return {"error": str(e)}


# ── AiToEarn Pipeline Handlers ────────────────────────────────────────────────


def _aitoearn_pipeline(body: dict) -> dict:
    """Run the full 5-stage AiToEarn pipeline."""
    category = body.get("category", "")
    mode = body.get("mode", "full")
    publish_options = body.get("publish_options")
    if not isinstance(publish_options, dict):
        publish_options = {}
    return run_full_pipeline(category=category, mode=mode, publish_options=publish_options)


def _aitoearn_stage_trend(body: dict) -> dict:
    return stage_trend(category=body.get("category", ""), limit=int(body.get("limit", 10)))


def _aitoearn_stage_create(body: dict) -> dict:
    return stage_create(limit=int(body.get("limit", 5)))


def _aitoearn_stage_publish(body: dict) -> dict:
    return stage_publish(body)


def _aitoearn_stage_engage(body: dict) -> dict:
    return stage_engage(platform=body.get("platform", "tiktok"))


def _aitoearn_stage_monetize(body: dict) -> dict:
    return stage_monetize(creator_id=int(body.get("creator_id", 1)))


def _aitoearn_accounts(body: dict) -> dict:
    platform = body.get("platform")
    return aitoearn_client.list_accounts(platform=platform)


def _aitoearn_publish_status(body: dict) -> dict:
    flow_id = str(body.get("flow_id") or body.get("flowId") or "").strip()
    if not flow_id:
        return {"error": "flow_id is required"}
    return aitoearn_client.get_publishing_task_status(flow_id=flow_id)


def _aitoearn_publish(body: dict) -> dict:
    """
    Publish to AiToEarn connected accounts with fanout controls.
    Body example:
      {
        "video_url": "https://...",
        "channels": ["tiktok","youtube","instagram"],
        "account_ids": ["tiktok_xxx","youtube_yyy"],
        "selected_accounts": {"tiktok": ["tiktok_xxx"], "youtube": ["youtube_yyy"]},
        "title": "...",
        "desc": "...",
        "topics": ["ai","marketing"]
      }
    """
    return stage_publish(body)


def _aitoearn_publish_restrictions(body: dict) -> dict:
    platforms_raw = body.get("platforms") or []
    if isinstance(platforms_raw, str):
        platforms = [x.strip() for x in platforms_raw.split(",") if x.strip()]
    elif isinstance(platforms_raw, list):
        platforms = platforms_raw
    else:
        platforms = []
    return aitoearn_client.get_publish_restrictions(platforms=platforms)


def _resolve_clip_local_path(clip_id: int, source_type: str) -> dict:
    """Resolve the on-disk video path for a stored clip."""
    if source_type == "arbitrage":
        row = db.execute_one(
            "SELECT id, local_path, youtube_title FROM arbitrage_assets WHERE id = %s",
            (clip_id,),
        )
        if not row:
            return {"ok": False, "error": f"arbitrage_assets #{clip_id} not found"}
        return {
            "ok": True,
            "local_path": row.get("local_path"),
            "title": row.get("youtube_title"),
        }
    row = db.execute_one(
        "SELECT id, file_path, caption FROM videos WHERE id = %s",
        (clip_id,),
    )
    if not row:
        return {"ok": False, "error": f"videos #{clip_id} not found"}
    return {"ok": True, "local_path": row.get("file_path"), "title": row.get("caption")}


def _publish_clip(body: dict) -> dict:
    """
    Manual publish of an already-downloaded clip to chosen AiToEarn accounts.

    Body:
      {
        "clip_id": 87,
        "source_type": "video" | "arbitrage",
        "channels": ["tiktok","youtube","instagram"],
        "selected_accounts": {"tiktok": ["tiktok_xxx"]},   # optional
        "account_ids": ["tiktok_xxx"],                       # optional
        "title": "...", "desc": "...", "caption": "...",
        "hashtags": ["#a"], "topics": ["a"],
        "cover_url": "...", "publish_time": "ISO8601",
        "yt_privacy": "public" | "unlisted" | "private"
      }
    """
    from scripts.adapters import media_host

    clip_id = body.get("clip_id")
    if clip_id is None:
        return {"ok": False, "error": "clip_id is required"}
    try:
        clip_id = int(clip_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "clip_id must be an integer"}

    source_type = str(body.get("source_type") or "video").strip().lower()
    resolved = _resolve_clip_local_path(clip_id, source_type)
    if not resolved.get("ok"):
        return resolved

    local_path = resolved.get("local_path")
    hosted = media_host.ensure_public_url(
        local_path,
        fallback_public_url=(
            body.get("video_url")
            or body.get("videoUrl")
            or body.get("source_url")
            or body.get("sourceUrl")
        ),
    )
    if not hosted.get("ok"):
        return {
            "ok": False,
            "error": f"media_hosting_failed: {hosted.get('error')}",
            "local_path": local_path,
        }

    publish_time = aitoearn_client.normalize_publish_time(
        body.get("publish_time") or body.get("publishTime")
    )
    raw_time = body.get("publish_time") or body.get("publishTime")
    if raw_time and not publish_time:
        return {
            "ok": False,
            "error": f"invalid_publish_time: {raw_time!r} (use ISO-8601, e.g. 2026-06-03T08:00:00Z)",
        }

    publish_payload = {
        "video_url": hosted["public_url"],
        "channels": body.get("channels") or ["tiktok", "youtube", "instagram", "facebook", "threads", "pinterest"],
        "selected_accounts": body.get("selected_accounts"),
        "account_ids": body.get("account_ids"),
        "title": body.get("title") or resolved.get("title") or "Automated post",
        "desc": body.get("desc") or body.get("description") or body.get("caption") or "",
        "caption": body.get("caption"),
        "hashtags": body.get("hashtags"),
        "topics": body.get("topics"),
        "cover_url": body.get("cover_url") or body.get("coverUrl"),
        "publishTime": publish_time,
    }
    if body.get("yt_privacy"):
        os.environ["AITOEARN_YT_PRIVACY"] = str(body["yt_privacy"])

    result = stage_publish(publish_payload)

    # Record the schedule on the video row so the Content Calendar reflects it.
    if publish_time and source_type == "video":
        try:
            db.execute(
                "UPDATE videos SET scheduled_for = %s WHERE id = %s",
                (publish_time, clip_id),
            )
        except Exception as exc:  # pragma: no cover - calendar sync is best-effort
            logger.warning(f"Failed to persist scheduled_for for video {clip_id}: {exc}")

    if isinstance(result, dict):
        result.setdefault("ok", bool(result.get("success", True)))
        result.setdefault(
            "media",
            {
                "public_url": hosted["public_url"],
                "uploaded": hosted.get("uploaded"),
                "provider": hosted.get("provider"),
            },
        )
        result.setdefault("clip_id", clip_id)
        result.setdefault("source_type", source_type)
        if publish_time:
            result.setdefault("scheduled_for", publish_time)
    return result


def _run_agent_crew(body: dict) -> dict:
    """
    Dispatch the CrewAI pipeline in a background thread and return immediately
    with a run_id. The crew logs progress to the standard logger.
    For synchronous execution (e.g. testing), pass sync=true in the body.
    """
    import threading, uuid
    from scripts.crew.pipeline_crew import run_pipeline

    prompt       = body.get("prompt", "Find top trending short-form content and post 5 videos")
    target_count = int(body.get("target_count", 5))
    dry_run      = bool(body.get("dry_run", False))
    sync         = bool(body.get("sync", False))
    run_id       = str(uuid.uuid4())[:8]

    def _extract_channel_and_account(text: str) -> tuple[str | None, str | None, str | None]:
        import re
        channel_match = re.search(r"https?://(?:www\.)?youtube\.com/channel/(UC[a-zA-Z0-9_-]{20,})", text or "")
        account_match = re.search(r"\bon\s+([A-Za-z0-9_.-]+)\s+account\b", text or "", flags=re.IGNORECASE)
        channel_url = channel_match.group(0) if channel_match else None
        channel_id = channel_match.group(1) if channel_match else None
        account = account_match.group(1) if account_match else None
        return channel_url, channel_id, account

    def _run_direct_channel_short_flow(channel_url: str, channel_id: str | None, account: str | None, dry_run_mode: bool = False) -> dict:
        # Deterministic path for prompts like:
        # "take the latest short from <channel_url> and post it on tiktok and youtube ..."
        source_result = asset_sourcer.main(limit=1, query_override=channel_url)
        if source_result.get("assets_queued", 0) <= 0:
            return {
                "success": False,
                "stage": "source",
                "error": f"No assets queued for channel: {channel_url}",
                "source_result": source_result,
            }

        asset = db.execute_one(
            """
            SELECT aa.*
            FROM arbitrage_assets aa
            WHERE aa.source_query = %s
              AND (%s IS NULL OR aa.source_channel_id = %s)
              AND aa.status IN ('pending', 'downloaded')
            ORDER BY aa.created_at DESC
            LIMIT 1
            """,
            (channel_url, channel_id, channel_id),
        )
        if not asset:
            return {"success": False, "stage": "select", "error": "No candidate asset found after sourcing"}

        if dry_run_mode:
            return {
                "success": True,
                "mode": "direct_channel_latest_short_dry_run",
                "asset_id": asset["id"],
                "channel_url": channel_url,
                "channel_id": channel_id,
                "tiktok_account": account or "nuggerchicken433",
                "source_result": source_result,
            }

        if asset.get("status") != "downloaded":
            dl = arb_downloader.download_asset(asset)
            if dl.get("status") != "downloaded":
                db.execute(
                    "UPDATE arbitrage_assets SET status='failed', error_message=%s, updated_at=NOW() WHERE id=%s",
                    (dl.get("error_message", "download failed"), asset["id"]),
                )
                return {"success": False, "stage": "download", "error": dl.get("error_message"), "asset_id": asset["id"]}
            db.execute(
                """
                UPDATE arbitrage_assets
                SET status='downloaded', local_path=%s, file_size_mb=%s,
                    duration_secs=COALESCE(%s, duration_secs), updated_at=NOW()
                WHERE id=%s
                """,
                (dl.get("local_path"), dl.get("file_size_mb"), dl.get("duration_secs"), asset["id"]),
            )
            asset["local_path"] = dl.get("local_path")

        video_path = asset.get("local_path")
        if not video_path or not os.path.exists(video_path):
            return {
                "success": False,
                "stage": "validate",
                "error": f"Downloaded video path missing: {video_path}",
                "asset_id": asset["id"],
            }

        # Use concrete uploader functions here (not Crew @tool wrappers).
        asset_row = db.execute_one(
            """
            SELECT a.*, t.hashtag
            FROM arbitrage_assets a
            LEFT JOIN trend_intel t ON a.trend_id = t.id
            WHERE a.id = %s
            """,
            (asset["id"],),
        ) or asset

        caption, hashtags = arb_distributor.generate_caption(
            asset_row.get("hashtag") or "fyp",
            asset_row.get("youtube_title") or "Must watch short clip",
        )
        tiktok_account = account or "nuggerchicken433"
        os.environ["DIRECT_TIKTOK_ACCOUNT"] = tiktok_account
        try:
            tiktok_result = arb_distributor.upload_to_tiktok(asset_row, caption, hashtags)
        finally:
            os.environ.pop("DIRECT_TIKTOK_ACCOUNT", None)
        youtube_result = arb_distributor.upload_to_youtube(asset_row, caption, hashtags)

        return {
            "success": bool(tiktok_result.get("success")) and bool(youtube_result.get("success")),
            "mode": "direct_channel_latest_short",
            "asset_id": asset["id"],
            "channel_url": channel_url,
            "channel_id": channel_id,
            "tiktok_account": tiktok_account,
            "tiktok": tiktok_result,
            "youtube": youtube_result,
        }

    if os.environ.get("SUMMON_BACKEND", "crewai").lower() == "deerflow":
        from scripts import deerflow_client
        result = deerflow_client.plan_campaign(prompt) if dry_run else deerflow_client.run_prompt(
            prompt=prompt,
            is_plan_mode=False,
            recursion_limit=100,
        )
        return {"run_id": run_id, "status": "completed", "result": result, "backend": "deerflow"}

    channel_url, channel_id, requested_account = _extract_channel_and_account(prompt)
    if channel_url and ("latest short" in prompt.lower() or "latest shorts" in prompt.lower()):
        result = _run_direct_channel_short_flow(
            channel_url=channel_url,
            channel_id=channel_id,
            account=requested_account,
            dry_run_mode=dry_run,
        )
        return {
            "run_id": run_id,
            "status": "completed",
            "backend": "direct_channel_flow",
            "result": result,
        }

    if sync:
        result = run_pipeline(prompt, target_count, dry_run)
        return {"run_id": run_id, "status": "completed", "result": result}

    def _run():
        logger.info(f"[crew:{run_id}] Starting pipeline: {prompt}")
        try:
            result = run_pipeline(prompt, target_count, dry_run)
            logger.info(f"[crew:{run_id}] Pipeline complete: {result}")
        except Exception as e:
            logger.error(f"[crew:{run_id}] Pipeline failed: {e}")

    thread = threading.Thread(target=_run, daemon=True, name=f"crew-{run_id}")
    thread.start()
    return {"run_id": run_id, "status": "dispatched",
            "message": f"Crew dispatched. Follow logs for run_id={run_id}"}


def _gig_finalize(body: dict) -> dict:
    """Update a gig_task with manual submission outcome, minutes, and payout."""
    task_id = int(body["task_id"])
    outcome = body.get("outcome")   # accepted | rejected | submitted_manual
    minutes = body.get("minutes")
    payout  = body.get("payout")

    valid_outcomes = {"accepted", "rejected", "submitted_manual"}
    updates: list[str] = ["updated_at=NOW()"]
    params:  list      = []

    if outcome in valid_outcomes:
        updates.append("status=%s")
        params.append(outcome)
    elif outcome:
        return {"error": f"Invalid outcome '{outcome}'. Use: {sorted(valid_outcomes)}"}

    if minutes is not None:
        updates.append("time_spent_minutes=%s")
        params.append(int(minutes))
    if payout is not None:
        updates.append("estimated_payout=%s")
        params.append(float(payout))

    params.append(task_id)
    db.execute(
        f"UPDATE gig_tasks SET {', '.join(updates)} WHERE id=%s",
        params,
    )
    logger.info(f"Finalized gig_task id={task_id} outcome={outcome} minutes={minutes} payout={payout}")
    return {
        "task_id": task_id,
        "updated": True,
        "outcome": outcome,
        "message": f"Task #{task_id} logged as {outcome}. Well done — keep going!",
    }


def _hermes_log_tail(body: dict) -> dict:
    """
    Return tail lines from Hermes log file inside docker-mounted logs dir.
    """
    lines = int(body.get("lines", 120))
    lines = max(10, min(lines, 2000))
    logs_dir = os.environ.get("LOGS_DIR", "/data/logs")
    log_path = os.path.join(logs_dir, "hermes_agent.log")
    if not os.path.exists(log_path):
        return {"ok": False, "error": f"log_not_found:{log_path}"}
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        data = f.readlines()
    tail = data[-lines:]
    return {
        "ok": True,
        "log_path": log_path,
        "lines": len(tail),
        "content": "".join(tail),
    }


ROUTES = {
    # ── AiToEarn Pipeline (primary) ───────────────────────────────────────────
    "/aitoearn/pipeline":       _aitoearn_pipeline,
    "/aitoearn/stage/trend":    _aitoearn_stage_trend,
    "/aitoearn/stage/create":   _aitoearn_stage_create,
    "/aitoearn/stage/publish":  _aitoearn_stage_publish,
    "/aitoearn/stage/engage":   _aitoearn_stage_engage,
    "/aitoearn/stage/monetize": _aitoearn_stage_monetize,
    # MCP account ops + publish fanout
    "/aitoearn/accounts":       _aitoearn_accounts,
    "/aitoearn/publish":        _aitoearn_publish,
    "/aitoearn/publish/status": _aitoearn_publish_status,
    "/aitoearn/publish/restrictions": _aitoearn_publish_restrictions,
    # Manual publish of a stored clip (resolves local file -> public URL -> fanout)
    # POST /publish/clip  { clip_id, source_type, channels?, selected_accounts?, ... }
    "/publish/clip":            _publish_clip,
    # ── Legacy manga endpoints (deprecated — use AiToEarn pipeline) ──────────
    "/fetch-trending":    lambda body: fetch_trending.main(body.get("limit", 20)),
    "/fetch-chapter":     lambda body: fetch_chapter.main(body["manga_id"]),
    "/download-panels":   lambda body: download_panels.main(body["chapter_id"]),
    "/check-duplicates":  lambda body: check_duplicates.main(body["chapter_id"]),
    "/generate-video":    lambda body: generate_video.main(body["chapter_id"]),
    # ── TikTok Upload (kept as an option) ─────────────────────────────────────
    "/upload-tiktok":     lambda body: upload_tiktok.main(body["video_id"]),
    "/upload-youtube":    lambda body: __import__('scripts.upload_youtube').upload_youtube.main(body["video_id"]),
    # POST /youtube/download-ingest  { url, caption?, create_video?: true }
    "/youtube/download-ingest": lambda body: youtube_download_ingest.main(body),
    "/yt-to-tiktok":      lambda body: __import__('scripts.yt_to_tiktok_manual').yt_to_tiktok_manual.main(body.get("url") or None, body.get("caption") or None, body.get("hashtags") or None),
    "/detect-shadow-ban": lambda body: detect_shadow_ban.main(
        body.get("min_posts", 5), body.get("threshold", 0.10)
    ),
    "/arbitrage/upload":  lambda body: upload_arbitrage.upload_arbitrage(body["asset_id"]),
    # ── Arbitrage Pipeline ────────────────────────────────────────────────────
    "/arbitrage/discover-trends": lambda body: trend_discovery.main(
        body.get("region", "US"), body.get("limit", 20)
    ),
    "/arbitrage/source-assets":   lambda body: asset_sourcer.main(
        body.get("limit", 5),
        body.get("query_override"),
    ),
    "/arbitrage/download":        lambda body: arb_downloader.process_pending(
        body.get("batch", 10)
    ),
    "/arbitrage/distribute":      lambda body: arb_distributor.process_pending(
        body.get("platforms", ["tiktok"]), body.get("batch", 5)
    ),
    # ── Research + DeerFlow ─────────────────────────────────────────────────────
    "/research/ingest":          _research_ingest,
    "/research/status":          _research_status,
    "/deerflow/run":             _run_deerflow,
    "/deerflow/recover-last-run": _recover_last_run,
    # ── CrewAI Agent Dispatch ─────────────────────────────────────────────────
    # POST /api/summon-agent
    # Body: { "prompt": "...", "target_count": 5, "dry_run": false, "sync": false }
    "/api/summon-agent":          _run_agent_crew,
    # Memory manager shortcuts
    "/api/memory/stats":          lambda body: _memory_stats(),
    # ── Gig Copilot ────────────────────────────────────────────────────────────
    # POST /gig/task/create   { user_id, platform, task_type, brief }
    # POST /gig/task/draft    { task_id }
    # POST /gig/task/score    { task_id }
    # POST /gig/task/finalize { task_id, outcome, minutes, payout }
    # POST /gig/session/today { user_id }
    # POST /gig/session/week  { user_id }
    "/gig/task/create":    lambda body: gig_prepare.main({**body, "action": "create"}),
    "/gig/task/draft":     lambda body: gig_prepare.main({**body, "action": "draft"}),
    "/gig/task/score":     lambda body: gig_score.main(body),
    "/gig/task/finalize":  lambda body: _gig_finalize(body),
    "/gig/session/today":  lambda body: gig_report.main({**body, "period": "today"}),
    "/gig/session/week":   lambda body: gig_report.main({**body, "period": "week"}),
    # ── Obsidian Vault Sync ────────────────────────────────────────────────────────────
    # POST /obsidian/task     { action:"task",     task:{}, output:{} }
    # POST /obsidian/session  { action:"session",  summary:{} }
    # POST /obsidian/research { action:"research", query:"", result:{} }
    # POST /obsidian/template { action:"template", platform, task_type, template_text, win_rate }
    # POST /obsidian/rejection{ action:"rejection",flag, task_ids:[], examples:[] }
    "/obsidian/task":      lambda body: obsidian_sync.main({**body, "action": "task"}),
    "/obsidian/session":   lambda body: obsidian_sync.main({**body, "action": "session"}),
    "/obsidian/research":  lambda body: obsidian_sync.main({**body, "action": "research"}),
    "/obsidian/template":  lambda body: obsidian_sync.main({**body, "action": "template"}),
    "/obsidian/rejection": lambda body: obsidian_sync.main({**body, "action": "rejection"}),
    # ── Monetization Control Plane ─────────────────────────────────────────────
    "/monetization/kpi/evaluate": lambda body: monetization_ops.main("evaluate", body),
    "/monetization/weekly-plan":  lambda body: monetization_ops.main("weekly-plan", body),
    "/monetization/snapshot":     lambda body: monetization_ops.main("save-snapshot", body),
    "/monetization/should-post-ad": lambda body: monetization_activation.main("should-post-ad", body),
    "/monetization/membership-cta": lambda body: monetization_activation.main("membership-cta", body),
    "/monetization/high-cpm-field": lambda body: monetization_activation.main("high-cpm-field", body),
    "/monetization/offer-matrix":   lambda body: monetization_activation.main("offer-matrix", body),
    "/monetization/optimize-weekly": lambda body: weekly_optimizer.run_weekly_optimization(),
    # ── Trend-Driven Autopilot (cross-domain) ─────────────────────────────────
    "/autopilot/plan-content": lambda body: trend_content_planner.plan(
        limit=int(body.get("limit", 10)),
        repurpose_ratio=float(body.get("repurpose_ratio", os.environ.get("TREND_REPURPOSE_RATIO", "0.5"))),
    ),
    "/autopilot/execute-content-plan": lambda body: trend_content_planner.execute(
        limit=int(body.get("limit", 10)),
        repurpose_ratio=float(body.get("repurpose_ratio", os.environ.get("TREND_REPURPOSE_RATIO", "0.5"))),
        batch=int(body.get("batch", 3)),
    ),
    # ── Voiceover Synthesis (ElevenLabs / Kokoro local) ───────────────────────
    "/voiceover/synthesize": lambda body: voiceover_service.synthesize(
        text=body.get("text", ""),
        provider=body.get("provider"),
        voice_id=body.get("voice_id"),
        model_id=body.get("model_id"),
        output_path=body.get("output_path"),
    ),
    "/api/memory/query-trends":   lambda body: __import__(
        'scripts.memory_manager', fromlist=['query_similar_trends']
    ).query_similar_trends(body.get("query", "manga"), body.get("n", 5)),
    "/api/memory/declining":      lambda body: __import__(
        'scripts.memory_manager', fromlist=['get_declining_trends']
    ).get_declining_trends(),
    # ── Genesis Discovery (Pod 0 — Omnichannel) ──────────────────────────────
    # POST /genesis/discover   { categories: "fiction,tech", limit: 15 }
    # POST /genesis/briefs     { categories: "fiction,tech", top: 3, action: "generate" }
    # POST /genesis/briefs     { action: "list", limit: 10 }
    "/genesis/discover":  lambda body: genesis_discover.main(body),
    "/genesis/briefs":    lambda body: genesis_briefs.main(body),
    # ── Omnichannel Distribution (Pods 1-5) ──────────────────────────────────
    # POST /omnichannel/distribute  { brief_id, profile?, channels?, postiz_multichannel?, postiz_media_path? }
    # POST /omnichannel/auto        { action: "auto", limit: 3 }
    "/omnichannel/distribute": lambda body: omnichannel.main(body),
    "/omnichannel/auto":       lambda body: omnichannel.main({**body, "action": "auto"}),
    # POST /omnichannel/plan  { category_slug: "tech", profile: "full" }
    "/omnichannel/plan":       lambda body: omnichannel.main({**body, "action": "plan"}),
    # POST /omnichannel/plan-all  { profile: "full" } — all genesis_categories
    "/omnichannel/plan-all":   lambda body: omnichannel.main({**body, "action": "plan_all_categories"}),
    # ── Editorial Publisher (Pod 3) ──────────────────────────────────────────
    # POST /editorial/publish  { brief_id: 1, platforms: "medium,substack,linkedin" }
    "/editorial/publish": lambda body: editorial.main(body),
    # ── Digital Products (Pod 5) ─────────────────────────────────────────────
    # POST /products/generate  { brief_ids: [1,2], categories: "tech" }
    "/products/generate": lambda body: digital_products.main(body),
    # ── Platform Uploaders ───────────────────────────────────────────────────
    # POST /upload/instagram  { video_path, caption, account, hashtags }
    # POST /upload/meta/instagram  { video_url, caption } — Graph API, needs public HTTPS URL
    # POST /upload/meta/facebook   { video_url, caption }
    # POST /upload/meta/threads    { video_url, text }
    "/upload/instagram": lambda body: upload_instagram.main(body),
    "/upload/meta/instagram": lambda body: meta_graph_publish.http_instagram(body),
    "/upload/meta/facebook": lambda body: meta_graph_publish.http_facebook(body),
    "/upload/meta/threads": lambda body: meta_graph_publish.http_threads(body),
    "/upload/meta/debug": lambda body: meta_graph_publish.debug_connection(),
    "/upload/pinterest": lambda body: upload_pinterest.main(body),
    # ── Podcast RSS (Pod 4) ──────────────────────────────────────────────────
    # POST /podcast/generate-feed  { limit: 50 }
    "/podcast/generate-feed": lambda body: podcast_rss.main(body),
    # ── Postiz unified publishing (alternative to brittle per-site RPA) ────────
    # POST /adapters/postiz  { action, ... } — see scripts/adapters/postiz_client.py
    "/adapters/postiz": lambda body: postiz_client.main(body),
    # POST /adapters/postiz/schedule-brief  { brief_id, media_path?, platform_slugs?, schedule_iso?, link? }
    "/adapters/postiz/schedule-brief": lambda body: postiz_bridge.main(
        {**body, "action": "schedule_brief"}
    ),
    # POST /adapters/postiz/integrations-map  {} — merged provider→id map for debugging
    "/adapters/postiz/integrations-map": lambda body: postiz_bridge.main(
        {"action": "resolve_integrations"}
    ),
    # ── Playwright RPA fallback (explicit dry-run defaults) ────────────────────
    # POST /rpa/session  { target: "pinterest", dry_run: true, caption: "..." }
    "/rpa/session": lambda body: rpa_pw.main(body),
    # ── Pod 2 long-form video (plan-only until vendor keys wired) ─────────────
    # POST /pod2/longform/queue  { brief_id: 1, target_duration_sec: 600 }
    "/pod2/longform/queue": lambda body: longform_video.main(body),
    # ── Gumroad / Etsy readiness —──────────────────────────────────────────────
    # POST /marketplace/ping  { platform: "gumroad" | "etsy" }
    "/marketplace/ping": lambda body: marketplace_listings.main(body),
    # ── Hermes Claude Ops Agent ────────────────────────────────────────────────
    # POST /hermes/status   {}
    # POST /hermes/diagnose { objective? }
    # POST /hermes/cycle    { execute_actions?, objective?, profile? }
    # POST /hermes/full-ops { category?, mode?, profile?, dry_run? }
    "/hermes/status": lambda body: hermes_agent.main({**body, "action": "status"}),
    "/hermes/diagnose": lambda body: hermes_agent.main({**body, "action": "diagnose"}),
    "/hermes/cycle": lambda body: hermes_agent.main({**body, "action": "cycle"}),
    "/hermes/full-ops": lambda body: hermes_agent.main({**body, "action": "full_ops"}),
    "/hermes/log-tail": _hermes_log_tail,
    # ── Finance / Side-Hustle: Earnings Proof + Referral Registry ─────────────
    # POST /earnings/ingest  { action: "scan" | "weekly-recap" | "update-earnings" }
    # POST /earnings/list    { tier?: 1|2|3 }
    "/earnings/ingest": lambda body: earnings_ingest.main(body),
    "/earnings/list":   lambda body: earnings_ingest.list_referral_platforms(
        tier=body.get("tier")
    ),
    # ── Finance Video Generator ───────────────────────────────────────────────
    # POST /finance/generate-video { type: "proof"|"voiceover"|"hook", week_iso?, brief_id? }
    "/finance/generate-video": lambda body: finance_video.main(body),
    # POST /finance/ai-video { provider: "creatify"|"heygen"|"invideo", week_iso?, style? }
    "/finance/ai-video":       lambda body: finance_video_ai.main(body),
    # POST /finance/list-avatars { provider: "creatify"|"heygen" }
    "/finance/list-avatars":   lambda body: (
        finance_video_ai.creatify_list_avatars() if body.get("provider", "creatify") == "creatify"
        else finance_video_ai.heygen_list_avatars()
    ),
    # ── Hermes Agent ──────────────────────────────────────────────────────────────
    # POST /hermes/finance-pipeline { provider?, background?, week_iso?, profile? }
    # Full pipeline: scan → generate video → distribute → Claude health-check
    "/hermes/finance-pipeline": lambda body: hermes_agent.run_finance_pipeline(body),
    # POST /hermes/viral-pipeline { provider?, background?, profile? }
    # Full pipeline: discover trends → draft brief → generate video → distribute → Claude health-check
    "/hermes/viral-pipeline": lambda body: hermes_agent.run_viral_pipeline(body),
    # POST /hermes/link-publish { source_url|link|video_url, channels?, selected_accounts?, account_ids? ... }
    # Pipeline: source/download from provided link or channel -> publish fanout
    "/hermes/link-publish": lambda body: hermes_agent.run_link_publish_pipeline(body),
    # POST /hermes/discover-publish { objective, channels?, ... }
    # Pipeline: discover matching YouTube short from objective -> verify -> publish fanout
    "/hermes/discover-publish": lambda body: hermes_agent.run_discover_publish_pipeline(body),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.info(fmt % args)

    def send_json(self, code: int, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError) as exc:
            # Client (e.g. telegram-bot) may disconnect on long pipelines before the body is read.
            logger.warning(f"Client disconnected before response was delivered: {exc}")

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "python-worker"})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self.send_json(400, {"error": "invalid JSON body"})
            return

        handler = ROUTES.get(self.path)
        if not handler:
            self.send_json(404, {"error": f"unknown route {self.path}"})
            return

        try:
            result = handler(body)
            envelope_ok = True
            if isinstance(result, dict):
                if self.path == "/api/summon-agent":
                    if result.get("status") == "completed":
                        crew_out = result.get("result")
                        if isinstance(crew_out, dict) and crew_out.get("error"):
                            envelope_ok = False
                elif self.path in ("/upload-tiktok", "/upload-youtube"):
                    envelope_ok = result.get("success") is True
                elif self.path == "/publish/clip":
                    envelope_ok = (
                        result.get("ok") is not False
                        and result.get("success") is not False
                    )
                elif self.path.startswith("/hermes/"):
                    envelope_ok = result.get("success") is not False
                elif self.path == "/arbitrage/distribute":
                    proc = result.get("processed") or 0
                    up = result.get("uploaded") or 0
                    if proc > 0 and up == 0:
                        envelope_ok = False
            # #region agent log
            _inner = result if isinstance(result, dict) else {}
            _distribute_ctx = {}
            if self.path == "/arbitrage/distribute":
                _distribute_ctx = {
                    "req_platforms": body.get("platforms"),
                    "req_batch": body.get("batch"),
                }
            _agent_debug_log(
                "H1",
                "worker.py:do_POST",
                "handler result vs HTTP envelope",
                {
                    "route": self.path,
                    "distribute": _distribute_ctx,
                    "inner_type": type(result).__name__,
                    "inner_keys": list(_inner.keys()) if isinstance(result, dict) else None,
                    "inner_success": _inner.get("success")
                    if isinstance(result, dict) and "success" in _inner
                    else None,
                    "inner_uploaded": _inner.get("uploaded")
                    if isinstance(result, dict)
                    else None,
                    "inner_processed": _inner.get("processed")
                    if isinstance(result, dict)
                    else None,
                    "inner_failed": _inner.get("failed")
                    if isinstance(result, dict)
                    else None,
                    "inner_error": (str(_inner.get("error"))[:200] if isinstance(result, dict) else None),
                    "http_envelope_success": envelope_ok,
                },
            )
            # #endregion
            self.send_json(200, {"success": envelope_ok, "result": result})
        except Exception as e:
            logger.error(f"Error in {self.path}: {e}\n{traceback.format_exc()}")
            self.send_json(500, {"success": False, "error": str(e)})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    logger.info(f"Python worker listening on port {port}")
    server.serve_forever()
