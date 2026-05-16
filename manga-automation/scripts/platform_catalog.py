"""
Unified platform catalog for the Omnichannel Content Factory (“All Platforms” guide).

- Every slug here maps to ONE row queued in platform_distributions (or wired handler).
- `profile=min` matches the legacy small footprint per category (fast iteration).
- `profile=full` expands to 40+ surfaces from lmao.html / monetization matrix:
  short-form, live, long video, newsletters, podcasts, owned/creator economy, niche marketplaces.

Wiring modes (see PLATFORM_META[*].implementation):
  queued     — persisted as pending distribution; downstream worker/renderer fills asset
  editorial  — Medium / Substack / LinkedIn only (wired in editorial_publisher)
  wired_uploader — uses existing TikTok/upload scripts once video rows exist (separate cron)
"""

from __future__ import annotations

from typing import Any, TypedDict


class PlatformMeta(TypedDict, total=False):
    slug: str
    guide_tab: str
    channel_group: str
    implementation: str
    monetization_notes: str
    postiz_provider: str  # docs.postiz __type hint when using Postiz public API


# ─── Channel keys ────────────────────────────────────────────────────────────
# editorial | short_video | long_video | live | audio | products | owned

MINIMAL_FALLBACK_CHANNEL_MAP: dict[str, list[str]] = {
    "editorial": ["medium"],
    "short_video": ["tiktok", "youtube_shorts"],
    "products": [],
    "audio": [],
}


MINIMAL_CATEGORY_CHANNEL_MAP: dict[str, dict[str, list[str]]] = {
    "tech": {
        "editorial": ["medium", "substack", "linkedin"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": ["pdf_guide"],
        "audio": ["spotify_podcast"],
    },
    "fiction": {
        "editorial": ["medium", "substack"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": ["pdf_guide"],
        "audio": ["spotify_podcast"],
    },
    "movies": {
        "editorial": ["medium"],
        "short_video": ["tiktok", "youtube_shorts", "instagram_reels"],
        "products": [],
        "audio": ["spotify_podcast"],
    },
    "art": {
        "editorial": ["medium"],
        "short_video": ["tiktok", "youtube_shorts", "instagram_reels", "pinterest_video"],
        "products": ["pdf_guide"],
        "audio": [],
    },
    "anime": {
        "editorial": ["medium"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": ["pdf_guide", "booth_pm_digital", "etsy_digital_product"],
        "audio": [],
    },
    "gaming": {
        "editorial": ["medium"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": [],
        "audio": ["spotify_podcast"],
    },
    "finance": {
        "editorial": ["medium", "substack", "linkedin"],
        "short_video": ["tiktok", "youtube_shorts"],
        "products": ["pdf_guide"],
        "audio": ["spotify_podcast"],
    },
    "tiktok_trending": {
        "editorial": [],
        "short_video": ["tiktok", "youtube_shorts", "instagram_reels"],
        "products": [],
        "audio": [],
    },
}


def _full_blueprint() -> dict[str, list[str]]:
    """Full-stack template shared by most categories — tuned per manga/lore monetization."""
    return {
        "editorial": [
            "medium",
            "substack",
            "linkedin",
            "beehiiv",
            "ghost",
            "linkedin_newsletter",
            "medium_partner",
            "devto",
            "hashnode",
            "wordpress",
            "threads",
            "bluesky",
            "mastodon",
            "x_twitter_threads",
            "telegram",
        ],
        "short_video": [
            "tiktok",
            "youtube_shorts",
            "instagram_reels",
            "facebook_reels",
            "snapchat_spotlight",
            "pinterest_video",
            "x_video",
            "youtube_shorts_organic_funnel",
        ],
        "long_video": [
            "youtube_long",
            "rumble_long",
            "youtube_podcasts_video_hub",
            "nebula_exclusive",
            "odysee_lbry_mirror",
            "floatplane_early_access",
        ],
        "live": [
            "kick_live",
            "youtube_live",
            "tiktok_live",
            "twitch_live",
            "rumble_live",
            "facebook_live",
        ],
        "audio": [
            "spotify_podcast",
            "apple_podcasts",
            "google_podcasts",
            "youtube_music_podcasts",
            "amazon_music_podcast",
            "acx_audible",
        ],
        "products": [
            "pdf_guide",
            "gumroad_asset",
            "etsy_digital_product",
            "redbubble_pod",
            "merch_amazon",
            "artstation_asset",
            "deviantart_print",
            "booth_pm_digital",
            "pixiv_fanbox_post",
            "onlyfans_exclusive_variant",
            "amazon_bookwalker_affiliate_page",
            "tiktok_shop_listing_mirror",
            "listmonk_email_product",
            "skool_offer",
            "discord_shop_mirror",
            "whop_product_mirror",
            "telegram_premium_offer",
            "patreon_exclusive_file",
            "kofi_shop_item",
            "postiz_publish_bundle",
        ],
        "owned": [
            "whop_membership_offer",
            "patreon_tier_offer",
            "kofi_subscription_tip",
            "discord_server_subscription_offer",
            "postiz_secondary_slot",
            "slack_community_offer",
            "youtube_channel_membership_offer",
            "tiktok_live_gift_bio_funnel",
        ],
    }


def _merge_full(overrides: dict[str, list[str]]) -> dict[str, list[str]]:
    base = _full_blueprint()
    base.update({k: list(v) for k, v in overrides.items()})
    return base


FULL_CATEGORY_CHANNEL_MAP: dict[str, dict[str, list[str]]] = {
    "tech": _full_blueprint(),
    "fiction": _merge_full({"audio": MINIMAL_CATEGORY_CHANNEL_MAP["fiction"]["audio"]}),
    "movies": _merge_full({}),
    "art": _merge_full(
        {
            "products": _full_blueprint()["products"] + ["nft_style_pack_stub"],
            "short_video": _full_blueprint()["short_video"] + ["dribbble_motion_stub"],
        }
    ),
    "anime": _merge_full(
        {
            "products": sorted(
                set(_full_blueprint()["products"] + ["doujin_guide_jp_mirror", "bookwalker_deep_link_kit"])
            ),
            "long_video": _full_blueprint()["long_video"] + ["youtube_anime_explainer_lens"],
            "live": _full_blueprint()["live"] + ["watchalong_event_stub"],
        }
    ),
    "gaming": _merge_full({"live": _full_blueprint()["live"]}),
    "finance": _merge_full({}),
    "tiktok_trending": _merge_full(
        {
            "editorial": [],
            "short_video": _full_blueprint()["short_video"],
            "products": [],
            "audio": [],
        }
    ),
    "_default": _full_blueprint(),
}


def resolve_channel_map(category_slug: str, profile: str) -> dict[str, list[str]]:
    prof = profile.strip().lower() if profile else "minimal"
    if prof in ("minimal", "min", ""):
        m = MINIMAL_CATEGORY_CHANNEL_MAP.get(category_slug)
        return m if m else MINIMAL_FALLBACK_CHANNEL_MAP.copy()
    if prof in ("full", "full_guide", "all"):
        return FULL_CATEGORY_CHANNEL_MAP.get(category_slug) or FULL_CATEGORY_CHANNEL_MAP["_default"]
    return resolve_channel_map(category_slug, "minimal")


PLATFORM_META: dict[str, PlatformMeta] = {
    # Short-form discovery
    "tiktok": {
        "slug": "tiktok",
        "guide_tab": "short",
        "channel_group": "short_video",
        "implementation": "queued_then_upload_tiktok",
        "monetization_notes": "Creator Rewards, Shop affiliate, LIVE gifts — enroll per region",
        "postiz_provider": "tiktok",
    },
    "youtube_shorts": {
        "slug": "youtube_shorts",
        "guide_tab": "short",
        "channel_group": "short_video",
        "implementation": "queued_then_upload_youtube",
        "monetization_notes": "Adsense via YPP thresholds; funnel to long-form",
        "postiz_provider": "youtube",
    },
    "instagram_reels": {
        "slug": "instagram_reels",
        "guide_tab": "short",
        "channel_group": "short_video",
        "implementation": "queued_then_instagram",
        "monetization_notes": "Subs/gifts/partnerships after eligibility",
        "postiz_provider": "instagram",
    },
    "facebook_reels": {
        "slug": "facebook_reels",
        "guide_tab": "short",
        "channel_group": "short_video",
        "implementation": "queued_stub",
        "monetization_notes": "Meta in-stream thresholds + affiliate",
        "postiz_provider": "facebook",
    },
    "snapchat_spotlight": {
        "slug": "snapchat_spotlight",
        "guide_tab": "short",
        "channel_group": "short_video",
        "implementation": "queued_stub",
        "monetization_notes": "Spotlight bonus eligibility — variable",
        "postiz_provider": "",
    },
    "pinterest_video": {
        "slug": "pinterest_video",
        "guide_tab": "short",
        "channel_group": "short_video",
        "implementation": "queued_then_pinterest_or_postiz",
        "monetization_notes": "Affiliate + traffic to owned funnel",
        "postiz_provider": "pinterest",
    },
    "x_twitter_threads": {"slug": "x_twitter_threads", "guide_tab": "short", "channel_group": "editorial", "implementation": "queued_stub_or_postiz", "postiz_provider": "x"},
    "x_video": {"slug": "x_video", "guide_tab": "short", "channel_group": "short_video", "implementation": "queued_stub_or_postiz", "postiz_provider": "x"},
    # Writing
    "medium": {"slug": "medium", "guide_tab": "write", "channel_group": "editorial", "implementation": "editorial_wired", "postiz_provider": "medium"},
    "medium_partner": {"slug": "medium_partner", "guide_tab": "write", "channel_group": "editorial", "implementation": "editorial_duplicate_medium", "monetization_notes": "MPP reading time"},
    "substack": {"slug": "substack", "guide_tab": "write", "channel_group": "editorial", "implementation": "editorial_wired"},
    "linkedin": {"slug": "linkedin", "guide_tab": "write", "channel_group": "editorial", "implementation": "editorial_wired", "postiz_provider": "linkedin"},
    "linkedin_newsletter": {"slug": "linkedin_newsletter", "guide_tab": "write", "channel_group": "editorial", "implementation": "queued_article"},
    "beehiiv": {"slug": "beehiiv", "guide_tab": "write", "channel_group": "editorial", "implementation": "queued_article", "monetization_notes": "Subs + boosts + ads"},
    "ghost": {"slug": "ghost", "guide_tab": "write", "channel_group": "editorial", "implementation": "queued_article"},
    "devto": {"slug": "devto", "guide_tab": "write", "channel_group": "editorial", "implementation": "queued_article", "postiz_provider": "devto"},
    "hashnode": {"slug": "hashnode", "guide_tab": "write", "channel_group": "editorial", "implementation": "queued_article", "postiz_provider": "hashnode"},
    "wordpress": {"slug": "wordpress", "guide_tab": "write", "channel_group": "editorial", "implementation": "queued_article", "postiz_provider": "wordpress"},
    "threads": {"slug": "threads", "guide_tab": "short", "channel_group": "editorial", "implementation": "queued_stub", "postiz_provider": "threads"},
    "bluesky": {"slug": "bluesky", "guide_tab": "write", "channel_group": "editorial", "implementation": "queued_stub", "postiz_provider": "bluesky"},
    "mastodon": {"slug": "mastodon", "guide_tab": "write", "channel_group": "editorial", "implementation": "queued_stub", "postiz_provider": "mastodon"},
    "telegram": {"slug": "telegram", "guide_tab": "write", "channel_group": "editorial", "implementation": "queued_stub", "postiz_provider": "telegram"},
}


# Auto-register remaining slugs referenced in FULL maps without verbose entries.
for _ch_name, lst in FULL_CATEGORY_CHANNEL_MAP.get("_default", {}).items():
    for _slug in lst:
        if _slug not in PLATFORM_META:
            guide = {"long_video": "long", "live": "live", "audio": "audio", "products": "niche", "owned": "owned"}.get(
                _ch_name, "short"
            )
            PLATFORM_META[_slug] = {
                "slug": _slug,
                "guide_tab": guide,
                "channel_group": _ch_name,
                "implementation": "queued_stub",
                "monetization_notes": "Requires platform enrollment + payouts setup",
                "postiz_provider": "",
            }


# Format used in platform_distributions.format column
CHANNEL_TO_DB_FORMAT = {
    "editorial": "article",
    "short_video": "short_video",
    "long_video": "long_video",
    "live": "live_broadcast",
    "audio": "audio",
    "products": "digital_product",
    "owned": "membership_offer",
}


def distribution_plan(category_slug: str, profile: str = "minimal") -> dict[str, Any]:
    m = resolve_channel_map(category_slug, profile)
    total = sum(len(v) for v in m.values())
    return {
        "category_slug": category_slug,
        "profile": profile,
        "channels": m,
        "platform_count": total,
        "platforms_flat": [{"channel": ck, "platform": pid} for ck, plist in m.items() for pid in plist],
        "hints": {
            "postiz_batch": "POST /adapters/postiz/schedule-brief { brief_id, media_path, platform_slugs? }",
            "postiz_docs": "https://docs.postiz.com/public-api",
            "rpa_fallback": "POST /rpa/session when Postiz has no connector",
        },
    }


def list_all_platform_slugs(profile: str = "full") -> list[str]:
    m = resolve_channel_map("_default", profile)
    seen: list[str] = []
    for plist in m.values():
        for s in plist:
            if s not in seen:
                seen.append(s)
    return seen
