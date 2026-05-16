#!/usr/bin/env python3
"""
Marketplace listing automation — BOILERPLATE for Gumroad, Etsy digital delivery.

Official APIs require human approval steps (Etsy OAuth app review). Implement:
  - Gumroad: POST product via Gumroad REST (API key per account)
  - Etsy: Etsy Open API v3 — listings + digital file attachment after onboarding

Until keys exist, this returns structured readiness checks only.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils.logger import setup_logger

logger = setup_logger("marketplace_listings")

GUMROAD_TOKEN = os.environ.get("GUMROAD_API_TOKEN", "")
ETSY_API_KEY = os.environ.get("ETSY_API_KEYSTRING", "")
ETSY_SECRET = os.environ.get("ETSY_API_SECRET", "")


def gumroad_ping() -> dict[str, Any]:
    if not GUMROAD_TOKEN:
        return {"ok": False, "platform": "gumroad", "error": "GUMROAD_API_TOKEN unset"}
    r = requests.get(
        "https://api.gumroad.com/v2/user",
        params={"access_token": GUMROAD_TOKEN},
        timeout=30,
    )
    if r.ok:
        return {"ok": True, "platform": "gumroad", "user": r.json()}
    return {"ok": False, "platform": "gumroad", "status": r.status_code, "body": r.text[:500]}


def etsy_ping() -> dict[str, Any]:
    if not (ETSY_API_KEY and ETSY_SECRET):
        return {
            "ok": False,
            "platform": "etsy",
            "error": "ETSY_API_KEYSTRING and ETSY_API_SECRET required for OAuth onboarding",
        }
    return {
        "ok": False,
        "platform": "etsy",
        "keys_present": True,
        "note": (
            "Keys present — implement OAuth token storage, then POST /shops/{id}/listings "
            "per https://developers.etsy.com/ (automated listings not wired in this boilerplate)."
        ),
    }


def main(body: dict | None = None, **kwargs) -> dict[str, Any]:
    if body is None:
        body = kwargs
    platform = body.get("platform", "gumroad")
    if platform == "gumroad":
        return gumroad_ping()
    if platform == "etsy":
        return etsy_ping()
    return {"ok": False, "error": f"unknown platform {platform}"}


if __name__ == "__main__":
    print(json.dumps(main({}), indent=2))
