#!/usr/bin/env python3
"""
Stickman AI panel library — generate, categorize, and reuse action panels.

Rico / Beckett style: black stick figures on pure white background.
Panels are stored under STICKMAN_PANEL_LIBRARY_DIR by action category so
future scenes can reuse matching poses without re-calling the image API.

Usage:
    from scripts.stickman_panel_library import resolve_or_generate_panel, list_library
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import requests

from scripts.utils.logger import setup_logger

logger = setup_logger("stickman_panel_library")

LIBRARY_DIR = Path(
    os.environ.get(
        "STICKMAN_PANEL_LIBRARY_DIR",
        "/data/videos/stickman-panel-library",
    ),
)
REGISTRY_NAME = "registry.json"

# Quality tiers. Primary provider = Kie.ai (KIA_API_KEY) → Nano Banana 2.
# Fallback = OpenRouter when provider=auto and Kie fails / missing.
# Docs: https://docs.kie.ai/market/google/nanobanana2
QUALITY = (os.environ.get("STICKMAN_PANEL_QUALITY") or "premium").strip().lower()

# auto = Kie if KIA/KIE key set, else OpenRouter
IMAGE_PROVIDER = (os.environ.get("STICKMAN_IMAGE_PROVIDER") or "auto").strip().lower()

KIE_QUALITY_MODELS: dict[str, list[str]] = {
    "premium": ["nano-banana-2", "nano-banana-pro"],
    "fast": ["nano-banana-2"],
}

OPENROUTER_QUALITY_MODELS: dict[str, list[str]] = {
    "premium": [
        "google/gemini-3.1-flash-image",
        "google/gemini-3.1-flash-image-preview",
        "black-forest-labs/flux.2-pro",
        "google/gemini-2.5-flash-image",
    ],
    "fast": [
        "google/gemini-2.5-flash-image",
        "google/gemini-3.1-flash-image",
    ],
}

# Back-compat alias
QUALITY_MODELS = OPENROUTER_QUALITY_MODELS

DEFAULT_IMAGE_MODEL = os.environ.get("STICKMAN_IMAGE_MODEL", "").strip()

# Rico Animations / Beckett tutorial look — expressive storyboard, NOT icon stickmen
STYLE_LOCK = (
    "Rico Animations style stick-figure illustration for viral YouTube shorts: "
    "clean black-and-white 2D vector storyboard art, thick bold black outlines, "
    "slightly thick limbs with clear joints, expressive body language and posture, "
    "minimal facial marks only when needed (dots/lines, never realistic face), "
    "pure solid white background, sparse symbolic props only, flat ink illustration, "
    "high contrast, centered cinematic framing, professional animatic quality"
)

NEGATIVE_LOCK = (
    "Avoid: photorealism, 3D render, CGI, gradients, gray backgrounds, clutter, "
    "watermarks, text captions, logos, color fills, soft shading, blurry lines, "
    "chibi, meme wojak, stickman emoji, children's scribble, low detail icon"
)

# Canonical action categories for future reuse
ACTION_CATEGORIES: dict[str, dict[str, Any]] = {
    "idle": {
        "label": "Idle standing",
        "keywords": ["idle", "stand", "standing", "plain", "neutral"],
        "prompt_hint": (
            "full-body stick figure standing confidently, weight on one leg, "
            "subtle personality in posture, eye-level camera, generous negative space"
        ),
    },
    "thinking": {
        "label": "Thinking",
        "keywords": ["think", "thinking", "wonder", "ponder", "realize", "question"],
        "prompt_hint": (
            "full-body stick figure in deep thought, hand to chin, other arm crossed, "
            "one empty thought bubble above head, contemplative mood, medium shot"
        ),
    },
    "sad": {
        "label": "Sad / lonely",
        "keywords": ["sad", "lonely", "alone", "depress", "cry", "down"],
        "prompt_hint": (
            "lonely stick figure with slumped shoulders and hanging head, "
            "small empty space around them emphasizing isolation, wide shot"
        ),
    },
    "happy": {
        "label": "Happy",
        "keywords": ["happy", "smile", "joy", "glad", "cheer"],
        "prompt_hint": (
            "stick figure with open joyful posture, slight bounce in stance, "
            "light energy, medium full-body shot"
        ),
    },
    "celebrating": {
        "label": "Celebrating / success",
        "keywords": ["celebrat", "success", "win", "victory", "triumph", "achieve"],
        "prompt_hint": (
            "stick figure leaping with both arms raised in victory, dynamic silhouette, "
            "triumphant energy, low-angle heroic framing"
        ),
    },
    "failing": {
        "label": "Failing / frustrated",
        "keywords": ["fail", "frustrat", "lost", "defeat", "mistake", "wrong"],
        "prompt_hint": (
            "stick figure clutching head in exaggerated frustration, bent knees, "
            "chaotic energy lines optional, expressive storyboard pose"
        ),
    },
    "running": {
        "label": "Running / chasing",
        "keywords": ["run", "running", "chase", "sprint", "hurry", "race"],
        "prompt_hint": (
            "stick figure sprinting mid-stride to the right, motion lines behind, "
            "dynamic diagonal composition, side view"
        ),
    },
    "walking": {
        "label": "Walking",
        "keywords": ["walk", "walking", "stroll"],
        "prompt_hint": (
            "stick figure walking thoughtfully left-to-right, calm gait, "
            "profile view, clean horizon line"
        ),
    },
    "pointing": {
        "label": "Pointing / explaining",
        "keywords": ["point", "explain", "show", "gesture", "lesson", "truth"],
        "prompt_hint": (
            "stick figure teacher pose pointing forward with one arm extended, "
            "confident stance, addressing the viewer, medium shot"
        ),
    },
    "sitting": {
        "label": "Sitting",
        "keywords": ["sit", "sitting", "wait", "waiting"],
        "prompt_hint": (
            "stick figure sitting on a simple block or ground line, patient waiting pose, "
            "quiet mood, centered composition"
        ),
    },
    "phone": {
        "label": "On phone / scrolling",
        "keywords": ["phone", "scroll", "social", "instagram", "tiktok", "screen"],
        "prompt_hint": (
            "stick figure hunched over a simple rectangle phone, face lit by screen metaphor, "
            "addicted scrolling energy, close-medium shot"
        ),
    },
    "computer": {
        "label": "At computer / working",
        "keywords": ["computer", "laptop", "work", "desk", "code", "type"],
        "prompt_hint": (
            "stick figure at a minimal desk with laptop rectangle, focused posture, "
            "side three-quarter view, clean workspace props only"
        ),
    },
    "money": {
        "label": "Money / buying",
        "keywords": ["money", "buy", "rich", "cash", "spend", "wealth", "impress"],
        "prompt_hint": (
            "stick figure overloaded with money bags or shopping bags, chasing approval, "
            "slightly absurd exaggeration, storytelling composition"
        ),
    },
    "crowd": {
        "label": "In a crowd",
        "keywords": ["crowd", "people", "everyone", "others", "audience", "nobody"],
        "prompt_hint": (
            "one detailed stick figure in focus among many smaller identical silhouettes, "
            "main character slightly larger/darker, social anxiety storytelling shot"
        ),
    },
    "mirror": {
        "label": "Looking in mirror",
        "keywords": ["mirror", "self", "imagine", "reflect"],
        "prompt_hint": (
            "stick figure facing a simple rectangular mirror, reflection matching pose, "
            "introspective mood, balanced left-right composition"
        ),
    },
    "clock": {
        "label": "Time / clock",
        "keywords": ["time", "clock", "late", "moment", "wait for perfect"],
        "prompt_hint": (
            "stick figure dwarfed by a large simple wall clock, looking up anxiously, "
            "time-pressure metaphor, strong scale contrast"
        ),
    },
    "shouting": {
        "label": "Shouting / arguing",
        "keywords": ["shout", "yell", "angry", "argue", "scream"],
        "prompt_hint": (
            "stick figure leaning forward shouting, sharp angular posture, "
            "anger lines, dramatic side angle"
        ),
    },
    "sleeping": {
        "label": "Sleeping",
        "keywords": ["sleep", "tired", "bed", "dream"],
        "prompt_hint": (
            "stick figure sleeping on a simple bed line with Z marks, "
            "peaceful or exhausted mood, horizontal composition"
        ),
    },
    "helping": {
        "label": "Helping / friendship",
        "keywords": ["help", "friend", "together", "support"],
        "prompt_hint": (
            "two stick figures, one pulling the other up, clear friendship story beat, "
            "warm supportive energy, two-shot framing"
        ),
    },
    "journey": {
        "label": "Journey / path",
        "keywords": ["path", "road", "journey", "start", "begin", "future", "dream"],
        "prompt_hint": (
            "stick figure walking toward a vanishing path or horizon line, "
            "hopeful forward motion, deep perspective, cinematic wide shot"
        ),
    },
}


def library_root() -> Path:
    root = LIBRARY_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def registry_path() -> Path:
    return library_root() / REGISTRY_NAME


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return {"version": 1, "panels": [], "categories": list(ACTION_CATEGORIES.keys())}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "panels": [], "categories": list(ACTION_CATEGORIES.keys())}


def save_registry(reg: dict[str, Any]) -> None:
    reg["updated_at"] = int(time.time())
    reg["categories"] = list(ACTION_CATEGORIES.keys())
    registry_path().write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")


def classify_action(
    text: str,
    *,
    preferred: str | None = None,
) -> str:
    """Map narration / image_prompt / video_prompt text to an action category."""
    if preferred and preferred in ACTION_CATEGORIES:
        return preferred

    lower = (text or "").lower()
    if not lower:
        return "idle"

    # Score categories by keyword hits
    best = "idle"
    best_score = 0
    for cat, meta in ACTION_CATEGORIES.items():
        score = 0
        for kw in meta.get("keywords") or []:
            if kw in lower:
                score += 1 + (1 if len(kw) > 4 else 0)
        if score > best_score:
            best_score = score
            best = cat
    return best


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s or "panel")[:max_len]


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]


def build_image_prompt(
    action: str,
    scene_prompt: str = "",
    narration: str = "",
    *,
    quality: str | None = None,
) -> str:
    """
    Premium prompt structure used by viral stickman tutorials:
    Subject + Action + Setting/Mood + Style lock + Negatives.
    """
    meta = ACTION_CATEGORIES.get(action) or ACTION_CATEGORIES["idle"]
    hint = meta["prompt_hint"]
    extra = (scene_prompt or narration or "").strip()
    q = (quality or QUALITY).lower()

    # Strip duplicated style locks from DeepSeek scene prompts to avoid bloat
    cleaned = re.sub(
        r"(?i)black stick figure on pure white background[^.]*(?:\.|$)",
        "",
        extra,
    ).strip(" .,")
    cleaned = re.sub(r"(?i)rico animation[^.]*(?:\.|$)", "", cleaned).strip(" .,")

    parts = [
        "Create one high-quality stick-figure animation still frame.",
        f"Subject: a consistent black stickman character.",
        f"Action: {action} — {hint}.",
    ]
    if cleaned:
        parts.append(f"Scene story beat: {cleaned[:320]}")
    parts.append(f"Style: {STYLE_LOCK}.")
    parts.append(NEGATIVE_LOCK + ".")
    if q == "premium":
        parts.append(
            "Quality bar: match viral Rico Animations / Google Flow Nano Banana panels — "
            "crisp linework, intentional composition, expressive silhouette readable at phone size."
        )
    parts.append(
        "Output a single centered frame, character large in frame, pure white void background, no border."
    )
    return " ".join(parts)


def _kie_api_key() -> str:
    from scripts.utils import kie_client

    return kie_client.api_key()


def _resolved_provider() -> str:
    """Return 'kie' or 'openrouter' based on env + available keys."""
    pref = IMAGE_PROVIDER
    has_kie = bool(_kie_api_key())
    has_or = bool(_openrouter_api_key())
    if pref in ("kie", "kia", "kie.ai"):
        return "kie"
    if pref in ("openrouter", "or"):
        return "openrouter"
    # auto
    if has_kie:
        return "kie"
    if has_or:
        return "openrouter"
    return "kie" if has_kie else "openrouter"


def model_candidates(explicit: str | None = None, *, provider: str | None = None) -> list[str]:
    prov = provider or _resolved_provider()
    cascade = (
        KIE_QUALITY_MODELS.get(QUALITY, KIE_QUALITY_MODELS["premium"])
        if prov == "kie"
        else OPENROUTER_QUALITY_MODELS.get(QUALITY, OPENROUTER_QUALITY_MODELS["premium"])
    )
    if explicit and explicit.strip():
        raw = [explicit.strip()]
    else:
        env_model = (os.environ.get("STICKMAN_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL or "").strip()
        raw = ([env_model] if env_model else []) + list(cascade)

    if prov == "kie":
        from scripts.utils import kie_client

        raw = [kie_client.to_kie_model(m) for m in raw]

    seen: set[str] = set()
    out: list[str] = []
    for m in raw:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out or list(cascade)


def image_model() -> str:
    return model_candidates()[0]


def find_library_panel(
    action: str,
    *,
    prompt_hash: str | None = None,
    allow_any_in_category: bool = True,
    prefer_quality: str | None = None,
) -> dict[str, Any] | None:
    """Find an existing panel. Prefer exact prompt hash, then premium-quality matches."""
    reg = load_registry()
    panels = [p for p in reg.get("panels") or [] if p.get("action") == action]
    if not panels:
        return None

    q = (prefer_quality or QUALITY).lower()

    if prompt_hash:
        for p in panels:
            if p.get("prompt_hash") == prompt_hash and Path(str(p.get("path") or "")).is_file():
                return p

    if not allow_any_in_category:
        return None

    # Prefer same quality tier, then newest valid file
    ranked = sorted(
        panels,
        key=lambda p: (
            1 if str(p.get("quality") or "").lower() == q else 0,
            int(p.get("created_at") or 0),
        ),
        reverse=True,
    )
    for p in ranked:
        if Path(str(p.get("path") or "")).is_file():
            return p
    return None


def register_panel(
    *,
    action: str,
    path: Path,
    prompt: str,
    source: str,
    model: str | None = None,
    narration: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    reg = load_registry()
    entry = {
        "id": f"{action}-{_prompt_hash(prompt)}-{int(time.time())}",
        "action": action,
        "label": (ACTION_CATEGORIES.get(action) or {}).get("label", action),
        "path": str(path),
        "prompt": prompt[:800],
        "prompt_hash": _prompt_hash(prompt),
        "source": source,
        "model": model,
        "quality": QUALITY,
        "narration": (narration or "")[:200],
        "tags": tags or [],
        "created_at": int(time.time()),
    }
    panels = reg.setdefault("panels", [])
    panels.append(entry)
    # Cap registry size per category to avoid unbounded growth
    by_action = [p for p in panels if p.get("action") == action]
    if len(by_action) > 40:
        # drop oldest for this action (keep files; only trim registry refs)
        drop_ids = {p["id"] for p in by_action[:-40]}
        reg["panels"] = [p for p in panels if p.get("id") not in drop_ids]
    save_registry(reg)
    return entry


def list_library(action: str | None = None) -> dict[str, Any]:
    reg = load_registry()
    panels = reg.get("panels") or []
    if action:
        panels = [p for p in panels if p.get("action") == action]
    counts: dict[str, int] = {}
    for p in reg.get("panels") or []:
        a = str(p.get("action") or "unknown")
        counts[a] = counts.get(a, 0) + 1
    return {
        "success": True,
        "library_dir": str(library_root()),
        "categories": [
            {"id": k, "label": v["label"], "count": counts.get(k, 0)}
            for k, v in ACTION_CATEGORIES.items()
        ],
        "panel_count": len(panels if action else reg.get("panels") or []),
        "panels": panels[-100:],
        "counts": counts,
    }


def _openrouter_api_key() -> str:
    return (os.environ.get("OPEN_ROUTER") or os.environ.get("OPENROUTER_API_KEY") or "").strip()


def can_generate_ai() -> bool:
    return bool(_kie_api_key() or _openrouter_api_key())


def _save_data_url(data_url: str, dest: Path) -> bool:
    m = re.match(r"^data:image/([\w+]+);base64,(.+)$", data_url, re.DOTALL)
    if not m:
        return False
    raw = base64.b64decode(m.group(2))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return dest.is_file() and dest.stat().st_size > 100


def generate_ai_panel(
    prompt: str,
    dest: Path,
    *,
    character_ref_path: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Generate a stickman panel.
    Prefer Kie.ai (KIA_API_KEY → Nano Banana 2); fall back to OpenRouter when provider=auto.
    """
    errors: list[dict[str, Any]] = []
    provider = _resolved_provider()
    prefer = IMAGE_PROVIDER

    if provider == "kie" and _kie_api_key():
        kie_result = _generate_ai_panel_kie(
            prompt,
            dest,
            character_ref_path=character_ref_path,
            model=model,
        )
        if kie_result.get("success"):
            kie_result["quality"] = QUALITY
            kie_result["provider"] = "kie"
            return kie_result
        errors.append({"provider": "kie", **{k: kie_result.get(k) for k in ("error", "attempts", "detail")}})
        logger.warning("Kie panel gen failed: %s", kie_result.get("error"))
        if prefer in ("kie", "kia", "kie.ai"):
            return {
                "success": False,
                "error": kie_result.get("error") or "kie_failed",
                "attempts": kie_result.get("attempts") or errors,
                "provider": "kie",
            }

    api_key = _openrouter_api_key()
    if not api_key:
        return {
            "success": False,
            "error": "no_image_api_key",
            "detail": "Set KIA_API_KEY (Kie) or OPEN_ROUTER",
            "attempts": errors,
        }

    for selected in model_candidates(model, provider="openrouter"):
        result = _generate_ai_panel_once(
            prompt,
            dest,
            api_key=api_key,
            model=selected,
            character_ref_path=character_ref_path,
        )
        if result.get("success"):
            result["quality"] = QUALITY
            result["provider"] = "openrouter"
            result["tried_models"] = model_candidates(model, provider="openrouter")
            return result
        errors.append({"provider": "openrouter", "model": selected, "error": result.get("error"), "detail": result.get("detail")})
        logger.warning("OpenRouter panel gen failed on %s: %s", selected, result.get("error"))

    return {
        "success": False,
        "error": "all_models_failed",
        "attempts": errors,
        "model": model_candidates(model)[0] if model_candidates(model) else None,
    }


def _generate_ai_panel_kie(
    prompt: str,
    dest: Path,
    *,
    character_ref_path: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    from scripts.utils import kie_client

    errors: list[dict[str, Any]] = []
    for selected in model_candidates(model, provider="kie"):
        result = kie_client.generate_image(
            prompt,
            dest,
            model=selected,
            aspect_ratio=os.environ.get("STICKMAN_IMAGE_ASPECT", "1:1"),
            character_ref_path=character_ref_path,
        )
        if result.get("success"):
            result["tried_models"] = model_candidates(model, provider="kie")
            return result
        errors.append({"model": selected, "error": result.get("error"), "detail": result.get("detail") or result.get("failMsg")})
        logger.warning("Kie model %s failed: %s", selected, result.get("error"))
    return {
        "success": False,
        "error": "all_kie_models_failed",
        "attempts": errors,
    }


def _modalities_for_model(model: str) -> list[str]:
    # Flux image-only models prefer modalities: ["image"]
    if "flux" in model.lower() or "black-forest" in model.lower():
        return ["image"]
    return ["image", "text"]


def _generate_ai_panel_once(
    prompt: str,
    dest: Path,
    *,
    api_key: str,
    model: str,
    character_ref_path: str | None = None,
) -> dict[str, Any]:
    selected = model.strip()
    content: Any
    if character_ref_path and Path(character_ref_path).is_file():
        try:
            raw = Path(character_ref_path).read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            mime = "image/png"
            suffix = Path(character_ref_path).suffix.lower()
            if suffix in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif suffix == ".webp":
                mime = "image/webp"
            content = [
                {
                    "type": "text",
                    "text": (
                        "CHARACTER REFERENCE LOCK: Match this stickman character design exactly "
                        "(proportions, line weight, head shape). Pose and scene may change.\n\n"
                        + prompt
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                },
            ]
        except Exception as exc:
            logger.warning("Could not attach character ref: %s", exc)
            content = prompt
    else:
        content = prompt

    payload: dict[str, Any] = {
        "model": selected,
        "messages": [{"role": "user", "content": content}],
        "modalities": _modalities_for_model(selected),
    }
    aspect = os.environ.get("STICKMAN_IMAGE_ASPECT", "1:1")
    # Gemini image_config; harmless if ignored by Flux
    payload["image_config"] = {"aspect_ratio": aspect}

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "https://localhost"),
                "X-Title": os.environ.get("OPENROUTER_TITLE", "manga-stickman-panels"),
            },
            json=payload,
            timeout=180,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            # Flux may need /images API instead of chat
            if "flux" in selected.lower():
                legacy = _legacy_images_generations(prompt, dest, model=selected, api_key=api_key)
                if legacy.get("success"):
                    return legacy
            err = data.get("error") if isinstance(data, dict) else data
            return {
                "success": False,
                "error": f"openrouter_http_{resp.status_code}",
                "detail": err,
                "model": selected,
            }

        choices = data.get("choices") or []
        if not choices:
            legacy = _legacy_images_generations(prompt, dest, model=selected, api_key=api_key)
            if legacy.get("success"):
                return legacy
            return {"success": False, "error": "empty_choices", "raw": data, "model": selected}

        message = choices[0].get("message") or {}
        images = message.get("images") or []

        if not images and isinstance(message.get("content"), list):
            for part in message["content"]:
                if isinstance(part, dict) and part.get("type") in ("image_url", "image"):
                    images.append(part)

        data_url = None
        for img in images:
            if not isinstance(img, dict):
                continue
            url = (
                (img.get("image_url") or {}).get("url")
                or img.get("url")
                or (img.get("imageUrl") or {}).get("url")
            )
            if url and str(url).startswith("data:image"):
                data_url = str(url)
                break

        if not data_url:
            legacy = _legacy_images_generations(prompt, dest, model=selected, api_key=api_key)
            if legacy.get("success"):
                return legacy
            return {
                "success": False,
                "error": "no_image_in_response",
                "model": selected,
                "content_preview": str(message.get("content") or "")[:400],
            }

        if not _save_data_url(data_url, dest):
            return {"success": False, "error": "failed_to_decode_image", "model": selected}

        return {
            "success": True,
            "path": str(dest),
            "model": selected,
            "source": "openrouter_chat",
            "bytes": dest.stat().st_size,
        }
    except Exception as exc:
        logger.exception("AI panel generation failed on %s", selected)
        return {"success": False, "error": str(exc)[:2000], "model": selected}


def _legacy_images_generations(
    prompt: str,
    dest: Path,
    *,
    model: str,
    api_key: str,
) -> dict[str, Any]:
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "prompt": prompt,
                "n": 1,
                "size": os.environ.get("STICKMAN_IMAGE_SIZE", "1024x1024"),
            },
            timeout=180,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"success": False, "error": data.get("error") or resp.text[:300]}
        items = data.get("data") or []
        if not items:
            return {"success": False, "error": "empty_image_data"}
        first = items[0]
        if first.get("b64_json"):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(base64.b64decode(first["b64_json"]))
            return {"success": True, "path": str(dest), "model": model, "source": "openrouter_images"}
        url = first.get("url")
        if url:
            img = requests.get(url, timeout=60)
            img.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(img.content)
            return {"success": True, "path": str(dest), "model": model, "source": "openrouter_images"}
        return {"success": False, "error": "no_b64_or_url"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def resolve_or_generate_panel(
    *,
    action: str | None = None,
    image_prompt: str = "",
    narration: str = "",
    video_prompt: str = "",
    character_ref_path: str | None = None,
    dest: Path | None = None,
    force_regenerate: bool = False,
    reuse_library: bool = True,
) -> dict[str, Any]:
    """
    Main entry: classify action → reuse library if possible → else AI generate → register.
    """
    blob = " ".join([image_prompt or "", narration or "", video_prompt or ""])
    action_id = classify_action(blob, preferred=action)
    prompt = build_image_prompt(action_id, scene_prompt=image_prompt or video_prompt, narration=narration)
    ph = _prompt_hash(prompt)

    if reuse_library and not force_regenerate:
        # Prefer exact prompt match; else reuse premium panel in category
        existing = find_library_panel(
            action_id,
            prompt_hash=ph,
            allow_any_in_category=True,
            prefer_quality=QUALITY,
        )
        # Skip reuse of old basic-quality panels when running premium
        if existing and QUALITY == "premium" and str(existing.get("quality") or "") not in ("", "premium"):
            # allow if no quality field but model looks premium
            model_name = str(existing.get("model") or "")
            if "3.1" not in model_name and "flux.2" not in model_name:
                existing = None
        if existing:
            src = Path(str(existing["path"]))
            out = dest or src
            if dest and src.resolve() != Path(dest).resolve():
                Path(dest).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                out = Path(dest)
            return {
                "success": True,
                "action": action_id,
                "path": str(out),
                "source": "library",
                "library_id": existing.get("id"),
                "model": existing.get("model"),
                "quality": existing.get("quality") or QUALITY,
                "prompt": prompt,
                "reused": True,
            }

    # Library miss → AI generate into category folder
    cat_dir = library_root() / action_id
    cat_dir.mkdir(parents=True, exist_ok=True)
    lib_name = f"{action_id}_{ph}_{int(time.time())}.png"
    lib_path = cat_dir / lib_name

    if can_generate_ai():
        gen = generate_ai_panel(
            prompt,
            lib_path,
            character_ref_path=character_ref_path,
        )
        if gen.get("success"):
            entry = register_panel(
                action=action_id,
                path=lib_path,
                prompt=prompt,
                source=str(gen.get("source") or "ai"),
                model=str(gen.get("model") or image_model()),
                narration=narration,
                tags=[action_id, QUALITY, "rico"],
            )
            out = dest or lib_path
            if dest and Path(dest).resolve() != lib_path.resolve():
                Path(dest).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(lib_path, dest)
            return {
                "success": True,
                "action": action_id,
                "path": str(out),
                "source": gen.get("source") or "ai",
                "provider": gen.get("provider") or gen.get("source"),
                "model": gen.get("model"),
                "quality": QUALITY,
                "library_id": entry.get("id"),
                "prompt": prompt,
                "reused": False,
            }
        ai_error = gen
    else:
        ai_error = {"error": "KIA_API_KEY / OPEN_ROUTER not set"}

    return {
        "success": False,
        "action": action_id,
        "prompt": prompt,
        "error": ai_error.get("error") if isinstance(ai_error, dict) else "ai_failed",
        "detail": ai_error.get("detail") if isinstance(ai_error, dict) else ai_error,
        "attempts": ai_error.get("attempts") if isinstance(ai_error, dict) else None,
        "model": ai_error.get("model") if isinstance(ai_error, dict) else None,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stickman AI panel library")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--action", default="")
    parser.add_argument("--generate", default="", help="Narration / prompt to generate")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(list_library(args.action or None), indent=2, ensure_ascii=False))
    elif args.generate:
        result = resolve_or_generate_panel(
            narration=args.generate,
            action=args.action or None,
            force_regenerate=args.force,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps(list_library(), indent=2, ensure_ascii=False))
