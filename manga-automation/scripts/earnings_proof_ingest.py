#!/usr/bin/env python3
"""
Earnings Proof Ingest — @mini.money.matters automation layer.

Watches data/earnings_screenshots/ for new image files, parses their filenames,
stores the earnings data in the earnings_snapshots table, and optionally triggers
a weekly recap brief via the genesis_brief_generator.

Filename convention:
    {platform_slug}_{YYYY-MM-DD}_{amount}.{ext}
    Example: honeygain_2026-05-07_4.37.png
             swagbucks_2026-05-07_12.50.jpg

Can be run as:
    - A one-shot scan:    python scripts/earnings_proof_ingest.py --scan
    - A file watcher:     python scripts/earnings_proof_ingest.py --watch
    - Via worker.py:      POST /earnings/ingest { "action": "scan" | "watch" }
    - Via worker.py:      POST /earnings/weekly-recap { "week_iso": "2026-W19" }
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("earnings_proof_ingest")

# ─── Configuration ────────────────────────────────────────────────────────────
SCREENSHOTS_DIR = Path(
    os.environ.get("EARNINGS_SCREENSHOTS_DIR", "/data/earnings_screenshots")
)
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Filename regex: platform_YYYY-MM-DD_amount.ext
FILENAME_RE = re.compile(
    r"^(?P<slug>[a-z][a-z0-9_]+)_"
    r"(?P<date>\d{4}-\d{2}-\d{2})_"
    r"(?P<amount>\d+(?:\.\d{1,2})?)$",
    re.IGNORECASE,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _iso_week(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to ISO week string 'YYYY-Www'."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        year, week, _ = dt.isocalendar()
        return f"{year}-W{week:02d}"
    except ValueError:
        now = datetime.now(timezone.utc)
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}"


def _parse_filename(filename: str) -> dict | None:
    """
    Parse earnings screenshot filename into components.
    Returns None if filename doesn't match the expected pattern.
    """
    stem = Path(filename).stem
    m = FILENAME_RE.match(stem)
    if not m:
        logger.debug(f"Filename '{filename}' does not match pattern — skipping")
        return None
    return {
        "slug": m.group("slug").lower(),
        "date": m.group("date"),
        "amount_usd": float(m.group("amount")),
        "week_iso": _iso_week(m.group("date")),
    }


def _get_active_slugs() -> set[str]:
    """Fetch all active referral platform slugs from the DB."""
    rows = db.execute("SELECT slug FROM referral_platforms WHERE is_active = true")
    return {r["slug"] for r in (rows or [])}


def _already_ingested(screenshot_path: str) -> bool:
    """Check if this screenshot path was already saved."""
    row = db.execute_one(
        "SELECT id FROM earnings_snapshots WHERE screenshot_path = %s",
        (screenshot_path,),
    )
    return row is not None


def _save_snapshot(slug: str, amount: float, screenshot_path: str, week_iso: str) -> int | None:
    """Insert an earnings snapshot and return its ID."""
    try:
        snap_id = db.execute_returning(
            """
            INSERT INTO earnings_snapshots
                (platform_slug, amount_usd, screenshot_path, week_iso)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (slug, amount, screenshot_path, week_iso),
        )
        if snap_id:
            # Update rolling monthly_payout_usd on the referral platform
            db.execute(
                """
                UPDATE referral_platforms
                SET monthly_payout_usd = monthly_payout_usd + %s,
                    updated_at = NOW()
                WHERE slug = %s
                """,
                (amount, slug),
            )
        return snap_id
    except Exception as e:
        logger.error(f"Failed to save snapshot for {slug}: {e}")
        return None


# ─── Core: scan ───────────────────────────────────────────────────────────────
def scan_screenshots(screenshots_dir: Path | None = None) -> dict[str, Any]:
    """
    One-shot scan of the screenshots directory.
    Parses every matching file and inserts new records.
    """
    target_dir = screenshots_dir or SCREENSHOTS_DIR
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created screenshots dir: {target_dir}")
        return {"ingested": 0, "skipped": 0, "errors": 0, "dir": str(target_dir)}

    active_slugs = _get_active_slugs()
    ingested = 0
    skipped = 0
    errors = 0
    results: list[dict] = []

    for f in sorted(target_dir.iterdir()):
        if f.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        parsed = _parse_filename(f.name)
        if not parsed:
            skipped += 1
            continue

        slug = parsed["slug"]
        abs_path = str(f.resolve())

        if slug not in active_slugs:
            logger.warning(f"Unknown platform slug '{slug}' in {f.name} — add to referral_platforms first")
            errors += 1
            continue

        if _already_ingested(abs_path):
            logger.debug(f"Already ingested: {f.name}")
            skipped += 1
            continue

        snap_id = _save_snapshot(
            slug=slug,
            amount=parsed["amount_usd"],
            screenshot_path=abs_path,
            week_iso=parsed["week_iso"],
        )

        if snap_id:
            ingested += 1
            results.append({
                "snapshot_id": snap_id,
                "platform": slug,
                "amount_usd": parsed["amount_usd"],
                "week_iso": parsed["week_iso"],
                "file": f.name,
            })
            logger.info(
                f"Ingested: {f.name} → ${parsed['amount_usd']:.2f} ({slug}, {parsed['week_iso']})"
            )
        else:
            errors += 1

    logger.info(f"Scan complete — ingested={ingested}, skipped={skipped}, errors={errors}")
    return {
        "ingested": ingested,
        "skipped": skipped,
        "errors": errors,
        "dir": str(target_dir),
        "results": results,
    }


# ─── Core: weekly recap brief ────────────────────────────────────────────────
def generate_weekly_recap(week_iso: str | None = None) -> dict[str, Any]:
    """
    Aggregate earnings for a given ISO week and trigger a content brief.
    Called automatically on Sunday evenings by the n8n monetization workflow.
    """
    if not week_iso:
        now = datetime.now(timezone.utc)
        yr, wk, _ = now.isocalendar()
        week_iso = f"{yr}-W{wk:02d}"

    rows = db.execute(
        """
        SELECT es.platform_slug, rp.display_name,
               SUM(es.amount_usd) AS total_usd,
               COUNT(*) AS proof_count,
               MAX(es.screenshot_path) AS sample_screenshot
        FROM earnings_snapshots es
        LEFT JOIN referral_platforms rp ON es.platform_slug = rp.slug
        WHERE es.week_iso = %s
          AND es.brief_generated = false
        GROUP BY es.platform_slug, rp.display_name
        ORDER BY total_usd DESC
        """,
        (week_iso,),
    )

    if not rows:
        return {
            "week_iso": week_iso,
            "status": "no_new_snapshots",
            "message": "No unprocessed snapshots for this week. Drop screenshots into data/earnings_screenshots/ first.",
        }

    total = sum(float(r["total_usd"]) for r in rows)
    top_platform = rows[0]["display_name"] or rows[0]["platform_slug"]

    # Build a platform earnings summary for the LLM brief
    platform_lines = "\n".join(
        f"  • {r['display_name'] or r['platform_slug']}: ${float(r['total_usd']):.2f} "
        f"({r['proof_count']} proof{'s' if r['proof_count'] > 1 else ''})"
        for r in rows
    )

    # Fetch the finance category ID
    finance_cat = db.execute_one(
        "SELECT id FROM genesis_categories WHERE slug = 'finance'",
    )
    if not finance_cat:
        return {"error": "Finance category not found — run migration 011 first"}

    cat_id = finance_cat["id"]

    # Fetch active referral links to embed in the brief
    ref_rows = db.execute(
        "SELECT slug, display_name, referral_url FROM referral_platforms WHERE is_active = true AND tier = 1 ORDER BY tier"
    )
    ref_lines = "\n".join(
        f"  • {r['display_name']}: {r['referral_url']}"
        for r in (ref_rows or [])
        if r.get("referral_url") and "YOUR_REF_ID" not in r["referral_url"]
    )

    brief_narrative = (
        f"WEEKLY EARNINGS RECAP — {week_iso}\n\n"
        f"Total earned this week: ${total:.2f}\n\n"
        f"Platform breakdown:\n{platform_lines}\n\n"
        f"Top earner: {top_platform}\n\n"
        f"Referral links to embed (CTA: 'Full list in bio'):\n"
        f"{ref_lines or 'Add your referral links to the referral_platforms table.'}\n\n"
        f"Content angle: Show the actual week-over-week growth. Use screenshot proof as thumbnail. "
        f"Hook: 'I earned ${total:.0f} doing basically nothing this week — here's the breakdown.' "
        f"CTA: Comment 'LIST' and I'll DM you every app I use."
    )

    # Save as a content brief
    brief_id = db.execute_returning(
        """
        INSERT INTO content_briefs
            (category_id, trend_name, viral_hook, target_audience,
             suggested_monetization, base_narrative, virality_score,
             source_signal_ids, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'approved')
        RETURNING id
        """,
        (
            cat_id,
            f"Weekly Earnings Recap {week_iso} — ${total:.0f} Earned",
            f"I made ${total:.0f} from passive income apps this week — proof inside",
            "Anyone curious about side hustles, passive income, or micro-investing",
            "affiliate_referral",
            brief_narrative,
            88,  # High virality — earnings proof always performs well
            [],
        ),
    )

    # Mark snapshots as processed
    db.execute(
        "UPDATE earnings_snapshots SET brief_generated = true WHERE week_iso = %s",
        (week_iso,),
    )

    logger.info(f"Weekly recap brief {brief_id} created for {week_iso} — total ${total:.2f}")

    return {
        "week_iso": week_iso,
        "brief_id": brief_id,
        "total_usd": total,
        "platforms": len(rows),
        "platforms_detail": [dict(r) for r in rows],
        "message": f"Brief #{brief_id} created. Run /omnichannel/distribute to publish.",
    }


# ─── Core: update platform earnings manually ─────────────────────────────────
def update_platform_earnings(slug: str, amount_usd: float) -> dict[str, Any]:
    """Manually log earnings for a platform (for when no screenshot exists)."""
    row = db.execute_one(
        "SELECT id, display_name FROM referral_platforms WHERE slug = %s AND is_active = true",
        (slug,),
    )
    if not row:
        return {"error": f"Platform '{slug}' not found or inactive"}

    db.execute(
        "UPDATE referral_platforms SET monthly_payout_usd = monthly_payout_usd + %s, updated_at = NOW() WHERE slug = %s",
        (amount_usd, slug),
    )
    logger.info(f"Manually logged ${amount_usd:.2f} for {slug}")
    return {"slug": slug, "display_name": row["display_name"], "added_usd": amount_usd}


# ─── Core: list referral platforms ────────────────────────────────────────────
def list_referral_platforms(tier: int | None = None) -> dict[str, Any]:
    """Return active referral platforms, optionally filtered by tier."""
    if tier:
        rows = db.execute(
            "SELECT * FROM referral_platforms WHERE is_active = true AND tier = %s ORDER BY tier, monthly_payout_usd DESC",
            (tier,),
        )
    else:
        rows = db.execute(
            "SELECT * FROM referral_platforms WHERE is_active = true ORDER BY tier, monthly_payout_usd DESC"
        )

    # Group by tier for readability
    grouped: dict[str, list] = {"tier1": [], "tier2": [], "tier3": []}
    for r in (rows or []):
        key = f"tier{r['tier']}"
        grouped.setdefault(key, []).append({
            "slug": r["slug"],
            "display_name": r["display_name"],
            "referral_url": r["referral_url"],
            "category": r["category"],
            "signup_bonus_usd": float(r.get("signup_bonus_usd") or 0),
            "monthly_payout_usd": float(r.get("monthly_payout_usd") or 0),
        })

    return {
        "total": len(rows or []),
        "platforms": grouped,
        "has_real_links": sum(
            1 for r in (rows or []) if "YOUR_REF_ID" not in (r.get("referral_url") or "")
        ),
    }


# ─── Watch mode ───────────────────────────────────────────────────────────────
def watch_screenshots(poll_interval: int = 30) -> None:
    """
    Long-running file watcher. Polls the screenshots directory every N seconds
    and ingests any new files found.
    """
    logger.info(f"Watching {SCREENSHOTS_DIR} every {poll_interval}s for new screenshots")
    while True:
        try:
            result = scan_screenshots()
            if result.get("ingested", 0) > 0:
                logger.info(f"Watcher: ingested {result['ingested']} new screenshots")
        except Exception as e:
            logger.error(f"Watcher scan error: {e}")
        time.sleep(poll_interval)


# ─── Worker entry point ────────────────────────────────────────────────────────
def main(body: dict | None = None, **kwargs) -> dict[str, Any]:
    """Entry point for worker.py integration."""
    if body is None:
        body = kwargs

    action = body.get("action", "scan")

    if action == "scan":
        return scan_screenshots()

    if action == "weekly-recap":
        return generate_weekly_recap(week_iso=body.get("week_iso"))

    if action == "update-earnings":
        slug = body.get("slug")
        amount = body.get("amount_usd") or body.get("amount")
        if not slug or amount is None:
            return {"error": "Requires: slug, amount_usd"}
        return update_platform_earnings(slug, float(amount))

    if action == "list":
        return list_referral_platforms(tier=body.get("tier"))

    return {"error": f"Unknown action '{action}'. Use: scan | weekly-recap | update-earnings | list"}


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Earnings Proof Ingest")
    parser.add_argument(
        "--scan", action="store_true",
        help="One-shot scan of the screenshots directory",
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="Long-running watcher mode",
    )
    parser.add_argument(
        "--weekly-recap", action="store_true",
        help="Generate weekly earnings recap brief",
    )
    parser.add_argument(
        "--week-iso", type=str, default=None,
        help="ISO week string e.g. 2026-W19 (default: current week)",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all active referral platforms",
    )
    parser.add_argument(
        "--poll-interval", type=int, default=30,
        help="Watch mode poll interval in seconds (default: 30)",
    )
    args = parser.parse_args()

    if args.watch:
        watch_screenshots(args.poll_interval)
    elif args.weekly_recap:
        result = generate_weekly_recap(week_iso=args.week_iso)
        print(json.dumps(result, indent=2, default=str))
    elif args.list:
        result = list_referral_platforms()
        print(json.dumps(result, indent=2, default=str))
    else:
        result = scan_screenshots()
        print(json.dumps(result, indent=2, default=str))
