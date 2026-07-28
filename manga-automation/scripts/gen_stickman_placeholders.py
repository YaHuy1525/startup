#!/usr/bin/env python3
"""Generate simple stick-figure placeholder PNGs for stickman render tests."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("pip install pillow")

CAPTIONS = [
    "sit down to code",
    "need coffee",
    "check phone",
    "procrastinate",
]

OUT = Path(__file__).resolve().parents[1] / "data" / "panels" / "stickman-test"
OUT.mkdir(parents=True, exist_ok=True)


def draw_stickman(draw: ImageDraw.ImageDraw, cx: int, cy: int, color: str) -> None:
    r = 40
    draw.ellipse((cx - r, cy - 120 - r, cx + r, cy - 120 + r), outline=color, width=8)
    draw.line((cx, cy - 80, cx, cy + 40), fill=color, width=8)
    draw.line((cx - 70, cy - 40, cx + 70, cy - 40), fill=color, width=8)
    draw.line((cx, cy + 40, cx - 50, cy + 130), fill=color, width=8)
    draw.line((cx, cy + 40, cx + 50, cy + 130), fill=color, width=8)


def main() -> None:
    colors = ["#1a1a1a", "#2563eb", "#dc2626", "#16a34a"]
    for i, (caption, color) in enumerate(zip(CAPTIONS, colors), start=1):
        img = Image.new("RGBA", (900, 900), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw_stickman(draw, 450, 420, color)
        draw.text((280, 760), caption, fill=color)
        path = OUT / f"scene-{i:02d}.png"
        img.save(path)
        print(path)


if __name__ == "__main__":
    main()
