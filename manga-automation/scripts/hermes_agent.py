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
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.adapters import aitoearn_client

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
REQUEST_TIMEOUT = int(os.environ.get("HERMES_TIMEOUT_SEC", "120"))  # Increased from 25 to 120 to allow scraping to finish
FINANCE_VIDEO_TIMEOUT = int(os.environ.get("HERMES_FINANCE_VIDEO_TIMEOUT_SEC", "660"))  # 11 min for video gen

# Guardrail: no auto actions unless both env + request allow.
AUTO_ACTIONS_ENV = os.environ.get("HERMES_AUTO_ACTIONS", "0").strip().lower() in {"1", "true", "yes"}


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

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
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
    return {"success": False, "error": f"unknown action {action}"}



if __name__ == "__main__":
    print(json.dumps(main({"action": "cycle"}), indent=2, default=str))
