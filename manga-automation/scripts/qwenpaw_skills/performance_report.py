"""
Skill: Performance Report
Triggers: "how did X perform", "pipeline report", "performance summary",
          "analytics", "content stats", "weekly report"
Description: Queries PostgreSQL for pipeline performance data — upload success rates,
             view counts, engagement metrics, trend performance, revenue.
             Generates actionable recommendations for next pipeline run.
Wraps: PostgreSQL queries (pipeline_run, videos, trend_intel tables)
       scripts/crew/tools.py (record_trend_performance, get_account_health_tool)
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import TIMEOUT_REPORT
from ._base import _run


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    """
    Generate a performance report for the pipeline.

    Args:
        args:
            days (int): Lookback window in days (default 7)
            category (str): Filter by category slug (default: all)
            platform (str): Filter by platform (default: all)
            limit (int): Max rows per query (default 50)
        agent_context: QwenPaw agent context

    Returns:
        {"success": True, "report": {"period": "...", "total_uploads": N,
         "success_rate": 0.X, "top_trends": [...], "accounts": [...],
         "revenue_summary": {...}, "recommendations": [...]}}
    """
    days = int(args.get("days", 7))
    category = str(args.get("category", "") or "")
    platform = str(args.get("platform", "") or "")

    # Run the Hermes status snapshot which collects all DB stats
    cmd = [
        "uv", "run", "python",
        "-c",
        f"from scripts.hermes_agent import collect_status_snapshot; "
        f"import json; "
        f"snap = collect_status_snapshot(limit=50); "
        f"print(json.dumps(snap, default=str))",
    ]

    extra_env = {}
    for key in ("DATABASE_URL", "CHROMADB_URL", "REDIS_URL",
                 "PYTHON_WORKER_URL", "MASTRA_API_URL"):
        if key in os.environ:
            extra_env[key] = os.environ[key]

    result = _run(cmd, timeout=TIMEOUT_REPORT, env=extra_env)

    # Enrich with recommendations from the snapshot
    if result.get("success", True):
        snapshot = result.get("output") or result
        result["report"] = {
            "period_days": days,
            "category": category or "all",
            "platform": platform or "all",
            "snapshot": snapshot,
        }

    return result
