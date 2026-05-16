#!/usr/bin/env python3
"""
Finance Brainrot Video Generator — @mini.money.matters style.

Uses trending AI video platforms to create viral finance content:

  PROVIDER 0: Revid.ai  — ⭐ BEST CHOICE for the brainrot style
              Text → video with Subway Surfers / Minecraft background,
              AI voiceover, bold animated captions. Exactly like the
              @mini.money.matters Instagram reels.
              API: https://www.revid.ai/api/public/v3/render
              Plans: Growth plan required (~$49/mo)

  PROVIDER 1: Creatify  — Ad-style proof videos (professional look)
              API: https://docs.creatify.ai/

  PROVIDER 2: HeyGen    — AI avatar talking-head videos (no face needed)
              API: https://docs.heygen.com/

  PROVIDER 3: InVideo   — Stock footage explainer videos
              API: https://invideo.io/

Usage:
    python scripts/finance_video_ai.py --provider revid --week 2026-W19
    python scripts/finance_video_ai.py --provider revid --background subway_surfers
    python scripts/finance_video_ai.py --provider creatify --week 2026-W19
    python scripts/finance_video_ai.py --provider heygen --brief-id 42

    Via worker:
    POST /finance/ai-video { "provider": "revid", "week_iso": "2026-W19" }
    POST /finance/ai-video { "provider": "revid", "background": "minecraft" }

Setup (.env):
    REVID_API_KEY=your_api_key          # from revid.ai/account
    REVID_VOICE_ID=your_voice_id        # from revid.ai/create → Get API Code
    REVID_BACKGROUND=subway_surfers     # subway_surfers | minecraft | temple_run
    CREATIFY_API_ID=your_api_id
    CREATIFY_API_KEY=your_api_key
    HEYGEN_API_KEY=your_api_key
    INVIDEO_API_KEY=your_api_key
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("finance_video_ai")

# ─── Environment ──────────────────────────────────────────────────────────────
REVID_API_KEY    = os.environ.get("REVID_API_KEY", "")
REVID_VOICE_ID   = os.environ.get("REVID_VOICE_ID", "")
REVID_BACKGROUND = os.environ.get("REVID_BACKGROUND", "subway_surfers")

CREATIFY_API_ID  = os.environ.get("CREATIFY_API_ID", "")
CREATIFY_API_KEY = os.environ.get("CREATIFY_API_KEY", "")
HEYGEN_API_KEY   = os.environ.get("HEYGEN_API_KEY", "")
INVIDEO_API_KEY  = os.environ.get("INVIDEO_API_KEY", "")

DEFAULT_PROVIDER = os.environ.get("FINANCE_VIDEO_PROVIDER", "revid")
VIDEOS_DIR = Path(os.environ.get("FINANCE_VIDEOS_DIR", "/data/finance_videos"))



# ─── Shared helpers ───────────────────────────────────────────────────────────
def _current_week() -> str:
    now = datetime.now(timezone.utc)
    yr, wk, _ = now.isocalendar()
    return f"{yr}-W{wk:02d}"


def _get_week_earnings(week_iso: str) -> dict[str, Any]:
    """Fetch aggregated earnings + referral links for a given week."""
    rows = db.execute(
        """
        SELECT es.platform_slug, rp.display_name, rp.referral_url,
               SUM(es.amount_usd) AS total_usd
        FROM earnings_snapshots es
        LEFT JOIN referral_platforms rp ON es.platform_slug = rp.slug
        WHERE es.week_iso = %s
        GROUP BY es.platform_slug, rp.display_name, rp.referral_url
        ORDER BY total_usd DESC
        """,
        (week_iso,),
    )

    if not rows:
        return {}

    total = sum(float(r["total_usd"]) for r in rows)
    platform_lines = "\n".join(
        f"• {r['display_name'] or r['platform_slug']}: ${float(r['total_usd']):.2f}"
        for r in rows
    )
    ref_links = [
        r["referral_url"] for r in rows
        if r.get("referral_url") and "YOUR_REF_ID" not in r["referral_url"]
    ]

    return {
        "total": total,
        "platforms": [dict(r) for r in rows],
        "platform_lines": platform_lines,
        "referral_urls": ref_links,
        "week_iso": week_iso,
    }


def _build_script(earnings: dict, style: str = "short") -> str:
    """
    Build a video script from earnings data.
    style: 'short' (15–30s) | 'long' (60–90s)
    """
    total = earnings.get("total", 0)
    platform_lines = earnings.get("platform_lines", "")
    ref_url = earnings.get("referral_urls", [""])[0] if earnings.get("referral_urls") else ""
    cta = f"Get my full list at {ref_url}" if ref_url else "Comment LIST for my full list"

    if style == "short":
        return (
            f"I made ${total:.2f} in passive income this week "
            f"doing basically nothing. "
            f"Here's the breakdown: {platform_lines}. "
            f"{cta}."
        )
    else:
        return (
            f"Okay so I need to show you my passive income results from this week "
            f"because I literally cannot believe this. "
            f"Total earned: ${total:.2f}. "
            f"Let me break it down for you. "
            f"{platform_lines}. "
            f"And the best part? These are all apps running in the background. "
            f"I didn't have to do anything extra this week. "
            f"If you want the full list of every single app I use, "
            f"{cta}."
        )


def _save_video_record(
    file_path: str | None,
    video_url: str | None,
    provider: str,
    week_iso: str,
    total: float,
    external_id: str | None = None,
) -> int | None:
    """Save a record to the videos table and return the video_id."""
    caption = (
        f"I made ${total:.2f} in passive income this week 💸 "
        f"Comment LIST for every app I use 👇"
    )
    hashtags = [
        "passiveincome", "sidehustle", "beermoney",
        "honeygain", "makemoney", "moneytok",
        "passiveincomeapps", "sidehustleideas", "workfromhome",
    ]
    return db.execute_returning(
        """
        INSERT INTO videos
            (file_path, caption, hashtags, status)
        VALUES (%s, %s, %s, 'ready')
        RETURNING id
        """,
        (
            file_path or video_url or f"remote:{provider}:{external_id}",
            caption,
            hashtags,
        ),
    )



# ─── Provider 0: Revid.ai ─────────────────────────────────────────────────────
# ⭐ BEST for the @mini.money.matters brainrot style
# Style: Subway Surfers / Minecraft background + AI voice + bold captions
# Price: Growth plan ~$49/mo (includes API access)
# Setup: Go to revid.ai/create → configure your video → "..." → "Get API Code"
#        Copy the backgroundId and voiceId from the generated JSON
# Docs:  https://www.revid.ai/api/public/v3/render
# ─────────────────────────────────────────────────────────────────────────────

REVID_BASE = "https://www.revid.ai/api/public/v3"

# Background preset mapping — readable names → Revid background slugs/IDs
# ⚠️  Get your exact backgroundId by going to revid.ai/create, picking your
#     background, then clicking "..." → "Get API Code"
REVID_BACKGROUNDS = {
    "subway_surfers": "subway-surfers",    # Most viral — high retention
    "minecraft":      "minecraft-parkour", # Trending gaming background
    "temple_run":     "temple-run",        # Alternative gaming
    "satisfying":     "satisfying-videos", # Satisfying slime/sand videos
    "gta":            "gta-gameplay",      # GTA driving footage
    "default":        "subway-surfers",    # Fallback
}


def revid_generate_video(
    script: str,
    background: str | None = None,
    voice_id: str | None = None,
    caption_preset: str = "Wrap 1",
) -> dict[str, Any]:
    """
    Generate a brainrot-style video via Revid.ai.

    The video has:
    - Your earnings script read as AI voiceover
    - Subway Surfers / Minecraft / other gameplay in the background
    - Bold animated captions auto-synced to the voice
    - 9:16 vertical format ready for TikTok/Reels/Shorts

    Args:
        script:         The earnings narration script (30–150 words ideal)
        background:     'subway_surfers' | 'minecraft' | 'temple_run' | 'gta'
        voice_id:       Revid voice ID (from revid.ai/create → Get API Code)
        caption_preset: Caption animation style ('Wrap 1' is the bold viral style)

    Returns dict with 'pid' (project ID) and polls until 'video_url' is ready.
    """
    if not REVID_API_KEY:
        return {
            "error": "REVID_API_KEY not set in .env",
            "hint": (
                "1. Sign up at revid.ai (Growth plan)\n"
                "2. Go to revid.ai/account → copy your API key\n"
                "3. Add REVID_API_KEY=your_key to .env"
            ),
        }

    selected_bg = REVID_BACKGROUNDS.get(
        (background or REVID_BACKGROUND).lower(),
        "subway-surfers",
    )
    selected_voice = voice_id or REVID_VOICE_ID

    payload: dict[str, Any] = {
        "workflow": "script-to-video",
        "source": {
            "text": script,
        },
        "media": {
            "type":      "moving-image",
            "quality":   "pro",
            "animation": "soft",
        },
        "background": {
            "id": selected_bg,
        },
        "captions": {
            "enabled":  True,
            "preset":   caption_preset,   # "Wrap 1" = bold viral style
            "position": "center",         # center is the brainrot standard
        },
    }

    if selected_voice:
        payload["voice"] = {
            "enabled": True,
            "voiceId": selected_voice,
        }
    else:
        payload["voice"] = {"enabled": True}   # Revid picks a default voice

    logger.info(f"Revid: submitting script ({len(script)} chars) | bg={selected_bg}")

    try:
        resp = requests.post(
            f"{REVID_BASE}/render",
            json=payload,
            headers={
                "key":          REVID_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": f"Revid render request failed: {e}"}

    pid = data.get("pid") or data.get("id") or data.get("projectId")
    if not pid:
        return {"error": f"Revid returned no project ID: {data}"}

    logger.info(f"Revid project created: pid={pid}")

    # Poll until done
    return _revid_poll(pid)


def _revid_poll(pid: str, max_wait: int = 600, poll_every: int = 10) -> dict[str, Any]:
    """Poll Revid project status until video is ready."""
    waited = 0
    while waited < max_wait:
        time.sleep(poll_every)
        waited += poll_every

        try:
            resp = requests.get(
                f"{REVID_BASE}/get_project_status",
                params={"pid": pid},
                headers={"key": REVID_API_KEY},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Revid poll error for {pid}: {e}")
            continue

        status = (data.get("status") or "").lower()
        video_url = data.get("videoUrl") or data.get("video_url") or data.get("url")

        logger.info(f"Revid {pid}: status={status} ({waited}s)")

        if video_url or status in ("done", "completed", "finished", "success"):
            return {
                "success":   True,
                "provider":  "revid",
                "pid":       pid,
                "video_url": video_url,
                "data":      data,
            }

        if status in ("failed", "error", "cancelled"):
            return {
                "error":  f"Revid video failed: {data.get('error', 'unknown')}",
                "pid":    pid,
                "status": status,
            }

    return {"error": f"Revid video {pid} timed out after {max_wait}s"}


# ─── Provider 1: Creatify ─────────────────────────────────────────────────────
# Best for: Short-form proof/ad videos (15–60s) — professional aesthetic
# Price:    ~$49/mo for API access
# Docs:     https://docs.creatify.ai/
# ─────────────────────────────────────────────────────────────────────────────

CREATIFY_BASE = "https://api.creatify.ai/api"


def _creatify_headers() -> dict:
    return {
        "X-API-ID":  CREATIFY_API_ID,
        "X-API-KEY": CREATIFY_API_KEY,
        "Content-Type": "application/json",
    }


def _creatify_check_keys() -> bool:
    if not CREATIFY_API_ID or not CREATIFY_API_KEY:
        return False
    return True


def creatify_generate_avatar_video(
    script: str,
    avatar_id: str | None = None,
    voice_id: str | None = None,
    aspect_ratio: str = "9:16",
) -> dict[str, Any]:
    """
    Generate an AI avatar video via Creatify.
    The avatar reads your earnings script — no face camera needed.

    Steps:
    1. POST /avatar-and-talking-photo-lipsyncs/ → get task ID
    2. Poll GET /avatar-and-talking-photo-lipsyncs/{id}/ until done
    3. Return video_url
    """
    if not _creatify_check_keys():
        return {"error": "CREATIFY_API_ID and CREATIFY_API_KEY not set in .env"}

    # Default: use a professional-looking finance avatar
    selected_avatar = avatar_id or os.environ.get("CREATIFY_AVATAR_ID", "")
    selected_voice  = voice_id  or os.environ.get("CREATIFY_VOICE_ID", "")

    if not selected_avatar:
        # List available avatars first
        avatars = creatify_list_avatars()
        if avatars.get("error"):
            return avatars
        av_list = avatars.get("data", [])
        if not av_list:
            return {"error": "No avatars available. Create one in Creatify studio first."}
        selected_avatar = av_list[0]["avatar_id"]
        logger.info(f"Auto-selected avatar: {selected_avatar}")

    payload = {
        "script":       script,
        "avatar_id":    selected_avatar,
        "aspect_ratio": aspect_ratio,
    }
    if selected_voice:
        payload["voice_id"] = selected_voice

    try:
        resp = requests.post(
            f"{CREATIFY_BASE}/avatar-and-talking-photo-lipsyncs/",
            json=payload,
            headers=_creatify_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        task = resp.json()
        task_id = task.get("id")
        logger.info(f"Creatify avatar task created: {task_id}")
    except Exception as e:
        return {"error": f"Creatify create task failed: {e}"}

    # Poll for completion (up to 10 min)
    return _creatify_poll(task_id, endpoint="avatar-and-talking-photo-lipsyncs")


def creatify_generate_link_video(
    script: str,
    landing_url: str | None = None,
) -> dict[str, Any]:
    """
    Generate a product/link-style promo video via Creatify.
    Provide a URL (e.g. your referral hub page) → Creatify auto-generates
    a short video ad with stock footage + your script.
    """
    if not _creatify_check_keys():
        return {"error": "CREATIFY_API_ID and CREATIFY_API_KEY not set in .env"}

    url = landing_url or os.environ.get("REFERRAL_HUB_URL", "")
    if not url or "your-domain" in url:
        return {"error": "Set REFERRAL_HUB_URL in .env to your actual referral page URL."}

    try:
        resp = requests.post(
            f"{CREATIFY_BASE}/link-to-videos/",
            json={
                "link":        url,
                "script":      script,
                "aspect_ratio": "9:16",
            },
            headers=_creatify_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        task = resp.json()
        task_id = task.get("id")
        logger.info(f"Creatify link-to-video task created: {task_id}")
    except Exception as e:
        return {"error": f"Creatify link-to-video failed: {e}"}

    return _creatify_poll(task_id, endpoint="link-to-videos")


def creatify_list_avatars() -> dict[str, Any]:
    """List available Creatify avatars."""
    if not _creatify_check_keys():
        return {"error": "Creatify API keys not set"}
    try:
        resp = requests.get(
            f"{CREATIFY_BASE}/avatars/",
            headers=_creatify_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _creatify_poll(
    task_id: str,
    endpoint: str,
    max_wait: int = 600,
    poll_every: int = 10,
) -> dict[str, Any]:
    """Poll a Creatify task until it completes or times out."""
    waited = 0
    while waited < max_wait:
        time.sleep(poll_every)
        waited += poll_every
        try:
            resp = requests.get(
                f"{CREATIFY_BASE}/{endpoint}/{task_id}/",
                headers=_creatify_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "").lower()
            logger.info(f"Creatify task {task_id} status: {status} ({waited}s elapsed)")

            if status == "done":
                video_url = data.get("output") or data.get("video_url") or data.get("url")
                return {
                    "success": True,
                    "provider": "creatify",
                    "task_id": task_id,
                    "video_url": video_url,
                    "data": data,
                }
            elif status in ("failed", "error"):
                return {
                    "error": f"Creatify task failed: {data.get('error_message', 'unknown')}",
                    "task_id": task_id,
                }
        except Exception as e:
            logger.warning(f"Poll error for {task_id}: {e}")

    return {"error": f"Creatify task {task_id} timed out after {max_wait}s"}


# ─── Provider 2: HeyGen ───────────────────────────────────────────────────────
# Best for: Avatar talking-head videos (person explains your earnings)
# Style:    "Someone on camera" without needing a camera
# Price:    $1 per minute of video (pay-as-you-go API)
# Docs:     https://docs.heygen.com/
# ─────────────────────────────────────────────────────────────────────────────

HEYGEN_BASE = "https://api.heygen.com"


def _heygen_headers() -> dict:
    return {
        "X-Api-Key":   HEYGEN_API_KEY,
        "Content-Type": "application/json",
    }


def heygen_list_avatars() -> dict[str, Any]:
    """List your HeyGen avatars."""
    if not HEYGEN_API_KEY:
        return {"error": "HEYGEN_API_KEY not set"}
    try:
        resp = requests.get(
            f"{HEYGEN_BASE}/v2/avatars",
            headers=_heygen_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def heygen_list_voices() -> dict[str, Any]:
    """List available HeyGen TTS voices."""
    if not HEYGEN_API_KEY:
        return {"error": "HEYGEN_API_KEY not set"}
    try:
        resp = requests.get(
            f"{HEYGEN_BASE}/v2/voices",
            headers=_heygen_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def heygen_generate_video(
    script: str,
    avatar_id: str | None = None,
    voice_id: str | None = None,
    dimension: dict | None = None,
) -> dict[str, Any]:
    """
    Generate a talking-head video with HeyGen.
    Your chosen avatar reads the earnings script.
    Cost: ~$1/minute of output video.
    """
    if not HEYGEN_API_KEY:
        return {"error": "HEYGEN_API_KEY not set in .env"}

    selected_avatar = avatar_id or os.environ.get("HEYGEN_AVATAR_ID", "")
    selected_voice  = voice_id  or os.environ.get("HEYGEN_VOICE_ID", "")

    if not selected_avatar:
        avatars = heygen_list_avatars()
        av_list = avatars.get("data", {}).get("avatars", [])
        if not av_list:
            return {
                "error": "No HeyGen avatars found. Create a photo avatar at heygen.com/photo-avatar"
            }
        selected_avatar = av_list[0]["avatar_id"]
        logger.info(f"Auto-selected HeyGen avatar: {selected_avatar}")

    if not selected_voice:
        voices = heygen_list_voices()
        v_list = voices.get("data", {}).get("voices", [])
        english = [v for v in v_list if v.get("language", "").startswith("en")]
        if english:
            selected_voice = english[0]["voice_id"]

    payload = {
        "video_inputs": [
            {
                "character": {
                    "type":      "avatar",
                    "avatar_id": selected_avatar,
                    "scale":     1.0,
                },
                "voice": {
                    "type":     "text",
                    "input_text": script,
                    "voice_id": selected_voice,
                },
                "background": {
                    "type":  "color",
                    "value": "#0a1628",  # dark navy — finance aesthetic
                },
            }
        ],
        "dimension": dimension or {"width": 1080, "height": 1920},  # 9:16 vertical
        "aspect_ratio": "9:16",
    }

    try:
        resp = requests.post(
            f"{HEYGEN_BASE}/v2/video/generate",
            json=payload,
            headers=_heygen_headers(),
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        video_id = data.get("data", {}).get("video_id")
        logger.info(f"HeyGen video task created: {video_id}")
    except Exception as e:
        return {"error": f"HeyGen generate failed: {e}"}

    return _heygen_poll(video_id)


def _heygen_poll(video_id: str, max_wait: int = 600, poll_every: int = 15) -> dict[str, Any]:
    """Poll HeyGen until video is ready."""
    waited = 0
    while waited < max_wait:
        time.sleep(poll_every)
        waited += poll_every
        try:
            resp = requests.get(
                f"{HEYGEN_BASE}/v1/video_status.get?video_id={video_id}",
                headers=_heygen_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            status = data.get("status", "").lower()
            logger.info(f"HeyGen {video_id} status: {status} ({waited}s elapsed)")

            if status == "completed":
                return {
                    "success": True,
                    "provider": "heygen",
                    "video_id": video_id,
                    "video_url": data.get("video_url"),
                    "thumbnail_url": data.get("thumbnail_url"),
                    "duration": data.get("duration"),
                }
            elif status == "failed":
                return {"error": f"HeyGen video failed: {data.get('error')}", "video_id": video_id}
        except Exception as e:
            logger.warning(f"HeyGen poll error: {e}")

    return {"error": f"HeyGen video {video_id} timed out after {max_wait}s"}


# ─── Provider 3: InVideo ──────────────────────────────────────────────────────
# Best for: Long-form explainer videos with stock footage
# Style:    Documentary/news explainer with auto-selected clips
# Price:    Check invideo.io/pricing
# Docs:     https://invideo.io/developer/
# ─────────────────────────────────────────────────────────────────────────────

INVIDEO_BASE = "https://api.invideo.io"


def invideo_generate_video(
    script: str,
    title: str = "Weekly Passive Income Report",
) -> dict[str, Any]:
    """
    Generate a stock-footage explainer video with InVideo.
    Script → AI selects relevant stock clips + adds captions + voice.
    """
    if not INVIDEO_API_KEY:
        return {"error": "INVIDEO_API_KEY not set in .env"}

    try:
        resp = requests.post(
            f"{INVIDEO_BASE}/v1/videos",
            json={
                "title":       title,
                "script":      script,
                "aspect_ratio": "9:16",
                "language":    "en",
            },
            headers={
                "Authorization": f"Bearer {INVIDEO_API_KEY}",
                "Content-Type":  "application/json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        video_id = data.get("id") or data.get("video_id")
        logger.info(f"InVideo task created: {video_id}")
        return {
            "success": True,
            "provider": "invideo",
            "video_id": video_id,
            "status": "processing",
            "message": (
                f"InVideo is generating your video (ID: {video_id}). "
                f"Check your InVideo dashboard or poll the status endpoint."
            ),
            "dashboard_url": "https://invideo.io/app/",
        }
    except Exception as e:
        return {"error": f"InVideo generate failed: {e}"}


# ─── Main entry point ─────────────────────────────────────────────────────────
def generate_finance_video(
    provider: str | None = None,
    week_iso: str | None = None,
    brief_id: int | None = None,
    video_style: str = "avatar",  # 'avatar' | 'link' | 'explainer'
    script_override: str | None = None,
) -> dict[str, Any]:
    """
    Generate a finance proof video using the chosen AI video platform.

    provider:    'creatify' | 'heygen' | 'invideo' (default: FINANCE_VIDEO_PROVIDER env)
    week_iso:    ISO week to pull earnings data for (default: current week)
    brief_id:    Use a specific brief's script (optional)
    video_style: 'avatar' (talking head) | 'link' (ad from URL) | 'explainer' (stock footage)
    """
    selected_provider = (provider or DEFAULT_PROVIDER).lower()
    week_iso = week_iso or _current_week()

    # ── Build script
    earnings = {}
    if script_override:
        script = script_override
    elif brief_id:
        # Fetch brief from DB
        brief = db.execute_one("SELECT trend_name, viral_hook, base_narrative FROM content_briefs WHERE id = %s", (brief_id,))
        if not brief:
            return {"error": f"Brief {brief_id} not found."}
        
        hook = brief.get("viral_hook", "")
        narrative = brief.get("base_narrative", "")
        content = f"{hook} {narrative}".strip()

        # Very simple extraction: use the brief content itself if short enough
        if len(content) > 300:
            script = content[:300]
        else:
            script = content
        
        if not script:
            script = brief.get("trend_name", "Trending Finance Topics")
    else:
        earnings = _get_week_earnings(week_iso)
        if not earnings:
            return {
                "error": f"No earnings data for {week_iso}.",
                "hint": "Drop screenshots into data/earnings_screenshots/ and run /earnings_scan first.",
            }
        script_style = "short"  # Revid and Creatify work best with short punchy scripts
        script = _build_script(earnings, style=script_style)

    logger.info(f"Generating video via {selected_provider} | style={video_style}")
    logger.info(f"Script ({len(script)} chars): {script[:100]}...")

    # ── Generate
    if selected_provider == "revid":
        result = revid_generate_video(
            script=script,
            background=video_style if video_style in REVID_BACKGROUNDS else None,
        )

    elif selected_provider == "creatify":
        if video_style == "link":
            result = creatify_generate_link_video(
                script=script,
                landing_url=earnings.get("referral_urls", [""])[0] if earnings else None,
            )
        else:
            result = creatify_generate_avatar_video(script=script)

    elif selected_provider == "heygen":
        result = heygen_generate_video(script=script)

    elif selected_provider == "invideo":
        result = invideo_generate_video(
            script=script,
            title=f"Passive Income Week {week_iso} — ${earnings.get('total', 0):.2f}",
        )

    else:
        return {
            "error": f"Unknown provider '{selected_provider}'",
            "valid": ["revid", "creatify", "heygen", "invideo"],
            "recommendation": "Use 'revid' for the @mini.money.matters brainrot style.",
        }

    if result.get("error"):
        return result

    # ── Save to DB
    video_id = _save_video_record(
        file_path=None,
        video_url=result.get("video_url"),
        provider=selected_provider,
        week_iso=week_iso,
        total=earnings.get("total", 0),
        external_id=str(result.get("task_id") or result.get("video_id") or ""),
    )

    return {
        **result,
        "db_video_id": video_id,
        "week_iso": week_iso,
        "total_earned": earnings.get("total", 0),
        "script_preview": script[:120] + "...",
        "message": (
            f"Video generated! db_video_id={video_id}. "
            + (f"Download from: {result.get('video_url')}" if result.get("video_url") else "")
        ),
    }


# ─── Worker entry point ────────────────────────────────────────────────────────
def main(body: dict | None = None, **kwargs) -> dict[str, Any]:
    if body is None:
        body = kwargs
    return generate_finance_video(
        provider=body.get("provider"),
        week_iso=body.get("week_iso"),
        brief_id=body.get("brief_id"),
        video_style=body.get("style", body.get("video_style", "avatar")),
        script_override=body.get("script"),
    )


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Finance AI Video Generator")
    parser.add_argument(
        "--provider", choices=["creatify", "heygen", "invideo"], default=DEFAULT_PROVIDER,
    )
    parser.add_argument("--week", type=str, default=None, help="ISO week e.g. 2026-W19")
    parser.add_argument("--style", choices=["avatar", "link", "explainer"], default="avatar")
    parser.add_argument("--brief-id", type=int, default=None)
    parser.add_argument("--script", type=str, default=None, help="Override script text")
    parser.add_argument(
        "--list-avatars", action="store_true",
        help="List available avatars for the chosen provider",
    )
    args = parser.parse_args()

    if args.list_avatars:
        if args.provider == "creatify":
            print(json.dumps(creatify_list_avatars(), indent=2))
        elif args.provider == "heygen":
            print(json.dumps(heygen_list_avatars(), indent=2))
        else:
            print("Avatar listing not supported for InVideo")
        sys.exit(0)

    result = generate_finance_video(
        provider=args.provider,
        week_iso=args.week,
        brief_id=args.brief_id,
        video_style=args.style,
        script_override=args.script,
    )
    print(json.dumps(result, indent=2, default=str))
