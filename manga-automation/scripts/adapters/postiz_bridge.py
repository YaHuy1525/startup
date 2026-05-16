#!/usr/bin/env python3
"""
Batch scheduling through Postiz Public API for platforms that are painful via direct API
(Pinterest, Instagram, TikTok, X, Meta, etc.) — one HTTPS call can carry many `posts[]`.

Prerequisites:
  - POSTIZ_API_KEY (or self-hosted equivalent)
  - OAuth-connected integrations inside Postiz UI
  - Optional POSTIZ_INTEGRATION_IDS_JSON to pin IDs when auto-match fails, e.g.
      {"tiktok":"...","youtube":"...","instagram":"...","pinterest":"...","x":"..."}
  - Pinterest video pins: POSTIZ_PINTEREST_BOARD (board id or name)

Docs: https://docs.postiz.com/public-api

Fallback when Postiz has no integration: see scripts/rpa/playwright_rpa_boilerplate.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.adapters import postiz_client

logger = setup_logger("postiz_bridge")

# Internal omnichannel slug → Postiz settings __type (see Postiz provider tables).
SLUG_TO_POSTIZ_TYPE: dict[str, str] = {
    "tiktok": "tiktok",
    "youtube_shorts": "youtube",
    "youtube_shorts_organic_funnel": "youtube",
    "youtube_long": "youtube",
    "youtube_live": "youtube",
    "youtube_podcasts_video_hub": "youtube",
    "instagram_reels": "instagram",
    "facebook_reels": "facebook",
    "facebook_live": "facebook",
    "pinterest_video": "pinterest",
    "x_video": "x",
    "x_twitter_threads": "x",
    "medium": "medium",
    "medium_partner": "medium",
    "linkedin": "linkedin",
    "linkedin_newsletter": "linkedin-page",
    "devto": "devto",
    "hashnode": "hashnode",
    "wordpress": "wordpress",
    "threads": "threads",
    "bluesky": "bluesky",
    "mastodon": "mastodon",
    "telegram": "telegram",
    "reddit": "reddit",
    "discord": "discord",
    "slack": "slack",
    "youtube_music_podcasts": "youtube",
}


def _integrations_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("integrations", "data", "items", "results"):
            v = raw.get(key)
            if isinstance(v, list):
                return v
        if all(isinstance(x, dict) for x in raw.values()):
            return list(raw.values())
    return []


def _provider_key(integ: dict[str, Any]) -> str:
    for k in (
        "provider",
        "type",
        "identifier",
        "internalIdentifier",
        "platform",
        "name",
    ):
        v = integ.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def _load_env_integration_overrides() -> dict[str, str]:
    raw = os.environ.get("POSTIZ_INTEGRATION_IDS_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {str(k).lower(): str(v) for k, v in data.items()}
    except json.JSONDecodeError:
        logger.warning("POSTIZ_INTEGRATION_IDS_JSON is not valid JSON")
        return {}


def resolve_postiz_integration_ids() -> dict[str, str]:
    """
    Map Postiz provider key → integration id.
    Merges GET /integrations with POSTIZ_INTEGRATION_IDS_JSON (overrides win).
    """
    overrides = _load_env_integration_overrides()
    try:
        raw = postiz_client.list_integrations()
    except Exception as e:
        logger.error(f"Postiz list_integrations failed: {e}")
        return dict(overrides)

    mapping: dict[str, str] = {}
    for item in _integrations_list(raw):
        iid = item.get("id") or item.get("_id") or item.get("integrationId")
        if not iid:
            continue
        key = _provider_key(item)
        if key:
            mapping[key] = str(iid)
        # duplicate common aliases
        if "linkedin" in key and "page" in key:
            mapping["linkedin-page"] = str(iid)
        if key == "twitter" or key == "x.com":
            mapping["x"] = str(iid)

    mapping.update(overrides)
    return mapping


def _brief_caption(brief: dict) -> str:
    parts = [
        brief.get("viral_hook") or "",
        brief.get("trend_name") or "",
        (brief.get("base_narrative") or "")[:1200],
    ]
    return "\n\n".join(p for p in parts if p).strip() or "Trend update"


def _default_link(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return os.environ.get(
        "DEFAULT_UTM_LINK",
        os.environ.get("AFFILIATE_FALLBACK_URL", "https://example.com"),
    )


def _settings_for_postiz_type(ptype: str, brief: dict, link: str) -> dict[str, Any]:
    title = (brief.get("trend_name") or "Update")[:500]
    subtitle = (brief.get("viral_hook") or "")[:300]

    if ptype == "pinterest":
        board = os.environ.get("POSTIZ_PINTEREST_BOARD", "")
        if not board:
            logger.warning("POSTIZ_PINTEREST_BOARD unset — Pinterest post may fail validation")
        return {"__type": "pinterest", "board": board, "title": title[:255], "link": link}

    if ptype == "instagram":
        return {"__type": "instagram", "post_type": "reel"}

    if ptype == "youtube":
        return {
            "__type": "youtube",
            "title": title,
            "type": "shorts",
            "selfDeclaredMadeForKids": False,
            "tags": [],
        }

    if ptype == "tiktok":
        return {
            "__type": "tiktok",
            "privacy_level": os.environ.get("POSTIZ_TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE"),
            "duet": True,
            "stitch": True,
            "comment": True,
            "autoAddMusic": False,
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
        }

    if ptype == "facebook":
        return {"__type": "facebook", "url": link}

    if ptype == "x":
        return {"__type": "x", "who_can_reply_post": "everyone"}

    if ptype == "medium":
        return {
            "__type": "medium",
            "title": title,
            "subtitle": subtitle,
            "tags": [{"value": "trending", "label": "Trending"}],
        }

    if ptype == "linkedin":
        return {"__type": "linkedin", "post_as_images_carousel": False}

    if ptype == "linkedin-page":
        return {"__type": "linkedin-page", "post_as_images_carousel": False}

    if ptype in ("devto", "hashnode"):
        return {"__type": ptype, "title": title, "tags": []}

    if ptype == "wordpress":
        return {"__type": "wordpress", "title": title, "type": "post"}

    if ptype in ("threads", "bluesky", "mastodon", "telegram"):
        return {"__type": ptype}

    if ptype == "reddit":
        return {
            "__type": "reddit",
            "subreddit": [{"title": title, "type": "image", "flair": None}],
        }

    return {"__type": ptype}


def _default_slug_batch() -> list[str]:
    raw = os.environ.get(
        "POSTIZ_AUTOPUBLISH_SLUGS",
        "tiktok,youtube_shorts,instagram_reels,pinterest_video,x_twitter_threads",
    )
    return [s.strip() for s in raw.split(",") if s.strip()]


def schedule_brief_multichannel(
    brief_id: int,
    *,
    platform_slugs: list[str] | None = None,
    media_path: str | None = None,
    schedule_iso: str | None = None,
    post_type: str = "now",
    link_override: str | None = None,
) -> dict[str, Any]:
    """
    Build a single Postiz /posts payload with one entry per resolvable integration.

    Rate limit: batches count as one request — keep slug list focused (≤ ~10).
    """
    brief = db.execute_one(
        """
        SELECT cb.*, gc.slug AS category_slug, gc.display_name AS category_name
        FROM content_briefs cb
        JOIN genesis_categories gc ON cb.category_id = gc.id
        WHERE cb.id = %s
        """,
        (brief_id,),
    )
    if not brief:
        return {"ok": False, "error": f"Brief {brief_id} not found"}

    slugs = platform_slugs if platform_slugs else _default_slug_batch()
    id_map = resolve_postiz_integration_ids()

    media: dict[str, Any] | None = None
    if media_path and os.path.isfile(media_path):
        try:
            media = postiz_client.upload_media(media_path)
        except Exception as e:
            return {"ok": False, "error": f"Postiz upload failed: {e}"}

    images: list[dict[str, Any]] = []
    if media and media.get("id") and media.get("path"):
        images.append({"id": media["id"], "path": media["path"]})

    caption = _brief_caption(brief)
    link = _default_link(link_override)

    posts: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for slug in slugs:
        ptype = SLUG_TO_POSTIZ_TYPE.get(slug)
        if not ptype:
            skipped.append({"slug": slug, "reason": "no_postiz_type_mapping"})
            continue
        integ_id = id_map.get(ptype)
        if not integ_id:
            p_norm = ptype.replace("-", "").replace("_", "")
            for k, v in id_map.items():
                k_norm = k.replace("-", "").replace("_", "")
                if k_norm == p_norm or ptype in k or k in ptype:
                    integ_id = v
                    break
        if not integ_id:
            skipped.append({"slug": slug, "reason": f"no_integration_id_for_{ptype}"})
            continue

        settings = _settings_for_postiz_type(ptype, brief, link)
        value_images = images
        # Text-first networks may work without media; video networks need upload
        if ptype in ("tiktok", "youtube", "instagram") and not value_images:
            skipped.append({"slug": slug, "reason": "media_required_not_provided"})
            continue

        body_md = caption
        if ptype == "medium":
            body_md = f"# {brief.get('trend_name') or 'Article'}\n\n{caption}"

        posts.append(
            {
                "integration": {"id": integ_id},
                "value": [{"content": body_md, "image": value_images}],
                "settings": settings,
            }
        )

    if not posts:
        return {
            "ok": False,
            "error": "No posts could be built — check integrations and POSTIZ_INTEGRATION_IDS_JSON",
            "skipped": skipped,
            "integration_keys_seen": sorted(id_map.keys()),
        }

    when = schedule_iso or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    payload: dict[str, Any] = {
        "type": "schedule" if post_type == "schedule" else "now",
        "date": when,
        "shortLink": False,
        "tags": [],
        "posts": posts,
    }

    try:
        data = postiz_client.create_posts(payload)
        return {
            "ok": True,
            "brief_id": brief_id,
            "posts_submitted": len(posts),
            "skipped": skipped,
            "postiz_response": data,
        }
    except Exception as e:
        logger.exception("Postiz create_posts failed")
        return {
            "ok": False,
            "error": str(e),
            "skipped": skipped,
            "payload_preview": {"type": payload["type"], "post_count": len(posts)},
        }


def main(body: dict | None = None, **kwargs) -> dict[str, Any]:
    if body is None:
        body = kwargs
    action = body.get("action", "resolve_integrations")

    try:
        if action == "resolve_integrations":
            return {"ok": True, "map": resolve_postiz_integration_ids()}
        if action == "schedule_brief":
            bids = body.get("brief_id")
            if not bids:
                return {"ok": False, "error": "brief_id required"}
            slugs = body.get("platform_slugs")
            if isinstance(slugs, str):
                slugs = [s.strip() for s in slugs.split(",") if s.strip()]
            return schedule_brief_multichannel(
                int(bids),
                platform_slugs=slugs if isinstance(slugs, list) else None,
                media_path=body.get("media_path") or body.get("video_path"),
                schedule_iso=body.get("schedule_iso"),
                post_type=str(body.get("post_type", "now")),
                link_override=body.get("link"),
            )
        return {"ok": False, "error": f"unknown action {action}"}
    except Exception as e:
        logger.exception("postiz_bridge error")
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    print(json.dumps(main({"action": "resolve_integrations"}), indent=2, default=str))
