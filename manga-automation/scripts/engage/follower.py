#!/usr/bin/env python3
"""
Auto-follow automation for social platforms.
Follows accounts in target niches to grow network and engagement reciprocity.
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.engage.browser import launch_browser, navigate_to, sleep_human

logger = setup_logger("engage_follower")

MAX_FOLLOWS_PER_SESSION = int(os.environ.get("ENGAGE_MAX_FOLLOWS", "15"))
FOLLOW_COOLDOWN_HOURS = int(os.environ.get("ENGAGE_FOLLOW_COOLDOWN_HOURS", "24"))


def _get_follow_targets(platform: str, category_id: int | None = None) -> list[dict]:
    """Get accounts to follow from trend_intel or configured targets."""
    rows = db.execute(
        """SELECT DISTINCT source_engine, source, hashtag
           FROM trend_intel
           WHERE status = 'new'
           ORDER BY trend_velocity DESC
           LIMIT %s""",
        (MAX_FOLLOWS_PER_SESSION,),
    )
    return [dict(r) for r in rows]


async def follow_accounts(platform: str, target_urls: list[str]) -> int:
    """Follow accounts from a list of profile URLs."""
    followed = 0
    async with launch_browser() as ctx:
        page = ctx["page"]
        for url in target_urls[:MAX_FOLLOWS_PER_SESSION]:
            if not await navigate_to(page, url):
                continue
            try:
                # Generic follow button detection
                follow_btns = await page.query_selector_all(
                    'button:has-text("Follow"), [aria-label*="Follow"], [data-testid*="follow"]'
                )
                if follow_btns:
                    await follow_btns[0].click()
                    followed += 1
                    logger.info(f"Followed: {url}")
                await sleep_human()
            except Exception as exc:
                logger.debug(f"Follow failed for {url}: {exc}")

    return followed


def run_follows(platform: str, category_id: int | None = None) -> int:
    targets = _get_follow_targets(platform, category_id)
    urls = [t.get("source_url", "") for t in targets if t.get("source_url")]
    if not urls:
        logger.info(f"No follow targets found for {platform}")
        return 0
    return asyncio.run(follow_accounts(platform, urls))
