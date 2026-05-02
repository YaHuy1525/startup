#!/usr/bin/env python3
"""
Pod 0 — Genesis Content Brief Generator.

Takes raw signals from `genesis_signals` and uses Claude to evaluate them,
producing ranked `content_briefs` that downstream Pods consume.

Usage:
    python scripts/genesis_brief_generator.py [--categories fiction,tech] [--top 3]
"""
from __future__ import annotations

import json
import os
import sys
import argparse
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("genesis_brief_generator")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
BRIEF_MODEL = os.environ.get("GENESIS_BRIEF_MODEL", "claude-sonnet-4-20250514")
TOP_SIGNALS_PER_CAT = int(os.environ.get("GENESIS_TOP_SIGNALS", "20"))


def _get_top_signals(category_id: int, limit: int = 20) -> list[dict]:
    """Fetch highest-velocity signals from the last 48 hours for a category."""
    return db.execute(
        """
        SELECT id, source_platform, source_url, title, body_preview,
               score, comment_count, velocity_score
        FROM genesis_signals
        WHERE category_id = %s
          AND scraped_at >= NOW() - INTERVAL '48 hours'
        ORDER BY velocity_score DESC, score DESC
        LIMIT %s
        """,
        (category_id, limit),
    )


def _evaluate_with_llm(category: dict, signals: list[dict], top_n: int = 3) -> list[dict]:
    """
    Send the raw signals to Claude and ask it to produce content briefs.
    Returns a list of brief dicts.
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — using fallback heuristic evaluation")
        return _fallback_evaluate(category, signals, top_n)

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic SDK not installed — using fallback")
        return _fallback_evaluate(category, signals, top_n)

    # Build the signal summary for the prompt
    signal_lines = []
    for s in signals[:TOP_SIGNALS_PER_CAT]:
        signal_lines.append(
            f"- [{s['source_platform']}] \"{s['title']}\" "
            f"(score={s['score']}, comments={s['comment_count']}, "
            f"velocity={s['velocity_score']})"
        )
    signals_text = "\n".join(signal_lines)

    prompt = f"""You are an expert trend analyst and content strategist. You are analyzing trending data for the category: **{category['display_name']}**.

Here are the top {len(signal_lines)} trending signals scraped from Reddit, HackerNews, and TikTok in the last 48 hours:

{signals_text}

From these signals, identify the top {top_n} most viral and monetizable content ideas. For each, produce a JSON object.

Return ONLY a valid JSON array (no markdown fences, no explanation) with {top_n} objects:
[
  {{
    "trend_name": "Short catchy name for the trend",
    "viral_hook": "A 1-sentence hook that would stop someone scrolling",
    "target_audience": "Who this content is for",
    "suggested_monetization": "e.g., SaaS affiliate, Etsy template, Audible book, TikTok Shop",
    "base_narrative": "A 300-500 word script outline or analytical breakdown",
    "virality_score": 85,
    "source_signal_ids": [1, 5, 12]
  }}
]

Rules:
- virality_score is 0-100 based on how likely this content would go viral if produced.
- source_signal_ids should reference the indices (0-based) of the input signals that inspired this brief.
- base_narrative should be specific enough for a video script writer to immediately start working.
- suggested_monetization should match the category: tech=SaaS/tools, fiction=audiobooks/Kindle, art=Procreate brushes/prints, movies=Amazon affiliate.
"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=BRIEF_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text.strip()

        # Handle potential markdown code fences
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        briefs = json.loads(raw_text)
        if not isinstance(briefs, list):
            briefs = [briefs]

        # Map source_signal_ids from indices to actual DB IDs
        for brief in briefs:
            idx_list = brief.get("source_signal_ids", [])
            real_ids = []
            for idx in idx_list:
                if isinstance(idx, int) and 0 <= idx < len(signals):
                    real_ids.append(signals[idx]["id"])
            brief["source_signal_ids"] = real_ids

        logger.info(f"LLM generated {len(briefs)} briefs for {category['slug']}")
        return briefs

    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}")
        return _fallback_evaluate(category, signals, top_n)
    except Exception as e:
        logger.error(f"LLM evaluation failed: {e}")
        return _fallback_evaluate(category, signals, top_n)


def _fallback_evaluate(category: dict, signals: list[dict], top_n: int = 3) -> list[dict]:
    """
    Simple heuristic evaluation when LLM is unavailable.
    Picks the highest-velocity signals and wraps them as briefs.
    """
    sorted_signals = sorted(signals, key=lambda s: s.get("velocity_score", 0), reverse=True)
    briefs = []

    for i, s in enumerate(sorted_signals[:top_n]):
        briefs.append({
            "trend_name": s["title"][:200],
            "viral_hook": f"Everyone is talking about this: {s['title'][:100]}",
            "target_audience": f"{category['display_name']} enthusiasts",
            "suggested_monetization": "affiliate",
            "base_narrative": (
                f"This topic is trending with a velocity score of {s['velocity_score']} "
                f"and {s['score']} engagement points. "
                f"Source: {s['source_platform']}. "
                f"Preview: {s.get('body_preview', '')[:300]}"
            ),
            "virality_score": max(10, min(95, int(50 + s.get("velocity_score", 0) * 0.1))),
            "source_signal_ids": [s["id"]],
        })

    logger.info(f"Fallback generated {len(briefs)} briefs for {category['slug']}")
    return briefs


def save_briefs(category_id: int, briefs: list[dict]) -> list[int]:
    """Insert content_briefs and return their IDs."""
    ids = []
    for b in briefs:
        try:
            brief_id = db.execute_returning(
                """
                INSERT INTO content_briefs
                    (category_id, trend_name, viral_hook, target_audience,
                     suggested_monetization, base_narrative, virality_score,
                     source_signal_ids, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'draft')
                RETURNING id
                """,
                (
                    category_id,
                    b.get("trend_name", "")[:255],
                    b.get("viral_hook", ""),
                    b.get("target_audience", ""),
                    b.get("suggested_monetization", ""),
                    b.get("base_narrative", ""),
                    b.get("virality_score", 50),
                    b.get("source_signal_ids", []),
                ),
            )
            if brief_id:
                ids.append(brief_id)
        except Exception as e:
            logger.error(f"Failed to save brief '{b.get('trend_name', '')[:60]}': {e}")
    return ids


def generate_briefs(
    categories: list[str] | None = None,
    top_n: int = 3,
) -> dict[str, Any]:
    """
    Full brief generation pipeline: fetch signals → LLM evaluate → save briefs.
    """
    from scripts.genesis_discover import get_categories

    cats = get_categories(categories)
    if not cats:
        return {"error": "No categories found", "briefs_generated": 0}

    results = {
        "categories_processed": len(cats),
        "total_briefs": 0,
        "per_category": {},
    }

    for cat in cats:
        signals = _get_top_signals(cat["id"], limit=TOP_SIGNALS_PER_CAT)
        if not signals:
            logger.info(f"No signals for {cat['slug']} — skipping. Run genesis_discover first.")
            results["per_category"][cat["slug"]] = {"signals": 0, "briefs": 0}
            continue

        briefs = _evaluate_with_llm(cat, signals, top_n=top_n)
        saved_ids = save_briefs(cat["id"], briefs)

        results["total_briefs"] += len(saved_ids)
        results["per_category"][cat["slug"]] = {
            "signals": len(signals),
            "briefs": len(saved_ids),
            "brief_ids": saved_ids,
        }

    logger.info(f"Brief generation complete: {results['total_briefs']} briefs total")
    return results


def get_actionable_briefs(
    categories: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Fetch top draft briefs ready for production, sorted by virality."""
    if categories:
        placeholders = ",".join(["%s"] * len(categories))
        return db.execute(
            f"""
            SELECT cb.*, gc.slug AS category_slug, gc.display_name AS category_name
            FROM content_briefs cb
            JOIN genesis_categories gc ON cb.category_id = gc.id
            WHERE cb.status = 'draft'
              AND gc.slug IN ({placeholders})
            ORDER BY cb.virality_score DESC
            LIMIT %s
            """,
            (*categories, limit),
        )
    return db.execute(
        """
        SELECT cb.*, gc.slug AS category_slug, gc.display_name AS category_name
        FROM content_briefs cb
        JOIN genesis_categories gc ON cb.category_id = gc.id
        WHERE cb.status = 'draft'
        ORDER BY cb.virality_score DESC
        LIMIT %s
        """,
        (limit,),
    )


def main(body: dict | None = None, **kwargs) -> dict:
    """Entry point for worker.py integration."""
    if body is None:
        body = kwargs

    action = body.get("action", "generate")

    if action == "list":
        categories_raw = body.get("categories")
        if isinstance(categories_raw, str):
            categories = [c.strip() for c in categories_raw.split(",")]
        elif isinstance(categories_raw, list):
            categories = categories_raw
        else:
            categories = None
        briefs = get_actionable_briefs(categories=categories, limit=int(body.get("limit", 10)))
        return {"briefs": briefs, "count": len(briefs)}

    # Default: generate
    categories_raw = body.get("categories")
    if isinstance(categories_raw, str):
        categories = [c.strip() for c in categories_raw.split(",")]
    elif isinstance(categories_raw, list):
        categories = categories_raw
    else:
        categories = None

    return generate_briefs(
        categories=categories,
        top_n=int(body.get("top", 3)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genesis Content Brief Generator")
    parser.add_argument("--categories", type=str, default=None)
    parser.add_argument("--top", type=int, default=3,
                        help="Number of briefs to generate per category")
    parser.add_argument("--action", choices=["generate", "list"], default="generate")
    args = parser.parse_args()

    cats = [c.strip() for c in args.categories.split(",")] if args.categories else None

    if args.action == "list":
        briefs = get_actionable_briefs(categories=cats)
        print(json.dumps(briefs, indent=2, ensure_ascii=False, default=str))
    else:
        result = generate_briefs(categories=cats, top_n=args.top)
        print(json.dumps(result, indent=2, ensure_ascii=False))
