#!/usr/bin/env python3
"""
Run last30days research queries, normalize the result, and store them in Postgres.

This integration is intentionally wrapper-based because last30days can be installed
in different ways (CLI, local clone, shell alias, etc.). Configure one of:

- LAST30DAYS_COMMAND_TEMPLATE='last30days "{query}"'
- LAST30DAYS_COMMAND='/usr/local/bin/last30days'

If a template contains "{query}", the query is interpolated before execution.
Otherwise the query is appended as the final shell-safe argument.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("research_ingest_last30days")

LOGS_DIR = os.environ.get("LOGS_DIR", "/data/logs")
DEFAULT_REGION = os.environ.get("LAST30DAYS_REGION", "US")
DEFAULT_QUERIES = os.environ.get("LAST30DAYS_DEFAULT_QUERIES", "")
RUNNER_TEMPLATE = (
    os.environ.get("LAST30DAYS_COMMAND_TEMPLATE")
    or os.environ.get("LAST30DAYS_COMMAND")
    or 'last30days "{query}"'
)


def _query_list_from_env() -> list[str]:
    if not DEFAULT_QUERIES.strip():
        return []
    parts = re.split(r"\r?\n|\|\|", DEFAULT_QUERIES)
    return [p.strip() for p in parts if p.strip()]


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return cleaned[:80] or "research_topic"


def _normalize_hashtag(tag: str) -> str:
    tag = (tag or "").strip().lstrip("#")
    tag = re.sub(r"[^A-Za-z0-9_]", "", tag)
    return tag[:200]


def _extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s)>\]]+", text or "")
    seen = set()
    ordered = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _extract_channels(text: str) -> list[dict]:
    channels = []
    seen = set()
    for match in re.finditer(r"https?://(?:www\.)?youtube\.com/channel/(UC[a-zA-Z0-9_-]{20,})", text or ""):
        channel_id = match.group(1)
        if channel_id in seen:
            continue
        seen.add(channel_id)
        channels.append({
            "channel_id": channel_id,
            "url": match.group(0),
            "label": channel_id,
        })
    return channels


def _extract_hashtags(text: str) -> list[str]:
    tags = []
    seen = set()
    for raw in re.findall(r"#([A-Za-z0-9_]+)", text or ""):
        tag = _normalize_hashtag(raw)
        if not tag:
            continue
        low = tag.lower()
        if low in seen:
            continue
        seen.add(low)
        tags.append(tag)
    return tags


def _extract_summary(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("Source URL:", "Title:", "#", "##", "---", "```")):
            continue
        lines.append(stripped)
        if len(" ".join(lines)) > 500:
            break
    return " ".join(lines)[:1000] if lines else "No structured summary extracted."


def _estimate_confidence(hashtags: list[str], channels: list[dict], urls: list[str], summary: str) -> float:
    score = 0.20
    score += min(len(hashtags), 5) * 0.10
    score += min(len(channels), 3) * 0.15
    score += min(len(urls), 10) * 0.02
    if len(summary) > 120:
        score += 0.10
    return round(min(score, 0.95), 4)


def _run_last30days(query: str) -> str:
    template = RUNNER_TEMPLATE.strip()
    if "{query}" in template:
        command = template.replace("{query}", query.replace('"', '\\"'))
    else:
        command = f"{template} {shlex.quote(query)}"

    logger.info(f"Running last30days query: {query}")
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("LAST30DAYS_TIMEOUT_SECONDS", "180")),
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise RuntimeError(stderr or stdout or f"last30days exited with code {proc.returncode}")
    return proc.stdout or proc.stderr or ""


def _store_raw_output(query: str, run_id: int, raw_output: str) -> str:
    out_dir = Path(LOGS_DIR) / "last30days"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{int(time.time())}_{run_id}_{_slug(query)}.md"
    path.write_text(raw_output, encoding="utf-8")
    return str(path)


def _upsert_trend_row(
    hashtag: str,
    hashtag_candidates: list[str],
    region: str,
    summary: str,
    confidence: float,
    channels: list[dict],
    evidence_urls: list[str],
    raw_path: str,
) -> int | None:
    tag = _normalize_hashtag(hashtag)
    if not tag:
        return None
    row = db.execute_one(
        """
        INSERT INTO trend_intel (
            hashtag, region, source, source_engine, status, research_summary,
            confidence, channel_candidates, hashtag_candidates, evidence_urls,
            raw_research_ref, last_researched_at
        )
        VALUES (%s, %s, 'last30days', 'last30days', 'new', %s, %s, %s::jsonb, %s, %s::jsonb, %s, NOW())
        ON CONFLICT (hashtag, region) DO UPDATE SET
            source = 'last30days',
            source_engine = 'last30days',
            research_summary = EXCLUDED.research_summary,
            confidence = GREATEST(COALESCE(trend_intel.confidence, 0), COALESCE(EXCLUDED.confidence, 0)),
            channel_candidates = EXCLUDED.channel_candidates,
            hashtag_candidates = EXCLUDED.hashtag_candidates,
            evidence_urls = EXCLUDED.evidence_urls,
            raw_research_ref = EXCLUDED.raw_research_ref,
            status = CASE WHEN trend_intel.status = 'done' THEN trend_intel.status ELSE 'new' END,
            last_researched_at = NOW()
        RETURNING id
        """,
        (
            tag,
            region,
            summary,
            confidence,
            json.dumps(channels),
            [_normalize_hashtag(x) for x in hashtag_candidates if _normalize_hashtag(x)],
            json.dumps(evidence_urls),
            raw_path,
        ),
    )
    return row["id"] if row else None


def ingest_query(query: str, region: str = DEFAULT_REGION) -> dict:
    run_row = db.execute_one(
        """
        INSERT INTO trend_research_runs (query, region, status, started_at)
        VALUES (%s, %s, 'started', NOW())
        RETURNING id
        """,
        (query, region),
    )
    run_id = run_row["id"]
    try:
        raw_output = _run_last30days(query)
        raw_path = _store_raw_output(query, run_id, raw_output)
        channels = _extract_channels(raw_output)
        hashtags = _extract_hashtags(raw_output)
        evidence_urls = _extract_urls(raw_output)
        summary = _extract_summary(raw_output)
        confidence = _estimate_confidence(hashtags, channels, evidence_urls, summary)

        if not hashtags:
            hashtags = [_slug(query)]

        trend_ids = []
        for hashtag in hashtags[:8]:
            trend_id = _upsert_trend_row(
                hashtag=hashtag,
                hashtag_candidates=hashtags[:8],
                region=region,
                summary=summary,
                confidence=confidence,
                channels=channels,
                evidence_urls=evidence_urls,
                raw_path=raw_path,
            )
            if trend_id:
                trend_ids.append(trend_id)

        db.execute(
            """
            UPDATE trend_research_runs
            SET status='completed',
                result_count=%s,
                confidence=%s,
                parsed_summary=%s,
                raw_output=%s,
                raw_output_path=%s,
                completed_at=NOW()
            WHERE id=%s
            """,
            (len(trend_ids), confidence, summary, raw_output[:20000], raw_path, run_id),
        )
        return {
            "success": True,
            "run_id": run_id,
            "query": query,
            "region": region,
            "summary": summary,
            "confidence": confidence,
            "hashtags": hashtags[:8],
            "channels": channels[:5],
            "evidence_urls": evidence_urls[:10],
            "trend_ids": trend_ids,
            "raw_output_path": raw_path,
        }
    except Exception as exc:
        db.execute(
            """
            UPDATE trend_research_runs
            SET status='failed', error_message=%s, completed_at=NOW()
            WHERE id=%s
            """,
            (str(exc)[:1000], run_id),
        )
        logger.error(f"last30days ingest failed for '{query}': {exc}")
        return {
            "success": False,
            "run_id": run_id,
            "query": query,
            "region": region,
            "error": str(exc),
        }


def ingest_queries(queries: list[str], region: str = DEFAULT_REGION) -> dict:
    results = [ingest_query(query, region=region) for query in queries if query.strip()]
    success_count = sum(1 for r in results if r.get("success"))
    return {
        "success": success_count == len(results) if results else False,
        "processed": len(results),
        "successful": success_count,
        "failed": len(results) - success_count,
        "results": results,
    }


def get_research_status(limit: int = 10) -> dict:
    runs = db.execute(
        """
        SELECT id, source_engine, query, region, status, result_count, confidence,
               parsed_summary, raw_output_path, error_message, started_at, completed_at
        FROM trend_research_runs
        ORDER BY started_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {"runs": runs}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run last30days ingest queries")
    parser.add_argument("--query", action="append", default=[], help="Research query to run (repeatable)")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--status", action="store_true", help="Show recent run status instead of ingesting")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(get_research_status(), ensure_ascii=False))
        return

    queries = args.query or _query_list_from_env()
    if not queries:
        raise SystemExit("No queries supplied. Use --query or LAST30DAYS_DEFAULT_QUERIES.")

    print(json.dumps(ingest_queries(queries, region=args.region), ensure_ascii=False))


if __name__ == "__main__":
    main()
