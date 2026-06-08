#!/usr/bin/env python3
"""
Media hosting helper.

AiToEarn/platform APIs need stable, publicly reachable media URLs.
This module accepts either:
- a local file path (preferred), then uploads it to one of several hosts
- an existing public URL, then validates whether it is stable enough to use
"""
import mimetypes
import os
import time
from urllib.parse import urlparse

import requests

from scripts.utils.logger import setup_logger

logger = setup_logger("media_host")

DEFAULT_BUCKET = (os.environ.get("SUPABASE_MEDIA_BUCKET") or "media").strip() or "media"
UPLOAD_TIMEOUT_SEC = int(os.environ.get("MEDIA_UPLOAD_TIMEOUT_SEC", "240"))
UPLOAD_USER_AGENT = "manga-automation-media-host/1.0"
STABLE_FALLBACK_ORDER = [
    p.strip().lower()
    for p in (os.environ.get("MEDIA_HOST_PROVIDERS") or "supabase,tmpfiles,0x0,transfer").split(",")
    if p.strip()
]


def _supabase_config() -> tuple[str, str]:
    base = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or ""
    ).strip()
    return base, key


def is_configured() -> bool:
    base, key = _supabase_config()
    return bool(base and key)


def is_public_http_url(value: str) -> bool:
    if not value:
        return False
    v = str(value).strip()
    if not (v.startswith("http://") or v.startswith("https://")):
        return False
    try:
        host = (urlparse(v).hostname or "").strip().lower()
        return bool(host and "." in host and host != "localhost")
    except Exception:
        return False


def is_stable_public_url(value: str) -> bool:
    """
    Heuristic guard for URLs that often expire quickly (e.g. googlevideo links).
    """
    if not is_public_http_url(value):
        return False
    v = str(value).strip()
    lower = v.lower()
    host = (urlparse(v).hostname or "").lower()

    if "googlevideo.com" in host:
        return False
    if "videoplayback" in lower and "youtube" in lower:
        return False
    if any(token in lower for token in ("expire=", "sig=", "signature=", "ip=", "ei=")):
        return False
    return True


def ensure_public_url(
    local_path: str,
    *,
    bucket: str | None = None,
    fallback_public_url: str | None = None,
) -> dict:
    """
    Ensure a stable public URL exists for a media input.

    Returns:
        {"ok": True, "public_url": "https://...", "uploaded": bool, "provider": "..."}
        {"ok": False, "error": "...", "attempts": [...]}
    """
    if not local_path:
        return {"ok": False, "error": "local_path is required"}

    raw = str(local_path).strip()
    fallback = str(fallback_public_url or "").strip()

    # Already remote URL path: accept only if stable.
    if is_public_http_url(raw):
        if is_stable_public_url(raw):
            return {"ok": True, "public_url": raw, "uploaded": False, "provider": "passthrough"}
        if fallback and is_stable_public_url(fallback):
            return {"ok": True, "public_url": fallback, "uploaded": False, "provider": "fallback_url"}
        return {
            "ok": False,
            "error": f"unstable_public_url: {raw}",
        }

    if not os.path.exists(raw):
        if fallback and is_stable_public_url(fallback):
            return {"ok": True, "public_url": fallback, "uploaded": False, "provider": "fallback_url"}
        return {"ok": False, "error": f"file not found: {raw}"}

    filename = os.path.basename(raw)
    bucket = bucket or DEFAULT_BUCKET
    attempts: list[dict] = []

    providers = STABLE_FALLBACK_ORDER or ["supabase", "tmpfiles", "0x0", "transfer"]
    for provider in providers:
        try:
            if provider == "supabase":
                result = _upload_supabase(raw, bucket=bucket)
            elif provider == "tmpfiles":
                result = _upload_tmpfiles(raw)
            elif provider in {"0x0", "0x0.st"}:
                result = _upload_0x0(raw)
            elif provider in {"transfer", "transfer.sh"}:
                result = _upload_transfer(raw)
            else:
                continue
        except Exception as exc:  # pragma: no cover - extra safety
            result = {"ok": False, "error": f"{provider}_exception: {exc}"}

        if result.get("ok"):
            public_url = str(result.get("public_url") or "").strip()
            if is_stable_public_url(public_url):
                logger.info(f"Hosted {filename} via {provider}: {public_url}")
                return {
                    "ok": True,
                    "public_url": public_url,
                    "uploaded": True,
                    "provider": provider,
                }
            attempts.append(
                {
                    "provider": provider,
                    "ok": False,
                    "error": f"provider_returned_unstable_url:{public_url}",
                }
            )
            continue

        attempts.append(
            {
                "provider": provider,
                "ok": False,
                "error": result.get("error") or "upload_failed",
            }
        )

    if fallback and is_stable_public_url(fallback):
        return {"ok": True, "public_url": fallback, "uploaded": False, "provider": "fallback_url"}

    error_msgs = "; ".join(
        f"{a.get('provider')}: {a.get('error')}" for a in attempts if a.get("error")
    )[:1200]
    return {
        "ok": False,
        "error": f"all_media_hosts_failed ({error_msgs or 'no_provider_succeeded'})",
        "attempts": attempts,
    }


def _upload_supabase(local_path: str, *, bucket: str) -> dict:
    base, key = _supabase_config()
    if not base or not key:
        return {
            "ok": False,
            "error": "supabase_not_configured",
        }

    filename = os.path.basename(local_path)
    object_key = f"clips/{int(time.time())}_{filename}"
    content_type = mimetypes.guess_type(local_path)[0] or "video/mp4"
    upload_url = f"{base}/storage/v1/object/{bucket}/{object_key}"
    public_url = f"{base}/storage/v1/object/public/{bucket}/{object_key}"

    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": content_type,
        "x-upsert": "true",
        "User-Agent": UPLOAD_USER_AGENT,
    }

    try:
        with open(local_path, "rb") as fh:
            resp = requests.post(
                upload_url,
                data=fh,
                headers=headers,
                timeout=UPLOAD_TIMEOUT_SEC,
            )
        if resp.status_code in (200, 201):
            return {"ok": True, "public_url": public_url}

        if resp.status_code == 400 and "Bucket not found" in resp.text:
            created = _create_bucket(base, key, bucket)
            if created:
                with open(local_path, "rb") as fh:
                    retry = requests.post(
                        upload_url,
                        data=fh,
                        headers=headers,
                        timeout=UPLOAD_TIMEOUT_SEC,
                    )
                if retry.status_code in (200, 201):
                    return {"ok": True, "public_url": public_url}
                return {
                    "ok": False,
                    "error": f"supabase_upload_failed_after_bucket_create:{retry.status_code}:{retry.text[:300]}",
                }

        return {"ok": False, "error": f"supabase_upload_failed:{resp.status_code}:{resp.text[:300]}"}
    except Exception as exc:
        logger.error(f"Supabase upload error: {exc}")
        return {"ok": False, "error": f"supabase_exception:{exc}"}


def _upload_tmpfiles(local_path: str) -> dict:
    """
    tmpfiles.org JSON API returns e.g. {"data":{"url":"https://tmpfiles.org/123/file.mp4"}}.
    Convert to direct file URL by inserting /dl/.
    """
    try:
        with open(local_path, "rb") as fh:
            resp = requests.post(
                "https://tmpfiles.org/api/v1/upload",
                files={"file": (os.path.basename(local_path), fh, "application/octet-stream")},
                headers={"User-Agent": UPLOAD_USER_AGENT},
                timeout=UPLOAD_TIMEOUT_SEC,
            )
        if resp.status_code >= 400:
            return {"ok": False, "error": f"tmpfiles_http_{resp.status_code}:{resp.text[:250]}"}
        data = resp.json()
        raw_url = ((data.get("data") or {}).get("url") or "").strip()
        if not raw_url:
            return {"ok": False, "error": f"tmpfiles_missing_url:{str(data)[:250]}"}
        direct = raw_url.replace("https://tmpfiles.org/", "https://tmpfiles.org/dl/")
        return {"ok": True, "public_url": direct}
    except Exception as exc:
        return {"ok": False, "error": f"tmpfiles_exception:{exc}"}


def _upload_0x0(local_path: str) -> dict:
    try:
        with open(local_path, "rb") as fh:
            resp = requests.post(
                "https://0x0.st",
                files={"file": (os.path.basename(local_path), fh, "application/octet-stream")},
                headers={"User-Agent": UPLOAD_USER_AGENT},
                timeout=UPLOAD_TIMEOUT_SEC,
            )
        if resp.status_code >= 400:
            return {"ok": False, "error": f"0x0_http_{resp.status_code}:{resp.text[:250]}"}
        raw = (resp.text or "").strip()
        if not raw.startswith("http"):
            return {"ok": False, "error": f"0x0_invalid_response:{raw[:250]}"}
        return {"ok": True, "public_url": raw}
    except Exception as exc:
        return {"ok": False, "error": f"0x0_exception:{exc}"}


def _upload_transfer(local_path: str) -> dict:
    safe_name = os.path.basename(local_path) or f"clip_{int(time.time())}.mp4"
    url = f"https://transfer.sh/{safe_name}"
    try:
        with open(local_path, "rb") as fh:
            resp = requests.put(
                url,
                data=fh,
                headers={"Max-Days": "7", "User-Agent": UPLOAD_USER_AGENT},
                timeout=UPLOAD_TIMEOUT_SEC,
            )
        if resp.status_code >= 400:
            return {"ok": False, "error": f"transfer_http_{resp.status_code}:{resp.text[:250]}"}
        raw = (resp.text or "").strip()
        if not raw.startswith("http"):
            return {"ok": False, "error": f"transfer_invalid_response:{raw[:250]}"}
        return {"ok": True, "public_url": raw}
    except Exception as exc:
        return {"ok": False, "error": f"transfer_exception:{exc}"}


def _create_bucket(base: str, key: str, bucket: str) -> bool:
    try:
        resp = requests.post(
            f"{base}/storage/v1/bucket",
            json={"id": bucket, "name": bucket, "public": True},
            headers={
                "Authorization": f"Bearer {key}",
                "apikey": key,
                "Content-Type": "application/json",
                "User-Agent": UPLOAD_USER_AGENT,
            },
            timeout=30,
        )
        ok = resp.status_code in (200, 201)
        if ok:
            logger.info(f"Created public Supabase bucket '{bucket}'")
        else:
            logger.warning(f"Bucket create failed: {resp.status_code} {resp.text[:200]}")
        return ok
    except Exception as exc:
        logger.warning(f"Bucket create error: {exc}")
        return False
