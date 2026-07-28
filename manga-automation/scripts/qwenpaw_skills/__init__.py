"""
QwenPaw Skills for the AiToEarn content arbitrage pipeline.

Each Skill is a thin wrapper that calls existing pipeline scripts via subprocess.
Skills contain NO business logic — all logic stays in scripts/*.py.

Design rules:
  - Every skill has an async execute(args, agent_context) -> dict function
  - args: dict of parameters from the agent's natural language request
  - agent_context: dict with agent_id, workspace_path, memory handle
  - Returns: JSON-serializable dict with at minimum {"success": bool, ...}
  - Subprocess calls use timeouts appropriate to the operation
  - Errors are caught and returned as {"success": False, "error": str}
"""

import os
import sys

# Ensure scripts/ is on the import path so Skills can import pipeline modules.
_scripts_dir = os.path.dirname(os.path.dirname(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# Project root (parent of scripts/)
PROJECT_ROOT = os.path.dirname(_scripts_dir)

# Default subprocess timeout per skill type (seconds)
TIMEOUT_TREND = 300       # API calls to TikTok, Reddit, YouTube, Twitter
TIMEOUT_SOURCE = 120      # YouTube sourcing + duplicate checks
TIMEOUT_RENDER = 600      # Remotion video rendering
TIMEOUT_PUBLISH = 300     # AiToEarn MCP fanout + status polling
TIMEOUT_ENGAGE = 180      # Browser automation
TIMEOUT_REPORT = 60       # DB queries
TIMEOUT_FINANCE = 660     # Finance video generation (matches Hermes timeout)
TIMEOUT_SEEDANCE = 900    # Seedance async video generation + poll
