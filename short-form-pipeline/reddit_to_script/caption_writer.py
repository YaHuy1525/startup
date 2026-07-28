"""Social caption writer for anime-theory Shorts (shortform-captioner agent).

Hermes/QwenPaw can call this; used before AiToEarn publish.
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from . import config


def write_caption(
    *,
    title: str,
    anime: str = "",
    scenes: list[dict[str, Any]] | None = None,
    hook: str = "",
    platforms: list[str] | None = None,
) -> dict[str, Any]:
    """Return title + caption + hashtags tuned for Shorts/TikTok."""
    platforms = platforms or ["tiktok", "youtube", "instagram"]
    scene_bits: list[str] = []
    for s in (scenes or [])[:6]:
        t = str(s.get("text") or "").strip()
        if t:
            scene_bits.append(t)
    body = "\n".join(scene_bits) or hook or title

    prompt = (
        "Write a viral social caption for an anime-theory YouTube Short / TikTok.\n"
        f"Title: {title}\n"
        f"Anime: {anime or 'infer'}\n"
        f"Platforms: {', '.join(platforms)}\n"
        f"Narration excerpt:\n{body[:1200]}\n\n"
        "Rules:\n"
        "- Return ONLY JSON: {\"title\":str,\"caption\":str,\"hashtags\":[str]}\n"
        "- title: punchy ≤70 chars, can match or tighten the video title\n"
        "- caption: 2–4 short lines, hook first, casual TikTok voice, no spoilers dump\n"
        "- hashtags: 6–10 tags, mix niche + broad (#jujutsukaisen #animetheory etc)\n"
        "- No 'link in bio', no emojis spam (0–2 max), no fake engagement bait\n"
    )

    api_key = getattr(config, "OPENAI_API_KEY", "") or ""
    if not api_key:
        # Deterministic fallback
        tags = _fallback_tags(title, anime)
        caption = f"{title}\n\nFull theory in the video.\n{' '.join(tags)}"
        return {
            "ok": True,
            "agent": "shortform-captioner",
            "title": title[:70],
            "caption": caption,
            "hashtags": tags,
            "fallback": True,
        }

    try:
        resp = requests.post(
            f"{config.OPENAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.resolved_llm_model()
                if hasattr(config, "resolved_llm_model")
                else (config.LLM_MODEL or "gpt-4o-mini"),
                "messages": [
                    {
                        "role": "system",
                        "content": "You write high-CTR anime Shorts captions. JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 400,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        if not resp.ok:
            raise RuntimeError(f"LLM {resp.status_code}: {resp.text[:200]}")
        raw = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        tags = _fallback_tags(title, anime)
        return {
            "ok": True,
            "agent": "shortform-captioner",
            "title": title[:70],
            "caption": f"{title}\n\n{' '.join(tags)}",
            "hashtags": tags,
            "fallback": True,
            "error": str(exc),
        }

    tags = data.get("hashtags") or _fallback_tags(title, anime)
    if isinstance(tags, str):
        tags = [t for t in re.split(r"[\s,]+", tags) if t]
    tags = [("#" + t.lstrip("#")) for t in tags if str(t).strip()][:10]
    cap = str(data.get("caption") or title).strip()
    if tags and not any(t.lstrip("#").lower() in cap.lower() for t in tags[:3]):
        cap = f"{cap}\n\n{' '.join(tags)}"
    return {
        "ok": True,
        "agent": "shortform-captioner",
        "title": str(data.get("title") or title).strip()[:70],
        "caption": cap,
        "hashtags": tags,
        "fallback": False,
    }


def _fallback_tags(title: str, anime: str) -> list[str]:
    tags = ["#animetheory", "#anime", "#shorts", "#fyp"]
    low = f"{title} {anime}".lower()
    if "jujutsu" in low or "yuta" in low or "gojo" in low or "sukuna" in low:
        tags = ["#jujutsukaisen", "#jjk", "#yuta", "#gojo", *tags]
    if "bleach" in low:
        tags = ["#bleach", *tags]
    return tags[:10]
