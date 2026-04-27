#!/usr/bin/env python3
"""
Gig Copilot — Session analytics and performance reporting.

Provides daily and weekly KPI summaries:
  - Tasks created / completed
  - Time spent
  - Estimated payout
  - Effective hourly rate
  - Average quality score

Called by:
  GET /gig/session/today  { user_id }
  GET /gig/session/week   { user_id }
"""
from __future__ import annotations

import os
import requests
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger    = setup_logger("gig_session_report")
WORKER_URL = os.getenv("TELEGRAM_WORKER_URL", "http://python-worker:8080").rstrip("/")


import threading

def _sync_obsidian_session(summary: dict) -> None:
    """Fire-and-forget vault write — never raises."""
    def _run():
        try:
            from scripts import obsidian_sync
            obsidian_sync.main({"action": "session", "summary": summary})
        except Exception as exc:
            logger.debug(f"Obsidian session sync skipped: {exc}")
    threading.Thread(target=_run, daemon=True).start()


def _fmt_currency(val: float) -> str:
    return f"${val:.2f}"


def _fmt_rate(val: float) -> str:
    return f"${val:.2f}/hr"


def today_summary(user_id: str = "default") -> dict:
    rows = db.execute(
        """
        SELECT
            t.id,
            t.platform,
            t.task_type,
            t.status,
            t.time_spent_minutes,
            t.estimated_payout,
            o.quality_score
        FROM gig_tasks t
        LEFT JOIN LATERAL (
            SELECT quality_score
            FROM gig_outputs
            WHERE task_id = t.id
            ORDER BY created_at DESC
            LIMIT 1
        ) o ON TRUE
        WHERE t.user_id = %s
          AND t.created_at >= CURRENT_DATE
        ORDER BY t.created_at DESC
        """,
        (user_id,),
    )

    if not rows:
        return {
            "user_id": user_id,
            "period":  "today",
            "message": "No gig tasks logged today. Start with /gig_new.",
        }

    total   = len(rows)
    done    = sum(1 for r in rows if r["status"] in ("accepted", "submitted_manual"))
    rejected = sum(1 for r in rows if r["status"] == "rejected")
    minutes = sum(int(r["time_spent_minutes"] or 0) for r in rows)
    payout  = sum(float(r["estimated_payout"] or 0) for r in rows)
    hourly  = (payout / (minutes / 60)) if minutes > 0 else 0.0
    scored  = [float(r["quality_score"]) for r in rows if r["quality_score"] is not None]
    avg_q   = (sum(scored) / len(scored)) if scored else 0.0

    # Acceptance rate
    submitted = done + rejected
    accept_rate = (done / submitted * 100) if submitted > 0 else 0.0

    platform_counts: dict[str, int] = {}
    for r in rows:
        p = r["platform"]
        platform_counts[p] = platform_counts.get(p, 0) + 1

    result = {
        "user_id":               user_id,
        "period":                "today",
        "tasks_today":           total,
        "tasks_completed":       done,
        "tasks_rejected":        rejected,
        "acceptance_rate_pct":   round(accept_rate, 1),
        "total_minutes":         minutes,
        "estimated_payout_usd":  round(payout, 2),
        "effective_hourly_rate": round(hourly, 2),
        "avg_quality_score":     round(avg_q, 2),
        "platform_breakdown":    platform_counts,
        "formatted": (
            f"📊 Today's Gig Report\n\n"
            f"Tasks: {total} created · {done} done · {rejected} rejected\n"
            f"Acceptance: {accept_rate:.0f}%\n"
            f"Time: {minutes} min\n"
            f"Payout: {_fmt_currency(payout)}\n"
            f"Effective rate: {_fmt_rate(hourly)}\n"
            f"Avg quality: {avg_q:.2f}/1.00\n"
            f"Platforms: {', '.join(f'{k}({v})' for k, v in platform_counts.items())}"
        ),
    }
    _sync_obsidian_session(result)
    return result



def week_summary(user_id: str = "default") -> dict:
    rows = db.execute(
        """
        SELECT
            DATE(t.created_at)               AS day,
            COUNT(*)                         AS tasks,
            SUM(t.time_spent_minutes)        AS minutes,
            SUM(t.estimated_payout)          AS payout,
            AVG(o.quality_score)             AS avg_quality,
            SUM(CASE WHEN t.status IN ('accepted','submitted_manual') THEN 1 ELSE 0 END) AS done,
            SUM(CASE WHEN t.status = 'rejected' THEN 1 ELSE 0 END)  AS rejected
        FROM gig_tasks t
        LEFT JOIN LATERAL (
            SELECT quality_score
            FROM gig_outputs
            WHERE task_id = t.id
            ORDER BY created_at DESC
            LIMIT 1
        ) o ON TRUE
        WHERE t.user_id = %s
          AND t.created_at >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY DATE(t.created_at)
        ORDER BY day DESC
        """,
        (user_id,),
    )

    if not rows:
        return {
            "user_id": user_id,
            "period":  "week",
            "message": "No gig tasks in the last 7 days.",
        }

    total_tasks   = sum(int(r["tasks"] or 0) for r in rows)
    total_minutes = sum(int(r["minutes"] or 0) for r in rows)
    total_payout  = sum(float(r["payout"] or 0) for r in rows)
    total_done    = sum(int(r["done"] or 0) for r in rows)
    total_rejected = sum(int(r["rejected"] or 0) for r in rows)
    total_hourly  = (total_payout / (total_minutes / 60)) if total_minutes > 0 else 0.0
    submitted = total_done + total_rejected
    accept_rate = (total_done / submitted * 100) if submitted > 0 else 0.0

    # Format day breakdown
    lines = []
    for r in rows:
        d_payout  = float(r["payout"] or 0)
        d_minutes = int(r["minutes"] or 0)
        d_rate    = (d_payout / (d_minutes / 60)) if d_minutes > 0 else 0.0
        lines.append(
            f"  {r['day']}: {r['tasks']} tasks · "
            f"{_fmt_currency(d_payout)} · {_fmt_rate(d_rate)}"
        )

    logger.info(f"Weekly report for user={user_id}: {total_tasks} tasks over 7 days")

    return {
        "user_id":               user_id,
        "period":                "week",
        "total_tasks":           total_tasks,
        "total_completed":       total_done,
        "total_rejected":        total_rejected,
        "acceptance_rate_pct":   round(accept_rate, 1),
        "total_minutes":         total_minutes,
        "total_payout_usd":      round(total_payout, 2),
        "effective_hourly_rate": round(total_hourly, 2),
        "daily_breakdown":       rows,
        "formatted": (
            f"📊 7-Day Gig Summary\n\n"
            f"Tasks: {total_tasks} · Done: {total_done} · Rejected: {total_rejected}\n"
            f"Acceptance: {accept_rate:.0f}%\n"
            f"Total payout: {_fmt_currency(total_payout)}\n"
            f"Total time: {total_minutes} min\n"
            f"Effective rate: {_fmt_rate(total_hourly)}\n\n"
            f"Daily breakdown:\n" + "\n".join(lines)
        ),
    }


def main(body: dict) -> dict:
    period  = str(body.get("period", "today")).lower()
    user_id = str(body.get("user_id", "default"))

    if period == "week":
        return week_summary(user_id)
    return today_summary(user_id)
