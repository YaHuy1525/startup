#!/usr/bin/env python3
"""
Playwright browser controller for cross-platform engagement automation.
Handles stealth launch, session management, and common actions (click, type, scroll).

Reuses patterns from scripts/rpa/ — headless by default, proxy-aware,
with human-like delays between actions.
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils.logger import setup_logger

logger = setup_logger("engage_browser")

HEADLESS = os.environ.get("ENGAGE_HEADLESS", "1").strip() in ("1", "true", "yes")
PROXY_URL = os.environ.get("ENGAGE_PROXY_URL", "")
MIN_DELAY_MS = int(os.environ.get("ENGAGE_MIN_DELAY_MS", "500"))
MAX_DELAY_MS = int(os.environ.get("ENGAGE_MAX_DELAY_MS", "3000"))


async def _ensure_stealth(browser_context):
    try:
        from playwright_stealth import Stealth
        await Stealth().apply_async(browser_context)
    except ImportError:
        pass


async def sleep_human():
    """Sleep for a random duration mimicking human pauses."""
    await asyncio.sleep(random.uniform(MIN_DELAY_MS / 1000, MAX_DELAY_MS / 1000))


@asynccontextmanager
async def launch_browser() -> AsyncIterator[dict[str, Any]]:
    """Launch a stealth Playwright browser. Yields {browser, context, page}."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("playwright not installed: pip install playwright && playwright install")
        raise

    launch_args: dict[str, Any] = {"headless": HEADLESS}
    if PROXY_URL:
        launch_args["proxy"] = {"server": PROXY_URL}

    pw = await async_playwright()
    browser = await pw.chromium.launch(**launch_args)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    )
    await _ensure_stealth(context)
    page = await context.new_page()

    try:
        yield {"browser": browser, "context": context, "page": page}
    finally:
        await context.close()
        await browser.close()
        await pw.__aexit__()


async def navigate_to(page, url: str, wait_until: str = "domcontentloaded") -> bool:
    """Navigate to a URL with error handling. Returns True on success."""
    try:
        await page.goto(url, wait_until=wait_until, timeout=30_000)
        await sleep_human()
        return True
    except Exception as exc:
        logger.warning(f"Navigation failed to {url}: {exc}")
        return False


async def random_scroll(page) -> None:
    """Perform a human-like random scroll."""
    scroll_amount = random.randint(300, 1200)
    await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
    await sleep_human()
