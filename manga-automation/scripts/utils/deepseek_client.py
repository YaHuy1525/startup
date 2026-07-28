#!/usr/bin/env python3
"""
DeepSeek chat client (OpenAI-compatible).

Uses DEEPSEEK_API_KEY against https://api.deepseek.com/v1 by default.
Falls back to OPEN_ROUTER / OPENROUTER_API_KEY with model deepseek/deepseek-chat.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from scripts.utils.logger import setup_logger

logger = setup_logger("deepseek_client")

DEFAULT_BASE = "https://api.deepseek.com/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek-chat"
OPENROUTER_MODEL = "deepseek/deepseek-chat"


def _config() -> dict[str, str]:
    deepseek_key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if deepseek_key:
        return {
            "api_key": deepseek_key,
            "base_url": (os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE).rstrip("/"),
            "model": os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
            "provider": "deepseek",
        }

    openrouter_key = (
        os.environ.get("OPEN_ROUTER") or os.environ.get("OPENROUTER_API_KEY") or ""
    ).strip()
    if openrouter_key:
        return {
            "api_key": openrouter_key,
            "base_url": OPENROUTER_BASE,
            "model": os.environ.get("DEEPSEEK_OPENROUTER_MODEL", OPENROUTER_MODEL),
            "provider": "openrouter",
        }

    return {}


def is_available() -> bool:
    return bool(_config().get("api_key"))


def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    response_format: dict[str, Any] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """
    Call DeepSeek (or OpenRouter DeepSeek) chat completions.

    Returns {"success": True, "content": str, "raw": dict, "provider": str, "model": str}
    or {"success": False, "error": str}.
    """
    cfg = _config()
    if not cfg.get("api_key"):
        return {
            "success": False,
            "error": "DEEPSEEK_API_KEY (or OPEN_ROUTER) not set",
        }

    selected_model = model or cfg["model"]
    url = f"{cfg['base_url']}/chat/completions"
    payload: dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    if cfg["provider"] == "openrouter":
        headers["HTTP-Referer"] = os.environ.get("OPENROUTER_REFERER", "https://localhost")
        headers["X-Title"] = os.environ.get("OPENROUTER_TITLE", "manga-automation-stickman")

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else data
            return {
                "success": False,
                "error": f"deepseek_http_{resp.status_code}",
                "detail": err or resp.text[:500],
                "provider": cfg["provider"],
                "model": selected_model,
            }

        choices = data.get("choices") or []
        if not choices:
            return {"success": False, "error": "empty_choices", "raw": data}

        content = choices[0].get("message", {}).get("content") or ""
        return {
            "success": True,
            "content": content,
            "raw": data,
            "provider": cfg["provider"],
            "model": selected_model,
        }
    except Exception as exc:
        logger.exception("DeepSeek chat failed")
        return {"success": False, "error": str(exc)[:2000]}


def chat_json(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.5,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> dict[str, Any]:
    """
    Chat and parse the assistant content as JSON.

    Returns {"success": True, "data": Any, ...} or {"success": False, "error": ...}.
    """
    result = chat(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    if not result.get("success"):
        return result

    content = str(result.get("content") or "").strip()
    parsed = extract_json(content)
    if parsed is None:
        return {
            "success": False,
            "error": "json_parse_failed",
            "content": content[:4000],
            "provider": result.get("provider"),
            "model": result.get("model"),
        }

    return {
        "success": True,
        "data": parsed,
        "content": content,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "raw": result.get("raw"),
    }


def extract_json(text: str) -> Any | None:
    """Extract JSON object/array from raw or markdown-fenced LLM output."""
    raw = text.strip()
    if not raw:
        return None

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None
