#!/usr/bin/env python3
"""
Discover and refresh React/Remotion video templates from the internet.

Sources:
  - Curated seed registry (data/video_templates/registry.json)
  - GitHub API (repo stars, description, updated_at)
  - Remotion official resources page (link harvest)

Agents call recommend_templates() or refresh_registry() via the
video_template_research QwenPaw skill / worker routes.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from scripts.utils.logger import setup_logger

logger = setup_logger("video_template_research")

_SEED_REGISTRY = Path(__file__).resolve().parent / "video_templates" / "registry.json"
_WRITABLE_REGISTRY = Path(
    os.environ.get("VIDEO_TEMPLATE_REGISTRY", "/data/video_templates/registry.json"),
)
# Local dev fallback when /data is not mounted
_LOCAL_REGISTRY = Path(__file__).resolve().parent / "video_templates" / "registry.json"


def _registry_path() -> Path:
    explicit = os.environ.get("VIDEO_TEMPLATE_REGISTRY", "").strip()
    if explicit:
        return Path(explicit)
    if _WRITABLE_REGISTRY.parent.exists() and os.access(str(_WRITABLE_REGISTRY.parent), os.W_OK):
        return _WRITABLE_REGISTRY
    return _LOCAL_REGISTRY


REGISTRY_PATH = _registry_path()
RESEARCH_LOG = REGISTRY_PATH.parent / "last_research.json"

GITHUB_API = "https://api.github.com/repos"
REMOTION_RESOURCES_URL = "https://www.remotion.dev/docs/resources"
REQUEST_TIMEOUT = int(os.environ.get("TEMPLATE_RESEARCH_TIMEOUT", "30"))
USER_AGENT = "manga-automation-template-research/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_registry_seed() -> None:
    if REGISTRY_PATH.is_file():
        return
    if not _SEED_REGISTRY.is_file():
        return
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(_SEED_REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")


def load_registry() -> dict[str, Any]:
    _ensure_registry_seed()
    if not REGISTRY_PATH.is_file():
        return {"version": 1, "templates": [], "composition_map": {}, "agent_rules": []}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(data: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    REGISTRY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_github_repo(repo: str) -> dict[str, Any] | None:
    if not repo or "/" not in repo:
        return None
    url = f"{GITHUB_API}/{repo}"
    try:
        resp = requests.get(url, headers=_github_headers(), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return {
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "description": data.get("description"),
            "homepage": data.get("homepage"),
            "topics": data.get("topics", []),
            "license": (data.get("license") or {}).get("spdx_id"),
            "pushed_at": data.get("pushed_at"),
            "open_issues": data.get("open_issues_count"),
        }
    except Exception as exc:
        logger.warning(f"github fetch failed for {repo}: {exc}")
        return None


def harvest_remotion_resource_links() -> list[dict[str, str]]:
    """Scrape markdown links from Remotion resources page."""
    try:
        resp = requests.get(REMOTION_RESOURCES_URL, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        logger.warning(f"remotion resources fetch failed: {exc}")
        return []

    # Markdown-style links in rendered docs: [Title](url)
    links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", html)
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    keywords = (
        "template", "remotion", "video", "component", "bits", "clippkit",
        "remocn", "onda", "caption", "audiogram", "editor",
    )
    for title, url in links:
        if url in seen:
            continue
        blob = f"{title} {url}".lower()
        if not any(k in blob for k in keywords):
            continue
        seen.add(url)
        out.append({"title": title.strip(), "url": url.strip()})
    return out[:80]


def refresh_registry(*, fetch_github: bool = True, fetch_remotion: bool = True) -> dict[str, Any]:
    registry = load_registry()
    templates: list[dict[str, Any]] = list(registry.get("templates", []))
    github_updates = 0
    remotion_links: list[dict[str, str]] = []

    if fetch_github:
        for tpl in templates:
            repo = tpl.get("repo")
            if not repo:
                continue
            meta = fetch_github_repo(str(repo))
            if not meta:
                continue
            tpl["github"] = meta
            if meta.get("description") and not tpl.get("description"):
                tpl["description"] = meta["description"]
            if meta.get("homepage") and not tpl.get("url"):
                tpl["url"] = meta["homepage"]
            github_updates += 1
            time.sleep(0.3)

    if fetch_remotion:
        remotion_links = harvest_remotion_resource_links()
        registry["remotion_resources"] = remotion_links

    registry["templates"] = templates
    registry["last_research"] = {
        "at": _now_iso(),
        "github_repos_updated": github_updates,
        "remotion_links_found": len(remotion_links),
        "sources": [
            REMOTION_RESOURCES_URL,
            "https://github.com (public API)",
        ],
    }
    save_registry(registry)

    log_entry = {
        "at": _now_iso(),
        "github_repos_updated": github_updates,
        "remotion_links_found": len(remotion_links),
        "registry_path": str(REGISTRY_PATH),
    }
    RESEARCH_LOG.write_text(json.dumps(log_entry, indent=2), encoding="utf-8")
    return {
        "success": True,
        "registry_path": str(REGISTRY_PATH),
        "template_count": len(templates),
        "github_repos_updated": github_updates,
        "remotion_links_found": len(remotion_links),
        "updated_at": registry.get("updated_at"),
    }


def list_templates(
    *,
    category: str | None = None,
    style: str | None = None,
    composition_id: str | None = None,
) -> dict[str, Any]:
    registry = load_registry()
    templates = list(registry.get("templates", []))

    if composition_id:
        comp_map = registry.get("composition_map", {}).get(composition_id, {})
        recommended_ids = set(comp_map.get("recommended_templates", []))
        templates = [t for t in templates if t.get("id") in recommended_ids] or templates

    if category:
        templates = [t for t in templates if t.get("category") == category]

    if style:
        needle = style.lower()
        templates = [
            t for t in templates
            if needle in " ".join(t.get("style_tags", [])).lower()
            or needle in (t.get("description") or "").lower()
            or needle in (t.get("name") or "").lower()
        ]

    templates.sort(key=lambda t: (t.get("github") or {}).get("stars") or 0, reverse=True)

    return {
        "success": True,
        "count": len(templates),
        "templates": templates,
        "composition_map": registry.get("composition_map", {}),
        "agent_rules": registry.get("agent_rules", []),
        "updated_at": registry.get("updated_at"),
    }


def recommend_templates(brief: str, *, composition_id: str | None = None) -> dict[str, Any]:
    """Rule-based template recommendation from a natural-language brief."""
    registry = load_registry()
    brief_lower = brief.lower()
    scores: list[tuple[int, dict[str, Any]]] = []

    keyword_weights: list[tuple[tuple[str, ...], str, int]] = [
        (("stickman", "stick figure", "canva", "explain", "story"), "internal-stickfigure", 10),
        (("caption", "subtitle", "tiktok", "short", "karaoke", "kinetic"), "remotion-captions-themes", 9),
        (("product", "saas", "brand", "promo", "nvidia", "launch"), "internal-product-promo", 10),
        (("product", "saas", "demo", "terminal", "changelog"), "remocn", 8),
        (("particle", "gradient", "animated text", "headline"), "remotion-bits", 7),
        (("transition", "motion graphics", "fade", "polish"), "onda", 7),
        (("intro", "split screen", "hero"), "clippkit", 6),
        (("podcast", "audiogram", "waveform"), "remotion-audiogram", 8),
        (("voiceover", "tts", "narrat", "elevenlabs"), "remotion-tts", 7),
        (("manga", "panel", "recap"), "remotion-bits", 5),
        (("lower third", "title card", "broadcast"), "remotion-ui", 6),
        (("chart", "data", "bar chart", "infographic"), "ai-video-editor", 6),
    ]

    by_id = {t["id"]: t for t in registry.get("templates", []) if t.get("id")}

    for tpl in registry.get("templates", []):
        score = 0
        tags = " ".join(tpl.get("style_tags", [])).lower()
        desc = (tpl.get("description") or "").lower()
        for keywords, tpl_id, weight in keyword_weights:
            if tpl.get("id") != tpl_id:
                continue
            if any(k in brief_lower for k in keywords):
                score += weight
        if any(w in brief_lower for w in tags.split()):
            score += 2
        if composition_id and composition_id in tpl.get("our_compositions", []):
            score += 5
        comp_rec = registry.get("composition_map", {}).get(composition_id or "", {})
        if tpl.get("id") in comp_rec.get("recommended_templates", []):
            score += 4
        if score > 0:
            scores.append((score, tpl))

    scores.sort(key=lambda x: (-x[0], -((x[1].get("github") or {}).get("stars") or 0)))
    top = [dict(t, recommendation_score=s) for s, t in scores[:6]]

    if not top and composition_id:
        comp = registry.get("composition_map", {}).get(composition_id, {})
        for tid in comp.get("recommended_templates", [])[:4]:
            if tid in by_id:
                top.append(dict(by_id[tid], recommendation_score=1))

    return {
        "success": True,
        "brief": brief,
        "composition_id": composition_id,
        "recommendations": top,
        "install_next_steps": [
            t.get("install") for t in top if t.get("install")
        ][:4],
        "agent_rules": registry.get("agent_rules", []),
    }


def run_template_research(body: dict[str, Any]) -> dict[str, Any]:
    action = str(body.get("action") or body.get("mode") or "recommend").lower()

    if action in {"refresh", "research", "learn", "update"}:
        return refresh_registry(
            fetch_github=body.get("fetch_github", True),
            fetch_remotion=body.get("fetch_remotion", True),
        )

    if action in {"list", "catalog"}:
        return list_templates(
            category=body.get("category"),
            style=body.get("style") or body.get("style_tag"),
            composition_id=body.get("composition_id") or body.get("compositionId"),
        )

    brief = str(body.get("brief") or body.get("prompt") or body.get("message") or "").strip()
    if not brief and not body.get("composition_id") and not body.get("compositionId"):
        return list_templates()

    return recommend_templates(
        brief or "general video",
        composition_id=body.get("composition_id") or body.get("compositionId"),
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="React/Remotion template research for agents")
    parser.add_argument("--refresh", action="store_true", help="Fetch latest from GitHub + Remotion docs")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--brief", default="")
    parser.add_argument("--composition", default="")
    args = parser.parse_args()

    if args.refresh:
        print(json.dumps(refresh_registry(), indent=2))
    elif args.list:
        print(json.dumps(list_templates(), indent=2))
    else:
        print(json.dumps(recommend_templates(args.brief or "stickman short", args.composition or None), indent=2))
