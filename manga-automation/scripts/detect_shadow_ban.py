#!/usr/bin/env python3
"""
Detect shadow bans by analysing the FYP-to-total-views ratio for each TikTok account.
Flags accounts where FYP% < threshold over the last N posts.

Usage:
    python3 scripts/detect_shadow_ban.py [--min-posts 5] [--threshold 0.10]

Output:
    JSON with list of checked accounts and their shadow-ban status.
    Exit 0 always (shadow bans are reported in output, not as an error code).
"""
import sys
import json
import argparse
import os
from dotenv import load_dotenv

load_dotenv()

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("detect_shadow_ban")

DEFAULT_THRESHOLD = float(os.environ.get("SHADOW_BAN_FYP_THRESHOLD", 0.10))
DEFAULT_MIN_POSTS = 5


def get_accounts() -> list[dict]:
    return db.execute(
        "SELECT id, username, shadow_banned FROM tiktok_accounts WHERE account_status != 'banned'"
    )


def get_recent_analytics(account_id: int, min_posts: int) -> list[dict]:
    return db.execute(
        """
        SELECT va.views, va.fyp_views, va.following_views, pv.published_at
        FROM video_analytics va
        JOIN published_videos pv ON va.published_video_id = pv.id
        WHERE pv.account_id = %s
        ORDER BY pv.published_at DESC
        LIMIT %s
        """,
        (account_id, min_posts),
    )


def compute_fyp_percentage(analytics: list[dict]) -> float:
    """Average FYP% across all posts. 0.0 if no data."""
    valid = [a for a in analytics if (a.get("views") or 0) > 0]
    if not valid:
        return 1.0  # No data → assume fine
    ratios = [
        (a.get("fyp_views") or 0) / a["views"]
        for a in valid
    ]
    return sum(ratios) / len(ratios)


def flag_shadow_banned(account_id: int, fyp_pct: float):
    db.execute(
        """
        UPDATE tiktok_accounts
        SET shadow_banned = true, shadow_ban_detected_at = NOW()
        WHERE id = %s
        """,
        (account_id,),
    )
    db.execute(
        """
        INSERT INTO shadow_ban_events
            (account_id, detected_at, detection_method, fyp_percentage)
        VALUES (%s, NOW(), 'fyp_percentage', %s)
        """,
        (account_id, round(fyp_pct * 100, 2)),
    )
    logger.warning(f"Account id={account_id} flagged as shadow-banned (FYP%={fyp_pct:.1%})")


def clear_shadow_ban(account_id: int):
    db.execute(
        """
        UPDATE tiktok_accounts
        SET shadow_banned = false, shadow_ban_detected_at = NULL
        WHERE id = %s
        """,
        (account_id,),
    )
    db.execute(
        """
        UPDATE shadow_ban_events
        SET resolved_at = NOW()
        WHERE account_id = %s AND resolved_at IS NULL
        """,
        (account_id,),
    )
    logger.info(f"Account id={account_id} shadow-ban cleared")


def main(min_posts: int = DEFAULT_MIN_POSTS, threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    accounts = get_accounts()
    results = []

    for acct in accounts:
        analytics = get_recent_analytics(acct["id"], min_posts)

        if len(analytics) < min_posts:
            logger.info(f"Account '{acct['username']}' has <{min_posts} posts, skipping")
            results.append({
                "account_id": acct["id"],
                "username": acct["username"],
                "status": "insufficient_data",
                "fyp_percentage": None,
                "shadow_banned": acct["shadow_banned"],
            })
            continue

        fyp_pct = compute_fyp_percentage(analytics)
        is_banned = fyp_pct < threshold

        if is_banned and not acct["shadow_banned"]:
            flag_shadow_banned(acct["id"], fyp_pct)
        elif not is_banned and acct["shadow_banned"]:
            clear_shadow_ban(acct["id"])

        results.append({
            "account_id": acct["id"],
            "username": acct["username"],
            "fyp_percentage": round(fyp_pct * 100, 2),
            "threshold_pct": round(threshold * 100, 2),
            "shadow_banned": is_banned,
            "status": "shadow_banned" if is_banned else "healthy",
        })

        logger.info(
            f"Account '{acct['username']}': FYP={fyp_pct:.1%} → {'SHADOW BANNED' if is_banned else 'OK'}"
        )

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-posts", type=int, default=DEFAULT_MIN_POSTS)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()

    results = main(args.min_posts, args.threshold)
    print(json.dumps(results, ensure_ascii=False))
    sys.exit(0)
