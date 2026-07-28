#!/usr/bin/env python3
"""
Audio post-processing for stickman / Canva-style voiceovers.

Mirrors the Audacity steps from the viral stickman tutorial:
  - Truncate silence (≈ -40dB, gaps > 0.3s → 0.3s)
  - Normalize loudness

Uses ffmpeg silenceremove + loudnorm (no Audacity GUI required).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from scripts.utils.logger import setup_logger

logger = setup_logger("stickman_audio")

FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.environ.get("FFPROBE_BIN", "ffprobe")


def probe_duration_secs(path: str) -> float | None:
    try:
        proc = subprocess.run(
            [
                FFPROBE_BIN,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return float(proc.stdout.strip())
    except Exception as exc:
        logger.warning(f"ffprobe failed for {path}: {exc}")
        return None


def optimize_voiceover(
    input_path: str,
    output_path: str | None = None,
    *,
    silence_threshold_db: float | None = None,
    min_silence_sec: float | None = None,
    keep_silence_sec: float | None = None,
) -> dict[str, Any]:
    """
    Truncate long silences and normalize audio for retention-focused pacing.
    """
    src = Path(input_path)
    if not src.is_file():
        return {"success": False, "error": f"input_not_found:{input_path}"}

    threshold = silence_threshold_db or float(os.environ.get("STICKMAN_SILENCE_THRESHOLD_DB", "-40"))
    min_silence = min_silence_sec or float(os.environ.get("STICKMAN_MIN_SILENCE_SEC", "0.3"))
    keep_silence = keep_silence_sec or float(os.environ.get("STICKMAN_KEEP_SILENCE_SEC", "0.3"))

    dst = Path(output_path or str(src.with_name(f"{src.stem}_optimized.mp3")))
    dst.parent.mkdir(parents=True, exist_ok=True)

    # silenceremove: collapse gaps longer than min_silence down to keep_silence
    af = (
        f"silenceremove=stop_periods=-1:stop_duration={keep_silence}:stop_threshold={threshold}dB,"
        f"loudnorm=I=-16:TP=-1.5:LRA=11"
    )

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(src),
        "-af",
        af,
        "-ar",
        "44100",
        "-ac",
        "1",
        str(dst),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
    except subprocess.CalledProcessError as exc:
        return {
            "success": False,
            "error": "ffmpeg_optimize_failed",
            "stderr": (exc.stderr or "")[-1500:],
        }

    before = probe_duration_secs(str(src))
    after = probe_duration_secs(str(dst))
    return {
        "success": True,
        "input_path": str(src),
        "output_path": str(dst),
        "duration_before_secs": before,
        "duration_after_secs": after,
        "filters": af,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Optimize stickman voiceover audio")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    print(
        json.dumps(
            optimize_voiceover(args.input, args.output or None),
            ensure_ascii=False,
        ),
    )
