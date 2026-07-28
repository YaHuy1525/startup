#!/usr/bin/env python3
"""
Hermes monitoring agent (Claude-powered) for the local app.

This module does not replace your whole app. It acts as an ops layer:
1) collect health/status signals
2) ask Claude for diagnosis + prioritized actions
3) optionally execute safe remediations only (guarded by env + request flag)
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.adapters import aitoearn_client, media_host
from scripts import source_youtube_assets

logger = setup_logger("hermes_agent")

WORKER_URL = os.environ.get("PYTHON_WORKER_URL", "http://localhost:18080").rstrip("/")
_fallback_worker_urls = [
    u.strip()
    for u in (os.environ.get("PYTHON_WORKER_URLS", "http://localhost:18080,http://localhost:8080")).split(",")
    if u.strip()
]
WORKER_URL_CANDIDATES: list[str] = []
for candidate in [WORKER_URL, *_fallback_worker_urls]:
    if candidate not in WORKER_URL_CANDIDATES:
        WORKER_URL_CANDIDATES.append(candidate)
MODEL = os.environ.get("HERMES_MODEL", os.environ.get("EDITORIAL_MODEL", "claude-sonnet-4-20250514"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HERMES_USE_CLAUDE = os.environ.get("HERMES_USE_CLAUDE", "1").strip().lower() in {"1", "true", "yes"}
REQUEST_TIMEOUT = int(os.environ.get("HERMES_TIMEOUT_SEC", "120"))  # Increased from 25 to 120 to allow scraping to finish
FINANCE_VIDEO_TIMEOUT = int(os.environ.get("HERMES_FINANCE_VIDEO_TIMEOUT_SEC", "660"))  # 11 min for video gen

# Guardrail: no auto actions unless both env + request allow.
AUTO_ACTIONS_ENV = os.environ.get("HERMES_AUTO_ACTIONS", "0").strip().lower() in {"1", "true", "yes"}
DISCOVER_MAX_CANDIDATES = int(os.environ.get("HERMES_DISCOVER_MAX_CANDIDATES", "12"))
DISCOVER_MIN_SCORE = float(os.environ.get("HERMES_DISCOVER_MIN_SCORE", "0.65"))


def _anthropic_base_url() -> str:
    """Normalize ANTHROPIC_BASE_URL; empty/invalid values fall back to the official API."""
    raw = (os.environ.get("ANTHROPIC_BASE_URL") or "").strip()
    if not raw:
        return "https://api.anthropic.com"
    if raw.startswith(("http://", "https://")):
        return raw.rstrip("/")
    return f"http://{raw.lstrip('/')}"


def _anthropic_client():
    import anthropic

    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url=_anthropic_base_url())


def _post(path: str, body: dict[str, Any] | None = None, timeout: int | None = None) -> dict[str, Any]:
    errors: list[str] = []
    for base in WORKER_URL_CANDIDATES:
        try:
            resp = requests.post(f"{base}{path}", json=body or {}, timeout=timeout or REQUEST_TIMEOUT)
            if resp.status_code == 404:
                errors.append(f"{base}{path} -> 404")
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            errors.append(f"{base}{path} -> {e}")
            continue
    raise RuntimeError("worker POST failed across candidates: " + " | ".join(errors))


def _get(path: str, timeout: int | None = None) -> dict[str, Any]:
    errors: list[str] = []
    for base in WORKER_URL_CANDIDATES:
        try:
            resp = requests.get(f"{base}{path}", timeout=timeout or REQUEST_TIMEOUT)
            if resp.status_code == 404:
                errors.append(f"{base}{path} -> 404")
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            errors.append(f"{base}{path} -> {e}")
            continue
    raise RuntimeError("worker GET failed across candidates: " + " | ".join(errors))


def _post_json(path: str, body: dict[str, Any], timeout: int) -> dict[str, Any]:
    errors: list[str] = []
    for base in WORKER_URL_CANDIDATES:
        try:
            resp = requests.post(f"{base}{path}", json=body, timeout=timeout)
            if resp.status_code == 404:
                errors.append(f"{base}{path} -> 404")
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            errors.append(f"{base}{path} -> {e}")
    raise RuntimeError("worker JSON POST failed across candidates: " + " | ".join(errors))


def _run_aitoearn_stage(
    stage: str,
    payload: dict[str, Any] | None = None,
    *,
    fallback_path: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """
    Execute a stage using official AiToEarn as primary, local worker as fallback.
    """
    payload = payload or {}
    remote_error: dict[str, Any] | None = None

    if aitoearn_client.enabled():
        remote = aitoearn_client.run_stage(stage, payload)
        if remote.get("ok"):
            return {
                "success": True,
                "execution_path": "aitoearn_primary",
                "stage": stage,
                "result": remote.get("result"),
                "url": remote.get("url"),
            }
        remote_error = remote

        if not aitoearn_client.CLIENT.config.fallback_local_enabled:
            return {
                "success": False,
                "execution_path": "aitoearn_primary",
                "stage": stage,
                "error": "remote_stage_failed_and_fallback_disabled",
                "remote_error": remote_error,
            }

    local_route = fallback_path or f"/aitoearn/stage/{stage}"
    local = _post(local_route, payload, timeout=timeout)
    return {
        "success": True,
        "execution_path": "local_fallback" if remote_error else "local_only",
        "stage": stage,
        "result": local,
        "remote_error": remote_error,
        "local_route": local_route,
    }


def _run_aitoearn_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Run full Trend→Create→Publish→Engage→Monetize using primary AiToEarn when enabled.
    """
    remote_error: dict[str, Any] | None = None
    if aitoearn_client.enabled():
        remote = aitoearn_client.run_action("pipeline", payload)
        if remote.get("ok"):
            return {
                "success": True,
                "execution_path": "aitoearn_primary",
                "result": remote.get("result"),
                "url": remote.get("url"),
            }
        remote_error = remote
        if not aitoearn_client.CLIENT.config.fallback_local_enabled:
            return {
                "success": False,
                "execution_path": "aitoearn_primary",
                "error": "remote_pipeline_failed_and_fallback_disabled",
                "remote_error": remote_error,
            }

    local = _post("/aitoearn/pipeline", payload)
    return {
        "success": True,
        "execution_path": "local_fallback" if remote_error else "local_only",
        "result": local,
        "remote_error": remote_error,
        "local_route": "/aitoearn/pipeline",
    }


def collect_status_snapshot(limit: int = 10) -> dict[str, Any]:
    """Collect lightweight runtime + DB snapshot used for diagnosis."""
    now = datetime.now(timezone.utc).isoformat()
    snapshot: dict[str, Any] = {"captured_at": now}

    # Worker health
    try:
        snapshot["worker_health"] = _get("/health")
    except Exception as e:
        snapshot["worker_health"] = {"status": "down", "error": str(e)}

    # DB queue-like signals
    try:
        snapshot["brief_counts"] = db.execute_one(
            """
            SELECT
              COUNT(*) FILTER (WHERE status='draft') AS draft,
              COUNT(*) FILTER (WHERE status='approved') AS approved,
              COUNT(*) FILTER (WHERE status='producing') AS producing,
              COUNT(*) FILTER (WHERE status='distributed') AS distributed
            FROM content_briefs
            """
        ) or {}
    except Exception as e:
        snapshot["brief_counts"] = {"error": str(e)}

    try:
        snapshot["distribution_counts"] = db.execute_one(
            """
            SELECT
              COUNT(*) FILTER (WHERE status='pending') AS pending,
              COUNT(*) FILTER (WHERE status='scheduled') AS scheduled,
              COUNT(*) FILTER (WHERE status='published') AS published,
              COUNT(*) FILTER (WHERE status='failed') AS failed
            FROM platform_distributions
            """
        ) or {}
    except Exception as e:
        snapshot["distribution_counts"] = {"error": str(e)}

    try:
        snapshot["latest_failures"] = db.execute(
            """
            SELECT platform, format, status, error_log, created_at
            FROM platform_distributions
            WHERE status='failed'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, min(limit, 50)),),
        )
    except Exception as e:
        snapshot["latest_failures"] = [{"error": str(e)}]

    # Optional status endpoints
    try:
        snapshot["research_status"] = _post("/research/status", {"limit": 5}).get("result")
    except Exception as e:
        snapshot["research_status"] = {"error": str(e)}

    try:
        snapshot["aitoearn_integration"] = aitoearn_client.startup_validation()
    except Exception as e:
        snapshot["aitoearn_integration"] = {"ok": False, "error": str(e)}

    return snapshot


def _claude_diagnose(snapshot: dict[str, Any], objective: str) -> dict[str, Any]:
    if not ANTHROPIC_API_KEY:
        return {
            "ok": False,
            "error": "ANTHROPIC_API_KEY not set",
            "fallback": _heuristic_diagnose(snapshot, objective),
        }

    try:
        import anthropic
    except Exception as e:
        return {
            "ok": False,
            "error": f"anthropic SDK unavailable: {e}",
            "fallback": _heuristic_diagnose(snapshot, objective),
        }

    prompt = f"""
You are Hermes, an SRE-style operations agent for a content automation app.
Objective: {objective}

You are given a JSON status snapshot. Return only valid JSON with this schema:
{{
  "summary": "short diagnosis",
  "severity": "low|medium|high|critical",
  "findings": [{{"issue":"...", "evidence":"...", "impact":"..."}}],
  "recommended_actions": [
    {{
      "action_id":"health_check|genesis_discover|genesis_briefs|omnichannel_auto|postiz_integrations_map|finance_video_generate|finance_video_distribute",
      "reason":"...",
      "priority": 1
    }}
  ]
}}

Rules:
- Recommend only action_id values listed above.
- Prefer low-risk actions first.
- Keep at most 5 recommended actions.

Snapshot JSON:
{json.dumps(snapshot, ensure_ascii=False)}
"""

    try:
        client = _anthropic_client()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1400,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        parsed = json.loads(raw)
        parsed["ok"] = True
        return parsed
    except Exception as e:
        logger.warning(f"Claude diagnose failed, using heuristic fallback: {e}")
        return {
            "ok": False,
            "error": str(e),
            "fallback": _heuristic_diagnose(snapshot, objective),
        }


def _heuristic_diagnose(snapshot: dict[str, Any], objective: str) -> dict[str, Any]:
    dist = snapshot.get("distribution_counts") or {}
    failed = int(dist.get("failed") or 0) if isinstance(dist, dict) else 0
    pending = int(dist.get("pending") or 0) if isinstance(dist, dict) else 0
    actions: list[dict[str, Any]] = [{"action_id": "health_check", "reason": "baseline health probe", "priority": 1}]
    findings: list[dict[str, str]] = []
    severity = "low"

    if failed > 0:
        severity = "high" if failed >= 10 else "medium"
        findings.append(
            {"issue": "failed_distributions", "evidence": f"{failed} failed rows", "impact": "publishing gaps"}
        )
        actions.append(
            {"action_id": "postiz_integrations_map", "reason": "confirm social integration mapping", "priority": 2}
        )
    if pending > 50:
        severity = "high"
        findings.append(
            {"issue": "distribution_backlog", "evidence": f"{pending} pending rows", "impact": "latency to publish"}
        )
        actions.append({"action_id": "omnichannel_auto", "reason": "kick processing cadence", "priority": 3})

    actions.extend(
        [
            {"action_id": "genesis_discover", "reason": "refresh trend signals", "priority": 4},
            {"action_id": "genesis_briefs", "reason": "keep briefs flowing", "priority": 5},
        ]
    )

    return {
        "ok": True,
        "summary": f"Heuristic diagnosis for objective: {objective}",
        "severity": severity,
        "findings": findings,
        "recommended_actions": actions[:5],
        "mode": "heuristic",
    }


def _run_safe_action(action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action_id == "health_check":
        return {"action_id": action_id, "result": _get("/health")}
    if action_id == "genesis_discover":
        return {"action_id": action_id, "result": _post("/genesis/discover", {"limit": payload.get("limit", 8)}, timeout=180)}
    if action_id == "genesis_briefs":
        return {"action_id": action_id, "result": _post("/genesis/briefs", {"top": payload.get("top", 2)}, timeout=180)}
    if action_id == "omnichannel_auto":
        return {
            "action_id": action_id,
            "result": _post(
                "/omnichannel/auto",
                {"limit": payload.get("auto_limit", 2), "profile": payload.get("profile", "minimal")},
            ),
        }
    if action_id == "postiz_integrations_map":
        return {"action_id": action_id, "result": _post("/adapters/postiz/integrations-map", {})}
    if action_id == "finance_video_generate":
        provider = payload.get("provider", "revid")
        week_iso = payload.get("week_iso")
        background = payload.get("background", "subway_surfers")
        body: dict[str, Any] = {"provider": provider, "style": background}
        if week_iso:
            body["week_iso"] = week_iso
        video_result = _post_json("/finance/ai-video", body, FINANCE_VIDEO_TIMEOUT)
        return {"action_id": action_id, "result": video_result}
    if action_id == "finance_video_distribute":
        video_id = payload.get("video_id")
        if not video_id:
            return {"action_id": action_id, "error": "video_id required for distribute"}
        result = _run_aitoearn_stage(
            "publish",
            {
                "video_id": video_id,
                "video_url": payload.get("video_url") or payload.get("videoUrl"),
                "profile": payload.get("profile", "minimal"),
                "channels": payload.get("channels", ["tiktok", "youtube_shorts", "instagram_reels"]),
                "selected_accounts": payload.get("selected_accounts"),
                "account_ids": payload.get("account_ids"),
                "title": payload.get("title"),
                "desc": payload.get("desc"),
                "caption": payload.get("caption"),
                "topics": payload.get("topics"),
                "hashtags": payload.get("hashtags"),
                "cover_url": payload.get("cover_url") or payload.get("coverUrl"),
                "img_urls": payload.get("img_urls") or payload.get("imgUrlList"),
                "idempotency_key": payload.get("idempotency_key", f"finance-distribute-{video_id}"),
            },
            fallback_path="/aitoearn/stage/publish",
        )
        return {"action_id": action_id, "result": result}
    return {"action_id": action_id, "error": f"unknown or disallowed action {action_id}"}


def run_cycle(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    objective = body.get("objective", "Monitor app health and keep publishing pipeline healthy.")
    snapshot = collect_status_snapshot(limit=int(body.get("failure_limit", 10)))
    diagnosis = _claude_diagnose(snapshot, objective)

    requested_auto = bool(body.get("execute_actions", False))
    can_execute = requested_auto and AUTO_ACTIONS_ENV
    action_results: list[dict[str, Any]] = []
    skipped_actions: list[str] = []

    for rec in diagnosis.get("recommended_actions", [])[:5]:
        action_id = rec.get("action_id")
        if not action_id:
            continue
        if can_execute:
            try:
                action_results.append(_run_safe_action(action_id, body))
            except Exception as e:
                action_results.append({"action_id": action_id, "error": str(e)})
        else:
            skipped_actions.append(action_id)

    return {
        "success": True,
        "objective": objective,
        "auto_actions_enabled": AUTO_ACTIONS_ENV,
        "executed": can_execute,
        "diagnosis": diagnosis,
        "snapshot": snapshot,
        "action_results": action_results,
        "skipped_actions": skipped_actions,
    }


def run_full_ops_pipeline(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Execute Trend → Create → Publish → Engage → Monetize via AiToEarn-first routing.
    """
    body = body or {}
    run_id = str(body.get("run_id") or uuid4())
    category = str(body.get("category", "") or "")
    mode = str(body.get("mode", "full") or "full")
    profile = str(body.get("profile", "minimal") or "minimal")
    engage_platform = str(body.get("engage_platform", "tiktok") or "tiktok")
    creator_id = int(body.get("creator_id", 1))
    dry_run = bool(body.get("dry_run", False))

    start_iso = datetime.now(timezone.utc).isoformat()
    steps: list[dict[str, Any]] = []

    if dry_run:
        return {
            "success": True,
            "pipeline": "hermes_full_ops",
            "dry_run": True,
            "run_id": run_id,
            "start": start_iso,
            "planned_stages": ["trend", "create", "publish", "engage", "monetize"],
            "execution_policy": {
                "aitoearn_primary": bool(aitoearn_client.enabled()),
                "fallback_local": bool(aitoearn_client.CLIENT.config.fallback_local_enabled),
            },
        }

    stage_payloads = {
        "trend": {"category": category, "limit": int(body.get("trend_limit", 10)), "run_id": run_id},
        "create": {"limit": int(body.get("create_limit", 5)), "category": category, "run_id": run_id},
        "publish": {
            "profile": profile,
            "mode": mode,
            "category": category,
            "run_id": run_id,
            "channels": body.get("channels"),
            "selected_accounts": body.get("selected_accounts"),
            "account_ids": body.get("account_ids"),
            "platform": body.get("platform"),
            "title": body.get("title"),
            "desc": body.get("desc"),
            "description": body.get("description"),
            "caption": body.get("caption"),
            "hashtags": body.get("hashtags"),
            "topics": body.get("topics"),
            "video_url": body.get("video_url") or body.get("videoUrl"),
            "cover_url": body.get("cover_url") or body.get("coverUrl"),
            "img_urls": body.get("img_urls") or body.get("imgUrlList"),
            "idempotency_key": f"{run_id}-publish",
        },
        "engage": {
            "platform": engage_platform,
            "mode": "light" if mode == "light" else "full",
            "run_id": run_id,
            "idempotency_key": f"{run_id}-engage",
        },
        "monetize": {"creator_id": creator_id, "run_id": run_id, "idempotency_key": f"{run_id}-monetize"},
    }

    for stage_name in ("trend", "create", "publish", "engage", "monetize"):
        try:
            result = _run_aitoearn_stage(stage_name, stage_payloads[stage_name], timeout=REQUEST_TIMEOUT)
            step_ok = bool(result.get("success"))
            steps.append({"stage": stage_name, "status": "ok" if step_ok else "error", "result": result})
            if not step_ok:
                break
        except Exception as e:
            steps.append({"stage": stage_name, "status": "error", "error": str(e)})
            break

    ended_iso = datetime.now(timezone.utc).isoformat()
    failed_steps = [s for s in steps if s.get("status") == "error"]
    return {
        "success": len(failed_steps) == 0,
        "pipeline": "hermes_full_ops",
        "run_id": run_id,
        "started_at": start_iso,
        "completed_at": ended_iso,
        "steps": steps,
        "steps_passed": len(steps) - len(failed_steps),
        "steps_failed": len(failed_steps),
        "execution_policy": {
            "aitoearn_primary": bool(aitoearn_client.enabled()),
            "fallback_local": bool(aitoearn_client.CLIENT.config.fallback_local_enabled),
        },
    }


def run_finance_pipeline(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Full autonomous pipeline — Claude orchestrates each step:

      1. Scan earnings screenshots  →  index new payouts
      2. Generate AI video (Revid)  →  brainrot-style proof video
      3. Distribute to all channels →  TikTok, YouTube, Instagram, Threads, Pinterest
      4. Claude health-check        →  confirm everything succeeded, report any failures

    Body params:
      provider    str  - 'revid' | 'creatify' | 'heygen'  (default: revid)
      background  str  - 'subway_surfers' | 'minecraft' (default: subway_surfers)
      week_iso    str  - ISO week e.g. '2026-W19' (default: current week)
      profile     str  - distribution profile: 'minimal' | 'full' (default: minimal)
      execute_actions bool - must be True to actually run (safety guardrail)
    """
    body = body or {}
    provider   = body.get("provider", "revid")
    background = body.get("background", "subway_surfers")
    week_iso   = body.get("week_iso")
    profile    = body.get("profile", "minimal")
    steps: list[dict[str, Any]] = []

    logger.info("Hermes: starting finance video pipeline")

    # ── Step 1: Scan earnings screenshots
    logger.info("Step 1: Scanning earnings screenshots...")
    try:
        scan_result = _post("/earnings/ingest", {"action": "scan"}, timeout=120)
        steps.append({"step": "earnings_scan", "status": "ok", "result": scan_result.get("result", {})})
        ingested = scan_result.get("result", {}).get("ingested", 0)
        logger.info(f"Step 1 done: {ingested} new snapshots ingested")
    except Exception as e:
        steps.append({"step": "earnings_scan", "status": "error", "error": str(e)})
        logger.warning(f"Step 1 failed (non-fatal): {e}")

    # ── Step 2: Generate brainrot video
    logger.info(f"Step 2: Generating {provider} video (bg={background})...")
    try:
        video_body: dict[str, Any] = {"provider": provider, "style": background}
        if week_iso:
            video_body["week_iso"] = week_iso
        raw_video_result = _post_json("/finance/ai-video", video_body, FINANCE_VIDEO_TIMEOUT)
        video_result = raw_video_result.get("result", raw_video_result)
        video_id = video_result.get("db_video_id") or video_result.get("video_id")
        video_url = video_result.get("video_url", "")
        steps.append({
            "step": "video_generate",
            "status": "ok" if video_id else "error",
            "video_id": video_id,
            "video_url": video_url,
            "provider": provider,
            "result": video_result,
        })
        logger.info(f"Step 2 done: video_id={video_id} url={video_url}")
    except Exception as e:
        steps.append({"step": "video_generate", "status": "error", "error": str(e)})
        logger.error(f"Step 2 failed: {e}")
        return {
            "success": False,
            "pipeline": "finance_video_pipeline",
            "steps": steps,
            "error": f"Video generation failed: {e}",
        }

    if not video_id:
        return {
            "success": False,
            "pipeline": "finance_video_pipeline",
            "steps": steps,
            "error": "Video generated but no video_id returned — check provider logs",
        }

    # ── Step 3: Publish (AiToEarn-first)
    logger.info(f"Step 3: Publishing video_id={video_id} profile={profile}...")
    try:
        stage_result = _run_aitoearn_stage(
            "publish",
            {
                "video_id": video_id,
                "video_url": video_url,
                "profile": profile,
                "channels": body.get("channels", ["tiktok", "youtube_shorts", "instagram_reels"]),
                "selected_accounts": body.get("selected_accounts"),
                "account_ids": body.get("account_ids"),
                "title": body.get("title", f"Finance update {week_iso or ''}".strip()),
                "desc": body.get("desc", "Automated finance update generated by Hermes."),
                "caption": body.get("caption"),
                "topics": body.get("topics"),
                "hashtags": body.get("hashtags"),
                "cover_url": body.get("cover_url") or body.get("coverUrl"),
                "idempotency_key": body.get("idempotency_key", f"finance-{video_id}-publish"),
            },
            fallback_path="/aitoearn/stage/publish",
        )
        dist_data = stage_result.get("result", {})
        succeeded = dist_data.get("succeeded", dist_data.get("published_count", 0))
        failed_dist = dist_data.get("failed", dist_data.get("failed_count", 0))
        steps.append({
            "step": "publish",
            "status": "ok",
            "succeeded": succeeded,
            "failed": failed_dist,
            "execution_path": stage_result.get("execution_path"),
            "result": dist_data,
        })
        logger.info(f"Step 3 done: {succeeded} platforms succeeded, {failed_dist} failed")
    except Exception as e:
        steps.append({"step": "publish", "status": "error", "error": str(e)})
        logger.error(f"Step 3 failed: {e}")

    # ── Step 4: Claude health-check
    logger.info("Step 4: Claude pipeline health check...")
    try:
        snapshot = collect_status_snapshot(limit=5)
        pipeline_context = {
            **snapshot,
            "pipeline_steps": steps,
            "pipeline_objective": "Verify finance video pipeline completed successfully.",
        }
        diagnosis = _claude_diagnose(
            pipeline_context,
            "Check that video was generated and distributed. Report any failures. Be concise.",
        )
        steps.append({"step": "hermes_healthcheck", "status": "ok", "diagnosis": diagnosis})
        logger.info(f"Step 4 done: severity={diagnosis.get('severity')} summary={diagnosis.get('summary', '')[:80]}")
    except Exception as e:
        steps.append({"step": "hermes_healthcheck", "status": "error", "error": str(e)})
        logger.warning(f"Step 4 failed (non-fatal): {e}")

    # ── Summary
    ok_steps = [s for s in steps if s.get("status") == "ok"]
    err_steps = [s for s in steps if s.get("status") == "error"]
    final_diagnosis = next(
        (s.get("diagnosis") for s in steps if s.get("step") == "hermes_healthcheck"),
        None,
    )

    return {
        "success": len(err_steps) == 0 or video_id is not None,
        "pipeline": "finance_video_pipeline",
        "video_id": video_id,
        "video_url": video_url if "video_url" in locals() else None,
        "steps_passed": len(ok_steps),
        "steps_failed": len(err_steps),
        "steps": steps,
        "hermes_summary": final_diagnosis.get("summary") if final_diagnosis else None,
        "hermes_severity": final_diagnosis.get("severity") if final_diagnosis else None,
        "message": (
            f"Pipeline complete: video #{video_id} generated via {provider} "
            f"and published to {steps[2].get('succeeded', '?')} platforms."
            if video_id else "Pipeline completed with errors."
        ),
    }


def run_anime_theory_pipeline(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Hermes entry: anime-theory Short E2E (script → Remotion → caption → AiToEarn).

    Body:
      topic / title / objective  str  required
      anime / series             str
      context                    str
      long                       bool
      publish                    bool  default True
      dry_run                    bool
      channels                   list  default tiktok,instagram,facebook
    """
    from scripts import shortform_pipeline

    body = body or {}
    logger.info(
        "Hermes: anime-theory pipeline topic=%r anime=%r publish=%s dry_run=%s",
        body.get("topic") or body.get("title") or body.get("objective"),
        body.get("anime") or body.get("series"),
        body.get("publish", True),
        body.get("dry_run", False),
    )
    result = shortform_pipeline.run_anime_theory_pipeline(body)
    return {
        "success": bool(result.get("ok") or result.get("success")),
        "pipeline": "anime_theory",
        **result,
    }


def run_viral_pipeline(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Full autonomous viral pipeline:
      1. Discover trending viral content
      2. Draft contents / briefs
      3. Generate brainrot video
      4. Distribute to platforms (TikTok, etc.)
      5. Claude health-check
    """
    body = body or {}
    provider   = body.get("provider", "revid")
    background = body.get("background", "subway_surfers")
    profile    = body.get("profile", "minimal")
    steps: list[dict[str, Any]] = []

    logger.info("Hermes: starting viral video pipeline")

    # ── Step 1: Discover trends
    logger.info("Step 1: Discovering trends...")
    try:
        disc_result = _post("/genesis/discover", {"categories": "finance", "limit": 10}, timeout=180)
        steps.append({"step": "genesis_discover", "status": "ok", "result": disc_result.get("result", {})})
        signals = disc_result.get("result", {}).get("per_category", {}).get("finance", {}).get("signals", 0)
        logger.info(f"Step 1 done: {signals} new signals")
    except Exception as e:
        steps.append({"step": "genesis_discover", "status": "error", "error": str(e)})
        logger.warning(f"Step 1 failed (non-fatal): {e}")

    # ── Step 2: Draft contents (Briefs)
    logger.info("Step 2: Drafting briefs...")
    brief_id = None
    try:
        briefs_result = _post("/genesis/briefs", {"categories": "finance", "top": 1, "action": "generate"}, timeout=180)
        fin_briefs = briefs_result.get("result", {}).get("per_category", {}).get("finance", {})
        brief_ids = fin_briefs.get("brief_ids", [])
        steps.append({"step": "genesis_briefs", "status": "ok", "result": briefs_result.get("result", {})})
        if brief_ids:
            brief_id = brief_ids[0]
            logger.info(f"Step 2 done: brief {brief_id} generated")
        else:
            logger.warning("Step 2 done but no briefs were generated")
    except Exception as e:
        steps.append({"step": "genesis_briefs", "status": "error", "error": str(e)})
        logger.error(f"Step 2 failed: {e}")
        return {
            "success": False,
            "pipeline": "viral_pipeline",
            "steps": steps,
            "error": f"Brief generation failed: {e}",
        }

    # ── Step 3: Generate brainrot video
    logger.info(f"Step 3: Generating {provider} video (bg={background}) for brief {brief_id}...")
    video_id = None
    try:
        video_body: dict[str, Any] = {"provider": provider, "style": background}
        if brief_id:
            video_body["brief_id"] = brief_id
        raw_video_result = _post_json("/finance/ai-video", video_body, FINANCE_VIDEO_TIMEOUT)
        video_result = raw_video_result.get("result", raw_video_result)
        video_id = video_result.get("db_video_id") or video_result.get("video_id")
        video_url = video_result.get("video_url", "")
        steps.append({
            "step": "video_generate",
            "status": "ok" if video_id else "error",
            "video_id": video_id,
            "video_url": video_url,
            "provider": provider,
            "result": video_result,
        })
        logger.info(f"Step 3 done: video_id={video_id} url={video_url}")
    except Exception as e:
        steps.append({"step": "video_generate", "status": "error", "error": str(e)})
        logger.error(f"Step 3 failed: {e}")
        return {
            "success": False,
            "pipeline": "viral_pipeline",
            "steps": steps,
            "error": f"Video generation failed: {e}",
        }

    if not video_id:
        return {
            "success": False,
            "pipeline": "viral_pipeline",
            "steps": steps,
            "error": "Video generated but no video_id returned — check provider logs",
        }

    # ── Step 4: Publish (AiToEarn-first)
    logger.info(f"Step 4: Publishing video_id={video_id} profile={profile}...")
    try:
        stage_result = _run_aitoearn_stage(
            "publish",
            {
                "video_id": video_id,
                "video_url": video_url,
                "profile": profile,
                "channels": body.get("channels", ["tiktok", "youtube_shorts", "instagram_reels"]),
                "selected_accounts": body.get("selected_accounts"),
                "account_ids": body.get("account_ids"),
                "title": body.get("title", "Viral content update"),
                "desc": body.get("desc", "Automated viral content generated by Hermes."),
                "caption": body.get("caption"),
                "topics": body.get("topics"),
                "hashtags": body.get("hashtags"),
                "cover_url": body.get("cover_url") or body.get("coverUrl"),
                "idempotency_key": body.get("idempotency_key", f"viral-{video_id}-publish"),
            },
            fallback_path="/aitoearn/stage/publish",
        )
        dist_data = stage_result.get("result", {})
        succeeded = dist_data.get("succeeded", dist_data.get("published_count", 0))
        failed_dist = dist_data.get("failed", dist_data.get("failed_count", 0))
        steps.append({
            "step": "publish",
            "status": "ok",
            "succeeded": succeeded,
            "failed": failed_dist,
            "execution_path": stage_result.get("execution_path"),
            "result": dist_data,
        })
        logger.info(f"Step 4 done: {succeeded} platforms succeeded, {failed_dist} failed")
    except Exception as e:
        steps.append({"step": "publish", "status": "error", "error": str(e)})
        logger.error(f"Step 4 failed: {e}")

    # ── Step 5: Claude health-check
    logger.info("Step 5: Claude pipeline health check...")
    try:
        snapshot = collect_status_snapshot(limit=5)
        pipeline_context = {
            **snapshot,
            "pipeline_steps": steps,
            "pipeline_objective": "Verify viral video pipeline completed successfully.",
        }
        diagnosis = _claude_diagnose(
            pipeline_context,
            "Check that trends were found, brief generated, video generated and distributed. Report any failures. Be concise.",
        )
        steps.append({"step": "hermes_healthcheck", "status": "ok", "diagnosis": diagnosis})
        logger.info(f"Step 5 done: severity={diagnosis.get('severity')} summary={diagnosis.get('summary', '')[:80]}")
    except Exception as e:
        steps.append({"step": "hermes_healthcheck", "status": "error", "error": str(e)})
        logger.warning(f"Step 5 failed (non-fatal): {e}")

    # ── Summary
    ok_steps = [s for s in steps if s.get("status") == "ok"]
    err_steps = [s for s in steps if s.get("status") == "error"]
    final_diagnosis = next(
        (s.get("diagnosis") for s in steps if s.get("step") == "hermes_healthcheck"),
        None,
    )

    return {
        "success": len(err_steps) == 0 or video_id is not None,
        "pipeline": "viral_pipeline",
        "video_id": video_id,
        "video_url": video_url if "video_url" in locals() else None,
        "steps_passed": len(ok_steps),
        "steps_failed": len(err_steps),
        "steps": steps,
        "hermes_summary": final_diagnosis.get("summary") if final_diagnosis else None,
        "hermes_severity": final_diagnosis.get("severity") if final_diagnosis else None,
        "message": (
            f"Pipeline complete: video #{video_id} generated via {provider} "
            f"and published to {steps[3].get('succeeded', '?')} platforms."
            if video_id else "Pipeline completed with errors."
        ),
    }


def _extract_first_url(text: str) -> str | None:
    m = re.search(r"https?://[^\s]+", text or "", flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(0).rstrip(">,.)")


def _objective_without_urls(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", " ", text or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _claude_json_call(prompt: str, *, max_tokens: int = 1800, temperature: float = 0.2) -> dict[str, Any]:
    if not HERMES_USE_CLAUDE:
        return {"ok": False, "error": "HERMES_USE_CLAUDE is disabled"}
    if not ANTHROPIC_API_KEY:
        return {"ok": False, "error": "ANTHROPIC_API_KEY not set"}

    try:
        client = _anthropic_client()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"invalid JSON from model: {e}", "raw": raw[:1200]}
        parsed["ok"] = True
        return parsed
    except Exception as e:
        logger.warning(f"Claude JSON call failed: {e}")
        return {"ok": False, "error": str(e)}


def _heuristic_discovery_plan(objective: str) -> dict[str, Any]:
    text = _objective_without_urls(objective).lower()
    hashtags = [h.lstrip("#") for h in re.findall(r"#([A-Za-z0-9_]{2,40})", objective or "")]
    channel_id = source_youtube_assets.extract_channel_id(objective or "")

    stop = {
        "i", "want", "to", "post", "this", "on", "my", "all", "of", "platforms", "platform",
        "video", "videos", "short", "shorts", "tiktok", "youtube", "instagram", "facebook",
        "threads", "pinterest", "find", "get", "upload", "publish", "using", "with", "from",
        "that", "are", "about", "please", "the", "a", "an", "and", "or", "for", "in",
    }
    words = [w for w in re.findall(r"[a-z0-9_]{3,}", text) if w not in stop]
    query_bits = hashtags[:3] or words[:6]
    query = " ".join(query_bits).strip() or text[:80] or "viral shorts"

    return {
        "content_summary": _objective_without_urls(objective)[:500],
        "search_queries": [f"{query} shorts", query],
        "channel_id": channel_id,
        "must_include": query_bits[:8],
        "must_exclude": ["music only", "lyrics only", "trailer only"],
        "language": None,
        "prefer_recent": True,
        "min_match_score": DISCOVER_MIN_SCORE,
        "mode": "heuristic",
    }


def _parse_discovery_plan(objective: str) -> dict[str, Any]:
    cleaned = _objective_without_urls(objective)
    if not cleaned:
        return _heuristic_discovery_plan(objective)

    channel_id = source_youtube_assets.extract_channel_id(objective)
    prompt = f"""
You are Hermes, a content sourcing planner.
Convert the user's posting request into a YouTube discovery plan.

User request:
{cleaned}

Return ONLY valid JSON:
{{
  "content_summary": "one sentence of what content they want",
  "search_queries": ["query1", "query2"],
  "channel_id": "UC... or null",
  "must_include": ["keyword", "theme"],
  "must_exclude": ["keyword"],
  "language": "en|vi|null",
  "prefer_recent": true,
  "min_match_score": 0.65
}}

Rules:
- Provide 1-3 high-signal YouTube search queries (short-form clips).
- must_include should reflect required themes from the user request.
- must_exclude should block clearly off-topic content types.
- If user gave a channel URL, set channel_id when possible.
- Do not include platform names (tiktok/youtube) in search queries.
"""
    parsed = _claude_json_call(prompt, max_tokens=900)
    if not parsed.get("ok"):
        plan = _heuristic_discovery_plan(objective)
        plan["planner_error"] = parsed.get("error")
        return plan

    queries = parsed.get("search_queries") or []
    if not isinstance(queries, list):
        queries = [str(queries)]
    queries = [str(q).strip() for q in queries if str(q).strip()][:3]
    if not queries:
        queries = _heuristic_discovery_plan(objective).get("search_queries", [])

    must_include = parsed.get("must_include") or []
    if not isinstance(must_include, list):
        must_include = [str(must_include)]
    must_include = [str(x).strip().lower() for x in must_include if str(x).strip()]

    must_exclude = parsed.get("must_exclude") or []
    if not isinstance(must_exclude, list):
        must_exclude = [str(must_exclude)]
    must_exclude = [str(x).strip().lower() for x in must_exclude if str(x).strip()]

    min_score = parsed.get("min_match_score", DISCOVER_MIN_SCORE)
    try:
        min_score = float(min_score)
    except (TypeError, ValueError):
        min_score = DISCOVER_MIN_SCORE

    return {
        "content_summary": str(parsed.get("content_summary") or cleaned)[:500],
        "search_queries": queries,
        "channel_id": parsed.get("channel_id") or channel_id,
        "must_include": must_include,
        "must_exclude": must_exclude,
        "language": parsed.get("language"),
        "prefer_recent": bool(parsed.get("prefer_recent", True)),
        "min_match_score": min(1.0, max(0.0, min_score)),
        "mode": "claude",
    }


def _heuristic_verify_candidates(
    objective: str,
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    must_include = [k.lower() for k in plan.get("must_include") or [] if k]
    must_exclude = [k.lower() for k in plan.get("must_exclude") or [] if k]
    min_score = float(plan.get("min_match_score") or DISCOVER_MIN_SCORE)
    ranked: list[dict[str, Any]] = []

    for cand in candidates:
        blob = " ".join(
            [
                str(cand.get("title") or ""),
                str(cand.get("description") or ""),
                str(cand.get("channel_title") or ""),
            ]
        ).lower()
        if must_exclude and any(x in blob for x in must_exclude):
            score = 0.0
            reason = "Excluded by must_exclude keyword match"
        elif not must_include:
            score = 0.7
            reason = "No strict include terms; default pass"
        else:
            hits = sum(1 for kw in must_include if kw in blob)
            score = hits / max(1, len(must_include))
            reason = f"Matched {hits}/{len(must_include)} include terms"

        ranked.append({**cand, "match_score": round(score, 3), "match_reason": reason})

    ranked.sort(key=lambda x: (x.get("match_score", 0), x.get("views", 0)), reverse=True)
    selected = ranked[0] if ranked and ranked[0].get("match_score", 0) >= min_score else None
    return {
        "ok": True,
        "mode": "heuristic",
        "ranked": ranked[:8],
        "selected": selected,
        "min_match_score": min_score,
        "verified": bool(selected),
    }


def _verify_video_candidates(
    objective: str,
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not candidates:
        return {"ok": False, "error": "no_candidates", "verified": False}

    min_score = float(plan.get("min_match_score") or DISCOVER_MIN_SCORE)
    compact = [
        {
            "video_id": c.get("video_id"),
            "title": c.get("title"),
            "description": (c.get("description") or "")[:500],
            "channel_title": c.get("channel_title"),
            "views": c.get("views"),
            "duration_secs": c.get("duration_secs"),
            "url": c.get("url"),
        }
        for c in candidates[:DISCOVER_MAX_CANDIDATES]
    ]
    prompt = f"""
You are Hermes content QA.
Decide which YouTube short best matches the user's requested content.

User request:
{_objective_without_urls(objective)}

Discovery plan:
{json.dumps(plan, ensure_ascii=False)}

Candidates JSON:
{json.dumps(compact, ensure_ascii=False)}

Return ONLY valid JSON:
{{
  "selected_video_id": "id or null",
  "min_match_score": {min_score},
  "ranked": [
    {{
      "video_id": "...",
      "match_score": 0.0,
      "match_reason": "why it matches or not"
    }}
  ]
}}

Rules:
- Score each candidate from 0.0 to 1.0 for topical fit.
- Reject candidates that are clearly off-topic even if popular.
- selected_video_id must be null if no candidate reaches min_match_score.
"""
    parsed = _claude_json_call(prompt, max_tokens=1600)
    if not parsed.get("ok"):
        verified = _heuristic_verify_candidates(objective, plan, candidates)
        verified["verifier_error"] = parsed.get("error")
        return verified

    ranked_raw = parsed.get("ranked") or []
    score_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(ranked_raw, list):
        for row in ranked_raw:
            if not isinstance(row, dict):
                continue
            vid = str(row.get("video_id") or "").strip()
            if not vid:
                continue
            try:
                score = float(row.get("match_score", 0))
            except (TypeError, ValueError):
                score = 0.0
            score_by_id[vid] = {
                "match_score": max(0.0, min(1.0, score)),
                "match_reason": str(row.get("match_reason") or "").strip(),
            }

    ranked: list[dict[str, Any]] = []
    for cand in candidates:
        vid = str(cand.get("video_id") or "")
        scored = score_by_id.get(vid, {})
        ranked.append(
            {
                **cand,
                "match_score": scored.get("match_score", 0.0),
                "match_reason": scored.get("match_reason", "Not scored by verifier"),
            }
        )
    ranked.sort(key=lambda x: (x.get("match_score", 0), x.get("views", 0)), reverse=True)

    selected_id = str(parsed.get("selected_video_id") or "").strip()
    selected = next((c for c in ranked if c.get("video_id") == selected_id), None)
    if not selected and ranked and ranked[0].get("match_score", 0) >= min_score:
        selected = ranked[0]
    if selected and selected.get("match_score", 0) < min_score:
        selected = None

    return {
        "ok": True,
        "mode": "claude",
        "ranked": ranked[:8],
        "selected": selected,
        "min_match_score": min_score,
        "verified": bool(selected),
    }


def _video_usage_check(
    *,
    url: str | None = None,
    video_id: str | None = None,
    used_ids: set[str] | None = None,
) -> dict[str, Any]:
    from scripts.youtube_download_ingest import is_youtube_video_already_used

    return is_youtube_video_already_used(
        url=url,
        video_id=video_id,
        use_chroma=False,
        used_ids=used_ids,
    )


def _candidate_is_blocked(
    cand: dict[str, Any],
    exclude_ids: set[str],
    used_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    vid = str(cand.get("video_id") or "").strip()
    if not vid:
        return None
    if vid in exclude_ids:
        return {"is_duplicate": True, "youtube_id": vid, "reasons": ["exclude_list"]}
    if used_ids is not None and vid in used_ids:
        return {"is_duplicate": True, "youtube_id": vid, "reasons": ["cached_used_id_set"]}
    return _video_usage_check(url=str(cand.get("url") or ""), video_id=vid, used_ids=used_ids)


def _filter_fresh_candidates(
    candidates: list[dict[str, Any]],
    exclude_ids: set[str],
    used_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fresh: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for cand in candidates:
        usage = _candidate_is_blocked(cand, exclude_ids, used_ids=used_ids)
        if usage and usage.get("is_duplicate"):
            skipped.append({**cand, "duplicate_check": usage})
            continue
        fresh.append(cand)
    return fresh, skipped


def _pick_unused_from_ranked(
    ranked: list[dict[str, Any]],
    *,
    min_score: float,
    exclude_ids: set[str],
    used_ids: set[str] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    skipped: list[dict[str, Any]] = []
    for cand in ranked:
        usage = _candidate_is_blocked(cand, exclude_ids, used_ids=used_ids)
        if usage and usage.get("is_duplicate"):
            skipped.append({**cand, "duplicate_check": usage})
            continue
        if float(cand.get("match_score") or 0) < min_score:
            continue
        return cand, skipped
    return None, skipped


def discover_video_from_objective(objective: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Discover a YouTube short from natural language, with content-fit verification.
    """
    body = body or {}
    objective = (objective or "").strip()
    if not objective:
        return {"success": False, "error": "objective is required for discovery"}

    if not os.environ.get("YOUTUBE_API_KEY"):
        return {
            "success": False,
            "error": "YOUTUBE_API_KEY not set — required for autonomous video discovery",
        }

    plan = _parse_discovery_plan(objective)
    max_candidates = int(body.get("max_candidates") or DISCOVER_MAX_CANDIDATES)
    min_score = float(plan.get("min_match_score") or DISCOVER_MIN_SCORE)
    channel_id = body.get("channel_id") or plan.get("channel_id")
    if isinstance(channel_id, str):
        channel_id = channel_id.strip() or None

    exclude_ids = {
        str(x).strip()
        for x in (body.get("exclude_youtube_ids") or [])
        if str(x).strip()
    }
    from scripts.youtube_download_ingest import load_used_youtube_id_set

    used_ids = load_used_youtube_id_set()

    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    queries = list(plan.get("search_queries") or [])
    if channel_id and not queries:
        queries = [""]

    search_limit = max_candidates
    for query in queries[:3]:
        found = source_youtube_assets.discover_short_videos(
            query,
            channel_id=channel_id if channel_id else None,
            max_results=search_limit + 5,
        )
        for cand in found:
            vid = str(cand.get("video_id") or "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            candidates.append(cand)
        if len(candidates) >= search_limit + 5:
            break
        search_limit += 5

    fresh_candidates, skipped_duplicates = _filter_fresh_candidates(
        candidates, exclude_ids, used_ids=used_ids
    )
    if not fresh_candidates and candidates:
        return {
            "success": False,
            "error": "all_candidates_already_used",
            "message": "All discovered videos were already downloaded or published. Try a different topic.",
            "discovery_plan": plan,
            "candidates_checked": len(candidates),
            "skipped_duplicates": skipped_duplicates[:10],
        }

    verification = _verify_video_candidates(objective, plan, fresh_candidates[:max_candidates])
    ranked = list(verification.get("ranked") or [])
    if not ranked and verification.get("selected"):
        ranked = [verification["selected"]]

    selected, skipped_used = _pick_unused_from_ranked(
        ranked,
        min_score=min_score,
        exclude_ids=exclude_ids,
        used_ids=used_ids,
    )
    if not selected:
        return {
            "success": False,
            "error": "no_verified_match",
            "message": "No new video met your content criteria (or all matches were already used).",
            "discovery_plan": plan,
            "candidates_checked": len(candidates),
            "fresh_candidates": len(fresh_candidates),
            "skipped_duplicates": (skipped_duplicates + skipped_used)[:12],
            "verification": verification,
        }

    return {
        "success": True,
        "video_url": selected.get("url"),
        "video_id": selected.get("video_id"),
        "title": selected.get("title"),
        "description": selected.get("description"),
        "match_score": selected.get("match_score"),
        "match_reason": selected.get("match_reason"),
        "discovery_plan": plan,
        "candidates_checked": len(candidates),
        "fresh_candidates": len(fresh_candidates),
        "skipped_duplicates": (skipped_duplicates + skipped_used)[:12],
        "verification": verification,
    }


def run_discover_publish_pipeline(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Natural-language discover -> verify -> download/ingest -> publish."""
    body = dict(body or {})
    objective = str(body.get("objective") or body.get("prompt") or "").strip()
    if not objective:
        return {"success": False, "pipeline": "discover_publish_pipeline", "error": "objective is required"}

    run_id = str(uuid4())
    discovery = discover_video_from_objective(objective, body)
    if not discovery.get("success"):
        return {
            "success": False,
            "pipeline": "discover_publish_pipeline",
            "run_id": run_id,
            "steps": [{"step": "discover_video", "status": "error", "result": discovery}],
            "error": discovery.get("error", "discovery_failed"),
            "message": discovery.get("message"),
        }

    publish_body = {
        **body,
        "source_url": discovery.get("video_url"),
        "objective": objective,
        "discovered_video": discovery,
        "discover": False,
    }
    result = run_link_publish_pipeline(publish_body)
    steps = [{"step": "discover_video", "status": "ok", "result": discovery}]
    if isinstance(result.get("steps"), list):
        steps.extend(result["steps"])
    result["pipeline"] = "discover_publish_pipeline"
    result["run_id"] = run_id
    result["steps"] = steps
    result["discovered_video"] = discovery
    return result


def run_link_publish_pipeline(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Link/Channel -> source/download -> publish.
    If no URL is provided, discovers a matching YouTube short from `objective`.

    Body:
      source_url | link | video_url  : input URL (video or channel)
      objective                    : natural-language content request (used for discovery)
      discover                     : force discovery even if URL present (default False)
      channels                     : target platforms
      selected_accounts/account_ids: optional targeting
      title/desc/caption/hashtags/topics: publish metadata
    """
    body = body or {}
    run_id = str(uuid4())
    steps: list[dict[str, Any]] = []
    objective = str(body.get("objective") or body.get("prompt") or "").strip()
    source_url = (
        str(body.get("source_url") or body.get("link") or body.get("video_url") or "").strip()
        or _extract_first_url(objective)
    )
    force_discover = bool(body.get("discover"))
    if (not source_url or force_discover) and objective and body.get("discover", True) is not False:
        discovery = discover_video_from_objective(objective, body)
        steps.append(
            {
                "step": "discover_video",
                "status": "ok" if discovery.get("success") else "error",
                "result": discovery,
            }
        )
        if not discovery.get("success"):
            return {
                "success": False,
                "pipeline": "link_publish_pipeline",
                "run_id": run_id,
                "error": discovery.get("error", "discovery_failed"),
                "message": discovery.get("message"),
                "steps": steps,
            }
        source_url = str(discovery.get("video_url") or "")
        body = {**body, "source_url": source_url, "discovered_video": discovery}
        logger.info(
            f"[link_publish:{run_id}] discovered video_id={discovery.get('video_id')} "
            f"score={discovery.get('match_score')} reason={discovery.get('match_reason')}"
        )

    if not source_url:
        return {
            "success": False,
            "pipeline": "link_publish_pipeline",
            "run_id": run_id,
            "error": "source_url or objective is required (video link, channel link, or content description)",
            "steps": steps,
        }

    src_lower = source_url.lower()
    is_youtube_link = ("youtube.com" in src_lower) or ("youtu.be" in src_lower)
    is_channel_like = (
        "/channel/" in src_lower
        or "youtube.com/@" in src_lower
        or "youtube.com/c/" in src_lower
        or "youtube.com/user/" in src_lower
    )

    resolved_video_url = source_url
    source_info: dict[str, Any] = {"source_url": source_url, "is_channel_like": is_channel_like}
    logger.info(
        f"[link_publish:{run_id}] start source_url={source_url} "
        f"channels={body.get('channels')} selected_accounts={'yes' if body.get('selected_accounts') else 'no'}"
    )

    # Step 1: If channel provided, pick a recent video first.
    if is_channel_like:
        try:
            channel_id = source_youtube_assets.extract_channel_id(source_url)
            raw_items: list[dict[str, Any]] = []
            if channel_id:
                raw_items = source_youtube_assets.search_youtube_channel(channel_id, max_results=5)
            if not raw_items:
                # Fallback for @handle/custom channel URLs.
                raw_items = source_youtube_assets.search_youtube(source_url, max_results=5)

            picked: dict[str, Any] | None = None
            skipped_channel_dupes: list[dict[str, Any]] = []
            from scripts.youtube_download_ingest import load_used_youtube_id_set

            channel_used_ids = load_used_youtube_id_set()
            for item in raw_items:
                vid = (item.get("id") or {}).get("videoId")
                if not vid:
                    continue
                usage = _video_usage_check(video_id=str(vid), used_ids=channel_used_ids)
                if usage.get("is_duplicate") and not body.get("allow_repost"):
                    skipped_channel_dupes.append(
                        {
                            "video_id": vid,
                            "title": (item.get("snippet") or {}).get("title"),
                            "duplicate_check": usage,
                        }
                    )
                    continue
                picked = item
                break
            if not picked:
                if skipped_channel_dupes:
                    raise RuntimeError("no_new_video_found_from_channel_all_already_used")
                raise RuntimeError("no_video_found_from_channel")

            vid = (picked.get("id") or {}).get("videoId")
            resolved_video_url = f"https://www.youtube.com/watch?v={vid}"
            source_info.update(
                {
                    "channel_id": channel_id,
                    "picked_video_id": vid,
                    "picked_title": (picked.get("snippet") or {}).get("title"),
                    "picked_video_url": resolved_video_url,
                    "skipped_duplicates": skipped_channel_dupes,
                }
            )
            steps.append({"step": "source_video_from_channel", "status": "ok", "result": source_info})
            logger.info(
                f"[link_publish:{run_id}] sourced channel video "
                f"channel_id={source_info.get('channel_id')} picked_video_id={source_info.get('picked_video_id')}"
            )
        except Exception as e:
            steps.append({"step": "source_video_from_channel", "status": "error", "error": str(e)})
            logger.error(f"[link_publish:{run_id}] source_video_from_channel failed: {e}")
            return {
                "success": False,
                "pipeline": "link_publish_pipeline",
                "run_id": run_id,
                "steps": steps,
                "error": f"Failed to source video from channel: {e}",
            }
    else:
        steps.append({"step": "resolve_source_link", "status": "ok", "result": source_info})
        logger.info(f"[link_publish:{run_id}] resolved direct source link")

    # Step 2: Best-effort ingest for metadata/library tracking (especially YouTube links).
    ingest_result: dict[str, Any] = {}
    if is_youtube_link or is_channel_like:
        from scripts.youtube_download_ingest import load_used_youtube_id_set

        used_ids = load_used_youtube_id_set()
        if not body.get("allow_repost"):
            usage = _video_usage_check(url=resolved_video_url, used_ids=used_ids)
            if usage.get("is_duplicate"):
                alternate = None
                discovered = body.get("discovered_video") or {}
                ranked = (discovered.get("verification") or {}).get("ranked") or []
                min_score = float(
                    (discovered.get("discovery_plan") or {}).get("min_match_score") or DISCOVER_MIN_SCORE
                )
                skip_vid = str(usage.get("youtube_id") or "")
                alternate, _ = _pick_unused_from_ranked(
                    ranked,
                    min_score=min_score,
                    exclude_ids={skip_vid} if skip_vid else set(),
                    used_ids=used_ids,
                )
                if alternate:
                    resolved_video_url = str(alternate.get("url") or resolved_video_url)
                    steps.append(
                        {
                            "step": "duplicate_avoidance",
                            "status": "ok",
                            "skipped_video_id": usage.get("youtube_id"),
                            "picked_video_id": alternate.get("video_id"),
                            "result": alternate,
                        }
                    )
                    logger.info(
                        f"[link_publish:{run_id}] skipped duplicate {usage.get('youtube_id')} "
                        f"-> alternate {alternate.get('video_id')}"
                    )
                else:
                    steps.append(
                        {
                            "step": "duplicate_check",
                            "status": "error",
                            "result": usage,
                        }
                    )
                    return {
                        "success": False,
                        "pipeline": "link_publish_pipeline",
                        "run_id": run_id,
                        "source_url": source_url,
                        "resolved_video_url": resolved_video_url,
                        "steps": steps,
                        "error": "video_already_used",
                        "message": "This video was already downloaded or published. Discovery found no unused alternative.",
                    }

        try:
            ingest_result = _post(
                "/youtube/download-ingest",
                {
                    "url": resolved_video_url,
                    "caption": body.get("caption"),
                    "create_video": body.get("create_video", True),
                    "reject_if_used": not bool(body.get("allow_repost")),
                },
                timeout=max(REQUEST_TIMEOUT, 300),
            ).get("result", {})
            steps.append(
                {
                    "step": "download_ingest",
                    "status": "ok" if ingest_result.get("success") else "error",
                    "result": ingest_result,
                }
            )
            logger.info(
                f"[link_publish:{run_id}] download_ingest success={ingest_result.get('success')} "
                f"video_id={ingest_result.get('video_id')} local_path={ingest_result.get('local_path')}"
            )
            if not ingest_result.get("success"):
                err = ingest_result.get("error", "unknown")
                if err == "video_already_used" and not body.get("allow_repost"):
                    discovered = body.get("discovered_video") or {}
                    ranked = (discovered.get("verification") or {}).get("ranked") or []
                    min_score = float(
                        (discovered.get("discovery_plan") or {}).get("min_match_score") or DISCOVER_MIN_SCORE
                    )
                    skip_id = str(ingest_result.get("youtube_id") or "")
                    alternate, _ = _pick_unused_from_ranked(
                        ranked,
                        min_score=min_score,
                        exclude_ids={skip_id} if skip_id else set(),
                        used_ids=used_ids,
                    )
                    if alternate:
                        resolved_video_url = str(alternate.get("url") or resolved_video_url)
                        steps.append(
                            {
                                "step": "duplicate_avoidance_retry",
                                "status": "ok",
                                "skipped_video_id": skip_id,
                                "picked_video_id": alternate.get("video_id"),
                            }
                        )
                        ingest_result = _post(
                            "/youtube/download-ingest",
                            {
                                "url": resolved_video_url,
                                "caption": body.get("caption"),
                                "create_video": body.get("create_video", True),
                                "reject_if_used": True,
                            },
                            timeout=max(REQUEST_TIMEOUT, 300),
                        ).get("result", {})
                        steps.append(
                            {
                                "step": "download_ingest",
                                "status": "ok" if ingest_result.get("success") else "error",
                                "result": ingest_result,
                            }
                        )
                if not ingest_result.get("success"):
                    return {
                        "success": False,
                        "pipeline": "link_publish_pipeline",
                        "run_id": run_id,
                        "source_url": source_url,
                        "resolved_video_url": resolved_video_url,
                        "steps": steps,
                        "error": f"source_ingest_failed: {ingest_result.get('error', 'unknown')}",
                    }
        except Exception as e:
            steps.append({"step": "download_ingest", "status": "error", "error": str(e)})
            logger.warning(f"[link_publish:{run_id}] download_ingest failed (non-fatal): {e}")
            return {
                "success": False,
                "pipeline": "link_publish_pipeline",
                "run_id": run_id,
                "source_url": source_url,
                "resolved_video_url": resolved_video_url,
                "steps": steps,
                "error": f"source_ingest_failed: {e}",
            }

    # Step 3: Ensure we publish a stable, publicly reachable media URL.
    media_input = (
        body.get("video_path")
        or ingest_result.get("local_path")
        or body.get("video_url_override")
        or ingest_result.get("public_video_url")
        or resolved_video_url
    )
    fallback_public_url = (
        body.get("video_url_override")
        or ingest_result.get("public_video_url")
        or resolved_video_url
    )
    hosted_media = media_host.ensure_public_url(
        str(media_input or ""),
        fallback_public_url=str(fallback_public_url or ""),
    )
    if not hosted_media.get("ok"):
        steps.append({"step": "host_media", "status": "error", "result": hosted_media})
        logger.error(
            f"[link_publish:{run_id}] host_media failed local_path={ingest_result.get('local_path')} "
            f"fallback_url={fallback_public_url} error={hosted_media.get('error')}"
        )
        return {
            "success": False,
            "pipeline": "link_publish_pipeline",
            "run_id": run_id,
            "source_url": source_url,
            "resolved_video_url": resolved_video_url,
            "steps": steps,
            "error": f"media_hosting_failed: {hosted_media.get('error')}",
        }
    publish_video_url = hosted_media.get("public_url")
    steps.append(
        {
            "step": "host_media",
            "status": "ok",
            "result": {
                "provider": hosted_media.get("provider"),
                "uploaded": hosted_media.get("uploaded"),
                "public_url": publish_video_url,
            },
        }
    )

    # Step 4: Publish via AiToEarn-first route.
    publish_payload = {
        "video_url": publish_video_url,
        "profile": body.get("profile", "minimal"),
        "channels": body.get("channels", ["tiktok", "youtube", "instagram", "facebook", "threads", "pinterest"]),
        "selected_accounts": body.get("selected_accounts"),
        "account_ids": body.get("account_ids"),
        "title": body.get("title") or ingest_result.get("title") or "Automated post from source link",
        "desc": body.get("desc") or body.get("description") or ingest_result.get("description") or ingest_result.get("caption") or "Automated publish via Hermes link pipeline",
        "caption": body.get("caption") or ingest_result.get("caption"),
        "topics": body.get("topics"),
        "hashtags": body.get("hashtags") if body.get("hashtags") is not None else ingest_result.get("hashtags"),
        "cover_url": body.get("cover_url") or body.get("coverUrl") or ingest_result.get("cover_url"),
        "idempotency_key": body.get("idempotency_key", f"link-publish-{uuid4().hex[:12]}"),
    }
    logger.info(
        f"[link_publish:{run_id}] publish payload "
        f"title={publish_payload.get('title')!r} "
        f"channels={publish_payload.get('channels')} "
        f"video_url={publish_payload.get('video_url')}"
    )
    try:
        stage_result = _run_aitoearn_stage(
            "publish",
            publish_payload,
            fallback_path="/aitoearn/stage/publish",
            timeout=max(REQUEST_TIMEOUT, 180),
        )
        dist_data = stage_result.get("result", {})
        succeeded = dist_data.get("succeeded", dist_data.get("published_count", 0))
        failed = dist_data.get("failed", dist_data.get("failed_count", 0))
        confirmed = dist_data.get("confirmed_count", 0)
        unverified = dist_data.get("unverified_count", 0)
        publish_step: dict[str, Any] = {
            "step": "publish",
            "status": "ok",
            "succeeded": succeeded,
            "failed": failed,
            "confirmed": confirmed,
            "unverified": unverified,
            "execution_path": stage_result.get("execution_path"),
            "result": dist_data,
        }
        steps.append(publish_step)

        # TikTok-specific fallback:
        # if AiToEarn publish failed on TikTok but we have a local video_id from ingest,
        # attempt legacy uploader v1 as recovery path.
        result_rows = dist_data.get("results") if isinstance(dist_data, dict) else None
        tiktok_fail_rows: list[dict[str, Any]] = []
        if isinstance(result_rows, list):
            tiktok_fail_rows = [
                row
                for row in result_rows
                if isinstance(row, dict)
                and row.get("platform") == "tiktok"
                and not row.get("success")
            ]
        if tiktok_fail_rows:
            fallback_video_id = ingest_result.get("video_id") or body.get("video_id")
            if fallback_video_id:
                try:
                    fallback_resp = _post(
                        "/upload-tiktok",
                        {"video_id": int(fallback_video_id)},
                        timeout=max(REQUEST_TIMEOUT, 240),
                    )
                    fallback_result = fallback_resp.get("result", fallback_resp)
                    fallback_success = bool(fallback_result.get("success"))
                    steps.append(
                        {
                            "step": "tiktok_fallback_local",
                            "status": "ok" if fallback_success else "error",
                            "video_id": int(fallback_video_id),
                            "result": fallback_result,
                            "reason": "aitoearn_tiktok_failed",
                        }
                    )
                    if fallback_success:
                        publish_step["succeeded"] = int(publish_step.get("succeeded", 0)) + 1
                        publish_step["failed"] = max(0, int(publish_step.get("failed", 0)) - 1)
                        publish_step["confirmed"] = int(publish_step.get("confirmed", 0)) + 1
                        if isinstance(dist_data, dict):
                            channels_obj = dist_data.get("channels")
                            if isinstance(channels_obj, dict):
                                tiktok_stats = channels_obj.setdefault("tiktok", {"success": 0, "failed": 0})
                                if isinstance(tiktok_stats, dict):
                                    tiktok_stats["success"] = int(tiktok_stats.get("success", 0)) + 1
                                    tiktok_stats["failed"] = max(0, int(tiktok_stats.get("failed", 0)) - 1)
                            dist_data["published_count"] = int(publish_step["succeeded"])
                            dist_data["failed_count"] = int(publish_step["failed"])
                            dist_data["confirmed_count"] = int(publish_step["confirmed"])
                            results_obj = dist_data.get("results")
                            if isinstance(results_obj, list):
                                results_obj.append(
                                    {
                                        "platform": "tiktok",
                                        "success": True,
                                        "verification": "local_tiktok_fallback",
                                        "video_id": int(fallback_video_id),
                                        "tool": "upload_tiktok_v1",
                                    }
                                )
                            fallbacks = dist_data.setdefault("fallbacks", [])
                            if isinstance(fallbacks, list):
                                fallbacks.append(
                                    {
                                        "platform": "tiktok",
                                        "uploader": "local_tiktok_v1",
                                        "video_id": int(fallback_video_id),
                                        "success": True,
                                    }
                                )
                    else:
                        logger.warning(
                            f"[link_publish:{run_id}] tiktok fallback uploader failed for video_id={fallback_video_id}: "
                            f"{fallback_result}"
                        )
                except Exception as fb_exc:
                    steps.append(
                        {
                            "step": "tiktok_fallback_local",
                            "status": "error",
                            "video_id": fallback_video_id,
                            "error": str(fb_exc),
                            "reason": "aitoearn_tiktok_failed",
                        }
                    )
                    logger.warning(
                        f"[link_publish:{run_id}] tiktok fallback uploader exception for video_id={fallback_video_id}: {fb_exc}"
                    )
            else:
                steps.append(
                    {
                        "step": "tiktok_fallback_local",
                        "status": "error",
                        "error": "missing_video_id_for_local_fallback",
                        "reason": "aitoearn_tiktok_failed",
                    }
                )
                logger.warning(
                    f"[link_publish:{run_id}] tiktok fallback skipped: no video_id available from ingest/body"
                )
        logger.info(
            f"[link_publish:{run_id}] publish done execution_path={stage_result.get('execution_path')} "
            f"succeeded={publish_step.get('succeeded')} failed={publish_step.get('failed')} "
            f"confirmed={publish_step.get('confirmed')} unverified={publish_step.get('unverified')}"
        )
        if publish_step.get("unverified"):
            logger.warning(
                f"[link_publish:{run_id}] publish accepted but unverified for {publish_step.get('unverified')} account(s); "
                "set AITOEARN_UNVERIFIED_AS_FAILURE=1 to mark unverified as failed"
            )
    except Exception as e:
        steps.append({"step": "publish", "status": "error", "error": str(e)})
        logger.error(f"[link_publish:{run_id}] publish failed: {e}")
        return {
            "success": False,
            "pipeline": "link_publish_pipeline",
            "run_id": run_id,
            "source_url": source_url,
            "resolved_video_url": resolved_video_url,
            "steps": steps,
            "error": f"publish_failed: {e}",
        }

    ok_steps = [s for s in steps if s.get("status") == "ok"]
    err_steps = [s for s in steps if s.get("status") == "error"]
    publish_step = next((s for s in steps if s.get("step") == "publish"), {})
    if publish_step.get("status") == "ok" and resolved_video_url and not body.get("allow_repost"):
        if os.environ.get("HERMES_REGISTER_CHROMA", "").strip().lower() in {"1", "true", "yes"}:
            try:
                from scripts.memory_manager import register_content

                register_content(
                    url=resolved_video_url,
                    metadata={"pipeline": "link_publish_pipeline", "run_id": run_id},
                )
            except Exception as reg_exc:
                logger.warning(f"[link_publish:{run_id}] register_content fingerprint failed: {reg_exc}")

    result = {
        "success": publish_step.get("status") == "ok",
        "pipeline": "link_publish_pipeline",
        "run_id": run_id,
        "source_url": source_url,
        "resolved_video_url": resolved_video_url,
        "publish_video_url": publish_payload.get("video_url"),
        "steps_passed": len(ok_steps),
        "steps_failed": len(err_steps),
        "steps": steps,
        "published_count": publish_step.get("succeeded", 0),
        "failed_count": publish_step.get("failed", 0),
        "confirmed_count": publish_step.get("confirmed", 0),
        "unverified_count": publish_step.get("unverified", 0),
        "message": (
            f"Link publish complete: {publish_step.get('succeeded', 0)} published, "
            f"{publish_step.get('failed', 0)} failed, "
            f"{publish_step.get('confirmed', 0)} confirmed, "
            f"{publish_step.get('unverified', 0)} unverified."
        ),
    }
    logger.info(
        f"[link_publish:{run_id}] complete success={result.get('success')} "
        f"published={result.get('published_count')} failed={result.get('failed_count')}"
    )
    return result



def run_learn_anime_style(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Hermes adaptive learning: scrape a competitor channel and refresh style memory.

    Prefer Hermes over QwenPaw for script-style adaptation. Hermes owns the
    playbook consumed by short-form anime-theory generation.
    """
    body = body or {}
    channel = str(body.get("channel") or body.get("url") or "@animeinsider64").strip()
    limit = int(body.get("limit") or 25)
    max_duration_s = float(body.get("max_duration_s") or body.get("max_duration") or 180)
    rebuild_only = bool(body.get("rebuild_only") or body.get("rebuildOnly"))

    shortform_root = Path(
        os.environ.get("SHORTFORM_ROOT")
        or str(Path(__file__).resolve().parents[2] / "short-form-pipeline")
    )
    if str(shortform_root) not in sys.path:
        sys.path.insert(0, str(shortform_root))

    try:
        from reddit_to_script import style_memory  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"style_memory_import_failed: {exc}",
            "hint": "Ensure short-form-pipeline is on PYTHONPATH / SHORTFORM_ROOT",
        }

    logger.info(
        "Hermes: learning anime Short style from %s (limit=%s rebuild_only=%s)",
        channel,
        limit,
        rebuild_only,
    )
    try:
        result = style_memory.train_channel(
            channel,
            limit=limit,
            max_duration_s=max_duration_s,
            scrape=not rebuild_only,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Hermes style learning failed")
        return {"success": False, "error": str(exc), "channel": channel}

    playbook = result.get("playbook") or {}
    return {
        "success": bool(result.get("ok")),
        "agent": "hermes",
        "action": "learn_anime_style",
        "channel": result.get("channel"),
        "playbook_path": result.get("playbook_path"),
        "sample_count": playbook.get("sample_count"),
        "median_words": playbook.get("median_words"),
        "avg_words": playbook.get("avg_words"),
        "avg_duration_s": playbook.get("avg_duration_s"),
        "top_hooks": playbook.get("top_hook_starters"),
        "style_brief": playbook.get("style_brief"),
    }


def run_learn_thumbnail_style(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Hermes adaptive learning: harvest competitor YouTube posters into thumbnail memory.

    Owned by shortform-thumbnail agent. Separate from script style memory.
    """
    body = body or {}
    channel = str(body.get("channel") or body.get("url") or "@animeinsider64").strip()
    limit = int(body.get("limit") or 80)
    run_vision = not bool(body.get("no_vision") or body.get("noVision"))

    shortform_root = Path(
        os.environ.get("SHORTFORM_ROOT")
        or str(Path(__file__).resolve().parents[2] / "short-form-pipeline")
    )
    if str(shortform_root) not in sys.path:
        sys.path.insert(0, str(shortform_root))

    try:
        from reddit_to_script import thumbnail_memory  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"thumbnail_memory_import_failed: {exc}",
            "hint": "Ensure short-form-pipeline is on PYTHONPATH / SHORTFORM_ROOT",
        }

    logger.info(
        "Hermes: learning thumbnail/poster style from %s (limit=%s vision=%s)",
        channel,
        limit,
        run_vision,
    )
    try:
        result = thumbnail_memory.train_thumbnails(
            channel,
            limit=limit,
            run_vision=run_vision,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Hermes thumbnail learning failed")
        return {"success": False, "error": str(exc), "channel": channel}

    playbook = result.get("playbook") or {}
    return {
        "success": bool(result.get("ok")),
        "agent": "hermes",
        "action": "learn_thumbnail_style",
        "owner_agent": "shortform-thumbnail",
        "channel": result.get("channel"),
        "playbook_path": result.get("playbook_path"),
        "thumbs_downloaded": result.get("thumbs_downloaded"),
        "sample_count": playbook.get("sample_count"),
        "median_overlay_words": playbook.get("median_overlay_words"),
        "title_shapes": playbook.get("title_shapes"),
        "style_brief": playbook.get("style_brief"),
    }


def run_learn_channel_quality(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Hermes: train ALL quality perspectives (script, edit/pacing, music, thumbnails).

    Default rebuild-only from existing scraped channel data (safe under YouTube IP bans).
    Pass scrape=true to attempt new transcripts.
    """
    body = body or {}
    channel = str(body.get("channel") or body.get("url") or "@animeinsider64").strip()
    limit = int(body.get("limit") or 80)
    max_duration_s = float(body.get("max_duration_s") or body.get("max_duration") or 180)
    scrape = bool(body.get("scrape"))
    run_vision = not bool(body.get("no_vision") or body.get("noVision"))

    shortform_root = Path(
        os.environ.get("SHORTFORM_ROOT")
        or str(Path(__file__).resolve().parents[2] / "short-form-pipeline")
    )
    if str(shortform_root) not in sys.path:
        sys.path.insert(0, str(shortform_root))

    try:
        from reddit_to_script import train_channel_quality  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"train_channel_quality_import_failed: {exc}",
            "hint": "Ensure short-form-pipeline is on PYTHONPATH / SHORTFORM_ROOT",
        }

    logger.info(
        "Hermes: channel quality train %s (scrape=%s limit=%s vision=%s)",
        channel,
        scrape,
        limit,
        run_vision,
    )
    try:
        result = train_channel_quality.train_all(
            channel,
            limit=limit,
            max_duration_s=max_duration_s,
            scrape=scrape,
            run_vision=run_vision,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Hermes channel quality training failed")
        return {"success": False, "error": str(exc), "channel": channel}

    return {
        "success": bool(result.get("ok")),
        "agent": "hermes",
        "action": "learn_channel_quality",
        **result,
    }


def main(body: dict | None = None, **kwargs) -> dict[str, Any]:
    if body is None:
        body = kwargs
    action = body.get("action", "cycle")

    if action == "status":
        return {"success": True, "snapshot": collect_status_snapshot(limit=int(body.get("failure_limit", 10)))}
    if action == "diagnose":
        snap = body.get("snapshot")
        if not isinstance(snap, dict):
            snap = collect_status_snapshot(limit=int(body.get("failure_limit", 10)))
        return {
            "success": True,
            "diagnosis": _claude_diagnose(snap, body.get("objective", "Diagnose app operations state.")),
        }
    if action in {"cycle", "monitor"}:
        return run_cycle(body)
    if action in {"full_ops", "full_ops_pipeline"}:
        return run_full_ops_pipeline(body)
    if action == "finance_pipeline":
        return run_finance_pipeline(body)
    if action == "viral_pipeline":
        return run_viral_pipeline(body)
    if action in {
        "anime_theory_pipeline",
        "anime-theory-pipeline",
        "anime_theory",
        "anime-theory",
    }:
        return run_anime_theory_pipeline(body)
    if action in {"link_publish", "source_publish", "link_publish_pipeline"}:
        return run_link_publish_pipeline(body)
    if action in {"discover_publish", "discover_publish_pipeline"}:
        return run_discover_publish_pipeline(body)
    if action in {
        "learn_anime_style",
        "learn_style",
        "train_channel",
        "anime_style",
    }:
        return run_learn_anime_style(body)
    if action in {
        "learn_thumbnail_style",
        "learn_thumbnails",
        "train_thumbnails",
        "thumbnail_style",
    }:
        return run_learn_thumbnail_style(body)
    if action in {
        "learn_channel_quality",
        "train_channel_quality",
        "channel_quality",
        "learn_all",
        "train_all",
    }:
        return run_learn_channel_quality(body)
    return {"success": False, "error": f"unknown action {action}"}



if __name__ == "__main__":
    print(json.dumps(main({"action": "cycle"}), indent=2, default=str))
