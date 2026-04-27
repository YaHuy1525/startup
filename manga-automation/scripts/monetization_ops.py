#!/usr/bin/env python3
"""
Monetization control-plane operations.

Provides:
1) KPI evaluation with warn/go thresholds
2) Weekly balanced platform plan generation
3) High-CPM field allocation recommendations
"""
import json
import math
from datetime import date
from typing import Any, Dict, List

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("monetization_ops")

HIGH_CPM_FIELDS = [
    "japanese_language_via_anime",
    "education_crossover",
    "manga_collecting_investment",
    "anime_tech_gear_reviews",
    "narrative_storytelling_analysis",
]


def _inverse_metric(metric_key: str) -> bool:
    return metric_key in {"error_rate"}


def _read_thresholds() -> List[Dict[str, Any]]:
    return db.execute(
        """
        SELECT metric_key, warn_threshold, go_threshold, unit, evaluation_window
        FROM monetization_kpi_thresholds
        ORDER BY metric_key ASC
        """
    )


def _read_latest_snapshots(days: int = 7) -> List[Dict[str, Any]]:
    return db.execute(
        """
        SELECT platform, metric_key, AVG(metric_value) AS metric_value
        FROM monetization_performance_snapshots
        WHERE snapshot_date >= CURRENT_DATE - (%s::int || ' days')::interval
        GROUP BY platform, metric_key
        """,
        (days,),
    )


def _snapshot_map(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    mapped: Dict[str, Dict[str, float]] = {}
    for row in rows:
        platform = row["platform"]
        metric_key = row["metric_key"]
        mapped.setdefault(platform, {})
        mapped[platform][metric_key] = float(row["metric_value"])
    return mapped


def evaluate_kpis(days: int = 7, write_alerts: bool = True) -> Dict[str, Any]:
    thresholds = _read_thresholds()
    snapshots = _snapshot_map(_read_latest_snapshots(days))

    platform_status: Dict[str, Dict[str, Any]] = {}
    alerts: List[Dict[str, Any]] = []

    for platform, metrics in snapshots.items():
        go_count = 0
        warn_count = 0
        fail_count = 0
        checks = []

        for threshold in thresholds:
            metric_key = threshold["metric_key"]
            if metric_key not in metrics:
                continue

            value = float(metrics[metric_key])
            warn_threshold = float(threshold["warn_threshold"])
            go_threshold = float(threshold["go_threshold"])
            inverse = _inverse_metric(metric_key)

            if inverse:
                is_go = value <= go_threshold
                is_warn = value <= warn_threshold
            else:
                is_go = value >= go_threshold
                is_warn = value >= warn_threshold

            state = "fail"
            if is_go:
                state = "go"
                go_count += 1
            elif is_warn:
                state = "warn"
                warn_count += 1
            else:
                fail_count += 1
                severity = "critical" if (not inverse and value < warn_threshold * 0.85) or (inverse and value > warn_threshold * 1.15) else "warn"
                alert = {
                    "platform": platform,
                    "metric_key": metric_key,
                    "severity": severity,
                    "observed_value": value,
                    "threshold_value": warn_threshold,
                    "message": f"{platform}: {metric_key}={value:.4f} below operational threshold {warn_threshold:.4f}" if not inverse else f"{platform}: {metric_key}={value:.4f} above allowed threshold {warn_threshold:.4f}",
                }
                alerts.append(alert)

            checks.append(
                {
                    "metric_key": metric_key,
                    "value": value,
                    "state": state,
                    "warn_threshold": warn_threshold,
                    "go_threshold": go_threshold,
                }
            )

        decision = "scale"
        if fail_count > 0:
            decision = "stabilize"
        elif warn_count > math.ceil(max(1, len(checks)) / 2):
            decision = "cautious_scale"

        platform_status[platform] = {
            "decision": decision,
            "go_count": go_count,
            "warn_count": warn_count,
            "fail_count": fail_count,
            "checks": checks,
        }

    if write_alerts and alerts:
        for alert in alerts:
            db.execute(
                """
                INSERT INTO monetization_alerts
                    (platform, metric_key, severity, observed_value, threshold_value, message)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    alert["platform"],
                    alert["metric_key"],
                    alert["severity"],
                    alert["observed_value"],
                    alert["threshold_value"],
                    alert["message"],
                ),
            )

    return {
        "window_days": days,
        "platform_status": platform_status,
        "alerts_created": len(alerts),
        "alerts": alerts,
    }


def build_weekly_balanced_plan() -> Dict[str, Any]:
    channels = db.execute(
        """
        SELECT platform, enabled, daily_min_posts, daily_max_posts, min_delay_minutes,
               ad_ratio_denominator, requires_manual_review
        FROM monetization_channel_config
        WHERE enabled = TRUE
        ORDER BY platform
        """
    )
    if not channels:
        return {"error": "No enabled channel config found"}

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    weekly_schedule = []
    field_rotation = {}

    for idx, weekday in enumerate(days):
        day_plan = {"day": weekday, "platforms": []}
        for channel in channels:
            # Weekend cadence soft reduction for non-primary channels.
            weekend = weekday in {"saturday", "sunday"}
            min_posts = int(channel["daily_min_posts"])
            max_posts = int(channel["daily_max_posts"])
            planned_posts = min_posts
            if max_posts > min_posts and not weekend:
                planned_posts = min_posts + 1
            elif weekend and channel["platform"] != "tiktok":
                planned_posts = min_posts

            day_plan["platforms"].append(
                {
                    "platform": channel["platform"],
                    "planned_posts": planned_posts,
                    "min_delay_minutes": int(channel["min_delay_minutes"]),
                    "ad_ratio_denominator": int(channel["ad_ratio_denominator"]),
                    "requires_manual_review": bool(channel["requires_manual_review"]),
                }
            )
        weekly_schedule.append(day_plan)
        field_rotation[weekday] = HIGH_CPM_FIELDS[idx % len(HIGH_CPM_FIELDS)]

    return {
        "generated_at": date.today().isoformat(),
        "weekly_schedule": weekly_schedule,
        "high_cpm_field_rotation": field_rotation,
    }


def save_snapshot(platform: str, metric_key: str, metric_value: float, source: str = "automation") -> Dict[str, Any]:
    db.execute(
        """
        INSERT INTO monetization_performance_snapshots
            (snapshot_date, platform, metric_key, metric_value, source)
        VALUES (CURRENT_DATE, %s, %s, %s, %s)
        ON CONFLICT (snapshot_date, platform, metric_key)
        DO UPDATE SET metric_value = EXCLUDED.metric_value, source = EXCLUDED.source
        """,
        (platform, metric_key, metric_value, source),
    )
    return {
        "saved": True,
        "platform": platform,
        "metric_key": metric_key,
        "metric_value": metric_value,
        "source": source,
    }


def main(action: str = "evaluate", payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload or {}
    if action == "evaluate":
        return evaluate_kpis(days=int(payload.get("days", 7)), write_alerts=bool(payload.get("write_alerts", True)))
    if action == "weekly-plan":
        return build_weekly_balanced_plan()
    if action == "save-snapshot":
        return save_snapshot(
            platform=str(payload["platform"]),
            metric_key=str(payload["metric_key"]),
            metric_value=float(payload["metric_value"]),
            source=str(payload.get("source", "automation")),
        )
    return {"error": f"Unsupported action: {action}"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--action", default="evaluate", choices=["evaluate", "weekly-plan", "save-snapshot"])
    parser.add_argument("--payload", default="{}")
    args = parser.parse_args()

    result = main(args.action, json.loads(args.payload))
    print(json.dumps(result, ensure_ascii=False))
