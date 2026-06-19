#!/usr/bin/env python3
"""Test Product Promo agent — props-only or full render via Mastra API."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("MASTRA_API_URL", "http://localhost:3001")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Product Promo Director agent")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Create a 60-second NVIDIA RTX promotion video for AI creators. "
        "Highlight GPU speed, real-time rendering, and studio-grade quality.",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Mastra API base URL")
    parser.add_argument("--no-render", action="store_true", help="Generate props only")
    parser.add_argument("--output", default="", help="Optional output filename")
    args = parser.parse_args()

    body: dict = {"prompt": args.prompt, "render": not args.no_render}
    if args.output:
        body["filename"] = args.output

    url = f"{args.url.rstrip('/')}/agents/product-promo"
    print(f"POST {url}")
    print(f"Prompt: {args.prompt[:100]}...")

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if result.get("filePath"):
        print(f"\nVideo: {result['filePath']}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
