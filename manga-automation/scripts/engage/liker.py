#!/usr/bin/env python3
"""
Auto-like automation for social platforms.
Likes posts/comments matching target criteria (hashtags, niches, competitor content).
"""
from __future__ import annotations

import asyncio
import os
import random
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.engage.browser import launch_browser, navigate_to, sleep_human, random_scroll

logger = setup_logger("engage_liker")

MAX_LIKES_PER_SESSION = int(os.environ.get("ENGAGE_MAX_LIKES", "30"))
PLATFORM_LIKE_SELECTORS = {
    "tiktok": '[data-e2e="like-icon"]',
    "youtube": "#segmented-like-button button",
    "instagram": 'svg[aria-label="Like"]',
    "twitter": '[data-testid="like"]',
}


async def like_posts(platform: str, search_url: str, count: int = MAX_LIKES_PER_SESSION) -> int:
    """Navigate to a search/explore page and like posts."""
    selector = PLATFORM_LIKE_SELECTORS.get(platform)
    if not selector:
        logger.warning(f"No like selector configured for {platform}")
        return 0

    liked = 0
    async with launch_browser() as ctx:
        page = ctx["page"]
        if not await navigate_to(page, search_url):
            return 0

        for _ in range(min(count, MAX_LIKES_PER_SESSION)):
            try:
                buttons = await page.query_selector_all(selector)
                if not buttons:
                    await random_scroll(page)
                    continue
                btn = random.choice(buttons[:5])
                await btn.click()
                liked += 1
                await sleep_human()
            except Exception as exc:
                logger.debug(f"Like attempt failed: {exc}")
                break

    logger.info(f"Liked {liked} posts on {platform}")
    return liked


def run_likes(platform: str, search_url: str, count: int = MAX_LIKES_PER_SESSION) -> int:
    return asyncio.run(like_posts(platform, search_url, count))
