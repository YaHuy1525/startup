#!/usr/bin/env python3
"""HTTP client for QwenPaw Console API (chat, agents, status)."""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

CONSOLE_URL = os.environ.get("QWENPAW_CONSOLE_URL", "http://qwenpaw:8088").rstrip("/")
DEFAULT_AGENT = os.environ.get("QWENPAW_DEFAULT_AGENT", "pipeline-manager")
CHAT_TIMEOUT = int(os.environ.get("QWENPAW_CHAT_TIMEOUT", "600"))


def _agent_url(agent_id: str, path: str) -> str:
    return f"{CONSOLE_URL}/api/agents/{agent_id}{path}"


def list_agents() -> list[dict[str, Any]]:
    resp = requests.get(f"{CONSOLE_URL}/api/agents", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        return data.get("agents") or []
    return data if isinstance(data, list) else []


def health() -> dict[str, Any]:
    try:
        resp = requests.get(f"{CONSOLE_URL}/", timeout=10)
        return {"ok": resp.status_code == 200, "status_code": resp.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _parse_sse_events(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in raw.split("\n\n"):
        for line in block.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    return events


def _extract_assistant_text(events: list[dict[str, Any]]) -> str:
    for ev in reversed(events):
        if ev.get("object") == "message" and ev.get("status") == "completed":
            if ev.get("role") != "assistant":
                continue
            parts: list[str] = []
            for block in ev.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            text = "".join(parts).strip()
            if text:
                return text
    parts: list[str] = []
    for ev in events:
        if ev.get("object") == "content" and ev.get("delta") and ev.get("type") == "text":
            parts.append(str(ev.get("text") or ""))
    return "".join(parts).strip()


def _build_prompt(body: dict[str, Any]) -> str:
    prompt = str(body.get("prompt") or body.get("objective") or body.get("message") or "").strip()
    source_url = str(body.get("source_url") or body.get("video_url") or "").strip()
    if not source_url:
        match = re.search(r"https?://\S+", prompt)
        source_url = match.group(0).rstrip(".,)") if match else ""

    channels = body.get("channels") or []
    if isinstance(channels, str):
        channels = [channels]

    extras: list[str] = []
    if source_url:
        extras.append(f"Source URL: {source_url}")
    if channels:
        extras.append(f"Target platforms: {', '.join(channels)}")
    if body.get("title"):
        extras.append(f"Title: {body['title']}")
    if body.get("desc") or body.get("description"):
        extras.append(f"Description: {body.get('desc') or body.get('description')}")
    if body.get("selected_accounts"):
        extras.append(f"Selected accounts: {json.dumps(body['selected_accounts'])}")

    if extras:
        prompt = prompt + "\n\n" + "\n".join(extras)
    prompt += (
        "\n\nWhen you run pipeline skills, use execute_shell_command with curl to "
        f"{os.environ.get('PYTHON_WORKER_URL', 'http://python-worker:8080')}/qwenpaw/skill/<skill_name>. "
        "After publishing, summarize published_count, failed_count, and per-platform results."
    )
    return prompt.strip()


def chat(body: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(body.get("agent_id") or DEFAULT_AGENT)
    session_id = str(body.get("session_id") or "dashboard")
    user_id = str(body.get("user_id") or "dashboard")
    message = _build_prompt(body)

    payload = {
        "input": [{"role": "user", "content": [{"type": "text", "text": message}]}],
        "user_id": user_id,
        "session_id": session_id,
    }

    resp = requests.post(
        _agent_url(agent_id, "/console/chat"),
        json=payload,
        timeout=CHAT_TIMEOUT,
        stream=True,
    )
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        return {"success": False, "error": f"qwenpaw_http_{resp.status_code}", "detail": detail}

    raw = resp.text
    events = _parse_sse_events(raw)
    text = _extract_assistant_text(events)

    structured: dict[str, Any] | None = None
    for candidate in (text,):
        match = re.search(r"\{[\s\S]*\}", candidate)
        if not match:
            continue
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                structured = parsed
                break
        except json.JSONDecodeError:
            continue

    result: dict[str, Any] = {
        "success": True,
        "agent_id": agent_id,
        "session_id": session_id,
        "text": text,
        "events": events[-20:],
    }
    if structured:
        result.update(structured)
        if "published_count" in structured:
            result["published_count"] = structured.get("published_count")
        if "failed_count" in structured:
            result["failed_count"] = structured.get("failed_count")
    return result


def status() -> dict[str, Any]:
    agents = list_agents()
    aitoearn_ok = False
    try:
        from scripts.adapters import aitoearn_client
        aitoearn_ok = bool(aitoearn_client.startup_validation().get("ok"))
    except Exception:
        pass
    return {
        "success": True,
        "backend": "qwenpaw",
        "console_url": CONSOLE_URL,
        "health": health(),
        "agents": [{"id": a.get("id"), "name": a.get("name")} for a in agents],
        "agent_count": len(agents),
        "aitoearn_ok": aitoearn_ok,
    }
