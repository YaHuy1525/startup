"""Stage 3 — submit a payload to short-video-maker, poll, and verify the MP4.

Mirrors the manual PowerShell flow:
    POST /api/short-video  ->  GET /api/short-video/{id}/status  ->  out/*.mp4
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests

from . import config


class RenderError(RuntimeError):
    """Raised when a render fails or times out."""


def api_ready(*, timeout: int = 5) -> bool:
    """Return True if the short-video-maker health endpoint responds ok."""
    try:
        resp = requests.get(f"{config.SVM_BASE_URL}/health", timeout=timeout)
        return resp.ok and resp.json().get("status") == "ok"
    except (requests.RequestException, ValueError):
        return False


def submit(payload: dict[str, Any]) -> str:
    """Submit a render job and return its videoId."""
    resp = requests.post(
        f"{config.SVM_BASE_URL}/api/short-video",
        json=payload,
        timeout=30,
    )
    if not resp.ok:
        raise RenderError(f"Submit failed {resp.status_code}: {resp.text[:300]}")
    video_id = resp.json().get("videoId")
    if not video_id:
        raise RenderError(f"No videoId in response: {resp.text[:300]}")
    return video_id


def poll(video_id: str, *, interval: int = 10, max_wait: int = 900) -> str:
    """Poll status until 'ready'/'failed' or timeout. Returns final status."""
    waited = 0
    while waited <= max_wait:
        try:
            resp = requests.get(
                f"{config.SVM_BASE_URL}/api/short-video/{video_id}/status", timeout=15
            )
            status = resp.json().get("status", "unknown") if resp.ok else "unknown"
        except (requests.RequestException, ValueError):
            status = "unknown"
        print(f"[{waited:>4}s] status={status}", flush=True)
        if status in ("ready", "failed"):
            return status
        time.sleep(interval)
        waited += interval
    raise RenderError(f"Render timed out after {max_wait}s (id={video_id}).")


def verify(video_id: str) -> Path:
    """Return the path to the finished MP4, raising if it is missing."""
    mp4 = config.SVM_OUT_DIR / f"{video_id}.mp4"
    # Bind-mount propagation on Windows/WSL2 can lag a few seconds.
    for _ in range(10):
        if mp4.exists() and mp4.stat().st_size > 0:
            return mp4
        time.sleep(2)
    raise RenderError(f"MP4 not found on disk: {mp4}")


def render(payload: dict[str, Any], *, max_wait: int = 900) -> Path:
    """Full submit -> poll -> verify cycle. Returns the MP4 path."""
    if not api_ready():
        raise RenderError(
            f"short-video-maker not reachable at {config.SVM_BASE_URL}. "
            "Start it: docker compose -f docker-compose.short-video-maker.yml up -d"
        )
    video_id = submit(payload)
    print(f"Submitted. videoId={video_id}", flush=True)
    status = poll(video_id, max_wait=max_wait)
    if status != "ready":
        raise RenderError(f"Render ended with status={status} (id={video_id}).")
    mp4 = verify(video_id)
    print(f"DONE -> {mp4} ({mp4.stat().st_size / 1_048_576:.2f} MB)", flush=True)
    return mp4


def _main() -> None:
    parser = argparse.ArgumentParser(description="Submit a payload JSON to short-video-maker.")
    parser.add_argument("payload_json", help="Path to a payload JSON file.")
    parser.add_argument("--max-wait", type=int, default=900)
    args = parser.parse_args()

    payload = json.loads(Path(args.payload_json).read_text(encoding="utf-8"))
    render(payload, max_wait=args.max_wait)


if __name__ == "__main__":
    _main()
