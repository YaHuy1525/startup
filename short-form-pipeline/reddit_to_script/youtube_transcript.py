"""Pull YouTube captions for anime-theory reference scripts.

Uses youtube-transcript-api (no API key). Falls back to yt-dlp auto-subs when
captions are unavailable.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


class TranscriptError(RuntimeError):
    pass


@dataclass
class ShortVideo:
    video_id: str
    title: str
    url: str
    duration_s: float
    transcript: str = ""
    language: str = ""
    word_count: int = 0
    status: str = "pending"
    error: str = ""


@dataclass
class ScrapeResult:
    query: str
    scraped_at: str
    max_duration_s: float
    videos: list[ShortVideo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "scraped_at": self.scraped_at,
            "max_duration_s": self.max_duration_s,
            "videos": [asdict(v) for v in self.videos],
        }


def extract_video_id(url_or_id: str) -> str:
    raw = (url_or_id or "").strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", raw):
        return raw
    patterns = (
        r"(?:youtube\.com/watch\?(?:[^&]*&)*v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    )
    for pat in patterns:
        m = re.search(pat, raw)
        if m:
            return m.group(1)
    raise TranscriptError(f"Could not parse YouTube video id from: {url_or_id!r}")


def _join_segments(segments: list[dict]) -> str:
    parts: list[str] = []
    for seg in segments:
        text = str(seg.get("text") or "").strip()
        if text:
            parts.append(text)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def fetch_transcript(url_or_id: str, *, max_chars: int = 14_000, english_only: bool = False) -> str:
    """Return plain-text transcript for a YouTube video or Short."""
    text, _lang = fetch_transcript_with_lang(
        url_or_id, max_chars=max_chars, english_only=english_only
    )
    return text


_API_IP_BLOCKED = False
_CAPTIONS_429 = False


def fetch_transcript_with_lang(
    url_or_id: str, *, max_chars: int = 14_000, english_only: bool = False
) -> tuple[str, str]:
    """Return (transcript, language_code) for a YouTube video or Short."""
    global _API_IP_BLOCKED, _CAPTIONS_429
    video_id = extract_video_id(url_or_id)
    text, lang = "", ""
    if not _API_IP_BLOCKED:
        try:
            text, lang = _fetch_via_api(video_id, english_only=english_only)
        except TranscriptError as exc:
            # IP bans on youtube-transcript-api — fall through to yt-dlp
            if "IP blocked" in str(exc) or "blocking requests" in str(exc):
                _API_IP_BLOCKED = True
                print(f"  [transcript] API IP-blocked; using yt-dlp/whisper for {video_id}+", flush=True)
            else:
                raise
    if not text and not _CAPTIONS_429:
        text = _fetch_via_ytdlp(video_id)
        if not text:
            # Caption CDN often 429s in the same session — skip further caption tries
            _CAPTIONS_429 = True
            print("  [transcript] caption downloads failing; preferring audio+whisper", flush=True)
        lang = lang or ("en" if text else "")
    if not text:
        text = _fetch_via_audio_whisper(video_id)
        lang = lang or ("en" if text else "")
    if not text:
        raise TranscriptError(f"No transcript found for {video_id}")
    if english_only:
        if lang and not is_english_lang(lang):
            raise TranscriptError(f"Transcript is not English (lang={lang!r}): {video_id}")
        if not looks_english(text):
            raise TranscriptError(f"Transcript text does not look English: {video_id}")
    if len(text) > max_chars:
        text = text[: max_chars - 3].rsplit(" ", 1)[0] + "..."
    return text, lang or "unknown"


def list_channel_videos(
    channel: str,
    *,
    limit: int = 40,
    max_duration_s: float = 180.0,
    include_shorts: bool = True,
    include_videos: bool = True,
) -> list[ShortVideo]:
    """List recent uploads from a channel handle/URL via yt-dlp (no API key)."""
    handle = _normalize_channel_handle(channel)
    tabs: list[str] = []
    if include_shorts:
        tabs.append(f"https://www.youtube.com/{handle}/shorts")
    if include_videos:
        tabs.append(f"https://www.youtube.com/{handle}/videos")
    if not tabs:
        raise TranscriptError("Nothing to list (enable shorts and/or videos).")

    found: list[ShortVideo] = []
    seen: set[str] = set()
    pool = max(limit * 3, 40)
    for tab in tabs:
        cmd = [
            "yt-dlp",
            "--no-update",
            "--flat-playlist",
            "--playlist-end",
            str(pool),
            "--print",
            "%(id)s\t%(title)s\t%(duration)s\t%(webpage_url)s",
            tab,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except FileNotFoundError as exc:
            raise TranscriptError("yt-dlp not installed. Run: pip install yt-dlp") from exc
        if result.returncode != 0:
            print(f"  [channel] yt-dlp warn on {tab}: {result.stderr[:200]}", flush=True)
            continue
        for line in result.stdout.splitlines():
            if not line.strip() or "\t" not in line:
                continue
            parts = line.split("\t", 3)
            if len(parts) < 4:
                continue
            vid, title, dur_s, page_url = parts
            vid = vid.strip()
            if not vid or vid in seen:
                continue
            try:
                duration = float(dur_s or 0)
            except ValueError:
                duration = 0.0
            # duration 0 often means Shorts metadata missing — keep if under pool
            if duration > max_duration_s:
                continue
            seen.add(vid)
            found.append(
                ShortVideo(
                    video_id=vid,
                    title=title.strip(),
                    url=page_url.strip()
                    or f"https://www.youtube.com/shorts/{vid}",
                    duration_s=duration,
                )
            )
            if len(found) >= limit:
                return found
    return found


def scrape_channel_scripts(
    channel: str,
    *,
    limit: int = 25,
    max_duration_s: float = 180.0,
    out_dir: Path | str | None = None,
    english_only: bool = True,
    include_shorts: bool = True,
    include_videos: bool = True,
) -> ScrapeResult:
    """Pull English narration transcripts from a competitor channel for style training."""
    from . import config

    handle = _normalize_channel_handle(channel)
    base = Path(out_dir) if out_dir else (
        config.PIPELINE_ROOT / "data" / "reference-scripts" / "channels" / handle.lstrip("@")
    )
    base.mkdir(parents=True, exist_ok=True)

    result = ScrapeResult(
        query=f"channel:{handle}",
        scraped_at=datetime.now(timezone.utc).isoformat(),
        max_duration_s=max_duration_s,
    )

    print(
        f"Listing channel {handle} (limit {limit}, <= {max_duration_s:g}s)...",
        flush=True,
    )
    candidates = list_channel_videos(
        handle,
        limit=max(limit * 2, limit),
        max_duration_s=max_duration_s,
        include_shorts=include_shorts,
        include_videos=include_videos,
    )
    print(f"  found {len(candidates)} candidate videos", flush=True)

    saved = 0
    skipped_existing = 0
    consecutive_blocks = 0
    for video in candidates:
        if saved >= limit:
            break
        # Resume-friendly: keep existing English transcripts
        existing = list(base.glob(f"{video.video_id}-*.txt"))
        if existing:
            try:
                scraped = parse_scraped_file(existing[0])
                if scraped.body and looks_english(scraped.body):
                    video.transcript = scraped.body
                    video.language = scraped.language or "en"
                    video.word_count = len(scraped.body.split())
                    video.status = "ok"
                    video.title = scraped.title or video.title
                    skipped_existing += 1
                    saved += 1
                    result.videos.append(video)
                    continue
            except Exception:  # noqa: BLE001
                pass
        print(
            f"  [{saved + 1}/{limit}] {video.title[:60]}... ({video.duration_s:g}s)",
            flush=True,
        )
        try:
            text, lang = fetch_transcript_with_lang(
                video.video_id, english_only=english_only
            )
            video.transcript = text
            video.language = lang
            video.word_count = len(text.split())
            video.status = "ok"
            slug = re.sub(r"[^a-z0-9]+", "-", video.title.lower()).strip("-")[:50] or video.video_id
            txt_path = base / f"{video.video_id}-{slug}.txt"
            txt_path.write_text(
                f"# {video.title}\n# {video.url}\n"
                f"# duration: {video.duration_s:g}s | lang: {lang} | channel: {handle}\n\n"
                f"{text}\n",
                encoding="utf-8",
            )
            print(f"      -> {video.word_count} words ({lang}) saved {txt_path.name}", flush=True)
            saved += 1
            consecutive_blocks = 0
            time.sleep(1.2)  # avoid YouTube IP rate limits
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            video.status = "skipped" if english_only and "English" in err else "error"
            video.error = err[:500]
            print(f"      skip: {video.error[:120]}", flush=True)
            if "IP blocked" in err or "blocking requests from your IP" in err or "IpBlocked" in err:
                consecutive_blocks += 1
                if consecutive_blocks >= 5:
                    print(
                        "  [channel] YouTube IP rate-limit — stopping early; "
                        "re-run later to resume (whisper fallback may still work).",
                        flush=True,
                    )
                    result.videos.append(video)
                    break
                time.sleep(3.0)
            else:
                consecutive_blocks = 0
                time.sleep(0.8)
        result.videos.append(video)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = base / f"scrape-{stamp}-{handle.lstrip('@')}.json"
    json_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved channel scrape index -> {json_path}", flush=True)
    ok = sum(1 for v in result.videos if v.status == "ok")
    print(f"Transcripts: {ok}/{len(result.videos)} ok", flush=True)
    if skipped_existing:
        print(f"  reused existing: {skipped_existing}", flush=True)
    return result


def _normalize_channel_handle(channel: str) -> str:
    raw = (channel or "").strip()
    if not raw:
        raise TranscriptError("Channel handle/URL required.")
    m = re.search(r"(?:youtube\.com/)?(@[\w.-]+)", raw, re.I)
    if m:
        return m.group(1)
    m = re.search(r"youtube\.com/(?:c|channel)/([\w.-]+)", raw, re.I)
    if m:
        return f"@{m.group(1)}" if not m.group(1).startswith("UC") else m.group(1)
    if raw.startswith("@"):
        return raw
    return f"@{raw}"


def search_shorts(
    query: str,
    *,
    limit: int = 10,
    max_duration_s: float = 90.0,
    search_pool: int | None = None,
) -> list[ShortVideo]:
    """Search YouTube and return Short-length candidates (duration <= max_duration_s)."""
    pool = search_pool or max(limit * 4, 20)
    search_url = f"ytsearch{pool}:{query}"
    cmd = [
        "yt-dlp",
        "--no-update",
        "--flat-playlist",
        "--print",
        "%(id)s\t%(title)s\t%(duration)s\t%(webpage_url)s",
        search_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise TranscriptError("yt-dlp not installed. Run: pip install yt-dlp") from exc
    if result.returncode != 0:
        raise TranscriptError(f"yt-dlp search failed: {result.stderr[:300]}")

    found: list[ShortVideo] = []
    for line in result.stdout.splitlines():
        if not line.strip() or "\t" not in line:
            continue
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        vid, title, dur_s, page_url = parts
        try:
            duration = float(dur_s or 0)
        except ValueError:
            duration = 0.0
        if duration <= 0 or duration > max_duration_s:
            continue
        found.append(
            ShortVideo(
                video_id=vid.strip(),
                title=title.strip(),
                url=page_url.strip() or f"https://www.youtube.com/shorts/{vid.strip()}",
                duration_s=duration,
            )
        )
        if len(found) >= limit:
            break
    return found


def scrape_short_scripts(
    query: str,
    *,
    limit: int = 5,
    max_duration_s: float = 90.0,
    out_dir: Path | str | None = None,
    english_only: bool = True,
) -> ScrapeResult:
    """Search Shorts, pull transcripts, save JSON + per-video .txt files."""
    from . import config

    base = Path(out_dir) if out_dir else (config.PIPELINE_ROOT / "data" / "reference-scripts")
    base.mkdir(parents=True, exist_ok=True)

    result = ScrapeResult(
        query=query,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        max_duration_s=max_duration_s,
    )

    print(f"Searching Shorts: {query!r} (<= {max_duration_s:g}s, limit {limit})...", flush=True)
    if english_only:
        print("  English-only transcripts", flush=True)
    pool = max(limit * 6, 30)
    candidates = search_shorts(
        query, limit=pool, max_duration_s=max_duration_s, search_pool=pool * 2
    )
    print(f"  found {len(candidates)} candidate Shorts", flush=True)

    saved = 0
    for i, video in enumerate(candidates, start=1):
        if saved >= limit:
            break
        print(f"  [{saved + 1}/{limit}] {video.title[:60]}... ({video.duration_s:g}s)", flush=True)
        try:
            text, lang = fetch_transcript_with_lang(video.video_id, english_only=english_only)
            video.transcript = text
            video.language = lang
            video.word_count = len(text.split())
            video.status = "ok"
            slug = re.sub(r"[^a-z0-9]+", "-", video.title.lower()).strip("-")[:50] or video.video_id
            txt_path = base / f"{video.video_id}-{slug}.txt"
            txt_path.write_text(
                f"# {video.title}\n# {video.url}\n# duration: {video.duration_s:g}s | lang: {lang}\n\n{text}\n",
                encoding="utf-8",
            )
            print(f"      -> {video.word_count} words ({lang}) saved {txt_path.name}", flush=True)
            saved += 1
        except Exception as exc:  # noqa: BLE001
            video.status = "skipped" if english_only and "English" in str(exc) else "error"
            video.error = str(exc)[:500]
            print(f"      skip: {video.error[:120]}", flush=True)
        result.videos.append(video)

    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:40] or "shorts"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = base / f"scrape-{stamp}-{slug}.json"
    json_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved scrape index -> {json_path}", flush=True)
    ok = sum(1 for v in result.videos if v.status == "ok")
    print(f"Transcripts: {ok}/{len(result.videos)} ok", flush=True)
    return result


def _fetch_via_api(video_id: str, *, english_only: bool = False) -> tuple[str, str]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise TranscriptError(
            "youtube-transcript-api not installed. Run: pip install youtube-transcript-api"
        ) from exc

    api = YouTubeTranscriptApi()
    last_err = ""
    for langs in (["en"], ["en-US", "en-GB", "en"]):
        try:
            fetched = api.fetch(video_id, languages=langs)
            segments = [{"text": s.text} for s in fetched]
            return _join_segments(segments), "en"
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            print(f"  [transcript] API fetch failed ({langs}): {exc}", flush=True)
            if "blocking requests from your IP" in last_err or "IpBlocked" in last_err:
                raise TranscriptError(f"YouTube IP blocked while fetching {video_id}") from exc
            continue
    try:
        listing = api.list(video_id)
        for tr in listing:
            lang = getattr(tr, "language_code", None) or getattr(tr, "language", "") or ""
            if english_only and lang and not is_english_lang(str(lang)):
                continue
            segments = [{"text": s.text} for s in tr.fetch()]
            text = _join_segments(segments)
            if not text:
                continue
            if english_only and not looks_english(text):
                continue
            return text, str(lang or "en")
    except Exception as exc:  # noqa: BLE001
        last_err = str(exc)
        print(f"  [transcript] API list failed: {exc}", flush=True)
        if "blocking requests from your IP" in last_err or "IpBlocked" in last_err:
            raise TranscriptError(f"YouTube IP blocked while fetching {video_id}") from exc
    return "", ""


def _fetch_via_ytdlp(video_id: str) -> str:
    """Download English auto/manual captions via yt-dlp (works when transcript API is IP-blocked)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmp:
        out_tpl = str(Path(tmp) / "subs")
        # Prefer human en subs, then auto-generated; json3 is easiest to parse.
        attempts = [
            ["--write-sub", "--sub-lang", "en.*,en", "--sub-format", "json3/vtt/best"],
            ["--write-auto-sub", "--sub-lang", "en.*,en", "--sub-format", "json3/vtt/best"],
        ]
        for flags in attempts:
            cmd = [
                "yt-dlp",
                "--skip-download",
                "--no-warnings",
                "-o",
                out_tpl,
                *flags,
                url,
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            except FileNotFoundError:
                print("  [transcript] yt-dlp not installed; skipping fallback", flush=True)
                return ""
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "")[:220]
                print(f"  [transcript] yt-dlp failed: {err}", flush=True)
                continue
            text = _parse_ytdlp_subs_dir(Path(tmp))
            if text:
                return text
        return ""


def _parse_ytdlp_subs_dir(tmp: Path) -> str:
    for path in sorted(tmp.glob("*.json3")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        events = data.get("events") or []
        parts: list[str] = []
        for ev in events:
            for seg in ev.get("segs") or []:
                t = str(seg.get("utf8") or "").strip()
                if t and t != "\n":
                    parts.append(t)
        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        if text:
            return text
    # VTT fallback
    for path in sorted(tmp.glob("*.vtt")):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        lines: list[str] = []
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("WEBVTT") or s.startswith("NOTE") or "-->" in s:
                continue
            if re.match(r"^\d+$", s):
                continue
            # drop simple cue tags
            s = re.sub(r"<[^>]+>", "", s).strip()
            if s:
                lines.append(s)
        # de-dupe consecutive identical auto-caption lines
        deduped: list[str] = []
        for line in lines:
            if not deduped or deduped[-1] != line:
                deduped.append(line)
        text = re.sub(r"\s+", " ", " ".join(deduped)).strip()
        if text:
            return text
    return ""


def _fetch_via_audio_whisper(video_id: str) -> str:
    """Download audio with yt-dlp and transcribe via OpenAI Whisper (caption 429 bypass)."""
    try:
        from . import config
    except Exception:  # noqa: BLE001
        return ""
    api_key = getattr(config, "OPENAI_API_KEY", "") or ""
    if not api_key:
        print("  [transcript] whisper fallback needs OPENAI_API_KEY", flush=True)
        return ""

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmp:
        out_tpl = str(Path(tmp) / "audio.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-warnings",
            "-f",
            "bestaudio[ext=m4a]/bestaudio/worst",
            "-o",
            out_tpl,
            url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        except FileNotFoundError:
            return ""
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")[:220]
            print(f"  [transcript] audio download failed: {err}", flush=True)
            return ""
        audio_files = [
            p
            for p in Path(tmp).iterdir()
            if p.is_file() and p.suffix.lower() in {".m4a", ".mp3", ".webm", ".opus", ".wav"}
        ]
        if not audio_files:
            print("  [transcript] no audio file after yt-dlp", flush=True)
            return ""
        audio_path = max(audio_files, key=lambda p: p.stat().st_size)
        print(f"  [transcript] whispering {audio_path.name} ({audio_path.stat().st_size // 1024}KB)...", flush=True)
        try:
            with audio_path.open("rb") as fh:
                resp = requests.post(
                    f"{config.OPENAI_BASE_URL}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (audio_path.name, fh, "application/octet-stream")},
                    data={"model": "whisper-1", "response_format": "text"},
                    timeout=300,
                )
        except requests.RequestException as exc:
            print(f"  [transcript] whisper request failed: {exc}", flush=True)
            return ""
        if not resp.ok:
            print(f"  [transcript] whisper HTTP {resp.status_code}: {resp.text[:200]}", flush=True)
            return ""
        text = re.sub(r"\s+", " ", (resp.text or "").strip())
        if text:
            print(f"  [transcript] whisper ok ({len(text.split())} words)", flush=True)
        return text


@dataclass
class ScrapedScript:
    title: str
    url: str
    duration_s: float | None
    language: str
    body: str
    path: Path
    video_id: str = ""


_ENGLISH_LANGS = frozenset({"en", "en-us", "en-gb", "en-au", "en-ca"})


def is_english_lang(lang: str) -> bool:
    code = (lang or "").strip().lower().replace("_", "-")
    return code in _ENGLISH_LANGS or code.startswith("en-")


def looks_english(text: str, *, min_ascii_ratio: float = 0.92) -> bool:
    """Heuristic: reject Hindi/CJK etc. when caption lang metadata is wrong."""
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    latin = sum(1 for c in letters if ord(c) < 0x0250)
    return (latin / len(letters)) >= min_ascii_ratio


def parse_scraped_file(path: Path | str) -> ScrapedScript:
    p = Path(path)
    if not p.is_file():
        raise TranscriptError(f"Reference file not found: {path}")
    lines = p.read_text(encoding="utf-8").splitlines()
    title = ""
    url = ""
    duration_s: float | None = None
    language = ""
    body_start = 0
    for i, line in enumerate(lines):
        if not line.startswith("# "):
            continue
        payload = line[2:].strip()
        if i == 0:
            title = payload
        elif payload.startswith("http"):
            url = payload
        elif "lang:" in payload:
            m = re.search(r"lang:\s*(\S+)", payload, re.I)
            if m:
                language = m.group(1)
            m = re.search(r"duration:\s*([\d.]+)s", payload, re.I)
            if m:
                duration_s = float(m.group(1))
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip()
    vid = ""
    if url:
        try:
            vid = extract_video_id(url)
        except TranscriptError:
            vid = p.stem.split("-")[0]
    return ScrapedScript(
        title=title or p.stem,
        url=url,
        duration_s=duration_s,
        language=language,
        body=body,
        path=p,
        video_id=vid,
    )


def infer_anime_series(title: str, body: str) -> str:
    blob = f"{title} {body}".lower()
    rules = (
        (("dragon ball", "goku", "vegeta", "saiyan", "gogeta"), "Dragon Ball"),
        (("jujutsu", "jjk", "gojo", "yuji", "yuuji", "sukuna", "itadori", "mahoraga", "megumi"), "Jujutsu Kaisen"),
        (("mushoku", "orsted", "rudeus", "roxy"), "Mushoku Tensei"),
        (("one piece", "luffy", "zoro", "haki"), "One Piece"),
        (("naruto", "sasuke", "konoha", "sharingan"), "Naruto"),
        (("attack on titan", " eren ", "aot", "titan shifter"), "Attack on Titan"),
        (("demon slayer", "tanjiro", "nezuko", "muzan"), "Demon Slayer"),
        (("bleach", "ichigo", "aizen", "quincy", "sternritter", "soul society", "tybw"), "Bleach"),
        (("invincible", "omni-man", "mark grayson", "viltrum", "conquest", "battle beast"), "Invincible"),
        (("chainsaw man", "denji", "makima", "pochita"), "Chainsaw Man"),
    )
    for keys, series in rules:
        if any(k in blob for k in keys):
            return series
    return ""


def list_english_scraped_scripts(
    out_dir: Path | str | None = None,
) -> list[ScrapedScript]:
    from . import config

    base = Path(out_dir) if out_dir else (config.PIPELINE_ROOT / "data" / "reference-scripts")
    if not base.is_dir():
        return []
    scripts: list[ScrapedScript] = []
    for path in sorted(base.glob("*.txt")):
        try:
            scraped = parse_scraped_file(path)
        except Exception:  # noqa: BLE001
            continue
        if not scraped.body:
            continue
        if scraped.language and not is_english_lang(scraped.language):
            continue
        if not looks_english(scraped.body):
            continue
        scripts.append(scraped)
    return scripts


def load_reference(path: str, *, english_only: bool = True) -> str:
    scraped = parse_scraped_file(path)
    body = scraped.body
    if not body:
        # Plain text file without header metadata.
        body = scraped.path.read_text(encoding="utf-8").strip()
    if english_only:
        if scraped.language and not is_english_lang(scraped.language):
            raise TranscriptError(
                f"Reference is not English (lang={scraped.language!r}): {path}"
            )
        if not looks_english(body):
            raise TranscriptError(f"Reference text does not look English: {path}")
    return body
