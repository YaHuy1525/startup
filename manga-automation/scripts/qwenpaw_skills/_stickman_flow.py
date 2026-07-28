"""
Shared helper for stickman flow specialist skills.
"""
from __future__ import annotations

import json
from typing import Any

from . import TIMEOUT_RENDER
from ._base import _run


def run_flow_body(body: dict[str, Any], timeout: int = TIMEOUT_RENDER) -> dict[str, Any]:
    extra_env = {"STICKMAN_FLOW_REQUEST_JSON": json.dumps(body)}
    cmd = [
        "uv",
        "run",
        "python",
        "-c",
        (
            "import json, os; "
            "from scripts.stickman_flow_pipeline import run_stickman_flow; "
            "body=json.loads(os.environ['STICKMAN_FLOW_REQUEST_JSON']); "
            "print(json.dumps(run_stickman_flow(body), ensure_ascii=False, default=str))"
        ),
    ]
    result = _run(cmd, timeout=timeout, env=extra_env)
    if isinstance(result, dict) and result.get("success") is False and "pipeline" not in result:
        return result
    payload = result if isinstance(result, dict) and result.get("pipeline") else result.get("result", result)
    if not isinstance(payload, dict):
        return {"success": False, "error": "invalid_stickman_flow_response", "raw": result}
    return payload
