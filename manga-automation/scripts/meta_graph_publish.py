"""
Meta Graph API publishing: Instagram Reels, Facebook Page Reels, Threads video.

Requires publicly reachable HTTPS video URLs (Graph API does not accept local paths).

Env:
  META_API_KEY or META_ACCESS_TOKEN — fallback token if platform-specific vars unset
  INSTAGRAM_USER_ID + (INSTAGRAM_ACCESS_TOKEN | META_API_KEY) — Instagram Reels
  FACEBOOK_PAGE_ID + (FACEBOOK_PAGE_ACCESS_TOKEN | META_API_KEY) — Page Reels
  THREADS_USER_ID + (THREADS_ACCESS_TOKEN | META_API_KEY) — Threads video posts
  META_GRAPH_VERSION — default v22.0
  THREADS_GRAPH_BASE — default https://graph.threads.net/v1.0
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

_gv = (os.environ.get("META_GRAPH_VERSION") or "v22.0").strip()
GRAPH_VER = _gv if _gv.startswith("v") else f"v{_gv}"
FB_BASE = f"https://graph.facebook.com/{GRAPH_VER}"
THREADS_BASE = os.environ.get("THREADS_GRAPH_BASE", "https://graph.threads.net/v1.0").rstrip("/")


def _meta_fallback_token() -> str | None:
    return (
        (os.environ.get("META_API_KEY") or "").strip()
        or (os.environ.get("META_ACCESS_TOKEN") or "").strip()
        or None
    )


def instagram_access_token() -> str | None:
    # Prefer META_* when set so a newly rotated app token overrides stale per-platform vars.
    t = _meta_fallback_token() or (os.environ.get("INSTAGRAM_ACCESS_TOKEN") or "").strip()
    return t or None


def facebook_page_token() -> str | None:
    t = _meta_fallback_token() or (os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    return t or None


def threads_access_token() -> str | None:
    t = _meta_fallback_token() or (os.environ.get("THREADS_ACCESS_TOKEN") or "").strip()
    return t or None


def _poll_ig_container(creation_id: str, token: str, timeout_sec: int = 300, interval: int = 5) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        r = requests.get(
            f"{FB_BASE}/{creation_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        last = r.json() if r.content else {}
        if not r.ok:
            return {"ok": False, "error": f"status_check_http_{r.status_code}", "body": last}
        code = (last.get("status_code") or last.get("status") or "").upper()
        if code in ("FINISHED",):
            return {"ok": True, "status": code, "body": last}
        if code in ("ERROR", "EXPIRED"):
            return {"ok": False, "status": code, "body": last}
        time.sleep(interval)
    return {"ok": False, "error": "timeout_waiting_for_ig_container", "body": last}


def _poll_threads_container(container_id: str, token: str, timeout_sec: int = 300, interval: int = 10) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        r = requests.get(
            f"{THREADS_BASE}/{container_id}",
            params={"fields": "status,error_message", "access_token": token},
            timeout=30,
        )
        last = r.json() if r.content else {}
        if not r.ok:
            return {"ok": False, "error": f"threads_status_http_{r.status_code}", "body": last}
        status = (last.get("status") or "").upper()
        if status == "FINISHED":
            return {"ok": True, "status": status, "body": last}
        if status in ("ERROR", "EXPIRED", "PUBLISHED"):
            if status == "PUBLISHED":
                return {"ok": True, "status": status, "body": last}
            return {"ok": False, "status": status, "body": last}
        time.sleep(interval)
    return {"ok": False, "error": "timeout_waiting_for_threads_container", "body": last}


def post_instagram_reel(*, video_url: str, caption: str = "") -> dict[str, Any]:
    ig_user_id = (os.environ.get("INSTAGRAM_USER_ID") or "").strip()
    token = instagram_access_token()
    if not ig_user_id or not token:
        return {"success": False, "error": "Missing INSTAGRAM_USER_ID or token (INSTAGRAM_ACCESS_TOKEN / META_API_KEY)"}
    cap = (caption or "")[:2100]
    try:
        create = requests.post(
            f"{FB_BASE}/{ig_user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": cap,
                "access_token": token,
            },
            timeout=60,
        )
        cj = create.json() if create.content else {}
        if not create.ok:
            return {"success": False, "error": "instagram_media_create_failed", "http_status": create.status_code, "details": cj}
        creation_id = cj.get("id")
        if not creation_id:
            return {"success": False, "error": "instagram_missing_creation_id", "details": cj}

        polled = _poll_ig_container(str(creation_id), token)
        if not polled.get("ok"):
            return {"success": False, "error": polled.get("error") or polled.get("status"), "creation_id": creation_id, "poll": polled}

        publish = requests.post(
            f"{FB_BASE}/{ig_user_id}/media_publish",
            data={"creation_id": str(creation_id), "access_token": token},
            timeout=60,
        )
        pj = publish.json() if publish.content else {}
        if not publish.ok:
            return {"success": False, "error": "instagram_publish_failed", "http_status": publish.status_code, "creation_id": creation_id, "details": pj}
        return {"success": True, "platform": "instagram", "media_id": pj.get("id"), "creation_id": creation_id, "raw": pj}
    except requests.RequestException as e:
        return {"success": False, "error": str(e), "platform": "instagram"}


def post_facebook_page_reel(*, video_url: str, caption: str = "") -> dict[str, Any]:
    page_id = (os.environ.get("FACEBOOK_PAGE_ID") or "").strip()
    token = facebook_page_token()
    if not page_id or not token:
        return {"success": False, "error": "Missing FACEBOOK_PAGE_ID or token (FACEBOOK_PAGE_ACCESS_TOKEN / META_API_KEY)"}
    desc = (caption or "")[:2200]
    try:
        post = requests.post(
            f"{FB_BASE}/{page_id}/video_reels",
            data={
                "upload_phase": "finish",
                "video_url": video_url,
                "description": desc,
                "access_token": token,
            },
            timeout=120,
        )
        j = post.json() if post.content else {}
        if not post.ok:
            return {"success": False, "error": "facebook_video_reels_failed", "http_status": post.status_code, "details": j}
        vid = j.get("video_id") or j.get("id")
        return {"success": True, "platform": "facebook", "video_id": vid, "raw": j}
    except requests.RequestException as e:
        return {"success": False, "error": str(e), "platform": "facebook"}


def post_threads_video(*, video_url: str, text: str = "") -> dict[str, Any]:
    uid = (os.environ.get("THREADS_USER_ID") or "").strip()
    token = threads_access_token()
    if not uid or not token:
        return {"success": False, "error": "Missing THREADS_USER_ID or token (THREADS_ACCESS_TOKEN / META_API_KEY)"}
    try:
        create = requests.post(
            f"{THREADS_BASE}/{uid}/threads",
            data={
                "media_type": "VIDEO",
                "video_url": video_url,
                "text": (text or "")[:500],
                "access_token": token,
            },
            timeout=60,
        )
        cj = create.json() if create.content else {}
        if not create.ok:
            return {"success": False, "error": "threads_create_failed", "http_status": create.status_code, "details": cj}
        container_id = cj.get("id")
        if not container_id:
            return {"success": False, "error": "threads_missing_container_id", "details": cj}

        polled = _poll_threads_container(str(container_id), token)
        if not polled.get("ok"):
            return {"success": False, "error": polled.get("error") or polled.get("status"), "container_id": container_id, "poll": polled}

        time.sleep(int(os.environ.get("THREADS_PUBLISH_DELAY_SEC", "3")))

        publish = requests.post(
            f"{THREADS_BASE}/{uid}/threads_publish",
            data={"creation_id": str(container_id), "access_token": token},
            timeout=60,
        )
        pj = publish.json() if publish.content else {}
        if not publish.ok:
            return {"success": False, "error": "threads_publish_failed", "http_status": publish.status_code, "container_id": container_id, "details": pj}
        return {"success": True, "platform": "threads", "post_id": pj.get("id"), "container_id": container_id, "raw": pj}
    except requests.RequestException as e:
        return {"success": False, "error": str(e), "platform": "threads"}


def debug_connection() -> dict[str, Any]:
    """Validate token(s) against Graph without posting media."""
    out: dict[str, Any] = {"facebook_graph_me": None, "instagram_profile": None, "errors": []}
    tok = instagram_access_token()
    if tok:
        try:
            r = requests.get(f"{FB_BASE}/me", params={"fields": "id,name", "access_token": tok}, timeout=20)
            out["facebook_graph_me"] = {"ok": r.ok, "status": r.status_code, "data": r.json() if r.content else {}}
        except requests.RequestException as e:
            out["errors"].append(f"me: {e}")
    else:
        out["errors"].append("no_token_for_me_check")

    ig_id = (os.environ.get("INSTAGRAM_USER_ID") or "").strip()
    if tok and ig_id:
        try:
            r = requests.get(
                f"{FB_BASE}/{ig_id}",
                params={"fields": "id,username,profile_picture_url", "access_token": tok},
                timeout=20,
            )
            out["instagram_profile"] = {"ok": r.ok, "status": r.status_code, "data": r.json() if r.content else {}}
        except requests.RequestException as e:
            out["errors"].append(f"ig_profile: {e}")
    return out


def http_instagram(body: dict) -> dict[str, Any]:
    url = (body.get("video_url") or body.get("public_video_url") or "").strip()
    caption = body.get("caption") or body.get("text") or ""
    if not url:
        return {"success": False, "error": "video_url required (public HTTPS URL)"}
    return post_instagram_reel(video_url=url, caption=str(caption))


def http_facebook(body: dict) -> dict[str, Any]:
    url = (body.get("video_url") or body.get("public_video_url") or "").strip()
    caption = body.get("caption") or body.get("description") or ""
    if not url:
        return {"success": False, "error": "video_url required (public HTTPS URL)"}
    return post_facebook_page_reel(video_url=url, caption=str(caption))


def http_threads(body: dict) -> dict[str, Any]:
    url = (body.get("video_url") or body.get("public_video_url") or "").strip()
    text = body.get("text") or body.get("caption") or ""
    if not url:
        return {"success": False, "error": "video_url required (public HTTPS URL)"}
    return post_threads_video(video_url=url, text=str(text))


def main_cli() -> None:
    p = argparse.ArgumentParser(description="Post a clip via Meta Graph (Instagram / Facebook / Threads)")
    p.add_argument("--platform", choices=("instagram", "facebook", "threads"), required=True)
    p.add_argument("--video-url", default="", help="Public HTTPS URL to MP4/MOV (required unless --dry-run)")
    p.add_argument("--caption", default="", help="Caption (Instagram/Facebook) or text (Threads)")
    p.add_argument("--dry-run", action="store_true", help="Only validate token + IDs via Graph /me and IG profile")
    args = p.parse_args()

    if args.dry_run:
        print(json.dumps(debug_connection(), indent=2))
        return

    if not args.video_url:
        raise SystemExit("Provide --video-url with a public HTTPS URL, or use --dry-run")

    if args.platform == "instagram":
        result = post_instagram_reel(video_url=args.video_url, caption=args.caption)
    elif args.platform == "facebook":
        result = post_facebook_page_reel(video_url=args.video_url, caption=args.caption)
    else:
        result = post_threads_video(video_url=args.video_url, text=args.caption)

    print(json.dumps(result, indent=2, default=str))
    if not result.get("success"):
        raise SystemExit(1)


if __name__ == "__main__":
    main_cli()
