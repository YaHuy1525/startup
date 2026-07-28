#!/usr/bin/env python3
"""Dispatch QwenPaw pipeline skills inside python-worker."""
from __future__ import annotations

import asyncio
import importlib
import traceback
from typing import Any

SKILL_NAMES = (
    "trend_discovery",
    "content_sourcing",
    "video_render",
    "publish_content",
    "engagement_cycle",
    "account_health",
    "performance_report",
    "content_plan",
    "finance_pipeline",
    "product_promo",
    "seedance_video",
    "stickman_video",
    "stickman_flow",
    "stickman_character_ref",
    "stickman_script",
    "stickman_scene_images",
    "stickman_animate",
    "stickman_voice",
    "stickman_edit",
    "video_template_research",
    "shortform_pipeline",
    "shortform_story_fetch",
    "shortform_script",
    "shortform_find_memes",
    "shortform_voice",
    "shortform_render",
    "shortform_publish",
    "shortform_monitor",
    "shortform_anime_theory",
    "shortform_thumbnail",
    "shortform_caption",
)


async def run_skill(skill_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    name = (skill_name or "").strip().replace("-", "_")
    if name not in SKILL_NAMES:
        return {"success": False, "error": f"unknown_skill:{name}"}
    try:
        mod = importlib.import_module(f"scripts.qwenpaw_skills.{name}")
        execute = getattr(mod, "execute")
        return await execute(args or {}, {})
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc()[-2000:],
        }


def run_skill_sync(skill_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return asyncio.run(run_skill(skill_name, args))
