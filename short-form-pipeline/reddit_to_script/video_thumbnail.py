"""Extract a thumbnail still from an anime-theory MP4 (frame from the video)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import config

# How many recent thumbs to remember when avoiding repeats.
_RECENT_LIMIT = 24
_REGISTRY_NAME = "_thumbnail_picks.json"


def _ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("ffmpeg not found (install ffmpeg or imageio-ffmpeg)") from exc


def _ffprobe_bin() -> str:
    found = shutil.which("ffprobe")
    if found:
        return found
    ff = _ffmpeg_bin()
    probe = Path(ff).with_name("ffprobe.exe" if ff.lower().endswith(".exe") else "ffprobe")
    if probe.is_file():
        return str(probe)
    return "ffprobe"


def probe_duration_seconds(video: Path) -> float:
    try:
        proc = subprocess.run(
            [
                _ffprobe_bin(),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return max(0.5, float(proc.stdout.strip()))
    except Exception:
        pass
    # Fallback: parse ffmpeg -i stderr
    try:
        proc = subprocess.run(
            [_ffmpeg_bin(), "-i", str(video)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return max(0.5, h * 3600 + mi * 60 + s)
    except Exception:
        pass
    return 30.0


def _registry_path() -> Path:
    return config.MEME_OUT_DIR / _REGISTRY_NAME


def _load_registry() -> list[dict]:
    path = _registry_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("picks") or []) if isinstance(data, dict) else []
    except Exception:
        return []


def _save_registry(picks: list[dict]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"picks": picks[-_RECENT_LIMIT:], "updated_at": time.time()}, indent=2),
        encoding="utf-8",
    )


def _fingerprint_jpeg(path: Path) -> str | None:
    """Cheap perceptual-ish fingerprint (average 8x8 grayscale)."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as im:
            small = im.convert("L").resize((8, 8))
            pixels = list(small.getdata())
        avg = sum(pixels) / max(1, len(pixels))
        bits = "".join("1" if p >= avg else "0" for p in pixels)
        return bits
    except Exception:
        try:
            raw = path.read_bytes()[:8192]
            return hashlib.md5(raw).hexdigest()
        except Exception:
            return None


def _hamming(a: str, b: str) -> int:
    if not a or not b or len(a) != len(b):
        return 64
    return sum(x != y for x, y in zip(a, b))


def _topic_key(stem: str) -> str:
    s = stem.lower()
    for prefix in ("anime-theory-",):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    # Drop timestamp/slug noise → keep character keywords for "same series" grouping
    tokens = re.findall(r"[a-z]+", s)
    stop = {
        "the", "a", "an", "and", "of", "in", "to", "for", "vs", "with", "from",
        "truth", "hidden", "connection", "between", "unexpected", "shocking",
        "revealed", "about", "movie", "jjk", "jujutsu", "kaisen", "compact",
    }
    keep = [t for t in tokens if t not in stop and len(t) > 2][:6]
    return "-".join(keep) or "general"


def candidate_timestamps(duration: float, *, stem: str = "") -> list[float]:
    """Prefer mid/late scenes — opening frames (Yuta close-ups) repeat too often."""
    duration = max(duration, 4.0)
    # Skip first ~12% and last ~8% (title/hook + end card)
    lo = max(2.0, duration * 0.12)
    hi = max(lo + 1.0, duration * 0.92)
    span = hi - lo
    # Spread candidates across the body of the video
    fracs = [0.15, 0.28, 0.42, 0.55, 0.68, 0.82]
    base = [round(lo + span * f, 2) for f in fracs]
    # Rotate order by video stem so consecutive Yuta videos don't pick the same slot
    if stem:
        h = int(hashlib.md5(stem.encode("utf-8")).hexdigest()[:8], 16)
        rot = h % len(base)
        base = base[rot:] + base[:rot]
    return base


def pick_thumbnail_seconds(
    video: Path,
    *,
    preferred: float | None = None,
    duration: float | None = None,
) -> float:
    """Choose a non-opening timestamp, rotated per video and recent history."""
    dur = float(duration) if duration is not None else probe_duration_seconds(video)
    if preferred is not None and preferred > 0:
        return min(max(0.3, preferred), max(0.3, dur - 0.4))

    cands = candidate_timestamps(dur, stem=video.stem)
    recent = _load_registry()
    topic = _topic_key(video.stem)
    used = {
        round(float(p.get("at_seconds") or 0), 1)
        for p in recent
        if p.get("topic") == topic
    }
    for ss in cands:
        if round(ss, 1) not in used:
            return ss
    # All slots used recently — pick least-recent for this topic
    return cands[0]


def extract_thumbnail_from_video(
    video_path: str | Path,
    *,
    out_path: str | Path | None = None,
    at_seconds: float | None = None,
    avoid_repeats: bool = True,
) -> Path:
    """Grab a JPEG frame from the rendered Short for AiToEarn cover_url.

    Default no longer sticks to 1.5s (which made recent Yuta videos share the
    same opening face). Picks a mid/late frame, rotated per title, and skips
    timestamps / fingerprints used on recent thumbs for the same topic.
    """
    video = Path(video_path)
    if not video.is_file():
        raise FileNotFoundError(str(video))
    out = Path(out_path) if out_path else (
        config.MEME_OUT_DIR / f"{video.stem}-thumb.jpg"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = _ffmpeg_bin()
    duration = probe_duration_seconds(video)

    def _run(ss: float) -> subprocess.CompletedProcess[str]:
        cmd = [
            ff,
            "-y",
            "-ss",
            str(max(0.0, ss)),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out),
        ]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if at_seconds is not None and float(at_seconds) > 0:
        candidates = [float(at_seconds)]
    else:
        candidates = candidate_timestamps(duration, stem=video.stem)
        # Prefer unused timestamp first
        first = pick_thumbnail_seconds(video, duration=duration)
        candidates = [first] + [c for c in candidates if abs(c - first) > 0.05]

    recent = _load_registry() if avoid_repeats else []
    topic = _topic_key(video.stem)
    recent_fps = [
        str(p.get("fingerprint") or "")
        for p in recent
        if p.get("topic") == topic and p.get("fingerprint")
    ]

    chosen_ss = candidates[0]
    last_err = ""
    for ss in candidates:
        result = _run(ss)
        if result.returncode != 0 or not out.is_file() or out.stat().st_size < 1000:
            last_err = (result.stderr or result.stdout or "")[:300]
            continue
        fp = _fingerprint_jpeg(out)
        if avoid_repeats and fp and any(_hamming(fp, old) <= 8 for old in recent_fps if len(old) == len(fp)):
            # Too similar to a recent Yuta (etc.) thumb — try next timestamp
            continue
        chosen_ss = ss
        break
    else:
        # Last resort: early frame if nothing else worked
        result = _run(min(2.0, duration * 0.2))
        if result.returncode != 0 or not out.is_file():
            raise RuntimeError(f"ffmpeg thumbnail failed: {last_err}")
        chosen_ss = min(2.0, duration * 0.2)
        fp = _fingerprint_jpeg(out)

    if avoid_repeats:
        picks = _load_registry()
        picks.append(
            {
                "video": video.name,
                "thumb": out.name,
                "topic": topic,
                "at_seconds": round(chosen_ss, 2),
                "duration": round(duration, 2),
                "fingerprint": fp,
                "ts": time.time(),
            }
        )
        _save_registry(picks)

    print(
        f"  thumbnail @ {chosen_ss:.1f}s / {duration:.1f}s -> {out.name} "
        f"(topic={topic})",
        flush=True,
    )
    global LAST_PICK
    LAST_PICK = {
        "file": str(out),
        "at_seconds": round(chosen_ss, 2),
        "duration": round(duration, 2),
        "topic": topic,
        "fingerprint": fp,
    }
    return out


# Set by the most recent extract_thumbnail_from_video call.
LAST_PICK: dict | None = None
