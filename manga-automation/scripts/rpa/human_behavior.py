"""Human-like pacing for browser automation (reduces trivial bot flags)."""
from __future__ import annotations

import os
import random
import time

_MIN = float(os.environ.get("RPA_DELAY_MIN_SEC", "0.8"))
_MAX = float(os.environ.get("RPA_DELAY_MAX_SEC", "3.5"))


def sleep_jitter(_reason: str | None = None) -> float:
    """Sleep a random interval; returns seconds slept."""
    lo, hi = min(_MIN, _MAX), max(_MIN, _MAX)
    sec = random.uniform(lo, hi)
    time.sleep(sec)
    return sec


def sleep_between_actions() -> float:
    return sleep_jitter()
