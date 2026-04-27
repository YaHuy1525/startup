#!/usr/bin/env python3
"""
Weekly optimization loop:
- aggregate platform analytics for last 7 days
- persist KPI snapshots
- trigger KPI evaluation
- produce posting allocation recommendations
"""
import json
from typing import Any, Dict, List

from scripts.utils import database as db
from scripts.utils.logger import setup_logger
from scripts.monetization_ops import save_snapshot, evaluate_kpis

logger = setup_logger("weekly_optimizer")


def _platform_analytics() -> List[Dict[str, Any]]:
    return db.execute(
        """
        WITH recent AS (
            SELECT
                LOWER(COALESCE(platform, 'unknown')) AS platform,
                COUNT(*)::numeric AS uploads,
                COUNT(*) FILTER (WHERE status = 'success')::numeric AS successes
            FROM arbitrage_uploads
            WHERE uploaded_at >= NOW() - INTERVAL '7 days'
            GROUP BY 1
        )
        SELECT
            platform,
            uploads,
            successes,
            CASE WHEN uploads > 0 THEN successes / uploads ELSE 0 END AS upload_success_rate,
            CASE WHEN uploads > 0 THEN (uploads - successes) / uploads ELSE 0 END AS error_rate
        FROM recent
        """
    )


def _estimate_revenue_per_video(platform: str) -> float:
    # Conservative defaults from plan: can be replaced with real payout APIs.
    map_usd = {
        "tiktok": 1.0,
        "youtube": 0.25,
        "instagram": 0.15,
        "facebook": 0.12,
        "pinterest": 0.18,
    }
    return map_usd.get(platform, 0.10)


def _recommend_allocation(kpi_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    output = []
    for platform, status in kpi_result.get("platform_status", {}).items():
        decision = status.get("decision")
        if decision == "scale":
            action = "increase_post_volume_10pct"
        elif decision == "cautious_scale":
            action = "keep_volume_flat_increase_high_cpm_share"
        else:
            action = "reduce_post_volume_20pct_focus_quality"
        output.append({"platform": platform, "decision": decision, "action": action})
    return output


def run_weekly_optimization() -> Dict[str, Any]:
    metrics = _platform_analytics()
    saved = []
    for row in metrics:
        platform = row["platform"]
        success_rate = float(row["upload_success_rate"])
        error_rate = float(row["error_rate"])
        revenue_per_video = _estimate_revenue_per_video(platform)

        saved.append(save_snapshot(platform, "upload_success_rate", success_rate, source="weekly_optimizer"))
        saved.append(save_snapshot(platform, "error_rate", error_rate, source="weekly_optimizer"))
        saved.append(save_snapshot(platform, "revenue_per_video_usd", revenue_per_video, source="weekly_optimizer"))

    kpi_result = evaluate_kpis(days=7, write_alerts=True)
    allocation = _recommend_allocation(kpi_result)

    return {
        "saved_snapshots": len(saved),
        "platform_metrics": metrics,
        "kpi_result": kpi_result,
        "allocation_recommendations": allocation,
    }


if __name__ == "__main__":
    print(json.dumps(run_weekly_optimization(), ensure_ascii=False))
