#!/usr/bin/env python3
"""
Simple scheduler for periodic last30days ingest.
"""
from __future__ import annotations

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.research_ingest_last30days import ingest_queries, _query_list_from_env
from scripts.utils.logger import setup_logger

logger = setup_logger("research_scheduler")


def main() -> None:
    interval_seconds = int(os.environ.get("LAST30DAYS_SCHEDULE_SECONDS", "21600"))
    logger.info(f"Starting research scheduler with interval={interval_seconds}s")

    while True:
        queries = _query_list_from_env()
        if not queries:
            logger.warning("LAST30DAYS_DEFAULT_QUERIES is empty; skipping ingest cycle")
        else:
            result = ingest_queries(queries)
            logger.info(f"Research ingest cycle complete: {result}")
        time.sleep(max(interval_seconds, 300))


if __name__ == "__main__":
    main()
