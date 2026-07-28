"""Keep rendered MP4s under a size budget (default 50 MB).

Uses Remotion's bundled ffmpeg when system ffmpeg is unavailable.
Strategy: target average video bitrate from duration, then escalate
(CRF → lower scale) if still over budget.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

DEFAULT_MAX_MB = float(os.getenv("MAX_VIDEO_MB", "50"))
AUDIO_BITRATE = "96k"
AUDIO_BPS = 96_000


def _pipeline_root() -> Path:
    return Path(__file__).resolve().parent.parent


def find_ffmpeg() -> str:
    """Prefer system ffmpeg, else Remotion compositor binary."""
    which = shutil.which("ffmpeg")
    if which:
        return which

    root = _pipeline_root() / "node_modules" / "@remotion"
    system = platform.system().lower()
    machine = platform.machine().lower()
    candidates: list[Path] = []
    if system == "windows":
        candidates.append(root / "compositor-win32-x64-msvc" / "ffmpeg.exe")
    elif system == "linux":
        if "aarch" in machine or "arm" in machine:
            candidates.append(root / "compositor-linux-arm64-gnu" / "ffmpeg")
        else:
            candidates.append(root / "compositor-linux-x64-gnu" / "ffmpeg")
            candidates.append(root / "compositor-linux-x64-musl" / "ffmpeg")
    elif system == "darwin":
        if "arm" in machine:
            candidates.append(root / "compositor-darwin-arm64" / "ffmpeg")
        else:
            candidates.append(root / "compositor-darwin-x64" / "ffmpeg")

    candidates.extend(root.glob("compositor-*/ffmpeg*"))
    for path in candidates:
        if path.is_file():
            return str(path)
    raise RuntimeError(
        "ffmpeg not found (system PATH or @remotion/compositor-*). "
        "Install ffmpeg or run npm install in short-form-pipeline."
    )


def _probe_duration_seconds(ffmpeg: str, path: Path) -> float:
    """Parse Duration from ffmpeg -i stderr (no ffprobe required)."""
    result = subprocess.run(
        [ffmpeg, "-i", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    blob = (result.stderr or "") + (result.stdout or "")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", blob)
    if not m:
        return 0.0
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def _size_mb(path: Path) -> float:
    return path.stat().st_size / 1_048_576


def _run_ffmpeg(ffmpeg: str, args: list[str]) -> None:
    cmd = [ffmpeg, "-y", *args]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "")[-800:]
        raise RuntimeError(f"ffmpeg failed ({result.returncode}): {err}")


def _reencode(
    ffmpeg: str,
    src: Path,
    dst: Path,
    *,
    video_bitrate: str | None = None,
    crf: int | None = None,
    scale: str | None = None,
) -> None:
    vf: list[str] = []
    if scale:
        vf.append(scale)
    args = ["-i", str(src)]
    if vf:
        args += ["-vf", ",".join(vf)]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium"]
    if video_bitrate:
        args += ["-b:v", video_bitrate, "-maxrate", video_bitrate, "-bufsize", video_bitrate]
    if crf is not None:
        args += ["-crf", str(crf)]
    args += [
        "-c:a",
        "aac",
        "-b:a",
        AUDIO_BITRATE,
        "-movflags",
        "+faststart",
        str(dst),
    ]
    _run_ffmpeg(ffmpeg, args)


def _install_compressed(src: Path, dest: Path) -> Path:
    """Install compressed ``src`` as ``dest`` (or a sibling if overwrite fails).

    Docker bind mounts on Windows often reject ``shutil.copy2`` metadata
    (utime → Operation not permitted) even when content writes work — use
    ``copyfile`` only. Prefer writing the final file under a system temp
    name then replacing into ``out/``.
    """
    def _copy_bytes(s: Path, d: Path) -> None:
        d.parent.mkdir(parents=True, exist_ok=True)
        with open(s, "rb") as rf, open(d, "wb") as wf:
            shutil.copyfileobj(rf, wf, length=1024 * 1024)

    # Try overwrite dest via a temp sibling in the same folder
    tmp = dest.with_name(f".{dest.stem}.tmp{dest.suffix}")
    try:
        _copy_bytes(src, tmp)
        try:
            os.replace(tmp, dest)
            return dest
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    except OSError:
        alt = dest.with_name(f"{dest.stem}-compact{dest.suffix}")
        try:
            _copy_bytes(src, alt)
            print(
                f"  (could not overwrite {dest.name}; wrote {alt.name})",
                flush=True,
            )
            return alt
        except OSError as exc:
            # Last resort: leave compressed bytes under /tmp and tell caller path
            raise RuntimeError(
                f"Cannot write compressed video to {dest.parent}: {exc}"
            ) from exc


def ensure_under_max_mb(
    path: Path,
    *,
    max_mb: float | None = None,
) -> Path:
    """If ``path`` exceeds ``max_mb``, re-encode until under budget."""
    max_mb = DEFAULT_MAX_MB if max_mb is None else float(max_mb)
    max_bytes = int(max_mb * 1_048_576)
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.stat().st_size <= max_bytes:
        print(f"  size OK: {_size_mb(path):.2f} MB (limit {max_mb:g} MB)", flush=True)
        return path

    ffmpeg = find_ffmpeg()
    duration = _probe_duration_seconds(ffmpeg, path)
    if duration <= 0.5:
        duration = 30.0

    print(
        f"  size {_size_mb(path):.2f} MB exceeds {max_mb:g} MB — compressing...",
        flush=True,
    )

    target_bits = int(max_bytes * 8 * 0.90)
    video_bps = max(150_000, int(target_bits / duration) - AUDIO_BPS)
    attempts: list[dict] = [
        {"video_bitrate": f"{video_bps}", "scale": None},
        {"video_bitrate": f"{int(video_bps * 0.75)}", "scale": None},
        {"video_bitrate": f"{int(video_bps * 0.55)}", "scale": "scale=720:-2"},
        {"crf": 32, "scale": "scale=720:-2"},
        {"crf": 36, "scale": "scale=540:-2"},
    ]

    result_path = path
    with tempfile.TemporaryDirectory(prefix="vid-compress-") as tmp:
        tmp_dir = Path(tmp)
        current = path
        for i, opts in enumerate(attempts, start=1):
            out = tmp_dir / f"pass-{i}.mp4"
            print(
                f"    compress pass {i}/{len(attempts)}: "
                f"bitrate={opts.get('video_bitrate')} crf={opts.get('crf')} "
                f"scale={opts.get('scale')}",
                flush=True,
            )
            _reencode(
                ffmpeg,
                current,
                out,
                video_bitrate=opts.get("video_bitrate"),
                crf=opts.get("crf"),
                scale=opts.get("scale"),
            )
            new_size = out.stat().st_size
            print(f"      -> {_size_mb(out):.2f} MB", flush=True)
            if new_size < path.stat().st_size:
                result_path = _install_compressed(out, path)
            if new_size <= max_bytes:
                print(
                    f"  compressed to {_size_mb(result_path):.2f} MB (under {max_mb:g} MB)",
                    flush=True,
                )
                return result_path
            current = out

    if result_path.stat().st_size <= max_bytes:
        return result_path
    raise RuntimeError(
        f"Could not shrink {path.name} under {max_mb:g} MB "
        f"(still {_size_mb(result_path):.2f} MB after {len(attempts)} passes)."
    )
