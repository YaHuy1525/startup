#!/usr/bin/env python3
"""
Kie.ai (KIA) API client — Nano Banana 2 / Pro image generation.

Docs: https://docs.kie.ai/market/google/nanobanana2
      https://docs.kie.ai/market/common/get-task-detail
      https://docs.kie.ai/file-upload-api/upload-file-stream

Env:
  KIA_API_KEY or KIE_API_KEY  — Bearer token
  KIE_API_BASE                — default https://api.kie.ai
  KIE_UPLOAD_BASE             — optional upload host override
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from scripts.utils.logger import setup_logger

logger = setup_logger("kie_client")

DEFAULT_BASE = "https://api.kie.ai"
DEFAULT_UPLOAD_BASE = "https://kieai.redpandaai.co"


def api_key() -> str:
    return (
        os.environ.get("KIA_API_KEY")
        or os.environ.get("KIE_API_KEY")
        or os.environ.get("KIEAI_API_KEY")
        or ""
    ).strip()


def api_base() -> str:
    return (os.environ.get("KIE_API_BASE") or DEFAULT_BASE).rstrip("/")


def upload_base() -> str:
    return (os.environ.get("KIE_UPLOAD_BASE") or DEFAULT_UPLOAD_BASE).rstrip("/")


def available() -> bool:
    return bool(api_key())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
    }


def to_kie_model(name: str | None) -> str:
    """Map OpenRouter-style names → Kie market model ids."""
    n = (name or "").strip().lower()
    if not n:
        return "nano-banana-2"
    if n in ("nano-banana-2", "nano-banana-pro", "nano-banana"):
        return n
    if "nano-banana-pro" in n or "gemini-3-pro" in n or "pro-image" in n:
        return "nano-banana-pro"
    if "nano-banana" in n and "pro" not in n:
        return "nano-banana-2"
    # Gemini Flash Image / Nano Banana 2 via OpenRouter naming
    if "3.1" in n or "gemini" in n or "flux" in n:
        return "nano-banana-2"
    return n


def upload_file(path: str | Path, *, upload_path: str = "stickman/refs") -> dict[str, Any]:
    """Upload a local file; returns downloadUrl for image_input."""
    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": "file_not_found", "path": str(p)}
    if not available():
        return {"success": False, "error": "KIA_API_KEY not set"}

    endpoints = [
        f"{upload_base()}/api/file-stream-upload",
        f"{api_base()}/api/file-stream-upload",
        f"{api_base()}/api/v1/file-stream-upload",
    ]
    last_err: Any = None
    for url in endpoints:
        try:
            with p.open("rb") as fh:
                resp = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key()}"},
                    files={"file": (p.name, fh, "application/octet-stream")},
                    data={"uploadPath": upload_path.strip("/"), "fileName": p.name},
                    timeout=120,
                )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400 or not (data.get("success") or data.get("code") == 200):
                last_err = {"status": resp.status_code, "body": data or resp.text[:300], "url": url}
                continue
            payload = data.get("data") or {}
            download = payload.get("downloadUrl") or payload.get("url")
            if not download:
                last_err = {"error": "no_downloadUrl", "body": data, "url": url}
                continue
            return {
                "success": True,
                "downloadUrl": str(download),
                "fileName": payload.get("fileName"),
                "source": url,
            }
        except Exception as exc:
            last_err = {"error": str(exc)[:500], "url": url}
    return {"success": False, "error": "upload_failed", "detail": last_err}


def create_task(
    *,
    prompt: str,
    model: str = "nano-banana-2",
    aspect_ratio: str = "1:1",
    resolution: str = "1K",
    output_format: str = "png",
    image_input: list[str] | None = None,
) -> dict[str, Any]:
    if not available():
        return {"success": False, "error": "KIA_API_KEY not set"}

    kie_model = to_kie_model(model)
    body: dict[str, Any] = {
        "model": kie_model,
        "input": {
            "prompt": prompt[:20000],
            "aspect_ratio": aspect_ratio or "1:1",
            "resolution": resolution or "1K",
            "output_format": output_format or "png",
        },
    }
    if image_input:
        body["input"]["image_input"] = [u for u in image_input if u][:14]

    try:
        resp = requests.post(
            f"{api_base()}/api/v1/jobs/createTask",
            headers=_headers(),
            json=body,
            timeout=60,
        )
        data = resp.json() if resp.content else {}
        code = data.get("code")
        if resp.status_code >= 400 or (code is not None and code != 200):
            return {
                "success": False,
                "error": f"kie_create_{resp.status_code}",
                "detail": data.get("msg") or data,
                "model": kie_model,
            }
        task_id = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get("taskId")
        if not task_id:
            return {"success": False, "error": "no_taskId", "detail": data, "model": kie_model}
        return {"success": True, "taskId": str(task_id), "model": kie_model, "raw": data}
    except Exception as exc:
        return {"success": False, "error": str(exc)[:2000], "model": kie_model}


def create_task_raw(model: str, input_obj: dict[str, Any]) -> dict[str, Any]:
    """Low-level createTask for any Kie market model (video, audio, etc.)."""
    if not available():
        return {"success": False, "error": "KIA_API_KEY not set"}

    body = {"model": model, "input": input_obj}
    try:
        resp = requests.post(
            f"{api_base()}/api/v1/jobs/createTask",
            headers=_headers(),
            json=body,
            timeout=60,
        )
        data = resp.json() if resp.content else {}
        code = data.get("code")
        if resp.status_code >= 400 or (code is not None and code != 200):
            return {
                "success": False,
                "error": f"kie_create_{resp.status_code}",
                "detail": data.get("msg") or data,
                "model": model,
            }
        task_id = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get("taskId")
        if not task_id:
            return {"success": False, "error": "no_taskId", "detail": data, "model": model}
        return {"success": True, "taskId": str(task_id), "model": model, "raw": data}
    except Exception as exc:
        return {"success": False, "error": str(exc)[:2000], "model": model}


def get_task(task_id: str) -> dict[str, Any]:
    try:
        resp = requests.get(
            f"{api_base()}/api/v1/jobs/recordInfo",
            headers=_headers(),
            params={"taskId": task_id},
            timeout=30,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"success": False, "error": f"kie_poll_{resp.status_code}", "detail": data}
        return {"success": True, "data": data.get("data") or {}, "raw": data}
    except Exception as exc:
        return {"success": False, "error": str(exc)[:2000]}


def _result_urls(task_data: dict[str, Any]) -> list[str]:
    raw = task_data.get("resultJson") or ""
    if isinstance(raw, dict):
        parsed = raw
    else:
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return []
    urls = parsed.get("resultUrls") or parsed.get("result_urls") or []
    if isinstance(urls, str):
        urls = [urls]
    return [str(u) for u in urls if u]


def wait_for_task(
    task_id: str,
    *,
    timeout_sec: float | None = None,
    poll_sec: float | None = None,
) -> dict[str, Any]:
    timeout_sec = float(timeout_sec or os.environ.get("KIE_POLL_TIMEOUT_SEC") or 180)
    poll_sec = float(poll_sec or os.environ.get("KIE_POLL_INTERVAL_SEC") or 2.5)
    deadline = time.time() + timeout_sec
    delay = poll_sec
    last: dict[str, Any] = {}

    while time.time() < deadline:
        last = get_task(task_id)
        if not last.get("success"):
            time.sleep(delay)
            delay = min(delay * 1.3, 12.0)
            continue
        data = last.get("data") or {}
        state = str(data.get("state") or "").lower()
        if state == "success":
            urls = _result_urls(data)
            if not urls:
                return {"success": False, "error": "success_but_no_urls", "data": data}
            return {
                "success": True,
                "state": state,
                "resultUrls": urls,
                "taskId": task_id,
                "data": data,
            }
        if state == "fail":
            return {
                "success": False,
                "error": "generation_failed",
                "failCode": data.get("failCode"),
                "failMsg": data.get("failMsg"),
                "data": data,
            }
        time.sleep(delay)
        delay = min(delay * 1.25, 10.0)

    return {"success": False, "error": "poll_timeout", "taskId": task_id, "last": last}


def download_url(url: str, dest: Path) -> dict[str, Any]:
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        if dest.stat().st_size < 100:
            return {"success": False, "error": "downloaded_file_too_small"}
        return {"success": True, "path": str(dest), "bytes": dest.stat().st_size}
    except Exception as exc:
        return {"success": False, "error": str(exc)[:2000]}


def generate_image(
    prompt: str,
    dest: Path,
    *,
    model: str = "nano-banana-2",
    aspect_ratio: str = "1:1",
    resolution: str | None = None,
    character_ref_path: str | None = None,
    character_ref_url: str | None = None,
) -> dict[str, Any]:
    """
    Create Nano Banana task → poll → download first result URL to dest.
    """
    if not available():
        return {"success": False, "error": "KIA_API_KEY not set"}

    image_input: list[str] = []
    if character_ref_url:
        image_input.append(character_ref_url)
    elif character_ref_path and Path(character_ref_path).is_file():
        up = upload_file(character_ref_path)
        if up.get("success") and up.get("downloadUrl"):
            image_input.append(str(up["downloadUrl"]))
            prompt = (
                "CHARACTER REFERENCE LOCK: Match this stickman character design exactly "
                "(proportions, line weight, head shape). Pose and scene may change.\n\n"
                + prompt
            )
        else:
            logger.warning("Kie character-ref upload failed: %s", up.get("error") or up)

    res = (resolution or os.environ.get("STICKMAN_IMAGE_RESOLUTION") or "1K").strip()
    aspect = aspect_ratio or os.environ.get("STICKMAN_IMAGE_ASPECT") or "1:1"

    created = create_task(
        prompt=prompt,
        model=model,
        aspect_ratio=aspect,
        resolution=res,
        output_format="png",
        image_input=image_input or None,
    )
    if not created.get("success"):
        return created

    task_id = str(created["taskId"])
    waited = wait_for_task(task_id)
    if not waited.get("success"):
        waited["model"] = created.get("model")
        waited["taskId"] = task_id
        return waited

    url = (waited.get("resultUrls") or [None])[0]
    if not url:
        return {"success": False, "error": "empty_resultUrls", "taskId": task_id}

    saved = download_url(url, dest)
    if not saved.get("success"):
        saved["taskId"] = task_id
        saved["model"] = created.get("model")
        return saved

    return {
        "success": True,
        "path": str(dest),
        "model": created.get("model"),
        "source": "kie",
        "taskId": task_id,
        "bytes": saved.get("bytes"),
        "resultUrl": url,
    }


# ─── Video (image-to-video) ───────────────────────────────────────────────────

# Models that take a singular `image_url` instead of `image_urls` array
_SINGLE_IMAGE_VIDEO_PREFIXES = ("kling", "wan", "bytedance", "seedance", "hailuo", "veo", "google/veo")


def _video_input(
    *,
    model: str,
    image_url: str | None,
    prompt: str,
    duration: int,
    resolution: str,
    aspect_ratio: str,
    mode: str,
) -> dict[str, Any]:
    m = model.lower()
    inp: dict[str, Any] = {"prompt": prompt[:5000]}
    if image_url:
        if any(m.startswith(p) or p in m for p in _SINGLE_IMAGE_VIDEO_PREFIXES):
            inp["image_url"] = image_url
        else:
            # grok-imagine/image-to-video + generic default
            inp["image_urls"] = [image_url]
    if "grok" in m:
        inp["mode"] = mode
        inp["duration"] = str(duration)
        inp["resolution"] = resolution if resolution in ("480p", "720p") else "720p"
        inp["aspect_ratio"] = aspect_ratio
    else:
        inp["duration"] = duration
        inp["aspect_ratio"] = aspect_ratio
        inp["resolution"] = resolution
    return inp


def generate_video(
    dest: Path,
    *,
    prompt: str,
    image_path: str | None = None,
    image_url: str | None = None,
    model: str | None = None,
    duration: int = 6,
    resolution: str = "720p",
    aspect_ratio: str = "9:16",
    mode: str = "normal",
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    """
    Image-to-video via Kie (Grok Imagine / Kling / Seedance / Veo). Poll → download mp4.
    """
    if not available():
        return {"success": False, "error": "KIA_API_KEY not set"}

    model = (model or os.environ.get("STICKMAN_VIDEO_MODEL") or "grok-imagine/image-to-video").strip()

    src_url = image_url
    if not src_url and image_path and Path(image_path).is_file():
        up = upload_file(image_path, upload_path="stickman/frames")
        if up.get("success") and up.get("downloadUrl"):
            src_url = str(up["downloadUrl"])
        else:
            return {"success": False, "error": "frame_upload_failed", "detail": up.get("error") or up}

    inp = _video_input(
        model=model,
        image_url=src_url,
        prompt=prompt,
        duration=duration,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        mode=mode,
    )
    created = create_task_raw(model, inp)
    if not created.get("success"):
        return created

    task_id = str(created["taskId"])
    waited = wait_for_task(
        task_id,
        timeout_sec=timeout_sec or float(os.environ.get("KIE_VIDEO_TIMEOUT_SEC") or 600),
        poll_sec=float(os.environ.get("KIE_VIDEO_POLL_SEC") or 5),
    )
    if not waited.get("success"):
        waited["model"] = model
        waited["taskId"] = task_id
        return waited

    url = (waited.get("resultUrls") or [None])[0]
    if not url:
        return {"success": False, "error": "empty_resultUrls", "taskId": task_id}

    saved = download_url(url, dest)
    if not saved.get("success"):
        saved["taskId"] = task_id
        return saved

    return {
        "success": True,
        "path": str(dest),
        "model": model,
        "source": "kie",
        "taskId": task_id,
        "bytes": saved.get("bytes"),
        "resultUrl": url,
    }


# ─── Text-to-speech (ElevenLabs on Kie) ───────────────────────────────────────

DEFAULT_TTS_MODEL = "elevenlabs/text-to-speech-turbo-2-5"
DEFAULT_TTS_VOICE = "EkK5I93UQWFDigLMpZcX"  # James — husky, engaging


def generate_speech(
    text: str,
    dest: Path,
    *,
    model: str | None = None,
    voice: str | None = None,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    speed: float = 1.0,
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    """
    Text-to-speech via Kie ElevenLabs. Poll → download mp3.
    """
    if not available():
        return {"success": False, "error": "KIA_API_KEY not set"}
    if not (text or "").strip():
        return {"success": False, "error": "empty_text"}

    model = (model or os.environ.get("KIE_TTS_MODEL") or DEFAULT_TTS_MODEL).strip()
    voice = (voice or os.environ.get("KIE_TTS_VOICE") or DEFAULT_TTS_VOICE).strip()

    inp = {
        "text": text[:5000],
        "voice": voice,
        "stability": stability,
        "similarity_boost": similarity_boost,
        "style": style,
        "speed": speed,
    }
    created = create_task_raw(model, inp)
    if not created.get("success"):
        return created

    task_id = str(created["taskId"])
    waited = wait_for_task(
        task_id,
        timeout_sec=timeout_sec or float(os.environ.get("KIE_TTS_TIMEOUT_SEC") or 180),
        poll_sec=float(os.environ.get("KIE_TTS_POLL_SEC") or 2.5),
    )
    if not waited.get("success"):
        waited["model"] = model
        waited["taskId"] = task_id
        return waited

    url = (waited.get("resultUrls") or [None])[0]
    if not url:
        return {"success": False, "error": "empty_resultUrls", "taskId": task_id}

    saved = download_url(url, dest)
    if not saved.get("success"):
        saved["taskId"] = task_id
        return saved

    return {
        "success": True,
        "path": str(dest),
        "model": model,
        "voice": voice,
        "source": "kie",
        "taskId": task_id,
        "bytes": saved.get("bytes"),
        "resultUrl": url,
    }
