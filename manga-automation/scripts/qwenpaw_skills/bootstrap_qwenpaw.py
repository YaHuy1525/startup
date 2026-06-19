#!/usr/bin/env python3
"""
QwenPaw Bootstrap Script for manga-automation (AiToEarn).

Initializes QwenPaw with:
  1. Default configuration (model, API keys, env vars)
  2. 7 agent workspaces (pipeline-manager + 6 specialists)
  3. Pipeline skills in skill pool + per-agent workspaces
  4. Telegram channel configuration
  5. Cron jobs for automated pipeline scheduling

Usage:
    python scripts/qwenpaw_skills/bootstrap_qwenpaw.py
    python scripts/qwenpaw_skills/bootstrap_qwenpaw.py --agent trend-scout
    python scripts/qwenpaw_skills/bootstrap_qwenpaw.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

CONSOLE_URL = os.environ.get("QWENPAW_CONSOLE_URL", "http://localhost:8088").rstrip("/")
BOOTSTRAP_DIR = os.path.dirname(__file__)
WORKSPACES_DIR = os.path.join(BOOTSTRAP_DIR, "workspaces")
PROJECT_ROOT = os.path.dirname(os.path.dirname(BOOTSTRAP_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.qwenpaw_skills.skill_definitions import SKILLS, skill_markdown  # noqa: E402

AGENTS = {
    "pipeline-manager": {
        "name": "Pipeline Manager",
        "description": (
            "Orchestrates the AiToEarn content pipeline: trend detection, "
            "content creation, publishing via AiToEarn (12 platforms), engagement, "
            "and monetization. Expert in TikTok/YouTube arbitrage and multi-platform "
            "distribution. Delegates to specialist agents via multi-agent collaboration."
        ),
        "skills": [
            "multi_agent_collaboration",
            "trend_discovery",
            "content_sourcing",
            "video_render",
            "publish_content",
            "engagement_cycle",
            "account_health",
            "performance_report",
            "content_plan",
            "finance_pipeline",
        ],
        "channels": ["telegram"],
    },
    "trend-scout": {
        "name": "Trend Scout",
        "description": (
            "Cross-domain trend analyst. Finds trending content across TikTok, "
            "Reddit, YouTube, and X/Twitter. Tracks trend velocity and confidence. "
            "Specializes in viral content arbitrage and early trend detection."
        ),
        "skills": ["trend_discovery", "content_plan"],
        "channels": [],
    },
    "content-harvester": {
        "name": "Content Harvester",
        "description": (
            "Sources high-quality videos from YouTube matching trend concepts. "
            "Verifies quality, checks duplicates, downloads assets."
        ),
        "skills": ["content_sourcing"],
        "channels": [],
    },
    "platform-publisher": {
        "name": "Platform Publisher",
        "description": (
            "Publishes content to TikTok, YouTube, Instagram, and 9 other platforms "
            "via AiToEarn MCP API. Verifies uploads with status polling."
        ),
        "skills": ["publish_content", "account_health"],
        "channels": [],
    },
    "performance-analyst": {
        "name": "Performance Analyst",
        "description": (
            "Analyzes pipeline results, records performance to memory, generates "
            "actionable recommendations."
        ),
        "skills": ["performance_report"],
        "channels": [],
    },
    "engagement-agent": {
        "name": "Engagement Agent",
        "description": (
            "Growth hacker agent. Drives algorithmic reach via automated engagement."
        ),
        "skills": ["engagement_cycle"],
        "channels": [],
    },
    "monetization-agent": {
        "name": "Monetization Agent",
        "description": (
            "Revenue optimization specialist. Matches creator content with "
            "highest-paying marketplace promotion tasks."
        ),
        "skills": [],
        "channels": [],
    },
    "product-promo-director": {
        "name": "Product Promo Director",
        "description": (
            "Remotion specialist for product and brand promotion videos. "
            "Uses ProductPromo composition with remotion-bits, remocn, and light-leaks. "
            "Turns natural-language briefs into 60s+ vertical promo videos."
        ),
        "skills": ["product_promo"],
        "channels": ["telegram"],
    },
}

PIPELINE_SKILL_NAMES = list(SKILLS.keys())


def _api(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{CONSOLE_URL}{path}"
    resp = requests.request(
        method=method.upper(),
        url=url,
        headers={"Content-Type": "application/json"},
        json=body or {},
        timeout=120,
    )
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise requests.HTTPError(f"{resp.status_code}: {detail}", response=resp)
    if not resp.content:
        return {}
    return resp.json()


def create_agent(agent_id: str, cfg: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    body = {"id": agent_id, "name": cfg["name"], "description": cfg["description"]}
    if dry_run:
        return {"dry_run": True, "agent_id": agent_id, "body": body}
    try:
        result = _api("POST", "/api/agents", body)
        print(f"  ✅ Created agent: {agent_id}")
        return result
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if status in (400, 409):
            result = _api("PUT", f"/api/agents/{agent_id}", body)
            print(f"  🔄 Updated agent: {agent_id}")
            return result
        raise


def copy_persona_files(agent_id: str, dry_run: bool = False) -> None:
    persona_dir = os.path.join(WORKSPACES_DIR, agent_id)
    for fname in ("AGENTS.md", "SOUL.md"):
        src = os.path.join(persona_dir, fname)
        if not os.path.exists(src):
            print(f"  ⚠️  Missing {fname} for {agent_id}")
            continue
        if dry_run:
            print(f"  [DRY RUN] Would copy {fname} -> workspace/{agent_id}/")
            continue
        with open(src, encoding="utf-8") as f:
            content = f.read()
        try:
            _api("PUT", f"/api/agents/{agent_id}/workspace/files/{fname}", {"content": content})
            print(f"  📄 Installed {fname} for {agent_id}")
        except Exception as exc:
            print(f"  ⚠️  Could not upload {fname} for {agent_id}: {exc}")


def register_pool_skill(skill_name: str, dry_run: bool = False) -> None:
    content = skill_markdown(skill_name)
    body = {"name": skill_name, "content": content, "enable": True}
    if dry_run:
        print(f"  [DRY RUN] Pool skill: {skill_name}")
        return
    try:
        _api("POST", "/api/skills/pool/create", body)
        print(f"  ✅ Pool skill: {skill_name}")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 409:
            _api("PUT", "/api/skills/pool/save", body)
            print(f"  🔄 Pool skill updated: {skill_name}")
        else:
            raise


def install_skills_for_agent(agent_id: str, skill_names: list[str], dry_run: bool = False) -> None:
    pipeline_skills = [s for s in skill_names if s in PIPELINE_SKILL_NAMES]
    if not pipeline_skills:
        return
    if dry_run:
        print(f"  [DRY RUN] Install skills on {agent_id}: {pipeline_skills}")
        return
    for skill_name in pipeline_skills:
        try:
            _api(
                "POST",
                "/api/skills/pool/download",
                {
                    "skill_name": skill_name,
                    "targets": [{"workspace_id": agent_id}],
                    "overwrite": True,
                },
            )
            print(f"  🧩 {agent_id}: enabled {skill_name}")
        except Exception as exc:
            print(f"  ⚠️  {agent_id}: failed {skill_name} — {exc}")


def configure_telegram(agent_id: str, dry_run: bool = False) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("  ℹ️  TELEGRAM_BOT_TOKEN not set — skipping Telegram channel")
        return
    if dry_run:
        print(f"  [DRY RUN] Enable Telegram on {agent_id}")
        return
    try:
        current = _api("GET", f"/api/agents/{agent_id}/config/channels")
        channels = current if isinstance(current, dict) else {}
        telegram = channels.get("telegram") or {}
        telegram["enabled"] = True
        telegram["bot_token"] = token
        channels["telegram"] = telegram
        _api("PUT", f"/api/agents/{agent_id}/config/channels", channels)
        print(f"  📱 Telegram enabled on {agent_id}")
    except Exception as exc:
        print(f"  ⚠️  Telegram config failed for {agent_id}: {exc}")


def create_cron_jobs(dry_run: bool = False) -> list[dict[str, Any]]:
    jobs = [
        {
            "name": "Trend Discovery (6h)",
            "cron": "0 */6 * * *",
            "prompt": (
                "Run trend discovery across all categories. "
                "Fetch from TikTok, Reddit, YouTube, and X/Twitter. "
                "Save top 20 trends to database."
            ),
        },
        {
            "name": "Morning Briefing",
            "cron": "17 8 * * *",
            "prompt": (
                "Morning briefing: top 10 trends, account health summary, "
                "yesterday's publishing results."
            ),
        },
        {
            "name": "Evening Arbitrage Pipeline",
            "cron": "3 21 * * *",
            "prompt": (
                "Run full arbitrage pipeline: top 10 trends → source 3 videos → "
                "publish via AiToEarn → engagement cycle → performance report."
            ),
        },
        {
            "name": "Account Health Monitor (30m)",
            "cron": "*/30 * * * *",
            "prompt": "Check shadow-ban status on all TikTok accounts. Alert if FYP ratio < 0.10.",
        },
        {
            "name": "Weekly Report (Monday)",
            "cron": "47 9 * * 1",
            "prompt": "Weekly performance report with 5 recommendations for next week.",
        },
    ]

    results = []
    agent_id = "pipeline-manager"
    for job in jobs:
        if dry_run:
            print(f"  [DRY RUN] Cron: {job['name']}")
            results.append({"dry_run": True, **job})
            continue
        spec = {
            "name": job["name"],
            "enabled": True,
            "schedule": {"type": "cron", "cron": job["cron"], "timezone": "UTC"},
            "task_type": "agent",
            "text": None,
            "request": {
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": job["prompt"]}],
                    }
                ],
                "session_id": f"cron-{job['name'].lower().replace(' ', '-')}",
                "user_id": "cron",
            },
            "dispatch": {
                "type": "channel",
                "channel": "console",
                "target": {
                    "user_id": "cron",
                    "session_id": f"cron-{job['name'].lower().replace(' ', '-')}",
                },
                "mode": "final",
            },
            "runtime": {"timeout_seconds": 900},
        }
        try:
            result = _api("POST", f"/api/agents/{agent_id}/cron/jobs", spec)
            results.append(result)
            print(f"  ⏰ Created cron: {job['name']} ({job['cron']})")
        except Exception as exc:
            print(f"  ⚠️  Failed cron: {job['name']} — {exc}")
            results.append({"error": str(exc), **job})
    return results


def verify_aitoearn_health() -> dict[str, Any]:
    try:
        from scripts.adapters import aitoearn_client
        return aitoearn_client.startup_validation()
    except ImportError:
        return {"ok": False, "error": "aitoearn_client_not_importable"}


def main():
    global CONSOLE_URL

    parser = argparse.ArgumentParser(description="Bootstrap QwenPaw for manga-automation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", help="Bootstrap a single agent by ID")
    parser.add_argument("--skip-cron", action="store_true")
    parser.add_argument("--skip-skills", action="store_true")
    parser.add_argument("--console-url", default=CONSOLE_URL)
    args = parser.parse_args()

    CONSOLE_URL = args.console_url.rstrip("/")

    print("=" * 60)
    print("  QwenPaw Bootstrap — manga-automation")
    print(f"  Console: {CONSOLE_URL}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    print("\n📡 Checking AiToEarn connectivity...")
    health = verify_aitoearn_health()
    if health.get("ok"):
        print(f"  ✅ AiToEarn reachable at: {health.get('base_url', 'unknown')}")
    else:
        print(f"  ⚠️  AiToEarn: {health.get('issues') or health.get('error') or health.get('warnings')}")

    if not args.skip_skills:
        print(f"\n🧩 Registering {len(PIPELINE_SKILL_NAMES)} pipeline skills in pool...")
        for skill_name in PIPELINE_SKILL_NAMES:
            try:
                register_pool_skill(skill_name, dry_run=args.dry_run)
            except Exception as exc:
                print(f"  ⚠️  Pool skill {skill_name}: {exc}")

    agents_to_create = [args.agent] if args.agent else list(AGENTS.keys())
    print(f"\n🤖 Creating {len(agents_to_create)} agent workspace(s)...")
    for agent_id in agents_to_create:
        if agent_id not in AGENTS:
            print(f"  ⚠️  Unknown agent: {agent_id}")
            continue
        cfg = AGENTS[agent_id]
        try:
            create_agent(agent_id, cfg, dry_run=args.dry_run)
            copy_persona_files(agent_id, dry_run=args.dry_run)
            if not args.skip_skills:
                install_skills_for_agent(agent_id, cfg.get("skills", []), dry_run=args.dry_run)
            if "telegram" in cfg.get("channels", []):
                configure_telegram(agent_id, dry_run=args.dry_run)
        except Exception as exc:
            print(f"  ❌ Failed agent {agent_id}: {exc}")

    if not args.skip_cron and (not args.agent or args.agent == "pipeline-manager"):
        print("\n⏰ Creating cron jobs on pipeline-manager...")
        create_cron_jobs(dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("  BOOTSTRAP COMPLETE" if not args.dry_run else "  DRY RUN COMPLETE")
    print(f"  Console: {CONSOLE_URL}")
    print("=" * 60)


if __name__ == "__main__":
    main()
