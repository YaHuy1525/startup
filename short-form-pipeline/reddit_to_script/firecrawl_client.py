"""Minimal Firecrawl v2 client used to scrape Reddit without the Reddit API.

Only the ``/v2/scrape`` endpoint is used. JSON mode (v2) embeds the schema
directly inside the ``formats`` array, e.g.::

    formats=[{"type": "json", "schema": {...}, "prompt": "..."}]
"""

from __future__ import annotations

from typing import Any

import requests

from . import config


class FirecrawlError(RuntimeError):
    """Raised when a Firecrawl request fails."""


def _post_scrape(payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    api_key = config.require_firecrawl()
    url = f"{config.FIRECRAWL_BASE_URL}/v2/scrape"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:  # network-level failure
        raise FirecrawlError(f"Firecrawl request failed: {exc}") from exc

    if resp.status_code == 402:
        raise FirecrawlError("Firecrawl returned 402 Payment Required — out of credits.")
    if resp.status_code == 401:
        raise FirecrawlError("Firecrawl returned 401 Unauthorized — check FIRECRAWL_API_KEY.")
    if not resp.ok:
        raise FirecrawlError(f"Firecrawl {resp.status_code}: {resp.text[:500]}")

    body = resp.json()
    if not body.get("success", True):
        raise FirecrawlError(f"Firecrawl error: {body.get('error', body)}")
    return body.get("data", {})


def scrape_json(
    target_url: str,
    schema: dict[str, Any],
    prompt: str,
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    """Scrape ``target_url`` and return LLM-extracted structured data (5 credits)."""
    data = _post_scrape(
        {
            "url": target_url,
            "onlyMainContent": True,
            "formats": [{"type": "json", "schema": schema, "prompt": prompt}],
        },
        timeout,
    )
    return data.get("json", {})


def scrape_markdown(target_url: str, *, timeout: int = 120) -> str:
    """Scrape ``target_url`` and return clean markdown (1 credit)."""
    data = _post_scrape(
        {"url": target_url, "onlyMainContent": True, "formats": ["markdown"]},
        timeout,
    )
    return data.get("markdown", "")
