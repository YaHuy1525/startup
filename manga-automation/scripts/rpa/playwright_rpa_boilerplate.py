#!/usr/bin/env python3
"""
Playwright-based RPA fallbacks for platforms with weak / no APIs.

Safeguards:
  RPA_DRY_RUN=1 (default) — only open creator URL; never log in or submit
  RPA_CONFIRM_UPLOAD=1   — required to run login_flow + upload_flow
  Set RPA_DRY_RUN=0 and RPA_CONFIRM_UPLOAD=1 for real uploads.

Env:
  RPA_HEADLESS=0 recommended; HTTP_PROXY / HTTPS_PROXY for residential proxy.
  playwright-stealth optional; strengthens basic fingerprint hygiene only.

Selectors are PLACEHOLDERS — regenerate with Playwright Codegen against live UI.

Usage: POST /rpa/session { "target": "pinterest", "dry_run": true }
"""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils.logger import setup_logger
from scripts.rpa.human_behavior import sleep_between_actions

logger = setup_logger("playwright_rpa")

HEADLESS = os.environ.get("RPA_HEADLESS", "0").strip() in ("1", "true", "yes")


def _playwright_cm():
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        return Stealth().use_async(async_playwright())
    except ImportError:
        logger.warning(
            "playwright-stealth not installed — using plain Playwright "
            "(pip install playwright-stealth)"
        )
        from playwright.async_api import async_playwright

        return async_playwright()


class WebUploaderRPA(ABC):
    login_url: str = ""
    create_url: str = ""

    @abstractmethod
    async def login_flow(self, page: Any) -> None:
        ...

    @abstractmethod
    async def upload_flow(
        self, page: Any, media_path: str, caption: str
    ) -> dict[str, Any]:
        ...


class PinterestWebRPA(WebUploaderRPA):
    login_url = "https://www.pinterest.com/login/"
    create_url = "https://www.pinterest.com/pin-builder/"

    async def login_flow(self, page: Any) -> None:
        email = os.environ.get("RPA_PINTEREST_EMAIL", "")
        password = os.environ.get("RPA_PINTEREST_PASSWORD", "")
        if not email or not password:
            raise ValueError("Set RPA_PINTEREST_EMAIL and RPA_PINTEREST_PASSWORD for RPA login")
        await page.goto(self.login_url)
        sleep_between_actions()
        await page.get_by_label("Email").fill(email)
        sleep_between_actions()
        await page.get_by_label("Password").fill(password)
        sleep_between_actions()
        await page.get_by_role("button", name="Log in").click()

    async def upload_flow(
        self, page: Any, media_path: str, caption: str
    ) -> dict[str, Any]:
        await page.goto(self.create_url)
        sleep_between_actions()
        logger.warning("Pinterest upload_flow uses placeholders — configure via codegen")
        return {"ok": False, "error": "placeholder_upload_flow_not_configured"}


class SnapchatWebStubRPA(WebUploaderRPA):
    login_url = "https://accounts.snapchat.com/"
    create_url = "https://web.snapchat.com/"

    async def login_flow(self, page: Any) -> None:
        raise NotImplementedError("Snapchat RPA stub — partner tools / manual preferred")

    async def upload_flow(
        self, page: Any, media_path: str, caption: str
    ) -> dict[str, Any]:
        raise NotImplementedError("Snapchat RPA stub")


class FacebookReelsStubRPA(WebUploaderRPA):
    login_url = "https://www.facebook.com/login/"
    create_url = "https://www.facebook.com/reel/create/"

    async def login_flow(self, page: Any) -> None:
        raise NotImplementedError("Prefer Graph API / official uploaders — RPA last resort")

    async def upload_flow(
        self, page: Any, media_path: str, caption: str
    ) -> dict[str, Any]:
        raise NotImplementedError("Facebook Reels RPA stub")


async def _run_target_async(
    target: str,
    media_path: str,
    caption: str,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    forced_dry = os.environ.get("RPA_DRY_RUN", "1").strip() in ("1", "true", "yes")
    effective_dry = dry_run or forced_dry

    if target == "pinterest":
        impl: WebUploaderRPA = PinterestWebRPA()
    elif target == "snapchat":
        impl = SnapchatWebStubRPA()
    elif target in ("facebook", "facebook_reels"):
        impl = FacebookReelsStubRPA()
    else:
        return {"ok": False, "error": f"unknown target {target}"}

    cm = _playwright_cm()
    async with cm as p:
        proxy_env = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        launch: dict[str, Any] = {
            "headless": HEADLESS,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if proxy_env:
            launch["proxy"] = {"server": proxy_env}

        browser = await p.chromium.launch(**launch)
        context = await browser.new_context(
            locale=os.environ.get("RPA_BROWSER_LOCALE", "en-AU"),
            timezone_id=os.environ.get("RPA_BROWSER_TIMEZONE", "Australia/Melbourne"),
        )
        page = await context.new_page()

        try:
            if effective_dry:
                await page.goto(impl.create_url, wait_until="domcontentloaded", timeout=60_000)
                sleep_between_actions()
                title = await page.title()
                return {
                    "ok": True,
                    "dry_run": True,
                    "target": target,
                    "page_title": title,
                    "note": "opened creator URL only; no login/upload",
                }

            confirm = os.environ.get("RPA_CONFIRM_UPLOAD", "0").strip() in ("1", "true", "yes")
            if not confirm:
                return {
                    "ok": False,
                    "error": "Set RPA_CONFIRM_UPLOAD=1 and RPA_DRY_RUN=0 for real uploads",
                }

            await impl.login_flow(page)
            sleep_between_actions()
            out = await impl.upload_flow(page, media_path, caption)
            out.setdefault("target", target)
            return out
        finally:
            await context.close()
            await browser.close()


def main(body: dict | None = None, **kwargs) -> dict[str, Any]:
    import asyncio

    if body is None:
        body = kwargs
    target = body.get("target", "pinterest")
    media = body.get("video_path") or body.get("media_path") or ""
    caption = body.get("caption", "")
    dry = bool(body.get("dry_run", True))

    try:
        return asyncio.run(
            _run_target_async(target, media, caption, dry_run=dry)
        )
    except NotImplementedError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("RPA failure")
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    import json

    print(json.dumps(main({"target": "pinterest", "dry_run": True}), indent=2))
