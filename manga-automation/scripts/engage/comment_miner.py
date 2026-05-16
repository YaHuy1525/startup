#!/usr/bin/env python3
"""
Comment mining engine — extracts high-conversion signals from social media comments.
Identifies buying intent, pain points, trending sentiment, and viral hooks.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("comment_miner")

# High-conversion signal patterns to detect in comments
SIGNAL_PATTERNS = {
    "buying_intent": [
        "where to buy", "how much", "price", "want this", "need this",
        "link", "shop", "purchase", "order", "get this",
    ],
    "pain_point": [
        "struggling with", "can't find", "hate when", "frustrated",
        "waste of", "doesn't work", "broken", "fix this",
    ],
    "viral_hook": [
        "wait for it", "watch till the end", "mind blown",
        "no way", "wtf", "holy", "insane", "this is crazy",
    ],
    "sentiment_positive": [
        "love this", "amazing", "best", "fire", "goated",
        "underrated", "gem", "perfect",
    ],
    "question_intent": [
        "how do", "what is", "can someone", "anyone know",
        "explain", "tutorial",
    ],
}


def mine_comments(comments: list[str]) -> list[dict[str, Any]]:
    """Analyze a batch of comments for high-conversion signals."""
    results: list[dict[str, Any]] = []
    for comment in comments:
        comment_lower = comment.lower()
        signals = {}
        for signal_type, patterns in SIGNAL_PATTERNS.items():
            matched = [p for p in patterns if p.lower() in comment_lower]
            if matched:
                signals[signal_type] = matched

        if signals:
            results.append({
                "comment": comment[:300],
                "signals": signals,
                "signal_types": list(signals.keys()),
                "score": len(signals) * 10,
            })
    return sorted(results, key=lambda x: x["score"], reverse=True)


def mine_from_platform(platform: str, content_url: str, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch and mine comments from a specific platform post."""
    # Placeholder: in production, scrape comments via Playwright or platform API
    try:
        rows = db.execute(
            """SELECT id, published_at FROM published_videos
               WHERE platform = %s AND platform_url = %s
               LIMIT 1""",
            (platform, content_url),
        )
        if not rows:
            logger.warning(f"Content not found: {platform} {content_url}")
            return []
    except Exception as exc:
        logger.warning(f"Database lookup failed: {exc}")
        return []

    logger.info(f"Mining comments for {platform} content: {content_url}")
    return []


def save_mining_results(platform: str, content_url: str, results: list[dict[str, Any]]) -> int:
    """Persist mined comment signals to database for content strategy optimization."""
    saved = 0
    for r in results[:20]:
        try:
            db.execute(
                """INSERT INTO comment_analytics
                   (platform, content_url, comment_text, signal_types, signal_score, mined_at)
                   VALUES (%s, %s, %s, %s, %s, NOW())""",
                (platform, content_url, r["comment"][:500],
                 json.dumps(r["signal_types"]), r["score"]),
            )
            saved += 1
        except Exception:
            pass
    return saved
