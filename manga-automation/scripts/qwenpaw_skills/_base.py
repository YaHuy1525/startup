"""
Shared utilities for QwenPaw Skills.

Provides the _run() helper that Skills use to call existing pipeline scripts
via subprocess with proper error handling, timeouts, and return formatting.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from . import PROJECT_ROOT


def _run(
    args: list[str],
    timeout: int = 120,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Run a pipeline script via subprocess and return parsed JSON.

    All Skills use this single entry point so we get consistent:
      - timeout handling
      - JSON parsing
      - error formatting
      - stdout/stderr capture

    Args:
        args: Command to run, e.g. ["uv", "run", "python", "scripts/aitoearn_pipeline.py", "--stage", "trend"]
        timeout: Max seconds before killing the subprocess
        cwd: Working directory (default: PROJECT_ROOT)
        env: Extra environment variables to merge with os.environ
    """
    cwd = cwd or PROJECT_ROOT
    merged_env = {**os.environ, **(env or {})}

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            env=merged_env,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"exit_code_{result.returncode}",
                "stderr": result.stderr[:2000],
                "stdout": result.stdout[:2000],
            }
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {
                "success": True,
                "output": result.stdout[:5000],
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"timeout_{timeout}s",
        }
    except FileNotFoundError as exc:
        return {
            "success": False,
            "error": f"command_not_found: {exc}",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc)[:2000],
        }
