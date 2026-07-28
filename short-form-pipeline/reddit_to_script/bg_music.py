"""Background music for anime-theory Shorts.

Priority:
  1. Pixabay Audio API (``PIXABAY_API_KEY``) — royalty-free music when accessible
  2. Openverse CC0/PDM commercial audio (Jamendo / Freesound / Wikimedia)
  3. Local ambient WAV beds (last resort)
"""

from __future__ import annotations

import hashlib
import math
import re
import wave
from pathlib import Path

import numpy as np
import requests

from . import config

# Map script music moods → search queries (Pixabay / Openverse)
MOOD_QUERIES: dict[str, list[str]] = {
    "dark": ["dark cinematic ambient", "dark mysterious soundtrack", "epic dark tension"],
    "uneasy": ["tense suspense ambient", "horror tension underscore", "uneasy cinematic"],
    "contemplative": ["soft contemplative piano ambient", "thoughtful cinematic ambient"],
    "sad": ["sad emotional piano ambient", "melancholy cinematic"],
    "melancholic": ["melancholic ambient piano", "bittersweet cinematic"],
    "hopeful": ["hopeful cinematic ambient", "uplifting soft emotional"],
    "chill": ["chill lo-fi ambient", "calm soft background"],
    "excited": ["energetic cinematic adventure", "upbeat dramatic"],
    "angry": ["intense dramatic tension", "dark aggressive cinematic"],
    "euphoric/high": ["epic triumphant cinematic", "uplifting orchestral"],
    "funny/quirky": ["quirky playful ukulele", "light comedy underscore"],
    "happy": ["happy upbeat acoustic", "bright cheerful"],
}

# Legacy synthetic bed filenames (fallback only)
MOOD_FILES: dict[str, str] = {
    "dark": "dark.wav",
    "uneasy": "uneasy.wav",
    "contemplative": "contemplative.wav",
    "sad": "sad.wav",
    "melancholic": "melancholic.wav",
    "hopeful": "hopeful.wav",
    "chill": "contemplative.wav",
    "excited": "hopeful.wav",
    "angry": "uneasy.wav",
    "euphoric/high": "hopeful.wav",
    "funny/quirky": "contemplative.wav",
    "happy": "hopeful.wav",
}

SR = 44100
_UA = {
    "User-Agent": "Mozilla/5.0 (compatible; anime-theory-pipeline/1.0)",
    "Accept": "*/*",
}


def music_dir() -> Path:
    d = config.PUBLIC_DIR / "music"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_music_src(mood: str | None, *, title: str = "") -> str | None:
    """Return public-relative path like ``music/dark-xyz.mp3`` or None."""
    key = (mood or config.DEFAULT_MUSIC or "dark").strip().lower()
    queries = list(MOOD_QUERIES.get(key) or MOOD_QUERIES["dark"])
    if title.strip():
        # Light topic hint — keep short so search stays musical
        hint = re.sub(r"[^a-zA-Z0-9\s]", " ", title)[:40].strip()
        if hint:
            queries = [f"{hint} {queries[0]}", *queries]

    # Prefer cached download for this mood
    cached = _cached_for_mood(key)
    if cached:
        return f"music/{cached.name}"

    track = _fetch_pixabay_music(queries) or _fetch_openverse_music(queries)
    if track:
        path = _download_track(key, track)
        if path:
            return f"music/{path.name}"

    # Synthetic bed last resort
    filename = MOOD_FILES.get(key) or MOOD_FILES.get("dark")
    path = music_dir() / filename
    if not path.exists():
        ensure_mood_beds()
    if path.exists():
        print(f"  [music] fallback synthetic bed {filename}", flush=True)
        return f"music/{filename}"
    for name in MOOD_FILES.values():
        alt = music_dir() / name
        if alt.exists():
            return f"music/{name}"
    return None


def _cached_for_mood(mood: str) -> Path | None:
    d = music_dir()
    # Prefer real downloaded mp3/ogg over synthetic wav
    for path in sorted(d.glob(f"{mood}-*.mp3")) + sorted(d.glob(f"{mood}-*.ogg")):
        if path.stat().st_size > 20_000:
            return path
    return None


def _fetch_pixabay_music(queries: list[str]) -> dict | None:
    """Try Pixabay Audio API. Returns {id, url, title, source} or None.

    Note: as of 2026 the public Pixabay key often gets HTTP 403 on /api/audio/
    (images/videos still work). We still try so it works if/when access opens.
    """
    key = getattr(config, "PIXABAY_API_KEY", "") or ""
    if not key:
        return None
    for q in queries[:3]:
        try:
            resp = requests.get(
                "https://pixabay.com/api/audio/",
                params={
                    "key": key,
                    "q": q,
                    "per_page": 10,
                    "safesearch": "true",
                },
                headers=_UA,
                timeout=25,
            )
        except requests.RequestException as exc:
            print(f"  [music] Pixabay audio error: {exc}", flush=True)
            return None
        if resp.status_code == 403:
            print(
                "  [music] Pixabay Audio API 403 (key works for images, not music) "
                "— using Openverse CC0 fallback",
                flush=True,
            )
            return None
        if not resp.ok:
            print(f"  [music] Pixabay audio {resp.status_code}: {resp.text[:120]}", flush=True)
            continue
        hits = (resp.json() or {}).get("hits") or []
        for hit in hits:
            url = (
                hit.get("audio")
                or hit.get("url")
                or (hit.get("audios") or {}).get("large", {}).get("url")
                or (hit.get("audios") or {}).get("medium", {}).get("url")
                or ""
            )
            if url:
                return {
                    "id": str(hit.get("id") or ""),
                    "url": url,
                    "title": str(hit.get("tags") or hit.get("user") or q)[:80],
                    "source": "pixabay",
                }
    return None


def _fetch_openverse_music(queries: list[str]) -> dict | None:
    """Royalty-free commercial audio via Openverse (Jamendo / Freesound / Wikimedia)."""
    bad = (
        "sfx", "sound effect", "foley", "whoosh", "voice", "speech", "talk",
        "vocal", "singing", "choir", "laugh", "scream", "crowd", "sample pack",
    )
    # Prefer Jamendo (instrumental music beds) over Freesound SFX-ish clips
    for source_pref in ("jamendo", None):
        for q in queries[:4]:
            params: dict = {
                "q": q,
                "page_size": 15,
            }
            if source_pref:
                params["source"] = source_pref
            else:
                # Broader search: keep commercial-safe when not locking to Jamendo
                params["license_type"] = "commercial"
            try:
                resp = requests.get(
                    "https://api.openverse.org/v1/audio/",
                    params=params,
                    headers=_UA,
                    timeout=30,
                )
            except requests.RequestException as exc:
                print(f"  [music] Openverse error: {exc}", flush=True)
                continue
            if not resp.ok:
                continue
            for hit in (resp.json() or {}).get("results") or []:
                url = (hit.get("url") or "").strip()
                if not url:
                    continue
                duration = hit.get("duration")
                try:
                    if duration is not None and float(duration) < 25:
                        continue
                except (TypeError, ValueError):
                    pass
                title = str(hit.get("title") or q)[:80]
                tags = hit.get("tags") or []
                tag_bits: list[str] = []
                for t in tags:
                    if isinstance(t, str):
                        tag_bits.append(t)
                    elif isinstance(t, dict):
                        tag_bits.append(str(t.get("name") or t.get("slug") or ""))
                blob = f"{title} {' '.join(tag_bits)}".lower()
                if any(x in blob for x in bad):
                    continue
                return {
                    "id": str(hit.get("id") or hashlib.md5(url.encode()).hexdigest()[:10]),
                    "url": url,
                    "title": title,
                    "source": str(hit.get("source") or "openverse"),
                }
    return None


def _download_track(mood: str, track: dict) -> Path | None:
    url = track["url"]
    ext = ".mp3"
    lower = url.lower().split("?", 1)[0]
    if lower.endswith(".ogg"):
        ext = ".ogg"
    elif lower.endswith(".wav"):
        ext = ".wav"
    elif lower.endswith(".m4a"):
        ext = ".m4a"
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "", str(track.get("id") or "x"))[:24] or "x"
    out = music_dir() / f"{mood}-{track.get('source', 'cc')}-{safe_id}{ext}"
    if out.exists() and out.stat().st_size > 20_000:
        print(f"  [music] cache hit {out.name} ({track.get('title')})", flush=True)
        return out
    try:
        resp = requests.get(url, headers=_UA, timeout=90, stream=True)
        if not resp.ok:
            print(f"  [music] download failed {resp.status_code} {url[:80]}", flush=True)
            return None
        data = resp.content
        if len(data) < 10_000:
            print(f"  [music] download too small ({len(data)} bytes)", flush=True)
            return None
        out.write_bytes(data)
        print(
            f"  [music] downloaded {out.name} via {track.get('source')} "
            f"“{track.get('title')}”",
            flush=True,
        )
        return out
    except requests.RequestException as exc:
        print(f"  [music] download error: {exc}", flush=True)
        return None


def _write_wav(path: Path, samples: np.ndarray) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def _bed(duration_s: float, freqs: list[float], *, wobble: float, noise: float) -> np.ndarray:
    n = int(SR * duration_s)
    t = np.arange(n, dtype=np.float64) / SR
    sig = np.zeros(n, dtype=np.float64)
    for i, f in enumerate(freqs):
        amp = 0.22 / (1 + 0.15 * i)
        mod = 1.0 + wobble * np.sin(2 * math.pi * (0.05 + 0.02 * i) * t)
        sig += amp * mod * np.sin(2 * math.pi * f * t)
    if noise > 0:
        rng = np.random.default_rng(42)
        raw = rng.normal(0, noise, n)
        k = 120
        kernel = np.ones(k) / k
        soft = np.convolve(raw, kernel, mode="same")
        sig += soft
    fade = int(SR * 1.5)
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return sig * env * 0.55


def ensure_mood_beds(*, duration_s: float = 120.0) -> dict[str, Path]:
    """Create missing ambient beds for theory Shorts (offline fallback)."""
    specs: dict[str, tuple[list[float], float, float]] = {
        "dark": ([55.0, 82.5, 110.0, 165.0], 0.08, 0.012),
        "uneasy": ([60.0, 90.0, 95.0, 127.0], 0.14, 0.018),
        "contemplative": ([65.0, 98.0, 130.0], 0.05, 0.008),
        "sad": ([58.0, 87.0, 116.0, 174.0], 0.06, 0.01),
        "melancholic": ([52.0, 78.0, 104.0, 156.0], 0.07, 0.011),
        "hopeful": ([72.0, 108.0, 144.0, 216.0], 0.04, 0.006),
    }
    out: dict[str, Path] = {}
    for mood, (freqs, wobble, noise) in specs.items():
        path = music_dir() / f"{mood}.wav"
        if path.exists() and path.stat().st_size > 10_000:
            out[mood] = path
            continue
        print(f"  [music] generating ambient bed: {mood}.wav", flush=True)
        samples = _bed(duration_s, freqs, wobble=wobble, noise=noise)
        _write_wav(path, samples)
        out[mood] = path
    return out
