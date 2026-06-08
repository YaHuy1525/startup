#!/usr/bin/env python3
"""
Run worker / agent HTTP routes on a fixed interval.

Configure jobs via AGENT_SCHEDULE_JOBS (JSON array). Example:

[
  {
    "name": "crew-trend-run",
    "interval_seconds": 14400,
    "path": "/api/summon-agent",
    "body": {"prompt": "Find top trending short-form content", "target_count": 5}
  },
  {
    "name": "gig-daily-kpi",
    "interval_seconds": 86400,
    "path": "/gig/session/today",
    "body": {"user_id": "default"}
  }
]

For cron expressions (e.g. daily at 21:00), use n8n Schedule Trigger — see n8n-workflows/.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.utils.logger import setup_logger

logger = setup_logger("agent_scheduler")

DEFAULT_WORKER_URL = "http://python-worker:8080"
MIN_INTERVAL = 60


def _worker_base() -> str:
    return (
        os.environ.get("AGENT_SCHEDULER_WORKER_URL")
        or os.environ.get("PYTHON_WORKER_URL")
        or os.environ.get("TELEGRAM_WORKER_URL")
        or DEFAULT_WORKER_URL
    ).rstrip("/")


def _load_jobs() -> list[dict[str, Any]]:
    raw = os.environ.get("AGENT_SCHEDULE_JOBS", "").strip()
    if not raw:
        return []
    try:
        jobs = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error(f"AGENT_SCHEDULE_JOBS invalid JSON: {exc}")
        return []
    if not isinstance(jobs, list):
        logger.error("AGENT_SCHEDULE_JOBS must be a JSON array")
        return []
    return [j for j in jobs if isinstance(j, dict)]


def _run_job(job: dict[str, Any], base_url: str) -> None:
    name = job.get("name") or job.get("path") or "unnamed"
    path = str(job.get("path", "")).strip()
    if not path.startswith("/"):
        path = f"/{path}"
    method = str(job.get("method", "POST")).upper()
    body = job.get("body") or {}
    timeout = int(job.get("timeout", 600))
    url = f"{base_url}{path}"

    logger.info(f"Running scheduled job '{name}' -> {method} {url}")
    try:
        if method == "GET":
            resp = requests.get(url, params=body, timeout=timeout)
        else:
            resp = requests.post(url, json=body, timeout=timeout)
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError:
            payload = {"text": resp.text[:500]}
        logger.info(f"Job '{name}' OK: {str(payload)[:400]}")
    except requests.RequestException as exc:
        logger.error(f"Job '{name}' failed: {exc}")


def main() -> None:
    base_url = _worker_base()
    tick_seconds = max(int(os.environ.get("AGENT_SCHEDULER_TICK_SECONDS", "60")), 10)
    jobs = _load_jobs()

    if not jobs:
        logger.warning(
            "No jobs in AGENT_SCHEDULE_JOBS — idle. "
            "Set env or use n8n Schedule Trigger workflows."
        )

    # name -> next_run_unix
    next_run: dict[str, float] = {}
    now = time.time()
    for job in jobs:
        name = str(job.get("name") or job.get("path") or id(job))
        interval = max(int(job.get("interval_seconds", 3600)), MIN_INTERVAL)
        next_run[name] = now  # run first cycle soon after start

    logger.info(
        f"Agent scheduler started: worker={base_url} jobs={len(jobs)} tick={tick_seconds}s"
    )

    while True:
        now = time.time()
        for job in jobs:
            name = str(job.get("name") or job.get("path") or id(job))
            interval = max(int(job.get("interval_seconds", 3600)), MIN_INTERVAL)
            if now >= next_run.get(name, 0):
                _run_job(job, base_url)
                next_run[name] = now + interval
        time.sleep(tick_seconds)


if __name__ == "__main__":
    main()
