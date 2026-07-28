#!/usr/bin/env python3
"""
AiToEarn Open Platform — Seedance video workflow.

Uses the official REST APIs documented at https://docs.aitoearn.cn/llms.txt:
  POST /api/ai/video/generations          — submit Seedance job
  GET  /api/ai/video/generations/{taskId} — poll status + video URL
  MCP publish fanout                      — distribute to connected channels

Pipeline:
  plan (optional) → generate (Seedance) → publish (AiToEarn MCP) → engage (optional)

Usage:
    python3 scripts/aitoearn_seedance_pipeline.py --prompt "Product shot of smart lamp"
    python3 scripts/aitoearn_seedance_pipeline.py --prompt-file brief.txt --publish
    python3 scripts/aitoearn_seedance_pipeline.py --task-id abc123 --status-only
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

from scripts.adapters import aitoearn_client
from scripts.adapters.media_host import ensure_public_url, is_public_http_url
from scripts.aitoearn_pipeline import stage_engage, stage_publish
from scripts.utils.logger import setup_logger

logger = setup_logger("aitoearn_seedance_pipeline")

DEFAULT_MODEL = os.environ.get("AITOEARN_SEEDANCE_MODEL", "seedance-2-beta-1080p")
DEFAULT_RATIO = os.environ.get("AITOEARN_SEEDANCE_RATIO", "9:16")
DEFAULT_RESOLUTION = os.environ.get("AITOEARN_SEEDANCE_RESOLUTION", "1080p")
DEFAULT_DURATION = float(os.environ.get("AITOEARN_SEEDANCE_DURATION", "12"))
DEFAULT_SOURCE = os.environ.get("AITOEARN_SEEDANCE_SOURCE", "ai_video")


def _public_urls(values: Any) -> list[str]:
    if not values:
        return []
    items = values if isinstance(values, list) else [values]
    out: list[str] = []
    for item in items:
        raw = str(item).strip()
        if not raw:
            continue
        if is_public_http_url(raw):
            out.append(raw)
            continue
        if os.path.isfile(raw):
            hosted = ensure_public_url(raw)
            if hosted.get("ok") and hosted.get("url"):
                out.append(str(hosted["url"]))
            else:
                logger.warning(f"Could not host reference media: {raw} — {hosted.get('error')}")
    return out


def build_seedance_payload(body: dict[str, Any]) -> dict[str, Any]:
    prompt = str(body.get("prompt") or body.get("message") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    model = str(body.get("model") or DEFAULT_MODEL).strip()
    ratio = str(body.get("ratio") or DEFAULT_RATIO).strip()
    resolution = str(body.get("resolution") or DEFAULT_RESOLUTION).strip()
    duration = body.get("duration", DEFAULT_DURATION)
    group_id = body.get("group_id") or body.get("groupId")

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "ratio": ratio,
        "resolution": resolution,
        "duration": float(duration),
        "source": str(body.get("source") or DEFAULT_SOURCE),
    }
    if group_id:
        payload["groupId"] = str(group_id)

    images = _public_urls(body.get("images") or body.get("image"))
    if images:
        payload["images"] = images[:9]
    videos = _public_urls(body.get("videos") or body.get("video"))
    if videos:
        payload["videos"] = videos[:3]
    audios = _public_urls(body.get("audios") or body.get("audio"))
    if audios:
        payload["audios"] = audios[:3]

    return payload


def stage_plan(body: dict[str, Any]) -> dict[str, Any]:
    """Lightweight prompt enrichment — no extra LLM required."""
    prompt = str(body.get("prompt") or "").strip()
    product = str(body.get("product") or body.get("brand") or "").strip()
    style = str(body.get("style") or "cinematic product promo").strip()
    audience = str(body.get("audience") or "social media creators").strip()

    enriched = prompt
    if product and product.lower() not in prompt.lower():
        enriched = f"{product}: {enriched}"
    if style and style.lower() not in enriched.lower():
        enriched = f"{enriched}. Style: {style}."
    if audience:
        enriched = f"{enriched} Target audience: {audience}."

    return {
        "original_prompt": prompt,
        "planned_prompt": enriched.strip(),
        "style": style,
        "audience": audience,
    }


def stage_generate(body: dict[str, Any], *, wait: bool = True) -> dict[str, Any]:
    if not aitoearn_client.api_key_configured():
        return {
            "ok": False,
            "error": "AITOEARN_API_KEY is required. Create one in AiToEarn Settings.",
        }

    planned = body.get("planned_prompt") or body.get("prompt")
    gen_body = {**body, "prompt": planned}
    payload = build_seedance_payload(gen_body)

    logger.info(
        "[SEEDANCE] Submitting video job model=%s ratio=%s duration=%s",
        payload.get("model"),
        payload.get("ratio"),
        payload.get("duration"),
    )

    if wait:
        result = aitoearn_client.generate_video_and_wait(payload)
    else:
        result = aitoearn_client.create_video_generation(payload)

    if not result.get("ok"):
        return result

    data = result.get("data") or {}
    return {
        "ok": True,
        "task_id": result.get("task_id") or data.get("id"),
        "status": result.get("status") or data.get("status"),
        "video_url": result.get("video_url") or data.get("videoUrl"),
        "cover_url": result.get("cover_url") or data.get("coverUrl"),
        "media_id": result.get("media_id") or data.get("mediaId"),
        "payload": payload,
        "raw": result,
    }


def stage_publish_seedance(body: dict[str, Any], generate_result: dict[str, Any]) -> dict[str, Any]:
    video_url = str(
        body.get("video_url")
        or generate_result.get("video_url")
        or ""
    ).strip()
    if not video_url:
        return {"ok": False, "error": "no_video_url_to_publish"}

    title = str(body.get("title") or body.get("caption") or "AI Seedance clip").strip()
    desc = str(body.get("desc") or body.get("description") or title).strip()
    cover_url = str(
        body.get("cover_url") or generate_result.get("cover_url") or ""
    ).strip()

    publish_body: dict[str, Any] = {
        "video_url": video_url,
        "title": title,
        "desc": desc,
        "channels": body.get("channels"),
        "platform": body.get("platform"),
        "selected_accounts": body.get("selected_accounts"),
        "account_ids": body.get("account_ids"),
        "hashtags": body.get("hashtags"),
        "topics": body.get("topics"),
        "publish_time": body.get("publish_time"),
        "mode": body.get("mode", "full"),
        "profile": body.get("profile", "minimal"),
    }
    if cover_url:
        publish_body["cover_url"] = cover_url

    logger.info("[SEEDANCE] Publishing via AiToEarn MCP fanout")
    published = stage_publish(publish_body)
    return {"ok": True, "publish": published, "video_url": video_url}


def run_seedance_workflow(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = dict(body or {})
    start = time.time()
    workflow: dict[str, Any] = {
        "pipeline": "aitoearn_seedance",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stages": {},
    }

    if body.get("status_only"):
        task_id = str(body.get("task_id") or body.get("taskId") or "").strip()
        if not task_id:
            return {"ok": False, "error": "task_id is required for status_only"}
        workflow["stages"]["status"] = aitoearn_client.get_video_generation_status(task_id)
        workflow["completed_at"] = datetime.now(timezone.utc).isoformat()
        workflow["duration_seconds"] = round(time.time() - start, 2)
        return workflow

    if body.get("plan", True) and not body.get("skip_plan"):
        plan = stage_plan(body)
        workflow["stages"]["plan"] = plan
        body["planned_prompt"] = plan["planned_prompt"]

    generate = stage_generate(body, wait=body.get("wait", True))
    workflow["stages"]["generate"] = generate
    if not generate.get("ok"):
        workflow["ok"] = False
        workflow["error"] = generate.get("error", "generation_failed")
        workflow["completed_at"] = datetime.now(timezone.utc).isoformat()
        workflow["duration_seconds"] = round(time.time() - start, 2)
        return workflow

    workflow["task_id"] = generate.get("task_id")
    workflow["video_url"] = generate.get("video_url")
    workflow["cover_url"] = generate.get("cover_url")

    if body.get("publish"):
        publish = stage_publish_seedance(body, generate)
        workflow["stages"]["publish"] = publish

    if body.get("engage"):
        workflow["stages"]["engage"] = stage_engage(
            platform=str(body.get("engage_platform") or body.get("platform") or "tiktok"),
        )

    workflow["ok"] = True
    workflow["completed_at"] = datetime.now(timezone.utc).isoformat()
    workflow["duration_seconds"] = round(time.time() - start, 2)
    logger.info(
        "Seedance workflow complete in %.1fs — video=%s",
        workflow["duration_seconds"],
        workflow.get("video_url"),
    )
    return workflow


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AiToEarn Seedance video workflow")
    parser.add_argument("--prompt", default="", help="Video generation prompt")
    parser.add_argument("--prompt-file", default="", help="Read prompt from file")
    parser.add_argument("--model", default="", help="Seedance model id")
    parser.add_argument("--ratio", default="", help="Aspect ratio e.g. 9:16")
    parser.add_argument("--duration", type=float, default=0, help="Duration seconds")
    parser.add_argument("--publish", action="store_true", help="Publish after generation")
    parser.add_argument("--engage", action="store_true", help="Run engagement after publish")
    parser.add_argument("--no-wait", action="store_true", help="Submit only, do not poll")
    parser.add_argument("--task-id", default="", help="Poll existing task id")
    parser.add_argument("--status-only", action="store_true", help="Only query task status")
    parser.add_argument("--json-file", default="", help="Full request body as JSON file")
    args = parser.parse_args()

    req: dict[str, Any] = {}
    if args.json_file:
        with open(args.json_file, encoding="utf-8") as f:
            req = json.load(f)
    if args.prompt:
        req["prompt"] = args.prompt
    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as f:
            req["prompt"] = f.read().strip()
    if args.model:
        req["model"] = args.model
    if args.ratio:
        req["ratio"] = args.ratio
    if args.duration:
        req["duration"] = args.duration
    if args.publish:
        req["publish"] = True
    if args.engage:
        req["engage"] = True
    if args.no_wait:
        req["wait"] = False
    if args.task_id:
        req["task_id"] = args.task_id
    if args.status_only:
        req["status_only"] = True

    print(json.dumps(run_seedance_workflow(req), ensure_ascii=False, default=str))
