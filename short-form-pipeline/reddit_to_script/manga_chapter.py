"""Fetch manga chapters from MangaDex and summarize panel content."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import requests

from . import config

MANGADEX_BASE = "https://api.mangadex.org"
_UA = "Mozilla/5.0 (compatible; manga-chapter-pipeline/1.0)"

# Known MangaDex UUIDs for quick lookup.
MANGA_PRESETS: dict[str, str] = {
    "baki rahen": "484f94e7-35c3-4cb5-a068-53d684c1439a",
    "baki": "484f94e7-35c3-4cb5-a068-53d684c1439a",
    "grappler baki": "ea3122bb-0c28-4669-8686-d6df1274512f",
    "new grappler baki": "0ee2f134-87c6-4715-b31e-b3b1344fa5ea",
}


class MangaChapterError(RuntimeError):
    pass


@dataclass
class ChapterMeta:
    manga_id: str
    manga_title: str
    chapter_id: str
    chapter_number: str
    chapter_title: str
    page_count: int
    page_urls: list[str]


def resolve_manga_id(series: str) -> tuple[str, str]:
    key = series.strip().lower()
    if key in MANGA_PRESETS:
        mid = MANGA_PRESETS[key]
        return mid, _manga_title(mid) or series

    resp = requests.get(
        f"{MANGADEX_BASE}/manga",
        params={"title": series, "limit": 10},
        headers={"User-Agent": _UA},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or []
    if not data:
        raise MangaChapterError(f"No MangaDex manga found for {series!r}")
    # Prefer English or ja-ro title match.
    best = data[0]
    for item in data:
        titles = item.get("attributes", {}).get("title", {})
        blob = " ".join(titles.values()).lower()
        if key in blob:
            best = item
            break
    titles = best.get("attributes", {}).get("title", {})
    title = titles.get("en") or titles.get("ja-ro") or next(iter(titles.values()), series)
    return best["id"], title


def _manga_title(manga_id: str) -> str:
    resp = requests.get(
        f"{MANGADEX_BASE}/manga/{manga_id}",
        headers={"User-Agent": _UA},
        timeout=30,
    )
    if not resp.ok:
        return ""
    titles = resp.json().get("data", {}).get("attributes", {}).get("title", {})
    return titles.get("en") or titles.get("ja-ro") or next(iter(titles.values()), "")


def _list_chapters(manga_id: str, *, limit: int = 200) -> list[dict]:
    chapters: list[dict] = []
    offset = 0
    while len(chapters) < limit:
        resp = requests.get(
            f"{MANGADEX_BASE}/manga/{manga_id}/feed",
            params={
                "limit": min(100, limit - len(chapters)),
                "offset": offset,
                "order[chapter]": "desc",
                "translatedLanguage[]": ["en"],
            },
            headers={"User-Agent": _UA},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json().get("data") or []
        if not batch:
            break
        chapters.extend(batch)
        offset += len(batch)
        if len(batch) < 100:
            break
    return chapters


def find_chapter(manga_id: str, chapter_number: str | float) -> dict:
    target = str(chapter_number).strip()
    for ch in _list_chapters(manga_id):
        num = str(ch.get("attributes", {}).get("chapter") or "").strip()
        if num == target:
            return ch
    raise MangaChapterError(
        f"Chapter {target} not found on MangaDex (English). "
        "Try --latest or a different chapter number."
    )


def get_latest_chapter(manga_id: str) -> dict:
    chapters = _list_chapters(manga_id, limit=1)
    if not chapters:
        raise MangaChapterError("No English chapters found on MangaDex.")
    return chapters[0]


def _chapter_page_urls(chapter_id: str) -> tuple[list[str], int]:
    resp = requests.get(
        f"{MANGADEX_BASE}/at-home/server/{chapter_id}",
        headers={"User-Agent": _UA},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    base_url = body["baseUrl"]
    chapter = body["chapter"]
    img_hash = chapter["hash"]
    pages = chapter.get("data") or chapter.get("dataSaver") or []
    quality = "data" if chapter.get("data") else "data-saver"
    urls = [f"{base_url}/{quality}/{img_hash}/{page}" for page in pages]
    return urls, len(pages)


def fetch_chapter(
    series: str,
    *,
    chapter_number: str | float | None = None,
    use_latest: bool = False,
) -> ChapterMeta:
    manga_id, manga_title = resolve_manga_id(series)
    if use_latest or chapter_number is None:
        ch = get_latest_chapter(manga_id)
    else:
        ch = find_chapter(manga_id, chapter_number)

    attr = ch.get("attributes", {})
    chapter_id = ch["id"]
    page_urls, page_count = _chapter_page_urls(chapter_id)
    if not page_urls:
        raise MangaChapterError(f"Chapter {chapter_id} has no page images.")

    return ChapterMeta(
        manga_id=manga_id,
        manga_title=manga_title,
        chapter_id=chapter_id,
        chapter_number=str(attr.get("chapter") or "?"),
        chapter_title=str(attr.get("title") or "").strip(),
        page_count=page_count,
        page_urls=page_urls,
    )


def _sample_indices(total: int, sample_count: int) -> list[int]:
    if total <= sample_count:
        return list(range(total))
    step = total / sample_count
    return [min(int(i * step), total - 1) for i in range(sample_count)]


def download_panel_samples(
    chapter: ChapterMeta,
    out_dir: Path,
    *,
    sample_count: int = 8,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    indices = _sample_indices(len(chapter.page_urls), sample_count)
    paths: list[Path] = []
    for i, idx in enumerate(indices, start=1):
        url = chapter.page_urls[idx]
        resp = requests.get(
            url,
            headers={"User-Agent": _UA, "Referer": "https://mangadex.org/"},
            timeout=60,
        )
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "jpeg" in ctype or "jpg" in ctype:
            ext = ".jpg"
        elif "webp" in ctype:
            ext = ".webp"
        elif "gif" in ctype:
            ext = ".gif"
        else:
            ext = ".png"
        dest = out_dir / f"panel-{i:02d}{ext}"
        dest.write_bytes(resp.content)
        paths.append(dest)
    return paths


def _mime_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


def _encode_image(path: Path) -> str:
    data = path.read_bytes()
    mime = _mime_for_path(path)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def summarize_chapter_panels(
    chapter: ChapterMeta,
    panel_paths: list[Path],
    *,
    timeout: int = 180,
) -> dict:
    """Use vision LLM to extract chapter events from sampled panels."""
    api_key = config.require_llm_key()
    model = config.resolved_llm_model()
    if "gpt-4" not in model and "gpt-4o" not in model:
        model = "gpt-4o-mini"

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"You are analyzing manga chapter panels from {chapter.manga_title} "
                f"Chapter {chapter.chapter_number}"
                + (f' titled "{chapter.chapter_title}"' if chapter.chapter_title else "")
                + ".\n\n"
                "Describe what happens in chronological order. Name characters you "
                "recognize. Note fights, dialogue beats, twists, and emotional moments.\n"
                "Return ONLY JSON:\n"
                '{"summary":str,"events":[{"beat":str,"characters":[str]}],'
                '"characters":[str]}'
            ),
        }
    ]
    for path in panel_paths:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _encode_image(path), "detail": "low"},
            }
        )

    resp = requests.post(
        f"{config.OPENAI_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "max_tokens": 2000,
        },
        timeout=timeout,
    )
    if not resp.ok:
        raise MangaChapterError(f"Vision summary failed {resp.status_code}: {resp.text[:300]}")
    raw = resp.json()["choices"][0]["message"]["content"]
    return json.loads(raw)


def chapter_label(chapter: ChapterMeta) -> str:
    label = f"{chapter.manga_title} Chapter {chapter.chapter_number}"
    if chapter.chapter_title:
        label += f": {chapter.chapter_title}"
    return label
