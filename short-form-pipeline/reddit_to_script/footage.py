"""Footage sourcing for the meme-video pipeline.

Two modes:
  * ``resolve_clip`` (legacy) — first Giphy hit, then Pexels fallback.
  * ``resolve_clip_agentic`` — pull top N Giphy candidates, ask the LLM which
    best matches the scene narration (with optional re-search), then Pexels.

Enable agentic mode with ``FOOTAGE_AGENTIC=true`` (default) or pass
``agentic=True`` explicitly. Pass ``scene_text`` so the picker can reason.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import requests

from . import config
from . import llm_client


class FootageError(RuntimeError):
    """Raised when no footage could be sourced for a search term."""


@dataclass
class Clip:
    """A resolved background clip for a scene."""

    url: str
    source: str  # "giphy" | "pexels"
    width: int = 0
    height: int = 0
    title: str = ""
    giphy_id: str = ""
    query_used: str = ""
    reason: str = ""


@dataclass
class _Candidate:
    id: str
    title: str
    url: str
    width: int
    height: int
    query: str
    tags: list[str] = field(default_factory=list)


def _agentic_enabled() -> bool:
    return os.getenv("FOOTAGE_AGENTIC", "true").strip().lower() not in ("0", "false", "no")


def _giphy_search(query: str, *, limit: int = 10, timeout: int = 20) -> list[dict]:
    resp = requests.get(
        "https://api.giphy.com/v1/gifs/search",
        params={
            "api_key": config.require_giphy(),
            "q": query[:50],
            "limit": limit,
            "rating": config.GIPHY_RATING,
            "bundle": "messaging_non_clips",
        },
        timeout=timeout,
    )
    if resp.status_code == 429:
        raise FootageError("Giphy rate limit hit (429).")
    if not resp.ok:
        raise FootageError(f"Giphy {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("data", [])


def _best_giphy_mp4(item: dict) -> Clip | None:
    """Pick the highest-quality mp4 rendition available for a Giphy result."""
    images = item.get("images", {})
    for key in ("original", "downsized_large", "fixed_height", "fixed_width", "downsized"):
        rendition = images.get(key) or {}
        mp4 = rendition.get("mp4")
        if mp4:
            return Clip(
                url=mp4,
                source="giphy",
                width=int(rendition.get("width") or 0),
                height=int(rendition.get("height") or 0),
                title=(item.get("title") or "").strip(),
                giphy_id=str(item.get("id") or ""),
            )
    return None


def _to_candidate(item: dict, query: str) -> _Candidate | None:
    clip = _best_giphy_mp4(item)
    if not clip:
        return None
    tags: list[str] = []
    for key in ("tags", "slug"):
        raw = item.get(key)
        if isinstance(raw, list):
            tags.extend(str(t) for t in raw[:8])
        elif isinstance(raw, str) and raw:
            tags.append(raw.replace("-", " ")[:60])
    return _Candidate(
        id=clip.giphy_id or str(item.get("id") or ""),
        title=clip.title or "untitled",
        url=clip.url,
        width=clip.width,
        height=clip.height,
        query=query,
        tags=tags[:8],
    )


def giphy_candidates(query: str, *, limit: int = 8) -> list[_Candidate]:
    try:
        results = _giphy_search(query, limit=limit)
    except FootageError:
        return []
    out: list[_Candidate] = []
    for item in results:
        cand = _to_candidate(item, query)
        if cand:
            out.append(cand)
    return out


def giphy_clip(query: str) -> Clip | None:
    """Return the first usable meme mp4 for a query (non-agentic)."""
    for cand in giphy_candidates(query, limit=5):
        return Clip(
            url=cand.url,
            source="giphy",
            width=cand.width,
            height=cand.height,
            title=cand.title,
            giphy_id=cand.id,
            query_used=query,
            reason="first_hit",
        )
    return None


def _pexels_clip(query: str, *, timeout: int = 20) -> Clip | None:
    if not config.PEXELS_API_KEY:
        return None
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        params={"query": query, "per_page": 5, "orientation": "portrait"},
        headers={"Authorization": config.PEXELS_API_KEY},
        timeout=timeout,
    )
    if not resp.ok:
        return None
    for video in resp.json().get("videos", []):
        files = sorted(
            video.get("video_files", []),
            key=lambda f: (f.get("width") or 0) * (f.get("height") or 0),
            reverse=True,
        )
        for f in files:
            if f.get("link") and (f.get("file_type") or "").endswith("mp4"):
                return Clip(
                    url=f["link"],
                    source="pexels",
                    width=int(f.get("width") or 0),
                    height=int(f.get("height") or 0),
                    title=(video.get("user") or {}).get("name", "pexels"),
                    query_used=query,
                    reason="pexels_fallback",
                )
    return None


_PICKER_SYSTEM = (
    "You pick reaction memes for viral short-form videos.\n"
    "Given a scene's narration and a list of Giphy candidates (id, title, tags), "
    "choose the SINGLE best match for the emotion and punchline of the line.\n"
    "Prefer clear reaction memes over random clips. Avoid NSFW/gore.\n"
    "If nothing fits, set reject=true and propose 1-2 better search queries.\n"
    "Return ONLY JSON: "
    '{"pick_id":"<id or null>","reject":bool,"reason":str,"alt_queries":[str]}'
)


def _llm_pick(
    scene_text: str,
    candidates: list[_Candidate],
    used_ids: set[str],
) -> dict:
    usable = [c for c in candidates if c.id not in used_ids]
    if not usable:
        return {"pick_id": None, "reject": True, "reason": "no_candidates", "alt_queries": []}

    catalog = [
        {"id": c.id, "title": c.title, "tags": c.tags, "query": c.query}
        for c in usable[:10]
    ]
    user = (
        f"Scene narration:\n{scene_text}\n\n"
        f"Candidates:\n{json.dumps(catalog, ensure_ascii=False)}\n\n"
        "Pick the best meme for this line."
    )
    try:
        return llm_client.complete_json(_PICKER_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001
        # Soft-fail: fall back to first candidate.
        return {
            "pick_id": usable[0].id,
            "reject": False,
            "reason": f"llm_fallback:{exc}",
            "alt_queries": [],
        }


def resolve_clip_agentic(
    search_terms: list[str],
    *,
    scene_text: str = "",
    used_ids: set[str] | None = None,
    max_rounds: int = 2,
) -> Clip:
    """Agentic meme picker: search → LLM rank → optional re-search → Pexels."""
    terms = [t for t in (search_terms or []) if t.strip()] or ["funny reaction"]
    used = set(used_ids or ())
    narration = (scene_text or " ".join(terms)).strip()
    tried_queries: list[str] = list(terms)
    pool: list[_Candidate] = []

    for term in terms:
        pool.extend(giphy_candidates(term, limit=8))

    for round_idx in range(max_rounds):
        # Deduplicate by id while preserving order.
        seen: set[str] = set()
        unique: list[_Candidate] = []
        for c in pool:
            if c.id and c.id not in seen and c.id not in used:
                seen.add(c.id)
                unique.append(c)

        if not unique:
            break

        decision = _llm_pick(narration, unique, used)
        pick_id = decision.get("pick_id")
        reject = bool(decision.get("reject"))
        reason = str(decision.get("reason") or "")

        if pick_id and not reject:
            for c in unique:
                if c.id == pick_id:
                    used.add(c.id)
                    return Clip(
                        url=c.url,
                        source="giphy",
                        width=c.width,
                        height=c.height,
                        title=c.title,
                        giphy_id=c.id,
                        query_used=c.query,
                        reason=reason or f"agentic_round_{round_idx}",
                    )

        alt = decision.get("alt_queries") or []
        new_queries = [str(q).strip() for q in alt if str(q).strip()][:2]
        if not new_queries:
            break
        for q in new_queries:
            if q.lower() in {t.lower() for t in tried_queries}:
                continue
            tried_queries.append(q)
            pool.extend(giphy_candidates(q, limit=8))

    # Non-agentic Giphy / Pexels fallbacks.
    for term in tried_queries:
        clip = giphy_clip(term)
        if clip and clip.giphy_id not in used:
            clip.reason = clip.reason or "agentic_exhausted_first_hit"
            return clip

    for term in tried_queries:
        clip = _pexels_clip(term)
        if clip:
            return clip

    clip = giphy_clip("funny reaction meme")
    if clip:
        return clip
    raise FootageError(f"No footage found for terms: {tried_queries}")


def resolve_clip(
    search_terms: list[str],
    *,
    scene_text: str = "",
    used_ids: set[str] | None = None,
    agentic: bool | None = None,
) -> Clip:
    """Public resolver. Defaults to agentic mode when FOOTAGE_AGENTIC is true."""
    use_agent = _agentic_enabled() if agentic is None else agentic
    if use_agent:
        return resolve_clip_agentic(
            search_terms, scene_text=scene_text, used_ids=used_ids
        )

    terms = [t for t in (search_terms or []) if t.strip()] or ["funny reaction"]
    for term in terms:
        clip = giphy_clip(term)
        if clip:
            return clip
    for term in terms:
        clip = _pexels_clip(term)
        if clip:
            return clip
    clip = giphy_clip("funny reaction meme")
    if clip:
        return clip
    raise FootageError(f"No footage found for terms: {terms}")
