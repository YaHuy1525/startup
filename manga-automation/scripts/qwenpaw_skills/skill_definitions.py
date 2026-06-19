"""SKILL.md definitions for manga-automation pipeline skills."""
from __future__ import annotations

import os

WORKER_URL = os.environ.get("PYTHON_WORKER_URL", "http://python-worker:8080").rstrip("/")

SKILLS: dict[str, dict[str, str]] = {
    "trend_discovery": {
        "description": (
            "Find trending topics across TikTok, Reddit, YouTube, and X/Twitter. "
            "Use when the user asks what's trending, trend discovery, or viral topics."
        ),
        "body": f"""# Trend Discovery

Run the trend stage on python-worker:

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/trend_discovery" \\
  -H "Content-Type: application/json" \\
  -d '{{"category": "", "count": 20}}'
```

Optional JSON fields: `category` (slug or empty for all), `count` (default 20).

Parse the JSON response and summarize top trends with platform and confidence.""",
    },
    "content_sourcing": {
        "description": (
            "Source and download YouTube videos for trending concepts. "
            "Use after trend discovery when harvesting content assets."
        ),
        "body": f"""# Content Sourcing

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/content_sourcing" \\
  -H "Content-Type: application/json" \\
  -d '{{"count": 5}}'
```

Optional: `youtube_channel_id`, `count` (default 5). Report assets queued and local paths.""",
    },
    "video_render": {
        "description": (
            "Render a Remotion video from queue panels or custom composition props. "
            "Supports MangaRecap, BrainrotFeed, CharacterEdit, and ChapterRecap."
        ),
        "body": f"""# Video Render

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/video_render" \\
  -H "Content-Type: application/json" \\
  -d '{{"chapter_id": 1, "composition_id": "MangaRecap"}}'
```

For custom compositions:

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/video_render" \\
  -H "Content-Type: application/json" \\
  -d '{{"composition_id":"BrainrotFeed","filename":"brainrot-demo.mp4","props":{{"panelImagePath":"...","subtitleText":"...","gameplayVideoPath":"...","panelDurationInFrames":240}}}}'
```

Accepted fields: `chapter_id`, `queue_id`, `template_id`, `random_template`,
`composition_id`, `filename`, `output_path`, and `props`.""",
    },
    "publish_content": {
        "description": (
            "Publish content via AiToEarn MCP to TikTok, YouTube, Instagram, and 9 other platforms. "
            "Use for upload, post, distribute, or publish requests."
        ),
        "body": f"""# Publish Content

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/publish_content" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "video_url": "https://example.com/video.mp4",
    "title": "Caption here",
    "desc": "Description",
    "channels": ["tiktok", "youtube"],
    "profile": "minimal"
  }}'
```

Required: `video_url` or `video_id`. Optional: `channels`, `hashtags`, `selected_accounts`, `account_ids`, `dry_run`.
Return published_count, failed_count, and per-platform results to the user.""",
    },
    "account_health": {
        "description": "Check TikTok account health, FYP ratio, and shadow-ban risk.",
        "body": f"""# Account Health

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/account_health" \\
  -H "Content-Type: application/json" \\
  -d '{{"threshold": 0.10}}'
```

Optional: `account` (username), `threshold` (default 0.10). Flag critical accounts.""",
    },
    "engagement_cycle": {
        "description": "Run automated engagement: likes, AI comments, follows, comment mining.",
        "body": f"""# Engagement Cycle

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/engagement_cycle" \\
  -H "Content-Type: application/json" \\
  -d '{{"platform": "tiktok", "mode": "light"}}'
```

Modes: light | medium | full.""",
    },
    "performance_report": {
        "description": "Pipeline performance stats, trend velocity, and recommendations.",
        "body": f"""# Performance Report

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/performance_report" \\
  -H "Content-Type: application/json" \\
  -d '{{}}'
```

Summarize views, revenue correlations, and top recommendations.""",
    },
    "content_plan": {
        "description": "Generate content briefs from trending topics.",
        "body": f"""# Content Plan

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/content_plan" \\
  -H "Content-Type: application/json" \\
  -d '{{"limit": 10}}'
```""",
    },
    "finance_pipeline": {
        "description": "Run earnings-proof finance video pipeline and publish via AiToEarn.",
        "body": f"""# Finance Pipeline

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/finance_pipeline" \\
  -H "Content-Type: application/json" \\
  -d '{{"profile": "minimal"}}'
```""",
    },
    "product_promo": {
        "description": (
            "Create product/brand promotion videos with Remotion ProductPromo composition. "
            "Uses remotion-bits, remocn, and light-leaks. Use for SaaS promos, tech ads, brand reels."
        ),
        "body": f"""# Product Promo

Calls the Product Promo Director on manga-agents (long-running render).

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/product_promo" \\
  -H "Content-Type: application/json" \\
  -d '{{"prompt": "60s NVIDIA RTX promo for AI video creators", "render": true}}'
```

Optional: `render` (default true), `filename`. Returns `filePath`, `durationSecs`, `props`.""",
    },
}


def skill_markdown(name: str) -> str:
    spec = SKILLS[name]
    return (
        f"---\n"
        f"name: {name}\n"
        f'description: "{spec["description"]}"\n'
        f"metadata:\n"
        f"  qwenpaw:\n"
        f'    emoji: "🎬"\n'
        f"---\n\n"
        f"{spec['body']}\n"
    )
