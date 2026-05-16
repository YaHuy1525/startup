#!/usr/bin/env python3
"""
Finance Proof Video Generator — @mini.money.matters style.

Converts earnings screenshots + AI-generated script into a TikTok/Reels-ready
vertical video (1080x1920) using FFmpeg. No face needed.

Video types:
  1. "proof"     — Screenshot slideshow with earnings amounts as text overlay
  2. "voiceover" — Same as proof + TTS narration (ElevenLabs/Kokoro)
  3. "hook"      — 3-second bold text hook card + proof slideshow

Usage:
    python scripts/finance_video_generator.py --type proof --week 2026-W19
    python scripts/finance_video_generator.py --type voiceover --brief-id 42
    python scripts/finance_video_generator.py --type hook --amount 47.23

    Via worker:
    POST /finance/generate-video { "type": "proof", "week_iso": "2026-W19" }
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("finance_video_generator")

# ─── Config ───────────────────────────────────────────────────────────────────
VIDEOS_DIR = Path(os.environ.get("FINANCE_VIDEOS_DIR", "/data/finance_videos"))
SCREENSHOTS_DIR = Path(os.environ.get("EARNINGS_SCREENSHOTS_DIR", "/data/earnings_screenshots"))
VOICEOVERS_DIR = Path(os.environ.get("VOICEOVER_DIR", "/data/voiceovers"))
FONTS_DIR = Path(os.environ.get("FONTS_DIR", "/data/fonts"))

# Vertical 9:16 — TikTok/Reels/Shorts native format
VIDEO_W = 1080
VIDEO_H = 1920
FPS = 30
SLIDE_DURATION = 4      # seconds per screenshot slide
HOOK_DURATION = 3       # seconds for hook card

# Brand colours (dark green finance aesthetic)
BG_COLOR = "0x0a1628"         # deep navy
ACCENT_COLOR = "0x00c853"     # money green
TEXT_COLOR = "0xffffff"
SUBTEXT_COLOR = "0xaab7c4"

FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _ensure_dirs() -> None:
    for d in (VIDEOS_DIR, VOICEOVERS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _safe_name(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)[:60]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ffmpeg(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    cmd = [FFMPEG_BIN, "-y"] + list(args)
    logger.debug(f"FFmpeg: {' '.join(cmd[:8])}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        logger.error(f"FFmpeg failed:\n{result.stderr[-2000:]}")
    return result


def _check_ffmpeg() -> bool:
    try:
        r = subprocess.run([FFMPEG_BIN, "-version"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


# ─── Step 1: Fetch data ───────────────────────────────────────────────────────
def _get_week_screenshots(week_iso: str) -> list[dict]:
    """Get earnings snapshots + screenshot paths for a given ISO week."""
    rows = db.execute(
        """
        SELECT es.platform_slug, es.amount_usd, es.screenshot_path,
               rp.display_name
        FROM earnings_snapshots es
        LEFT JOIN referral_platforms rp ON es.platform_slug = rp.slug
        WHERE es.week_iso = %s
        ORDER BY es.amount_usd DESC
        """,
        (week_iso,),
    )
    # Filter to files that actually exist
    valid = []
    for r in (rows or []):
        if r.get("screenshot_path") and Path(r["screenshot_path"]).exists():
            valid.append(dict(r))
        else:
            logger.warning(f"Screenshot missing: {r.get('screenshot_path')}")
    return valid


def _get_brief_narrative(brief_id: int) -> dict | None:
    return db.execute_one(
        "SELECT trend_name, viral_hook, base_narrative FROM content_briefs WHERE id = %s",
        (brief_id,),
    )


def _get_current_week() -> str:
    now = datetime.now(timezone.utc)
    yr, wk, _ = now.isocalendar()
    return f"{yr}-W{wk:02d}"


# ─── Step 2: Generate hook card (FFmpeg lavfi) ────────────────────────────────
def _generate_hook_card(amount: float, output_path: str) -> bool:
    """
    Generate a 3-second hook card:
    Dark navy background + bold green dollar amount + subtext.
    No images needed — pure FFmpeg text rendering.
    """
    hook_line1 = f"I made ${amount:.2f}"
    hook_line2 = "doing basically nothing"
    hook_line3 = "this week 👇"

    # Try to find a font
    font_path = _find_font()
    font_opt = f":fontfile={font_path}" if font_path else ""

    drawtext_args = (
        f"drawtext=text='{hook_line1}'"
        f":fontsize=96:fontcolor=0x00c853{font_opt}"
        f":x=(w-text_w)/2:y=(h-text_h)/2-180:box=0,"

        f"drawtext=text='{hook_line2}'"
        f":fontsize=52:fontcolor=white{font_opt}"
        f":x=(w-text_w)/2:y=(h-text_h)/2-60:box=0,"

        f"drawtext=text='{hook_line3}'"
        f":fontsize=52:fontcolor=white{font_opt}"
        f":x=(w-text_w)/2:y=(h-text_h)/2+20:box=0"
    )

    proc = _ffmpeg(
        "-f", "lavfi",
        "-i", f"color=c=0x0a1628:size={VIDEO_W}x{VIDEO_H}:rate={FPS}:duration={HOOK_DURATION}",
        "-vf", drawtext_args,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        output_path,
    )
    return proc.returncode == 0


def _find_font() -> str | None:
    """Find a usable font file for FFmpeg drawtext."""
    candidates = [
        str(FONTS_DIR / "Roboto-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


# ─── Step 3: Scale a screenshot to 1080x1920 ─────────────────────────────────
def _scale_screenshot_to_vertical(input_path: str, output_path: str) -> bool:
    """
    Scale any screenshot to 1080x1920 vertical with padding.
    Preserves aspect ratio — fills with blurred background.
    """
    scale_filter = (
        f"[0:v]scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color=0x0a1628[fg];"
        f"[0:v]scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_W}:{VIDEO_H},boxblur=20:20[bg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )

    proc = _ffmpeg(
        "-i", input_path,
        "-filter_complex", scale_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-t", str(SLIDE_DURATION),
        output_path,
    )
    return proc.returncode == 0


# ─── Step 4: Add earnings amount text overlay to scaled screenshot ────────────
def _add_earnings_overlay(
    input_path: str,
    output_path: str,
    platform_name: str,
    amount: float,
    slide_index: int,
    total_slides: int,
) -> bool:
    """
    Add platform name + earnings amount as text overlay on the screenshot slide.
    Bottom 1/4 of screen — doesn't cover the screenshot content.
    """
    font_path = _find_font()
    font_opt = f":fontfile={font_path}" if font_path else ""

    amount_text = f"${amount:.2f}"
    platform_text = platform_name.upper()
    counter_text = f"{slide_index}/{total_slides}"

    drawtext_args = (
        # Semi-transparent dark box at bottom
        f"drawbox=x=0:y=ih*0.72:w=iw:h=ih*0.28:color=0x0a1628@0.85:t=fill,"

        # Platform name
        f"drawtext=text='{platform_text}'"
        f":fontsize=44:fontcolor=0xaab7c4{font_opt}"
        f":x=(w-text_w)/2:y=h*0.75:box=0,"

        # Earnings amount — large green
        f"drawtext=text='{amount_text}'"
        f":fontsize=110:fontcolor=0x00c853{font_opt}"
        f":x=(w-text_w)/2:y=h*0.80:box=0,"

        # Slide counter
        f"drawtext=text='{counter_text}'"
        f":fontsize=36:fontcolor=0xaab7c4{font_opt}"
        f":x=w-100:y=h*0.95:box=0"
    )

    proc = _ffmpeg(
        "-i", input_path,
        "-vf", drawtext_args,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        output_path,
    )
    return proc.returncode == 0


# ─── Step 5: Outro card ───────────────────────────────────────────────────────
def _generate_outro_card(total: float, output_path: str) -> bool:
    """Generate a 3-second CTA outro card."""
    font_path = _find_font()
    font_opt = f":fontfile={font_path}" if font_path else ""

    lines = [
        (f"TOTAL: ${total:.2f}", 96, "0x00c853", "h/2-140"),
        ("Comment  L I S T", 52, "white", "h/2-30"),
        ("for every app I use", 48, "0xaab7c4", "h/2+40"),
        ("👇  Link in bio  👇", 44, "white", "h/2+110"),
    ]

    drawtext_args = ",".join(
        f"drawtext=text='{text}':fontsize={sz}:fontcolor={color}{font_opt}"
        f":x=(w-text_w)/2:y={y}:box=0"
        for text, sz, color, y in lines
    )

    proc = _ffmpeg(
        "-f", "lavfi",
        "-i", f"color=c=0x0a1628:size={VIDEO_W}x{VIDEO_H}:rate={FPS}:duration=4",
        "-vf", drawtext_args,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        output_path,
    )
    return proc.returncode == 0


# ─── Step 6: Concatenate all clips ────────────────────────────────────────────
def _concat_clips(clip_paths: list[str], output_path: str) -> bool:
    """Concatenate multiple MP4 clips using FFmpeg concat demuxer."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
        concat_list = f.name

    proc = _ffmpeg(
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        output_path,
    )

    try:
        Path(concat_list).unlink()
    except Exception:
        pass

    return proc.returncode == 0


# ─── Step 7: Optionally add voiceover audio ───────────────────────────────────
def _add_voiceover(video_path: str, audio_path: str, output_path: str) -> bool:
    """Mix a voiceover audio track into the video."""
    proc = _ffmpeg(
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",            # end when shorter stream ends
        "-filter_complex", "[1:a]volume=1.0[a]",
        "-map", "0:v",
        "-map", "[a]",
        output_path,
    )
    return proc.returncode == 0


# ─── Main pipeline ────────────────────────────────────────────────────────────
def generate_proof_video(
    week_iso: str | None = None,
    video_type: str = "proof",
    brief_id: int | None = None,
    amount_override: float | None = None,
) -> dict[str, Any]:
    """
    Full pipeline: screenshots → vertical slides → hook card → concat → output MP4.

    Args:
        week_iso:        ISO week (e.g. '2026-W19'). Defaults to current week.
        video_type:      'proof' | 'voiceover' | 'hook'
        brief_id:        Content brief ID for voiceover script. Auto-detected if None.
        amount_override: Use this total instead of summing DB snapshots.
    """
    if not _check_ffmpeg():
        return {"error": "FFmpeg not found. Install FFmpeg and ensure it's in PATH."}

    _ensure_dirs()
    week_iso = week_iso or _get_current_week()

    # ── Fetch screenshots
    slides = _get_week_screenshots(week_iso)
    if not slides and not amount_override:
        return {
            "error": f"No screenshots found for {week_iso}. "
                     f"Drop images into {SCREENSHOTS_DIR} named "
                     f"platform_YYYY-MM-DD_amount.png first.",
            "hint": "Run /earnings_scan to index them first.",
        }

    total = amount_override or sum(float(s["amount_usd"]) for s in slides)

    logger.info(f"Generating {video_type} video for {week_iso}: ${total:.2f} across {len(slides)} slides")

    ts = _timestamp()
    work_dir = VIDEOS_DIR / f"work_{ts}"
    work_dir.mkdir(parents=True, exist_ok=True)

    clip_paths: list[str] = []

    # ── Clip 0: Hook card
    hook_path = str(work_dir / "00_hook.mp4")
    if _generate_hook_card(total, hook_path):
        clip_paths.append(hook_path)
        logger.info("Hook card generated ✓")
    else:
        logger.warning("Hook card generation failed — skipping")

    # ── Clips 1..N: Screenshot slides
    for i, slide in enumerate(slides, start=1):
        scaled_path = str(work_dir / f"{i:02d}_scaled.mp4")
        overlay_path = str(work_dir / f"{i:02d}_overlay.mp4")

        platform_name = slide.get("display_name") or slide.get("platform_slug") or "App"
        amount = float(slide["amount_usd"])

        ok1 = _scale_screenshot_to_vertical(slide["screenshot_path"], scaled_path)
        if not ok1:
            logger.warning(f"Scaling failed for slide {i}: {slide['screenshot_path']}")
            continue

        ok2 = _add_earnings_overlay(
            scaled_path, overlay_path,
            platform_name, amount,
            slide_index=i, total_slides=len(slides),
        )
        if ok2:
            clip_paths.append(overlay_path)
            logger.info(f"Slide {i}/{len(slides)}: {platform_name} ${amount:.2f} ✓")
        else:
            clip_paths.append(scaled_path)  # fallback: no overlay
            logger.warning(f"Overlay failed for slide {i} — using raw scaled")

    # ── Outro card
    outro_path = str(work_dir / "outro.mp4")
    if _generate_outro_card(total, outro_path):
        clip_paths.append(outro_path)
        logger.info("Outro card generated ✓")

    if not clip_paths:
        return {"error": "All clip generation steps failed. Check FFmpeg installation."}

    # ── Concatenate
    concat_path = str(work_dir / "concat.mp4")
    if not _concat_clips(clip_paths, concat_path):
        return {"error": "Clip concatenation failed."}

    final_path = str(VIDEOS_DIR / f"finance_{_safe_name(week_iso)}_{ts}.mp4")

    # ── Add voiceover (optional)
    if video_type == "voiceover":
        brief = None
        if brief_id:
            brief = _get_brief_narrative(brief_id)
        if not brief:
            # Auto-find the latest finance brief
            brief = db.execute_one(
                """
                SELECT trend_name, viral_hook, base_narrative
                FROM content_briefs
                JOIN genesis_categories gc ON category_id = gc.id
                WHERE gc.slug = 'finance'
                ORDER BY created_at DESC LIMIT 1
                """
            )

        if brief:
            script = brief.get("viral_hook", "") + ". " + brief.get("base_narrative", "")[:400]
            try:
                from scripts.voiceover_service import synthesize
                vo_result = synthesize(text=script)
                if vo_result.get("success") and vo_result.get("output_path"):
                    voiced_path = final_path.replace(".mp4", "_voiced.mp4")
                    ok = _add_voiceover(concat_path, vo_result["output_path"], voiced_path)
                    if ok:
                        final_path = voiced_path
                        logger.info("Voiceover added ✓")
                    else:
                        logger.warning("Voiceover mix failed — using silent video")
                else:
                    logger.warning(f"Voiceover synthesis failed: {vo_result.get('error')}")
            except Exception as e:
                logger.warning(f"Voiceover skipped: {e}")
        else:
            logger.warning("No finance brief found for voiceover — using silent video")

    # ── Move final file
    import shutil
    shutil.copy2(concat_path, final_path)

    # ── Save to videos table
    size_mb = round(Path(final_path).stat().st_size / (1024 * 1024), 2)
    video_id = db.execute_returning(
        """
        INSERT INTO videos (file_path, file_size_mb, caption, hashtags, status)
        VALUES (%s, %s, %s, %s, 'ready')
        RETURNING id
        """,
        (
            final_path,
            size_mb,
            f"I made ${total:.2f} in passive income this week — here's the breakdown 💸",
            [
                "passiveincome", "sidehustle", "beermoney",
                "honeygain", "makemoneyonline", "moneytok",
                "passiveincomeapps", "sidehustleideas",
            ],
        ),
    )

    # ── Cleanup work dir
    try:
        shutil.rmtree(work_dir)
    except Exception:
        pass

    logger.info(f"Finance video ready: video_id={video_id} path={final_path} size={size_mb}MB")

    return {
        "video_id": video_id,
        "file_path": final_path,
        "size_mb": size_mb,
        "total_earned": total,
        "slides": len(slides),
        "week_iso": week_iso,
        "video_type": video_type,
        "message": (
            f"Video #{video_id} ready. "
            f"Run /upload_tiktok {video_id} or /upload_youtube {video_id} to publish."
        ),
    }


# ─── Worker entry point ────────────────────────────────────────────────────────
def main(body: dict | None = None, **kwargs) -> dict[str, Any]:
    """Entry point for worker.py integration."""
    if body is None:
        body = kwargs

    return generate_proof_video(
        week_iso=body.get("week_iso"),
        video_type=body.get("type", body.get("video_type", "proof")),
        brief_id=body.get("brief_id"),
        amount_override=float(body["amount"]) if body.get("amount") else None,
    )


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Finance Proof Video Generator")
    parser.add_argument(
        "--type", choices=["proof", "voiceover", "hook"], default="proof",
        help="Video type: proof (slideshow only), voiceover (+ TTS), hook (bold hook card only)",
    )
    parser.add_argument("--week", type=str, default=None, help="ISO week e.g. 2026-W19")
    parser.add_argument("--brief-id", type=int, default=None, help="Brief ID for voiceover script")
    parser.add_argument("--amount", type=float, default=None, help="Override total earnings amount")
    args = parser.parse_args()

    result = generate_proof_video(
        week_iso=args.week,
        video_type=args.type,
        brief_id=args.brief_id,
        amount_override=args.amount,
    )
    print(json.dumps(result, indent=2, default=str))
