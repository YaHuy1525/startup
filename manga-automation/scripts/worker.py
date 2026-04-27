#!/usr/bin/env python3
"""
Python worker HTTP server.
n8n calls these endpoints instead of running docker exec.
Runs all Python scripts as in-process functions.

Endpoints:
    POST /fetch-trending        body: { limit: 20 }
    POST /fetch-chapter         body: { manga_id: 1 }
    POST /download-panels       body: { chapter_id: 1 }
    POST /check-duplicates      body: { chapter_id: 1 }
    POST /generate-video        body: { chapter_id: 1 }
    POST /upload-tiktok         body: { video_id: 1 }
    POST /detect-shadow-ban     body: {}
    GET  /health

    ── CrewAI Agent ──────────────────────────────────────────────────────────
    POST /api/summon-agent      body: { prompt, target_count, dry_run, sync }
    POST /api/memory/stats      body: {}
    POST /api/memory/query-trends body: { query, n }
    POST /api/memory/declining  body: {}
"""
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
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
from scripts.utils import database as db


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


def _run_agent_crew(body: dict) -> dict:
    """
    Dispatch the CrewAI pipeline in a background thread and return immediately
    with a run_id. The crew logs progress to the standard logger.
    For synchronous execution (e.g. testing), pass sync=true in the body.
    """
    import threading, uuid
    from scripts.crew.pipeline_crew import run_pipeline

    prompt       = body.get("prompt", "Find top trending manga content and post 5 videos")
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


ROUTES = {
    "/fetch-trending":    lambda body: fetch_trending.main(body.get("limit", 20)),
    "/fetch-chapter":     lambda body: fetch_chapter.main(body["manga_id"]),
    "/download-panels":   lambda body: download_panels.main(body["chapter_id"]),
    "/check-duplicates":  lambda body: check_duplicates.main(body["chapter_id"]),
    "/generate-video":    lambda body: generate_video.main(body["chapter_id"]),
    "/upload-tiktok":     lambda body: upload_tiktok.main(body["video_id"]),
    "/upload-youtube":    lambda body: __import__('scripts.upload_youtube').upload_youtube.main(body["video_id"]),
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
        body.get("limit", 5)
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
    "/api/memory/query-trends":   lambda body: __import__(
        'scripts.memory_manager', fromlist=['query_similar_trends']
    ).query_similar_trends(body.get("query", "manga"), body.get("n", 5)),
    "/api/memory/declining":      lambda body: __import__(
        'scripts.memory_manager', fromlist=['get_declining_trends']
    ).get_declining_trends(),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.info(fmt % args)

    def send_json(self, code: int, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
    server = HTTPServer(("0.0.0.0", port), Handler)
    logger.info(f"Python worker listening on port {port}")
    server.serve_forever()
