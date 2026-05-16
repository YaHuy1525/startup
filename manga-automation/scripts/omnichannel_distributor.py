#!/usr/bin/env python3
"""
Pod 1 — Omnichannel Distribution Orchestrator.

Loads platform targets from `platform_catalog`:
  profile=min — lean path (few platforms, wired editorial + queued short/audio/product)
  profile=full — 40+ targets from All Platforms Money Guide (queued + wired where coded)

channels: editorial, short_video, long_video, live, audio, products, owned

Usage:
    python scripts/omnichannel_distributor.py --brief-id 1 --profile full
    python scripts/omnichannel_distributor.py --plan --category tech --profile full
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db  # noqa: E402
from scripts.utils.logger import setup_logger  # noqa: E402
from scripts.platform_catalog import (  # noqa: E402
    CHANNEL_TO_DB_FORMAT,
    distribution_plan as build_distribution_plan,
    resolve_channel_map,
)
from scripts.adapters import aitoearn_client  # noqa: E402

logger = setup_logger("omnichannel_distributor")

CHANNEL_ORDER = [
    "editorial",
    "short_video",
    "long_video",
    "live",
    "audio",
    "products",
    "owned",
]

EDITORIAL_WIRED = frozenset({"medium", "substack", "linkedin"})


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


def _queue_master_and_distributions(
    brief: dict,
    *,
    platforms: list[str],
    db_format: str,
    asset_title_suffix: str,
    shuffle: bool = True,
) -> list[dict]:
    """Create one master_assets row + pending rows in platform_distributions."""
    results: list[dict] = []
    if not platforms:
        return results
    plist = list(platforms)
    if shuffle:
        random.shuffle(plist)
    title = brief.get("trend_name", "")[:400]
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
                f"{asset_title_suffix} {title}".strip(),
                brief.get("base_narrative", ""),
            ),
        )
        if not asset_id:
            raise RuntimeError("master_assets insert returned no id")

        for platform in plist:
            try:
                db.execute(
                    """
                    INSERT INTO platform_distributions
                        (master_asset_id, platform, format, status)
                    VALUES (%s, %s, %s, 'pending')
                    ON CONFLICT (master_asset_id, platform) DO NOTHING
                    """,
                    (asset_id, platform, db_format),
                )
                results.append({
                    "channel": db_format,
                    "platform": platform,
                    "success": True,
                    "status": "queued",
                    "master_asset_id": asset_id,
                })
            except Exception as e:
                results.append({
                    "channel": db_format,
                    "platform": platform,
                    "success": False,
                    "error": str(e),
                })
    except Exception as e:
        logger.error(f"{db_format} queue failed: {e}")
        results.append({"channel": db_format, "platform": "all", "success": False, "error": str(e)})
    return results


def distribute_editorial(brief: dict, platforms: list[str]) -> list[dict]:
    """Medium/Substack/LinkedIn wired; every other slug queued as article stubs."""
    results: list[dict] = []
    if not platforms:
        return results

    wired = [p for p in platforms if p in EDITORIAL_WIRED]
    queued = [p for p in platforms if p not in EDITORIAL_WIRED]

    if wired:
        try:
            from scripts.editorial_publisher import publish_brief

            result = publish_brief(brief["id"], platforms=wired)
            for platform, r in result.get("platforms", {}).items():
                results.append({
                    "channel": "editorial",
                    "platform": platform,
                    "success": r.get("success", False),
                    "url": r.get("url"),
                    "error": r.get("error"),
                })
        except Exception as e:
            logger.error(f"Editorial wired distribution failed: {e}")
            results.append({"channel": "editorial", "platform": "wired_all", "success": False, "error": str(e)})

    if queued:
        results.extend(
            _queue_master_and_distributions(
                brief,
                platforms=queued,
                db_format=CHANNEL_TO_DB_FORMAT["editorial"],
                asset_title_suffix="[Queued article]",
            )
        )
    return results


def distribute_short_video(brief: dict, platforms: list[str]) -> list[dict]:
    return _queue_master_and_distributions(
        brief,
        platforms=platforms,
        db_format=CHANNEL_TO_DB_FORMAT["short_video"],
        asset_title_suffix="[Short video]",
        shuffle=True,
    )


def distribute_long_video(brief: dict, platforms: list[str]) -> list[dict]:
    return _queue_master_and_distributions(
        brief,
        platforms=platforms,
        db_format=CHANNEL_TO_DB_FORMAT["long_video"],
        asset_title_suffix="[Long-form video]",
        shuffle=True,
    )


def distribute_live(brief: dict, platforms: list[str]) -> list[dict]:
    return _queue_master_and_distributions(
        brief,
        platforms=platforms,
        db_format=CHANNEL_TO_DB_FORMAT["live"],
        asset_title_suffix="[Live]",
        shuffle=True,
    )


def distribute_audio_channels(brief: dict, platforms: list[str]) -> list[dict]:
    return _queue_master_and_distributions(
        brief,
        platforms=platforms,
        db_format=CHANNEL_TO_DB_FORMAT["audio"],
        asset_title_suffix="[Audio/podcast]",
        shuffle=True,
    )


def distribute_owned_offers(brief: dict, platforms: list[str]) -> list[dict]:
    """Membership / funnel rows — monetization_vectors filled later by tooling."""
    return _queue_master_and_distributions(
        brief,
        platforms=platforms,
        db_format=CHANNEL_TO_DB_FORMAT["owned"],
        asset_title_suffix="[Owned monetization]",
        shuffle=True,
    )


def distribute_products(brief: dict, product_targets: list[str]) -> list[dict]:
    """
    pdf_guide: render PDF via digital_product_generator, link rows.
    ALL other targets: queued digital_product placements (listing automation later).
    """
    results: list[dict] = []
    if not product_targets:
        return results

    targets = list(set(product_targets))
    random.shuffle(targets)

    asset_id = None
    try:
        asset_title = brief.get("trend_name", "")[:380]
        asset_id = db.execute_returning(
            """
            INSERT INTO master_assets (brief_id, category, title, base_script, status)
            VALUES (%s, %s, %s, %s, 'raw')
            RETURNING id
            """,
            (
                brief["id"],
                brief.get("category_slug", "general"),
                f"[Digital products] {asset_title}".strip(),
                brief.get("base_narrative", ""),
            ),
        )

        for slug in targets:
            if slug == "pdf_guide":
                try:
                    from scripts.digital_product_generator import generate_pdf_guide, save_product

                    path = generate_pdf_guide(brief)
                    product_id = save_product(
                        brief["id"],
                        path,
                        brief.get("trend_name", "Guide"),
                        brief.get("category_slug", "general"),
                        master_asset_id=asset_id,
                    )
                    db.execute(
                        """
                        INSERT INTO platform_distributions
                            (master_asset_id, platform, format, status)
                        VALUES (%s, %s, %s, 'pending')
                        ON CONFLICT (master_asset_id, platform) DO NOTHING
                        """,
                        (asset_id, "pdf_guide", CHANNEL_TO_DB_FORMAT["products"]),
                    )
                    results.append({
                        "channel": "products",
                        "platform": "pdf_guide",
                        "success": True,
                        "path": path,
                        "product_id": product_id,
                        "master_asset_id": asset_id,
                    })
                except Exception as e:
                    logger.error(f"PDF product failed: {e}")
                    results.append({
                        "channel": "products",
                        "platform": "pdf_guide",
                        "success": False,
                        "error": str(e),
                    })
            else:
                try:
                    db.execute(
                        """
                        INSERT INTO platform_distributions
                            (master_asset_id, platform, format, status)
                        VALUES (%s, %s, %s, 'pending')
                        ON CONFLICT (master_asset_id, platform) DO NOTHING
                        """,
                        (asset_id, slug, CHANNEL_TO_DB_FORMAT["products"]),
                    )
                    results.append({
                        "channel": "products",
                        "platform": slug,
                        "success": True,
                        "status": "queued_marketplace_stub",
                        "master_asset_id": asset_id,
                    })
                except Exception as e:
                    results.append({
                        "channel": "products",
                        "platform": slug,
                        "success": False,
                        "error": str(e),
                    })
    except Exception as e:
        logger.error(f"Product distribution failed at master asset setup: {e}")
        results.append({"channel": "products", "platform": "all", "success": False, "error": str(e)})

    return results


def distribute_brief(
    brief_id: int,
    channels: list[str] | None = None,
    *,
    profile: str = "minimal",
) -> dict[str, Any]:
    brief = _get_brief(brief_id)
    if not brief:
        return {"error": f"Brief {brief_id} not found"}

    category = brief.get("category_slug", "general")
    platform_map = resolve_channel_map(category, profile)

    if channels is None:
        channels_filter = None
        active_channels = CHANNEL_ORDER
    else:
        channels_filter = set(channels)
        active_channels = CHANNEL_ORDER

    _update_brief_status(brief_id, "producing")

    all_results: list[dict] = []

    for channel in active_channels:
        if channels_filter is not None and channel not in channels_filter:
            continue
        platforms = platform_map.get(channel) or []
        if not platforms:
            continue

        if channel == "editorial":
            all_results.extend(distribute_editorial(brief, platforms))
        elif channel == "short_video":
            all_results.extend(distribute_short_video(brief, platforms))
        elif channel == "long_video":
            all_results.extend(distribute_long_video(brief, platforms))
        elif channel == "live":
            all_results.extend(distribute_live(brief, platforms))
        elif channel == "audio":
            all_results.extend(distribute_audio_channels(brief, platforms))
        elif channel == "products":
            all_results.extend(distribute_products(brief, platforms))
        elif channel == "owned":
            all_results.extend(distribute_owned_offers(brief, platforms))

    _update_brief_status(brief_id, "distributed")

    success_count = sum(1 for r in all_results if r.get("success"))
    fail_count = sum(1 for r in all_results if not r.get("success"))

    logger.info(
        f"Brief {brief_id} distributed (profile={profile}): "
        f"{success_count} ok, {fail_count} errors"
    )

    return {
        "brief_id": brief_id,
        "category": category,
        "profile": profile,
        "channels_processed": list(channels) if channels is not None else list(platform_map.keys()),
        "platform_map_snapshot": platform_map,
        "total_actions": len(all_results),
        "succeeded": success_count,
        "failed": fail_count,
        "results": all_results,
    }


def auto_distribute(
    limit: int = 3,
    channels: list[str] | None = None,
    *,
    profile: str = "minimal",
) -> dict:
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
        result = distribute_brief(brief["id"], channels=channels, profile=profile)
        results.append(result)

    total_success = sum(r.get("succeeded", 0) for r in results)
    total_fail = sum(r.get("failed", 0) for r in results)

    return {
        "profile": profile,
        "briefs_processed": len(briefs),
        "total_actions": total_success + total_fail,
        "total_succeeded": total_success,
        "total_failed": total_fail,
        "per_brief": results,
    }


def main(body: dict | None = None, **kwargs) -> dict:
    if body is None:
        body = kwargs

    action = body.get("action", "distribute")
    profile = str(body.get("profile") or body.get("distribution_profile") or "minimal")
    channels_raw = body.get("channels")

    if isinstance(channels_raw, str):
        channels = [c.strip() for c in channels_raw.split(",") if c.strip()]
    elif isinstance(channels_raw, list):
        channels = channels_raw
    else:
        channels = None

    if action == "plan":
        cat = body.get("category_slug") or body.get("category") or "tech"
        if isinstance(cat, list):
            cat = cat[0]
        return build_distribution_plan(str(cat), profile)

    if action == "plan_all_categories":
        from scripts.genesis_discover import get_categories

        out = []
        for row in get_categories(None):
            out.append(build_distribution_plan(row["slug"], profile))
        return {"profile": profile, "categories": len(out), "plans": out}

    if action == "auto":
        return auto_distribute(
            limit=int(body.get("limit", 3)),
            channels=channels,
            profile=profile,
        )

    brief_id = body.get("brief_id")
    video_id = body.get("video_id")
    if not brief_id and video_id:
        if aitoearn_client.enabled():
            publish_payload = {
                "video_id": video_id,
                "profile": profile,
                "channels": channels,
                "idempotency_key": body.get("idempotency_key", f"omnichannel-video-{video_id}"),
            }
            remote = aitoearn_client.run_stage("publish", publish_payload)
            if remote.get("ok"):
                return {
                    "success": True,
                    "path": "aitoearn_primary",
                    "video_id": video_id,
                    "result": remote.get("result"),
                    "url": remote.get("url"),
                }
            if not aitoearn_client.CLIENT.config.fallback_local_enabled:
                return {
                    "success": False,
                    "path": "aitoearn_primary",
                    "video_id": video_id,
                    "error": "publish_failed_and_fallback_disabled",
                    "remote_error": remote,
                }
        return {
            "error": "brief_id is required for local omnichannel path; provide brief_id or enable AiToEarn publish endpoints",
            "video_id": video_id,
        }

    if not brief_id:
        return {"error": "brief_id is required ( or use action=plan | action=auto )"}

    result = distribute_brief(int(brief_id), channels=channels, profile=profile)
    if body.get("postiz_multichannel"):
        from scripts.adapters import postiz_bridge

        pz_slugs = body.get("postiz_platform_slugs")
        if isinstance(pz_slugs, str):
            pz_slugs = [s.strip() for s in pz_slugs.split(",") if s.strip()]
        result["postiz"] = postiz_bridge.schedule_brief_multichannel(
            int(brief_id),
            platform_slugs=pz_slugs if isinstance(pz_slugs, list) else None,
            media_path=body.get("postiz_media_path") or body.get("media_path"),
            schedule_iso=body.get("postiz_schedule_iso"),
            post_type=str(body.get("postiz_post_type", "now")),
            link_override=body.get("postiz_link"),
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Omnichannel distributor + planner")
    parser.add_argument("--brief-id", type=int, default=None)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--category", type=str, default="tech")
    parser.add_argument("--plan-all-categories", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "--profile",
        type=str,
        default="minimal",
        help="minimal | full",
    )
    parser.add_argument(
        "--channels",
        type=str,
        default=None,
        help="Comma-separated editorial,short_video,...",
    )
    args = parser.parse_args()

    channels = [c.strip() for c in args.channels.split(",")] if args.channels else None

    if args.plan:
        result = main({"action": "plan", "category_slug": args.category, "profile": args.profile})
    elif args.plan_all_categories:
        result = main({"action": "plan_all_categories", "profile": args.profile})
    elif args.auto:
        result = auto_distribute(limit=args.limit, channels=channels, profile=args.profile)
    elif args.brief_id:
        result = distribute_brief(args.brief_id, channels=channels, profile=args.profile)
    else:
        print("Use --brief-id N | --auto | --plan [--category] | --plan-all-categories")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))
