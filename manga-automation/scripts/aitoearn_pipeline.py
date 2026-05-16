#!/usr/bin/env python3
"""
AiToEarn Autonomous Pipeline Orchestrator.
Coordinates the full 5-stage pipeline:
  Trend → Create → Publish → Engage → Monetize

Usage:
    python3 scripts/aitoearn_pipeline.py [--once] [--category tech] [--mode full]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.adapters import aitoearn_client

logger = setup_logger("aitoearn_pipeline")

STAGE_ORDER = ["trend", "create", "publish", "engage", "monetize"]


def stage_trend(category: str = "", limit: int = 10) -> dict[str, Any]:
    """Stage 1: Detect trending topics from all sources."""
    logger.info("[STAGE 1/5] Trend Detection")

    # Run all trend fetchers
    results: dict[str, Any] = {"fetchers": {}}

    try:
        from scripts.fetch_tiktok_trends_apify import main as tiktok_fetch
        results["fetchers"]["tiktok"] = tiktok_fetch(region="US", limit=limit)
    except Exception as exc:
        logger.warning(f"TikTok fetch failed: {exc}")

    try:
        from scripts.fetch_twitter_trends import main as twitter_fetch
        results["fetchers"]["twitter"] = twitter_fetch(region="US", limit=limit)
    except Exception as exc:
        logger.warning(f"Twitter fetch failed: {exc}")

    try:
        from scripts.fetch_youtube_trends import main as youtube_fetch
        results["fetchers"]["youtube"] = youtube_fetch(region="US", limit=limit)
    except Exception as exc:
        logger.warning(f"YouTube fetch failed: {exc}")

    try:
        from scripts.fetch_reddit_trends import main as reddit_fetch
        results["fetchers"]["reddit"] = reddit_fetch(category_slug=category, limit=limit)
    except Exception as exc:
        logger.warning(f"Reddit fetch failed: {exc}")

    # Count total trends
    total = sum(
        f.get("count", 0) if isinstance(f, dict) else 0
        for f in results["fetchers"].values()
    )
    results["total_trends"] = total
    results["timestamp"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"[STAGE 1/5] Trend Detection complete — {total} trends found")
    return results


def stage_create(limit: int = 5) -> dict[str, Any]:
    """Stage 2: Generate content for top trends."""
    logger.info("[STAGE 2/5] Content Creation")

    try:
        from scripts.trend_content_planner import execute as plan_execute
        plan_result = plan_execute(limit=limit)
        logger.info(f"[STAGE 2/5] Content plan: {plan_result.get('count', 0)} items")
        return plan_result
    except Exception as exc:
        logger.warning(f"Content planner failed: {exc}")
        return {"error": str(exc), "count": 0}


def _stage_publish_local(limit: int = 5) -> dict[str, Any]:
    """Local fallback: publish ready content via TikTok uploader v1."""
    logger.info("[STAGE 3/5] Publishing (local TikTok v1 fallback)")

    os.environ["USE_NEW_TIKTOK_UPLOADER"] = "false"
    from scripts import upload_tiktok

    candidates = db.execute(
        """SELECT id FROM videos
           WHERE status IN ('ready', 'publishing')
           ORDER BY created_at DESC
           LIMIT %s""",
        (limit,),
    )

    results: list[dict[str, Any]] = []
    for row in candidates:
        video_id = row["id"]
        try:
            db.execute(
                "UPDATE videos SET status = 'publishing' WHERE id = %s",
                (video_id,),
            )
            outcome = upload_tiktok.main(video_id)
            if not outcome:
                results.append({"video_id": video_id, "success": False, "error": "not_ready_or_not_found"})
                continue
            results.append(outcome)
        except Exception as exc:
            logger.warning(f"Publish failed for video {video_id}: {exc}")
            results.append({"video_id": video_id, "success": False, "error": str(exc)})

    published = sum(1 for r in results if r.get("success"))
    failed = len(results) - published
    logger.info(f"[STAGE 3/5] Publishing complete — {published}/{len(candidates)} uploaded")
    return {
        "published_count": published,
        "failed_count": failed,
        "ready_count": len(candidates),
        "uploader": "local_tiktok_v1",
        "path": "local_fallback",
        "channels": {
            "tiktok": {"success": published, "failed": failed},
        },
        "results": results,
    }


def stage_publish(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Stage 3 publish routing:
    - Primary: official AiToEarn API stage endpoint
    - Fallback: local TikTok uploader path
    """
    body = body or {}
    run_id = body.get("run_id") or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    local_limit = int(body.get("local_limit", 5))
    force_local = bool(body.get("force_local", False))

    if not force_local and aitoearn_client.enabled():
        remote_payload = {
            "run_id": run_id,
            "category": body.get("category", ""),
            "channels": body.get("channels"),
            "selected_accounts": body.get("selected_accounts"),
            "account_ids": body.get("account_ids"),
            "platform": body.get("platform"),
            "profile": body.get("profile", "minimal"),
            "mode": body.get("mode", "full"),
            "title": body.get("title"),
            "desc": body.get("desc"),
            "description": body.get("description"),
            "caption": body.get("caption"),
            "hashtags": body.get("hashtags"),
            "topics": body.get("topics"),
            "video_url": body.get("video_url") or body.get("videoUrl"),
            "cover_url": body.get("cover_url") or body.get("coverUrl"),
            "img_urls": body.get("img_urls") or body.get("imgUrlList"),
            "idempotency_key": body.get("idempotency_key", f"publish-{run_id}"),
        }
        remote = aitoearn_client.run_stage("publish", remote_payload)
        if remote.get("ok"):
            result = remote.get("result", {})
            channels = result.get("channels")
            if not isinstance(channels, dict):
                channels = {}
            return {
                "published_count": result.get("published_count", 0),
                "failed_count": result.get("failed_count", 0),
                "ready_count": result.get("ready_count", 0),
                "uploader": "aitoearn_api",
                "path": "remote_primary",
                "remote_url": remote.get("url"),
                "channels": channels,
                "result": result,
            }

        if not aitoearn_client.CLIENT.config.fallback_local_enabled:
            return {
                "error": "aitoearn_remote_publish_failed",
                "path": "remote_primary",
                "remote_error": remote,
            }
        logger.warning(f"AiToEarn remote publish failed, falling back to local uploader: {remote}")

    return _stage_publish_local(limit=local_limit)


def stage_engage(platform: str = "tiktok") -> dict[str, Any]:
    """Stage 4: Auto-engage with published content."""
    logger.info("[STAGE 4/5] Engagement")

    try:
        from scripts.engage.engine import run_engage_cycle
        result = run_engage_cycle(platform=platform, mode="light")
        return result
    except Exception as exc:
        logger.warning(f"Engagement failed: {exc}")
        return {"error": str(exc), "actions": 0}


def stage_monetize(creator_id: int = 1) -> dict[str, Any]:
    """Stage 5: Monetize content via marketplace matching + settlement."""
    logger.info("[STAGE 5/5] Monetization")

    try:
        from scripts.monetize.marketplace import match_creator
        matches = match_creator(creator_id, limit=5)

        # Calculate earnings for any active assignments
        from scripts.monetize.settlement import get_creator_earnings
        earnings = get_creator_earnings(creator_id, days=7)

        return {
            "match_count": len(matches),
            "earnings": earnings.get("total_earnings", 0),
            "settlement_count": earnings.get("transactions", 0),
        }
    except Exception as exc:
        logger.warning(f"Monetization failed: {exc}")
        return {"error": str(exc), "match_count": 0}


def run_full_pipeline(
    category: str = "",
    mode: str = "full",
    publish_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the complete AiToEarn pipeline."""
    start = time.time()
    pipeline_run: dict[str, Any] = {
        "pipeline": "aitoearn",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stages": {},
    }

    # Stage 1: Trend Detection
    pipeline_run["stages"]["trend"] = stage_trend(category=category)

    # Stage 2: Content Creation
    pipeline_run["stages"]["create"] = stage_create()

    # Stage 3: Publishing
    pipeline_run["stages"]["publish"] = stage_publish(publish_options)

    # Stage 4: Engagement (light mode for safety)
    if mode == "full":
        pipeline_run["stages"]["engage"] = stage_engage()

    # Stage 5: Monetization
    pipeline_run["stages"]["monetize"] = stage_monetize()

    pipeline_run["duration_seconds"] = round(time.time() - start, 2)
    pipeline_run["completed_at"] = datetime.now(timezone.utc).isoformat()

    # Log to database
    try:
        db.execute(
            """INSERT INTO workflow_executions (workflow_name, status, started_at, completed_at)
               VALUES ('aitoearn_pipeline', 'completed', %s, %s)""",
            (pipeline_run["started_at"], pipeline_run["completed_at"]),
        )
    except Exception:
        pass

    logger.info(f"Pipeline complete in {pipeline_run['duration_seconds']}s")
    return pipeline_run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AiToEarn Autonomous Pipeline")
    parser.add_argument("--once", action="store_true", default=True, help="Run once and exit")
    parser.add_argument("--category", default="", help="Target category slug")
    parser.add_argument("--mode", choices=["light", "full"], default="full")
    parser.add_argument("--stage", choices=STAGE_ORDER, help="Run a single stage only")
    args = parser.parse_args()

    if args.stage:
        stage_fn = {
            "trend": lambda: stage_trend(args.category),
            "create": stage_create,
            "publish": stage_publish,
            "engage": stage_engage,
            "monetize": stage_monetize,
        }[args.stage]
        result = stage_fn()
    else:
        result = run_full_pipeline(category=args.category, mode=args.mode)

    print(json.dumps(result, ensure_ascii=False, default=str))
