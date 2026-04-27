#!/usr/bin/env python3
"""
Activation helpers for monetization rollout.

Implements staged rollout:
- affiliate insertion ratio controls
- high-CPM slot enforcement
- membership CTA rotation (Patreon + Whop + Instagram subs)
"""
import json
from datetime import datetime
from typing import Any, Dict, List

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("monetization_activation")

DEFAULT_MEMBERSHIP_CTAS = [
    "Join Patreon for early chapter breakdowns",
    "Get exclusive tier lists on Whop",
    "Subscribe on Instagram for members-only posts",
]


def _get_channel(platform: str) -> Dict[str, Any] | None:
    return db.execute_one(
        """
        SELECT platform, ad_ratio_denominator, daily_min_posts, daily_max_posts
        FROM monetization_channel_config
        WHERE platform = %s
        """,
        (platform,),
    )


def _count_recent_posts(platform: str, days: int = 7) -> Dict[str, int]:
    row = db.execute_one(
        """
        SELECT
            COUNT(*)::int AS total_posts,
            COUNT(*) FILTER (
                WHERE COALESCE(LOWER(caption), '') LIKE '%%shop%%'
                   OR COALESCE(LOWER(caption), '') LIKE '%%affiliate%%'
                   OR COALESCE(LOWER(caption), '') LIKE '%%link in bio%%'
            )::int AS ad_like_posts
        FROM arbitrage_uploads
        WHERE platform = %s
          AND uploaded_at >= NOW() - (%s::int || ' days')::interval
          AND status = 'success'
        """,
        (platform, days),
    )
    return row or {"total_posts": 0, "ad_like_posts": 0}


def should_post_ad(platform: str, days: int = 7) -> Dict[str, Any]:
    channel = _get_channel(platform)
    if not channel:
        return {"error": f"Channel config missing for platform={platform}"}

    counts = _count_recent_posts(platform, days=days)
    total_posts = counts["total_posts"]
    ad_posts = counts["ad_like_posts"]
    denominator = max(1, int(channel["ad_ratio_denominator"]))

    # ratio target: ads <= total / denominator
    max_allowed_ads = total_posts // denominator
    allow_ad = ad_posts <= max_allowed_ads

    return {
        "platform": platform,
        "window_days": days,
        "total_posts": total_posts,
        "ad_like_posts": ad_posts,
        "target_ratio": f"1:{denominator}",
        "max_allowed_ads": max_allowed_ads,
        "allow_ad": allow_ad,
    }


def membership_cta_for_slot(slot_index: int) -> Dict[str, str]:
    cta = DEFAULT_MEMBERSHIP_CTAS[slot_index % len(DEFAULT_MEMBERSHIP_CTAS)]
    return {"slot_index": str(slot_index), "cta": cta}


def high_cpm_field_for_week(week_seed: int) -> Dict[str, str]:
    fields = [
        "japanese_language_via_anime",
        "education_crossover",
        "manga_collecting_investment",
        "anime_tech_gear_reviews",
        "narrative_storytelling_analysis",
    ]
    return {"field": fields[week_seed % len(fields)]}


def build_offer_matrix() -> Dict[str, Any]:
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "offers": [
            {"content_type": "lore_short", "primary_cta": "follow", "secondary_cta": "membership_teaser"},
            {"content_type": "affiliate_ad", "primary_cta": "shop_link", "secondary_cta": "membership_bundle"},
            {"content_type": "youtube_longform", "primary_cta": "affiliate_storefront", "secondary_cta": "patreon_deep_dive"},
            {"content_type": "instagram_carousel", "primary_cta": "save_and_follow", "secondary_cta": "ig_subscription"},
            {"content_type": "pinterest_pin", "primary_cta": "affiliate_click", "secondary_cta": "youtube_longform_bridge"},
        ],
    }


def main(action: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload or {}
    if action == "should-post-ad":
        return should_post_ad(str(payload.get("platform", "tiktok")), int(payload.get("days", 7)))
    if action == "membership-cta":
        return membership_cta_for_slot(int(payload.get("slot_index", 0)))
    if action == "high-cpm-field":
        return high_cpm_field_for_week(int(payload.get("week_seed", datetime.utcnow().isocalendar().week)))
    if action == "offer-matrix":
        return build_offer_matrix()
    return {"error": f"Unsupported action {action}"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["should-post-ad", "membership-cta", "high-cpm-field", "offer-matrix"])
    parser.add_argument("--payload", default="{}")
    args = parser.parse_args()
    print(json.dumps(main(args.action, json.loads(args.payload)), ensure_ascii=False))
