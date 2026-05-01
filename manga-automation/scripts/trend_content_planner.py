#!/usr/bin/env python3
"""
Trend-driven content planner (not anime-only).

Builds a ranked queue from research + trend tables and decides whether each topic
should be handled by:
- generate_original (script + render)
- repurpose_youtube (source/download/distribute)
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("trend_content_planner")

DEFAULT_LIMIT = int(os.environ.get("TREND_PLANNER_LIMIT", "10"))
REPURPOSE_RATIO = float(os.environ.get("TREND_REPURPOSE_RATIO", "0.5"))
MIN_CONFIDENCE = float(os.environ.get("TREND_MIN_CONFIDENCE", "0.30"))


def _fetch_candidates(limit: int) -> list[dict[str, Any]]:
    """
    Pull cross-domain trend candidates.
    Uses confidence, velocity, and recency, independent of anime-only tags.
    """
    rows = db.execute(
        """
        SELECT
            id,
            hashtag,
            region,
            COALESCE(confidence, 0) AS confidence,
            COALESCE(trend_velocity, 0) AS trend_velocity,
            COALESCE(post_count, 0) AS post_count,
            COALESCE(avg_views, 0) AS avg_views,
            source,
            source_engine,
            status,
            discovered_at,
            last_researched_at,
            research_summary
        FROM trend_intel
        WHERE status IN ('new', 'sourcing', 'done')
          AND COALESCE(confidence, 0) >= %s
        ORDER BY COALESCE(confidence, 0) DESC,
                 COALESCE(trend_velocity, 0) DESC,
                 COALESCE(avg_views, 0) DESC,
                 COALESCE(last_researched_at, discovered_at) DESC
        LIMIT %s
        """,
        (MIN_CONFIDENCE, limit * 3),
    )
    return rows


def _score(candidate: dict[str, Any]) -> float:
    confidence = float(candidate.get("confidence") or 0)
    velocity = float(candidate.get("trend_velocity") or 0)
    avg_views = float(candidate.get("avg_views") or 0)
    post_count = float(candidate.get("post_count") or 0)
    # Conservative blended score.
    return round((confidence * 0.55) + (velocity * 0.20) + (min(avg_views, 5_000_000) / 5_000_000 * 0.20) + (min(post_count, 5000) / 5000 * 0.05), 6)


def _mode_for_rank(rank: int, repurpose_ratio: float) -> str:
    """
    Alternate by target ratio while preserving top-ranked priority.
    Example ratio 0.6 => more repurpose slots.
    """
    if repurpose_ratio <= 0:
        return "generate_original"
    if repurpose_ratio >= 1:
        return "repurpose_youtube"
    interval = max(1, round(1 / repurpose_ratio))
    return "repurpose_youtube" if rank % interval == 0 else "generate_original"


def _build_query_text(candidate: dict[str, Any]) -> str:
    tag = (candidate.get("hashtag") or "").strip("# ").strip()
    summary = (candidate.get("research_summary") or "").strip()
    if summary:
        return f"{tag} {summary[:120]}"
    return f"{tag} viral shorts"


def plan(limit: int = DEFAULT_LIMIT, repurpose_ratio: float = REPURPOSE_RATIO) -> dict[str, Any]:
    candidates = _fetch_candidates(limit=limit)
    if not candidates:
        return {"generated_at": datetime.utcnow().isoformat(), "items": [], "count": 0}

    ranked = sorted(
        [
            {
                **row,
                "priority_score": _score(row),
            }
            for row in candidates
        ],
        key=lambda x: x["priority_score"],
        reverse=True,
    )[:limit]

    items = []
    for idx, row in enumerate(ranked, start=1):
        mode = _mode_for_rank(idx, repurpose_ratio=repurpose_ratio)
        items.append(
            {
                "trend_id": row["id"],
                "topic": row["hashtag"],
                "query_text": _build_query_text(row),
                "mode": mode,
                "priority_score": row["priority_score"],
                "confidence": float(row.get("confidence") or 0),
                "region": row.get("region") or "US",
                "source": row.get("source") or row.get("source_engine") or "unknown",
            }
        )

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "count": len(items),
        "repurpose_ratio": repurpose_ratio,
        "items": items,
    }


def execute(limit: int = DEFAULT_LIMIT, repurpose_ratio: float = REPURPOSE_RATIO, batch: int = 3) -> dict[str, Any]:
    """
    Execute first N planned items:
    - repurpose_youtube: queue assets via source_youtube_assets
    - generate_original: return topics for script/video generation pipelines
    """
    from scripts import source_youtube_assets as source_assets

    plan_data = plan(limit=limit, repurpose_ratio=repurpose_ratio)
    items = plan_data.get("items", [])[:batch]
    original_queue = []
    repurpose_runs = []

    for item in items:
        if item["mode"] == "repurpose_youtube":
            result = source_assets.main(limit=1, query_override=item["query_text"])
            repurpose_runs.append({"topic": item["topic"], "result": result})
        else:
            original_queue.append(
                {
                    "topic": item["topic"],
                    "query_text": item["query_text"],
                    "trend_id": item["trend_id"],
                    "priority_score": item["priority_score"],
                }
            )

    return {
        "plan": plan_data,
        "executed_batch": len(items),
        "repurpose_runs": repurpose_runs,
        "original_queue": original_queue,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["plan", "execute"], default="plan")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--repurpose-ratio", type=float, default=REPURPOSE_RATIO)
    parser.add_argument("--batch", type=int, default=3)
    args = parser.parse_args()

    if args.action == "execute":
        payload = execute(limit=args.limit, repurpose_ratio=args.repurpose_ratio, batch=args.batch)
    else:
        payload = plan(limit=args.limit, repurpose_ratio=args.repurpose_ratio)

    print(json.dumps(payload, ensure_ascii=False))
