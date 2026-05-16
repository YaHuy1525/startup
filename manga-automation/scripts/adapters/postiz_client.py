#!/usr/bin/env python3
"""
Postiz Public API client (agent-friendly alternative to DIY scrapers).

Official flows use OAuth-connected channels in Postiz; this module only calls
HTTPS endpoints documented at https://docs.postiz.com/public-api

Self-host: set POSTIZ_PUBLIC_API_BASE to
  https://<your-backend-host>/public/v1
Cloud: default https://api.postiz.com/public/v1

Authentication: Settings → Developers → Public API → API key in Authorization header.

Rate limit: 30 requests/hour — batch schedules when possible.

This file is boilerplate: fill integration IDs from GET /integrations responses.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils.logger import setup_logger

logger = setup_logger("postiz_client")

DEFAULT_BASE = os.environ.get(
    "POSTIZ_PUBLIC_API_BASE",
    "https://api.postiz.com/public/v1",
).rstrip("/")
API_KEY = os.environ.get("POSTIZ_API_KEY", "")


def _headers() -> dict[str, str]:
    if not API_KEY:
        raise ValueError("POSTIZ_API_KEY is not set")
    return {"Authorization": API_KEY}


def list_integrations() -> dict[str, Any]:
    """GET /integrations — map Postiz 'channels' to API integration ids."""
    r = requests.get(f"{DEFAULT_BASE}/integrations", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def upload_media(file_path: str) -> dict[str, Any]:
    """POST multipart /upload — returns asset id/path for posts payload."""
    with open(file_path, "rb") as f:
        r = requests.post(
            f"{DEFAULT_BASE}/upload",
            headers={"Authorization": API_KEY},
            files={"file": (os.path.basename(file_path), f)},
            timeout=120,
        )
    r.raise_for_status()
    return r.json()


def create_posts(payload: dict[str, Any]) -> dict[str, Any]:
    """
    POST /posts — body matches Postiz docs (type schedule|now, posts[], etc.).

    Example Pinterest video pin — build `value`/`settings` via Postiz UI wizard
    (docs: Generate Output) once, then replay JSON here.
    """
    r = requests.post(
        f"{DEFAULT_BASE}/posts",
        headers=_headers(),
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def schedule_pinterest_pin(
    integration_id: str,
    *,
    board_id_or_name: str,
    title: str,
    link: str,
    caption: str,
    media_upload_id: str | None,
    media_path: str | None,
    schedule_iso: str | None,
) -> dict[str, Any]:
    """
    Minimal Pinterest-shaped payload (__type pinterest). Prefer generated wizard JSON.

    If you only have local file paths, upload_media first and pass id/path.
    """
    images: list[dict[str, Any]] = []
    if media_upload_id and media_path:
        images.append({"id": media_upload_id, "path": media_path})

    post_type = "schedule" if schedule_iso else "now"
    payload: dict[str, Any] = {
        "type": post_type,
        "date": schedule_iso or "2026-05-02T12:00:00.000Z",
        "shortLink": False,
        "tags": [],
        "posts": [
            {
                "integration": {"id": integration_id},
                "value": [{"content": caption, "image": images}],
                "settings": {
                    "__type": "pinterest",
                    "board": board_id_or_name,
                    "title": title,
                    "link": link,
                },
            }
        ],
    }
    return create_posts(payload)


def main(body: dict | None = None, **kwargs) -> dict[str, Any]:
    """Worker entry: action list_integrations | upload | create_posts | schedule_pinterest."""
    if body is None:
        body = kwargs
    action = body.get("action", "list_integrations")
    try:
        if action == "list_integrations":
            return {"ok": True, "data": list_integrations()}
        if action == "upload":
            path = body.get("file_path") or body.get("path")
            if not path:
                return {"ok": False, "error": "file_path required"}
            return {"ok": True, "data": upload_media(path)}
        if action == "create_posts":
            payload = body.get("payload")
            if not isinstance(payload, dict):
                return {"ok": False, "error": "payload dict required"}
            return {"ok": True, "data": create_posts(payload)}
        if action == "schedule_pinterest":
            return {
                "ok": True,
                "data": schedule_pinterest_pin(
                    body["integration_id"],
                    board_id_or_name=body.get("board", ""),
                    title=body.get("title", ""),
                    link=body.get("link", "https://example.com"),
                    caption=body.get("caption", ""),
                    media_upload_id=body.get("media_id"),
                    media_path=body.get("media_path"),
                    schedule_iso=body.get("schedule_iso"),
                ),
            }
        if action in ("schedule_brief", "resolve_integrations"):
            from scripts.adapters import postiz_bridge

            return postiz_bridge.main(body)
        return {"ok": False, "error": f"unknown action {action}"}
    except Exception as e:
        logger.exception("Postiz API error")
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    print(json.dumps(main({"action": "list_integrations"}), indent=2, default=str))
