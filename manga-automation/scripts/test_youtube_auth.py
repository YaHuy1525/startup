#!/usr/bin/env python3
"""
Validate YouTube OAuth credentials for Shorts uploads.

Checks:
1) Required env vars exist
2) Refresh token can mint an access token
3) Scope includes youtube.upload
4) Optional: calls channels.list(mine=true) to verify account access
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()

REQUIRED_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def _error(message: str, details: Any | None = None) -> dict:
    return {"ok": False, "error": message, "details": details}


def run_auth_test(check_channel: bool = True) -> dict:
    client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()

    missing = [
        key
        for key, value in (
            ("YOUTUBE_CLIENT_ID", client_id),
            ("YOUTUBE_CLIENT_SECRET", client_secret),
            ("YOUTUBE_REFRESH_TOKEN", refresh_token),
        )
        if not value
    ]
    if missing:
        return _error("Missing required env vars", {"missing": missing})

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except Exception as exc:
        return _error(
            "google auth dependencies missing",
            {"message": str(exc), "hint": "pip install google-auth google-api-python-client"},
        )

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=[REQUIRED_SCOPE],
        )
        creds.refresh(Request())
    except Exception as exc:
        return _error(
            "Refresh token exchange failed",
            {
                "message": str(exc),
                "hint": "Regenerate token with youtube.upload scope and prompt=consent",
            },
        )

    scopes = list(creds.scopes or [])
    if REQUIRED_SCOPE not in scopes:
        return _error(
            "Required scope missing from credentials",
            {"required": REQUIRED_SCOPE, "scopes": scopes},
        )

    result = {
        "ok": True,
        "access_token_obtained": bool(creds.token),
        "scopes": scopes,
    }

    if check_channel:
        try:
            import googleapiclient.discovery

            youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
            response = youtube.channels().list(part="snippet", mine=True, maxResults=1).execute()
            items = response.get("items", [])
            if items:
                channel = items[0]
                result["channel"] = {
                    "id": channel.get("id"),
                    "title": channel.get("snippet", {}).get("title"),
                }
            else:
                result["channel"] = None
                result["warning"] = "No channel returned for mine=true"
        except Exception as exc:
            return _error(
                "Token refreshed but channel lookup failed",
                {"message": str(exc), "hint": "Token may be valid but account/channel permissions are incomplete"},
            )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Test YouTube OAuth upload credentials")
    parser.add_argument("--no-channel-check", action="store_true", help="Skip channels.list(mine=true)")
    args = parser.parse_args()

    result = run_auth_test(check_channel=not args.no_channel_check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
