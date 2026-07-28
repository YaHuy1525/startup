"""Provider-swappable LLM chat client (OpenAI or Anthropic).

Exposes a single ``complete_json`` helper that sends a system+user prompt and
returns parsed JSON. Switch providers via the ``LLM_PROVIDER`` env var.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from . import config


class LLMError(RuntimeError):
    """Raised when the LLM request fails or returns unparseable output."""


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort parse of a JSON object from a model response."""
    text = text.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` fences.
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise LLMError(f"Model did not return valid JSON: {exc}") from exc
        raise LLMError("Model response contained no JSON object.")


def _complete_openai(system: str, user: str, timeout: int) -> str:
    api_key = config.require_llm_key()
    url = f"{config.OPENAI_BASE_URL}/chat/completions"
    payload = {
        "model": config.resolved_llm_model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if not resp.ok:
        raise LLMError(f"OpenAI {resp.status_code}: {resp.text[:500]}")
    return resp.json()["choices"][0]["message"]["content"]


def _complete_anthropic(system: str, user: str, timeout: int) -> str:
    api_key = config.require_llm_key()
    url = f"{config.ANTHROPIC_BASE_URL}/v1/messages"
    payload = {
        "model": config.resolved_llm_model(),
        "max_tokens": 2000,
        "temperature": 0.8,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if not resp.ok:
        raise LLMError(f"Anthropic {resp.status_code}: {resp.text[:500]}")
    return resp.json()["content"][0]["text"]


def complete_json(system: str, user: str, *, timeout: int = 120) -> dict[str, Any]:
    """Send system+user prompts and return the parsed JSON object."""
    if config.LLM_PROVIDER == "openai":
        raw = _complete_openai(system, user, timeout)
    elif config.LLM_PROVIDER == "anthropic":
        raw = _complete_anthropic(system, user, timeout)
    else:
        raise LLMError(f"Unsupported LLM_PROVIDER: {config.LLM_PROVIDER!r}")
    return _extract_json(raw)
