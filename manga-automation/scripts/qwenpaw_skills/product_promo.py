"""
Skill: Product Promo Render
Triggers: "product promo", "brand video", "promotional video", "SaaS trailer", "NVIDIA promo"
Description: Uses the Product Promo Director agent to plan and render a Remotion
             ProductPromo composition with remotion-bits, remocn, and light-leaks.
Wraps: POST /agents/product-promo on manga-agents (Mastra)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from . import TIMEOUT_RENDER


async def execute(args: dict[str, Any], agent_context: dict[str, Any]) -> dict[str, Any]:
    prompt = str(args.get("prompt") or args.get("message") or "").strip()
    if not prompt:
        return {"success": False, "error": "prompt is required"}

    mastra_url = os.environ.get("MASTRA_API_URL", "http://manga-agents:3001").rstrip("/")
    render = args.get("render", True)
    filename = args.get("filename")

    body: dict[str, Any] = {"prompt": prompt, "render": bool(render)}
    if filename:
        body["filename"] = filename

    req = urllib.request.Request(
        f"{mastra_url}/agents/product-promo",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_RENDER) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"success": False, "error": detail or str(exc), "status": exc.code}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    return {
        "success": result.get("success", True),
        "composition": result.get("composition"),
        "props": result.get("props"),
        "filePath": result.get("filePath"),
        "durationSecs": result.get("durationSecs"),
        "fileSizeMb": result.get("fileSizeMb"),
        "agent_id": agent_context.get("agent_id", "product-promo-director"),
    }
