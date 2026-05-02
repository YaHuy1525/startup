#!/usr/bin/env python3
"""
Pod 1 — Omnichannel Distribution Orchestrator.

Takes approved content briefs and orchestrates distribution across all platforms:
  - Short-form video: TikTok, YouTube Shorts, Instagram Reels, Pinterest
  - Long-form: Medium, Substack, LinkedIn
  - Audio: Podcast RSS
  - Products: PDF Guides (Gumroad/Etsy)

This is the "conductor" that calls the specialized publisher modules.

Usage:
    python scripts/omnichannel_distributor.py --brief-id 1
    python scripts/omnichannel_distributor.py --auto --limit 3
"""
from __future__ import annotations

import json
import os
import sys
import argparse
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("omnichannel_distributor")


# ─── Platform Registry ──────────────────────────────────────────────────────
# Maps categories to which distribution channels make sense.
CATEGORY_PLATFORM_MAP = {
    "tech": {
        "editorial": ["medium", "substack", "linkedin"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": ["pdf_guide"],
        "audio": ["podcast"],
    },
    "fiction": {
        "editorial": ["medium", "substack"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": ["pdf_guide"],
        "audio": ["podcast"],
    },
    "movies": {
        "editorial": ["medium"],
        "short_video": ["tiktok", "youtube_shorts", "instagram_reels"],
        "products": [],
        "audio": ["podcast"],
    },
    "art": {
        "editorial": ["medium"],
        "short_video": ["tiktok", "instagram_reels", "pinterest"],
        "products": ["pdf_guide"],
        "audio": [],
    },
    "anime": {
        "editorial": ["medium"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": ["pdf_guide"],
        "audio": [],
    },
    "gaming": {
        "editorial": ["medium"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": [],
        "audio": ["podcast"],
    },
    "finance": {
        "editorial": ["medium", "substack", "linkedin"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": ["pdf_guide"],
        "audio": ["podcast"],
    },
    "tiktok_trending": {
        "editorial": [],
        "short_video": ["tiktok", "youtube_shorts", "instagram_reels"],
        "products": [],
        "audio": [],
    },
}

# Default for categories not explicitly mapped
DEFAULT_PLATFORMS = {
    "editorial": ["medium"],
    "short_video": ["tiktok", "youtube_shorts"],
    "products": [],
    "audio": [],
}


def _get_brief(brief_id: int) -> dict | None:
    return db.execute_one(
        """
        SELECT cb.*, gc.slug AS category_slug, gc.display_name AS category_name
        FROM content_briefs cb
        JOIN genesis_categories gc ON cb.category_id = gc.id
        WHERE cb.id = %s
        """,
        (brief_id,),
    )


def _update_brief_status(brief_id: int, status: str):
    db.execute(
        "UPDATE content_briefs SET status = %s WHERE id = %s",
        (status, brief_id),
    )


def distribute_editorial(brief: dict, platforms: list[str]) -> list[dict]:
    """Distribute to editorial platforms (Medium, Substack, LinkedIn)."""
    results = []
    if not platforms:
        return results

    try:
        from scripts.editorial_publisher import publish_brief
        result = publish_brief(brief["id"], platforms=platforms)
        for platform, r in result.get("platforms", {}).items():
            results.append({
                "channel": "editorial",
                "platform": platform,
                "success": r.get("success", False),
                "url": r.get("url"),
                "error": r.get("error"),
            })
    except Exception as e:
        logger.error(f"Editorial distribution failed: {e}")
        results.append({"channel": "editorial", "platform": "all", "success": False, "error": str(e)})

    return results


def distribute_products(brief: dict, product_types: list[str]) -> list[dict]:
    """Generate digital products from the brief."""
    results = []
    if not product_types:
        return results

    try:
        from scripts.digital_product_generator import generate_from_briefs
        result = generate_from_briefs(brief_ids=[brief["id"]])
        for product in result.get("products", []):
            results.append({
                "channel": "products",
                "platform": "pdf_guide",
                "success": True,
                "path": product.get("path"),
                "product_id": product.get("product_id"),
            })
    except Exception as e:
        logger.error(f"Product generation failed: {e}")
        results.append({"channel": "products", "platform": "pdf", "success": False, "error": str(e)})

    return results


def distribute_short_video(brief: dict, platforms: list[str]) -> list[dict]:
    """
    Queue short-video content for platforms.
    Creates a master_asset record and links it to the brief for downstream video rendering.
    """
    results = []
    if not platforms:
        return results

    # Create a master asset entry for the video to be produced
    try:
        asset_id = db.execute_returning(
            """
            INSERT INTO master_assets (brief_id, category, title, base_script, status)
            VALUES (%s, %s, %s, %s, 'raw')
            RETURNING id
            """,
            (
                brief["id"],
                brief.get("category_slug", "general"),
                brief.get("trend_name", ""),
                brief.get("base_narrative", ""),
            ),
        )

        # Queue platform distributions
        for platform in platforms:
            try:
                db.execute(
                    """
                    INSERT INTO platform_distributions
                        (master_asset_id, platform, format, status)
                    VALUES (%s, %s, 'short_video', 'pending')
                    ON CONFLICT (master_asset_id, platform) DO NOTHING
                    """,
                    (asset_id, platform),
                )
                results.append({
                    "channel": "short_video",
                    "platform": platform,
                    "success": True,
                    "status": "queued",
                    "master_asset_id": asset_id,
                })
            except Exception as e:
                results.append({
                    "channel": "short_video",
                    "platform": platform,
                    "success": False,
                    "error": str(e),
                })
    except Exception as e:
        logger.error(f"Short video distribution failed: {e}")
        results.append({"channel": "short_video", "platform": "all", "success": False, "error": str(e)})

    return results


def distribute_audio(brief: dict, platforms: list[str]) -> list[dict]:
    """
    Queue audio content (podcast episodes).
    Creates a master_asset with audio placeholder for voiceover_service to fill.
    """
    results = []
    if not platforms:
        return results

    try:
        asset_id = db.execute_returning(
            """
            INSERT INTO master_assets (brief_id, category, title, base_script, status)
            VALUES (%s, %s, %s, %s, 'raw')
            RETURNING id
            """,
            (
                brief["id"],
                brief.get("category_slug", "general"),
                f"[Podcast] {brief.get('trend_name', '')}",
                brief.get("base_narrative", ""),
            ),
        )

        for platform in platforms:
            db.execute(
                """
                INSERT INTO platform_distributions
                    (master_asset_id, platform, format, status)
                VALUES (%s, %s, 'audio', 'pending')
                ON CONFLICT (master_asset_id, platform) DO NOTHING
                """,
                (asset_id, platform),
            )
            results.append({
                "channel": "audio",
                "platform": platform,
                "success": True,
                "status": "queued_for_narration",
                "master_asset_id": asset_id,
            })
    except Exception as e:
        logger.error(f"Audio distribution failed: {e}")
        results.append({"channel": "audio", "platform": "all", "success": False, "error": str(e)})

    return results


def distribute_brief(brief_id: int, channels: list[str] | None = None) -> dict[str, Any]:
    """
    Full distribution orchestration for a single content brief.
    channels: list of 'editorial', 'short_video', 'products', 'audio' (or None for all)
    """
    brief = _get_brief(brief_id)
    if not brief:
        return {"error": f"Brief {brief_id} not found"}

    category = brief.get("category_slug", "general")
    platform_map = CATEGORY_PLATFORM_MAP.get(category, DEFAULT_PLATFORMS)

    if channels is None:
        channels = list(platform_map.keys())

    _update_brief_status(brief_id, "producing")

    all_results: list[dict] = []

    for channel in channels:
        platforms = platform_map.get(channel, [])
        if not platforms:
            continue

        if channel == "editorial":
            all_results.extend(distribute_editorial(brief, platforms))
        elif channel == "short_video":
            all_results.extend(distribute_short_video(brief, platforms))
        elif channel == "products":
            all_results.extend(distribute_products(brief, platforms))
        elif channel == "audio":
            all_results.extend(distribute_audio(brief, platforms))

    _update_brief_status(brief_id, "distributed")

    success_count = sum(1 for r in all_results if r.get("success"))
    fail_count = sum(1 for r in all_results if not r.get("success"))

    logger.info(
        f"Brief {brief_id} distributed: {success_count} succeeded, {fail_count} failed "
        f"across {len(channels)} channels"
    )

    return {
        "brief_id": brief_id,
        "category": category,
        "channels_processed": channels,
        "total_actions": len(all_results),
        "succeeded": success_count,
        "failed": fail_count,
        "results": all_results,
    }


def auto_distribute(limit: int = 3, channels: list[str] | None = None) -> dict:
    """
    Automatically distribute the top N approved/draft briefs.
    """
    briefs = db.execute(
        """
        SELECT cb.id, cb.trend_name, cb.virality_score, gc.slug AS category_slug
        FROM content_briefs cb
        JOIN genesis_categories gc ON cb.category_id = gc.id
        WHERE cb.status IN ('draft', 'approved')
        ORDER BY cb.virality_score DESC
        LIMIT %s
        """,
        (limit,),
    )

    if not briefs:
        return {"error": "No actionable briefs found", "distributed": 0}

    results = []
    for brief in briefs:
        result = distribute_brief(brief["id"], channels=channels)
        results.append(result)

    total_success = sum(r.get("succeeded", 0) for r in results)
    total_fail = sum(r.get("failed", 0) for r in results)

    return {
        "briefs_processed": len(briefs),
        "total_actions": total_success + total_fail,
        "total_succeeded": total_success,
        "total_failed": total_fail,
        "per_brief": results,
    }


def main(body: dict | None = None, **kwargs) -> dict:
    """Entry point for worker.py integration."""
    if body is None:
        body = kwargs

    action = body.get("action", "distribute")
    channels_raw = body.get("channels")

    if isinstance(channels_raw, str):
        channels = [c.strip() for c in channels_raw.split(",")]
    elif isinstance(channels_raw, list):
        channels = channels_raw
    else:
        channels = None

    if action == "auto":
        return auto_distribute(
            limit=int(body.get("limit", 3)),
            channels=channels,
        )

    brief_id = body.get("brief_id")
    if not brief_id:
        return {"error": "brief_id is required (or use action='auto')"}

    return distribute_brief(brief_id=int(brief_id), channels=channels)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Omnichannel Distributor")
    parser.add_argument("--brief-id", type=int, default=None)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--channels", type=str, default=None,
                        help="Comma-separated: editorial,short_video,products,audio")
    args = parser.parse_args()

    channels = [c.strip() for c in args.channels.split(",")] if args.channels else None

    if args.auto:
        result = auto_distribute(limit=args.limit, channels=channels)
    elif args.brief_id:
        result = distribute_brief(brief_id=args.brief_id, channels=channels)
    else:
        print("Use --brief-id N or --auto")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))
