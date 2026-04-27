#!/usr/bin/env python3
"""
Minimal DeerFlow HTTP client for hybrid integration.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

DEERFLOW_URL = os.environ.get("DEERFLOW_URL", "http://deerflow:2026").rstrip("/")
DEERFLOW_GATEWAY_URL = os.environ.get("DEERFLOW_GATEWAY_URL", f"{DEERFLOW_URL}/api").rstrip("/")
DEERFLOW_LANGGRAPH_URL = os.environ.get("DEERFLOW_LANGGRAPH_URL", f"{DEERFLOW_URL}/api/langgraph").rstrip("/")
DEERFLOW_MODEL_NAME = os.environ.get("DEERFLOW_MODEL_NAME", "").strip()


def _event_data(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return raw


def health() -> dict:
    models = requests.get(f"{DEERFLOW_GATEWAY_URL}/models", timeout=20)
    models.raise_for_status()
    return {"status": "ok", "models": models.json().get("models", [])}


def list_models() -> dict:
    response = requests.get(f"{DEERFLOW_GATEWAY_URL}/models", timeout=20)
    response.raise_for_status()
    return response.json()


def create_thread(metadata: dict | None = None) -> dict:
    response = requests.post(
        f"{DEERFLOW_LANGGRAPH_URL}/threads",
        json={"metadata": metadata or {}},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def run_prompt(
    prompt: str,
    thread_id: str | None = None,
    model_name: str | None = None,
    thinking_enabled: bool = True,
    is_plan_mode: bool = False,
    recursion_limit: int = 100,
) -> dict:
    thread = {"thread_id": thread_id} if thread_id else create_thread()
    payload = {
        "input": {
            "messages": [
                {"role": "user", "content": prompt},
            ]
        },
        "config": {
            "recursion_limit": recursion_limit,
            "configurable": {
                "thinking_enabled": bool(thinking_enabled),
                "is_plan_mode": bool(is_plan_mode),
            },
        },
        "stream_mode": ["values", "messages-tuple"],
    }
    if model_name or DEERFLOW_MODEL_NAME:
        payload["config"]["configurable"]["model_name"] = model_name or DEERFLOW_MODEL_NAME

    response = requests.post(
        f"{DEERFLOW_LANGGRAPH_URL}/threads/{thread['thread_id']}/runs/stream",
        json=payload,
        timeout=300,
        stream=True,
    )
    response.raise_for_status()

    final_messages: list[str] = []
    values_snapshot: dict[str, Any] | None = None
    current_event: str | None = None

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
            continue
        if not line.startswith("data:"):
            continue

        data = _event_data(line.split(":", 1)[1].strip())
        if current_event == "values" and isinstance(data, dict):
            values_snapshot = data
        elif current_event in ("messages", "messages-tuple") and isinstance(data, dict):
            content = data.get("content")
            if content:
                final_messages.append(str(content))

    final_text = "\n".join([m for m in final_messages if str(m).strip()]).strip()
    if not final_text and values_snapshot:
        messages = values_snapshot.get("messages", [])
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "assistant":
                final_text = str(message.get("content") or "").strip()
                if final_text:
                    break

    return {
        "thread_id": thread["thread_id"],
        "response": final_text,
        "snapshot": values_snapshot,
    }


def plan_campaign(goal: str) -> dict:
    prompt = (
        "You are planning content operations for a manga automation system. "
        "Return a concise plan for the following goal, including content ideas, "
        "research angle, risk checks, and execution order.\n\n"
        f"Goal: {goal}"
    )
    return run_prompt(prompt, is_plan_mode=True)


def recover_last_run(failure_context: str) -> dict:
    prompt = (
        "You are a recovery planner for an automation system. Analyze the failure context "
        "and propose a deterministic next-step recovery plan with checks, retries, and "
        "operator actions.\n\n"
        f"Failure context:\n{failure_context}"
    )
    return run_prompt(prompt, is_plan_mode=True)
