"""Persist anime-theory pipeline runs to Postgres / Supabase."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("anime_theory_store")


def _ensure_db_url() -> bool:
    """Prefer DATABASE_URL; fall back to Supabase Postgres URL."""
    if os.environ.get("DATABASE_URL"):
        return True
    alt = (
        os.environ.get("SUPABASE_DB_URL")
        or os.environ.get("SUPABASE_DATABASE_URL")
        or ""
    ).strip()
    if alt:
        os.environ["DATABASE_URL"] = alt
        return True
    return False


def _probe_duration_secs(file_path: str | None) -> float | None:
    if not file_path or not Path(file_path).is_file():
        return None
    try:
        import re
        import subprocess

        from reddit_to_script import compress_video  # type: ignore

        ff = compress_video.find_ffmpeg()
        proc = subprocess.run(
            [ff, "-i", file_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
        if not m:
            return None
        h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return round(h * 3600 + mi * 60 + s, 2)
    except Exception:
        return None


def save_anime_theory_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Insert videos + anime_theory_runs (+ workflow_executions) rows.

    Non-fatal: returns {ok:false} if DB unavailable so pipeline still succeeds.
    """
    if payload.get("dry_run"):
        return {"ok": True, "skipped": "dry_run"}

    if not _ensure_db_url():
        return {"ok": False, "error": "database_url_not_configured"}

    file_path = str(payload.get("file") or payload.get("file_path") or "").strip() or None
    title = str(payload.get("title") or payload.get("topic") or "Anime Theory").strip()
    topic = str(payload.get("topic") or title).strip()
    anime = str(payload.get("anime") or "").strip() or None
    caption = str(payload.get("caption") or title).strip()
    hashtags = payload.get("hashtags") or []
    if isinstance(hashtags, str):
        hashtags = [t for t in hashtags.replace(",", " ").split() if t]
    hashtags = [str(t) for t in hashtags][:20]

    size_mb = payload.get("size_mb")
    if size_mb is None and file_path and Path(file_path).is_file():
        size_mb = round(Path(file_path).stat().st_size / 1_048_576, 2)

    duration = payload.get("duration_secs")
    if duration is None:
        duration = _probe_duration_secs(file_path)

    pub = payload.get("publish") if isinstance(payload.get("publish"), dict) else {}
    public_url = payload.get("public_url") or pub.get("public_url")
    cover_url = payload.get("cover_url") or pub.get("cover_url")
    thumb_meta = pub.get("thumbnail_meta") if isinstance(pub, dict) else None
    thumbnail_path = None
    if isinstance(thumb_meta, dict):
        thumbnail_path = thumb_meta.get("file")
    thumbnail_path = thumbnail_path or payload.get("thumbnail_path") or payload.get("cover_file")

    publish_ok = bool(payload.get("published") or (pub.get("ok") if pub else False))
    published_count = payload.get("published_count")
    failed_count = payload.get("failed_count")
    if published_count is None and isinstance(pub.get("result"), dict):
        published_count = pub["result"].get("published_count")
        failed_count = pub["result"].get("failed_count")

    status = "failed"
    if payload.get("ok") or payload.get("success"):
        status = "published" if publish_ok else ("rendered" if file_path else "ready")
    if payload.get("error") and not file_path:
        status = "failed"

    channels = payload.get("channels") or []
    if isinstance(channels, str):
        channels = [c.strip() for c in channels.split(",") if c.strip()]

    scenes = payload.get("scenes")
    scenes_json = json.dumps(scenes) if scenes is not None else None
    publish_result_json = None
    if pub:
        try:
            publish_result_json = json.dumps(pub.get("result") or pub, default=str)
        except Exception:
            publish_result_json = None

    started = payload.get("started_at") or datetime.now(timezone.utc).isoformat()
    completed = datetime.now(timezone.utc).isoformat()

    video_id = None
    workflow_id = None
    run_id = None

    try:
        # 1) videos row (dashboard / publish tracking)
        if file_path or public_url:
            video_id = db.execute_returning(
                """
                INSERT INTO videos
                    (file_path, thumbnail_path, duration_secs, file_size_mb,
                     caption, hashtags, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    file_path or public_url or f"anime-theory:{topic[:40]}",
                    thumbnail_path or cover_url,
                    duration,
                    size_mb,
                    caption,
                    hashtags or None,
                    "published" if publish_ok else "ready",
                ),
            )

        # 2) workflow_executions (Pipelines page)
        try:
            workflow_id = db.execute_returning(
                """
                INSERT INTO workflow_executions
                    (workflow_name, status, started_at, completed_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    "anime-theory",
                    "completed" if status in {"rendered", "published", "ready"} else "failed",
                    started,
                    completed,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"workflow_executions insert skipped: {exc}")

        # 3) anime_theory_runs detail
        run_id = db.execute_returning(
            """
            INSERT INTO anime_theory_runs
                (topic, title, anime, context, file_path, public_url, cover_url,
                 thumbnail_path, caption, hashtags, scene_count, scenes,
                 size_mb, duration_secs, video_id, workflow_id,
                 publish_ok, published_count, failed_count, publish_result,
                 channels, status, error, dry_run)
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s::jsonb,
                %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb,
                %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                topic,
                title,
                anime,
                str(payload.get("context") or "")[:2000] or None,
                file_path,
                public_url,
                cover_url,
                thumbnail_path,
                caption,
                hashtags or None,
                payload.get("scene_count"),
                scenes_json,
                size_mb,
                duration,
                video_id,
                workflow_id,
                publish_ok,
                published_count or 0,
                failed_count or 0,
                publish_result_json,
                channels or None,
                status,
                str(payload.get("error") or "")[:1000] or None,
                bool(payload.get("dry_run")),
            ),
        )

        # 4) published_videos stubs per successful channel (best-effort)
        if video_id and publish_ok:
            pub_result = pub.get("result") if isinstance(pub, dict) else None
            results = []
            if isinstance(pub_result, dict):
                inner = pub_result.get("result") if isinstance(pub_result.get("result"), dict) else pub_result
                results = inner.get("results") or pub_result.get("results") or []
            for row in results if isinstance(results, list) else []:
                if not isinstance(row, dict) or not row.get("success"):
                    continue
                try:
                    db.execute(
                        """
                        INSERT INTO published_videos
                            (video_id, platform, account_name, caption, hashtags, status)
                        VALUES (%s, %s, %s, %s, %s, 'published')
                        """,
                        (
                            video_id,
                            str(row.get("platform") or "unknown"),
                            str(row.get("account") or row.get("account_id") or "")[:100],
                            caption,
                            hashtags or None,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"published_videos insert skipped: {exc}")

        logger.info(
            f"Saved anime_theory_run id={run_id} video_id={video_id} status={status}"
        )
        return {
            "ok": True,
            "run_id": run_id,
            "video_id": video_id,
            "workflow_id": workflow_id,
            "status": status,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"anime_theory_store failed: {exc}")
        return {"ok": False, "error": str(exc)}
