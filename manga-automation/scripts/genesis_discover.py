#!/usr/bin/env python3
"""
Pod 0 — Genesis Trending Discovery Agent.

Crawls public sources (Reddit JSON, HackerNews API, TikTok web) to discover
trending topics across configurable categories. Stores raw signals in
`genesis_signals` for downstream LLM evaluation.

No API keys required — all sources use public endpoints.

Usage:
    python scripts/genesis_discover.py [--categories fiction,tech,movies] [--limit 15]
"""
from __future__ import annotations

import json
import os
import sys
import time
import argparse
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("genesis_discover")

# ─── Configuration ───────────────────────────────────────────────────────────
USER_AGENT = os.environ.get(
    "GENESIS_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
)
REQUEST_TIMEOUT = int(os.environ.get("GENESIS_TIMEOUT", "15"))
REDDIT_DELAY = float(os.environ.get("GENESIS_REDDIT_DELAY", "2.0"))  # be polite


# ─── Reddit (public JSON — no API key needed) ────────────────────────────────
def scrape_reddit(subreddits: list[str], limit: int = 15) -> list[dict]:
    """
    Fetch hot posts from subreddits using Reddit's public `.json` endpoint.
    No OAuth token required.
    """
    signals: list[dict] = []
    headers = {"User-Agent": USER_AGENT}

    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}&raw_json=1"
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                logger.warning(f"Reddit rate-limited on r/{sub}, sleeping 10s")
                time.sleep(10)
                resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            posts = resp.json().get("data", {}).get("children", [])

            for post in posts:
                d = post.get("data", {})
                if d.get("stickied") or d.get("is_self") is False and not d.get("selftext"):
                    pass  # still process link posts — they have titles

                created_utc = d.get("created_utc", time.time())
                hours_age = max((time.time() - created_utc) / 3600, 0.1)
                score = d.get("score", 0)
                velocity = round(score / hours_age, 4)

                signals.append({
                    "source_platform": "reddit",
                    "source_url": f"https://www.reddit.com{d.get('permalink', '')}",
                    "title": d.get("title", "")[:500],
                    "body_preview": (d.get("selftext") or "")[:500],
                    "score": score,
                    "comment_count": d.get("num_comments", 0),
                    "velocity_score": velocity,
                    "subreddit": sub,
                })

            logger.info(f"r/{sub}: fetched {len(posts)} posts")
        except Exception as e:
            logger.error(f"Reddit r/{sub} failed: {e}")

        time.sleep(REDDIT_DELAY)  # rate-limit politeness

    return signals


# ─── HackerNews (public API — no key needed) ─────────────────────────────────
def scrape_hackernews(limit: int = 15) -> list[dict]:
    """
    Fetch top stories from HackerNews using the public Firebase API.
    """
    signals: list[dict] = []
    try:
        resp = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        story_ids = resp.json()[:limit]

        for sid in story_ids:
            try:
                item = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=REQUEST_TIMEOUT,
                ).json()
                if not item or item.get("type") != "story":
                    continue

                created_utc = item.get("time", time.time())
                hours_age = max((time.time() - created_utc) / 3600, 0.1)
                score = item.get("score", 0)
                velocity = round(score / hours_age, 4)

                signals.append({
                    "source_platform": "hackernews",
                    "source_url": item.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                    "title": item.get("title", "")[:500],
                    "body_preview": "",
                    "score": score,
                    "comment_count": item.get("descendants", 0),
                    "velocity_score": velocity,
                })
            except Exception as e:
                logger.debug(f"HN item {sid} failed: {e}")

        logger.info(f"HackerNews: fetched {len(signals)} stories")
    except Exception as e:
        logger.error(f"HackerNews top stories failed: {e}")

    return signals


# ─── TikTok (public web scrape — no API key needed) ──────────────────────────
async def _scrape_tiktok_nodriver(hashtags: list[str], limit: int = 10) -> list[dict]:
    import nodriver as uc
    import asyncio
    import re

    signals = []
    browser = await uc.start()
    for tag in hashtags[:limit]:
        clean_tag = tag.lstrip("#").strip()
        if not clean_tag:
            continue
        url = f"https://www.tiktok.com/tag/{clean_tag}"
        try:
            page = await browser.get(url)
            await asyncio.sleep(4)  # Wait for JS execution
            content = await page.get_content()
            
            view_match = re.search(r'"viewCount"\s*:\s*(\d+)', content)
            video_match = re.search(r'"videoCount"\s*:\s*(\d+)', content)
            
            view_count = int(view_match.group(1)) if view_match else 0
            video_count = int(video_match.group(1)) if video_match else 0
            
            if view_count > 0:
                signals.append({
                    "source_platform": "tiktok",
                    "source_url": url,
                    "title": f"#{clean_tag} trending on TikTok",
                    "body_preview": f"Views: {view_count:,} | Videos: {video_count:,}",
                    "score": view_count,
                    "comment_count": video_count,
                    "velocity_score": round(view_count / 1_000_000, 4),
                })
                logger.info(f"TikTok #{clean_tag} (nodriver): views={view_count:,}")
            else:
                signals.append({
                    "source_platform": "tiktok",
                    "source_url": url,
                    "title": f"#{clean_tag} (seed — views not found)",
                    "body_preview": "",
                    "score": 0,
                    "comment_count": 0,
                    "velocity_score": 0,
                })
        except Exception as e:
            logger.warning(f"TikTok #{clean_tag} scrape failed via nodriver: {e}")
    
    # Properly close nodriver
    try:
        browser.stop()
    except Exception:
        pass
    return signals


def scrape_tiktok_hashtags(hashtags: list[str], limit: int = 10) -> list[dict]:
    """
    Lightweight scrape of TikTok hashtag pages for viewcount and post metadata.
    Falls back to returning seed data if scraping is blocked.
    Uses curl_cffi for TLS fingerprint bypass if available.
    """
    signals: list[dict] = []
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Try curl_cffi first for TLS fingerprint bypass
    use_curl_cffi = False
    try:
        from curl_cffi import requests as cffi_requests
        use_curl_cffi = True
    except ImportError:
        pass

    # Try nodriver first (async)
    try:
        import nodriver
        import asyncio
        return asyncio.run(_scrape_tiktok_nodriver(hashtags, limit))
    except ImportError:
        logger.info("nodriver not installed, falling back to curl_cffi/requests")
    except Exception as e:
        logger.warning(f"nodriver execution failed: {e}")

    # Fallback logic
    for tag in hashtags[:limit]:
        clean_tag = tag.lstrip("#").strip()
        if not clean_tag:
            continue

        url = f"https://www.tiktok.com/tag/{clean_tag}"
        try:
            if use_curl_cffi:
                resp = cffi_requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, impersonate="chrome")
            else:
                resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                text = resp.text
                import re
                view_match = re.search(r'"viewCount"\s*:\s*(\d+)', text)
                video_match = re.search(r'"videoCount"\s*:\s*(\d+)', text)

                view_count = int(view_match.group(1)) if view_match else 0
                video_count = int(video_match.group(1)) if video_match else 0

                signals.append({
                    "source_platform": "tiktok",
                    "source_url": url,
                    "title": f"#{clean_tag} trending on TikTok",
                    "body_preview": f"Views: {view_count:,} | Videos: {video_count:,}",
                    "score": view_count,
                    "comment_count": video_count,
                    "velocity_score": round(view_count / 1_000_000, 4) if view_count else 0,
                })
                logger.info(f"TikTok #{clean_tag} (fallback): views={view_count:,}")
            else:
                logger.warning(f"TikTok #{clean_tag} (fallback): HTTP {resp.status_code}")
                signals.append({
                    "source_platform": "tiktok",
                    "source_url": url,
                    "title": f"#{clean_tag} (seed — scrape blocked)",
                    "body_preview": "",
                    "score": 0,
                    "comment_count": 0,
                    "velocity_score": 0,
                })
        except Exception as e:
            logger.warning(f"TikTok #{clean_tag} scrape failed: {e}")

        time.sleep(1)

    return signals


# ─── Database Persistence ────────────────────────────────────────────────────
def save_signals(category_id: int, signals: list[dict]) -> int:
    """Upsert raw signals into genesis_signals. Returns count saved."""
    saved = 0
    for s in signals:
        if not s.get("source_url"):
            continue
        try:
            db.execute(
                """
                INSERT INTO genesis_signals
                    (category_id, source_platform, source_url, title,
                     body_preview, score, comment_count, velocity_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_platform, source_url) DO UPDATE SET
                    score          = EXCLUDED.score,
                    comment_count  = EXCLUDED.comment_count,
                    velocity_score = EXCLUDED.velocity_score,
                    scraped_at     = NOW()
                """,
                (
                    category_id,
                    s["source_platform"],
                    s["source_url"][:2000],
                    s["title"][:500],
                    (s.get("body_preview") or "")[:500],
                    s.get("score", 0),
                    s.get("comment_count", 0),
                    s.get("velocity_score", 0),
                ),
            )
            saved += 1
        except Exception as e:
            logger.error(f"Failed to save signal '{s.get('title', '')[:60]}': {e}")
    return saved


def get_categories(slugs: list[str] | None = None) -> list[dict]:
    """Fetch active categories, optionally filtered by slug list."""
    if slugs:
        placeholders = ",".join(["%s"] * len(slugs))
        return db.execute(
            f"SELECT * FROM genesis_categories WHERE is_active = true AND slug IN ({placeholders})",
            tuple(slugs),
        )
    return db.execute("SELECT * FROM genesis_categories WHERE is_active = true")


# ─── Main Orchestrator ───────────────────────────────────────────────────────
def discover(categories: list[str] | None = None, limit: int = 15) -> dict[str, Any]:
    """
    Run the full discovery pipeline across all active categories.
    Returns summary stats.
    """
    cats = get_categories(categories)
    if not cats:
        logger.warning("No active categories found. Run migration 010 first.")
        return {"error": "No categories found", "categories_checked": 0}

    results: dict[str, Any] = {
        "categories_checked": len(cats),
        "total_signals": 0,
        "total_saved": 0,
        "per_category": {},
    }

    for cat in cats:
        cat_slug = cat["slug"]
        cat_id = cat["id"]
        cat_signals: list[dict] = []
        subreddits = cat.get("subreddits") or []
        tiktok_tags = cat.get("tiktok_hashtags") or []
        use_hn = cat.get("hackernews", False)

        logger.info(f"── Discovering: {cat['display_name']} ({cat_slug}) ──")

        # Reddit
        if subreddits:
            reddit_signals = scrape_reddit(subreddits, limit=limit)
            cat_signals.extend(reddit_signals)

        # HackerNews
        if use_hn:
            hn_signals = scrape_hackernews(limit=limit)
            cat_signals.extend(hn_signals)

        # TikTok
        if tiktok_tags:
            tt_signals = scrape_tiktok_hashtags(tiktok_tags, limit=limit)
            cat_signals.extend(tt_signals)

        # Persist
        saved = save_signals(cat_id, cat_signals)

        results["total_signals"] += len(cat_signals)
        results["total_saved"] += saved
        results["per_category"][cat_slug] = {
            "signals": len(cat_signals),
            "saved": saved,
            "sources": {
                "reddit": sum(1 for s in cat_signals if s["source_platform"] == "reddit"),
                "hackernews": sum(1 for s in cat_signals if s["source_platform"] == "hackernews"),
                "tiktok": sum(1 for s in cat_signals if s["source_platform"] == "tiktok"),
            },
        }

    logger.info(
        f"Discovery complete: {results['total_signals']} signals across "
        f"{results['categories_checked']} categories, {results['total_saved']} saved"
    )
    return results


def main(body: dict | None = None, **kwargs) -> dict:
    """Entry point for worker.py integration."""
    if body is None:
        body = kwargs
    categories_raw = body.get("categories") or body.get("category")
    limit = int(body.get("limit", 15))

    if isinstance(categories_raw, str):
        categories = [c.strip() for c in categories_raw.split(",") if c.strip()]
    elif isinstance(categories_raw, list):
        categories = categories_raw
    else:
        categories = None

    return discover(categories=categories, limit=limit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genesis Trending Discovery Agent")
    parser.add_argument("--categories", type=str, default=None,
                        help="Comma-separated category slugs (e.g., 'fiction,tech,movies')")
    parser.add_argument("--limit", type=int, default=15,
                        help="Max items per source per category")
    args = parser.parse_args()

    cats = [c.strip() for c in args.categories.split(",")] if args.categories else None
    result = discover(categories=cats, limit=args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))
