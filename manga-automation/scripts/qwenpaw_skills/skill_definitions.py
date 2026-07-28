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
            "Supports MangaRecap, BrainrotFeed, CharacterEdit, ChapterRecap, and StickFigureStory."
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
    "seedance_video": {
        "description": (
            "Generate short AI videos with AiToEarn Seedance models (4-15s). "
            "Supports reference images/video/audio. Optionally publish via AiToEarn MCP."
        ),
        "body": f"""# Seedance Video (AiToEarn Open Platform)

Uses `POST /api/ai/video/generations` and polls task status.

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/seedance_video" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "prompt": "Cinematic NVIDIA RTX GPU product shot, green accent lighting, 9:16",
    "model": "seedance-2-beta-1080p",
    "ratio": "9:16",
    "duration": 12,
    "publish": true,
    "title": "RTX for AI creators",
    "channels": ["tiktok", "youtube"]
  }}'
```

Or full workflow endpoint:

```bash
curl -sf -X POST "{WORKER_URL}/aitoearn/seedance/workflow" \\
  -H "Content-Type: application/json" \\
  -d @scripts/test_seedance_request.json
```

Optional: `images`, `videos`, `audios` (URLs or local paths), `group_id`, `wait` (default true), `task_id` + `status_only`.""",
    },
    "stickman_video": {
        "description": (
            "Viral stick-figure videos (Canva tutorial style). Voiceover, audio pacing, "
            "scene storyboard with @zidansasc hints, optional Remotion render."
        ),
        "body": f"""# Stickman Video

Based on [this stickman tutorial](https://youtu.be/b2k4xoXv3S4).

```bash
curl -sf -X POST "{WORKER_URL}/stickman/workflow" \\
  -H "Content-Type: application/json" \\
  -d @scripts/test_stickman_request.json
```

Or via QwenPaw skill:

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/stickman_video" \\
  -H "Content-Type: application/json" \\
  -d '{{"script": "Why developers procrastinate...", "plan": true, "render": false}}'
```

Set `render: true` after exporting stick-figure PNGs to `/data/stickman-assets/`.
Optional: `voice_id` (ElevenLabs Mark), `assets_dir`, `scenes`, `filename`.""",
    },
    "stickman_flow": {
        "description": (
            "Full stickman Flow orchestrator: DeepSeek topics/script + scene stills + "
            "Remotion motion presets + voiceover + StickFigureStory edit/sync."
        ),
        "body": f"""# Stickman Flow (DeepSeek + Remotion)

Automates the tutorial without Google Flow / Omni Flash.

```bash
curl -sf -X POST "{WORKER_URL}/stickman/flow" \\
  -H "Content-Type: application/json" \\
  -d '{{"duration_secs": 60, "topic_hint": "why procrastination is useful", "auto_pick_topic": true, "render": true}}'
```

Or skill: `stickman_flow` with same JSON fields.
Requires `DEEPSEEK_API_KEY` (or OPEN_ROUTER). Remotion animate/edit always available.""",
    },
    "stickman_character_ref": {
        "description": "Source/copy stickman character reference image for consistency across scenes.",
        "body": f"""# Stickman Character Ref

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/stickman_character_ref" \\
  -H "Content-Type: application/json" \\
  -d '{{"character_ref_url": "https://example.com/stickman.png"}}'
```

Or pass `character_ref_path`. If neither set, generates a default stick-figure PNG.""",
    },
    "stickman_script": {
        "description": "DeepSeek: 20 topic ideas + full script with narration/image_prompt/video_prompt per scene.",
        "body": f"""# Stickman Script (DeepSeek)

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/stickman_script" \\
  -H "Content-Type: application/json" \\
  -d '{{"duration_secs": 60, "topic_hint": "AI side hustles", "auto_pick_topic": false}}'
```

Returns 20 topics when `auto_pick_topic` is false. Re-submit with `topic` chosen.""",
    },
    "stickman_scene_images": {
        "description": "Generate per-scene stickman stills (OpenRouter image model or programmatic figures).",
        "body": f"""# Stickman Scene Images

Pass `scenes` (from stickman_script) and optional `character_ref_path` / `job_id`.

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/stickman_scene_images" \\
  -H "Content-Type: application/json" \\
  -d '{{"scenes": [{{"narration": "...", "image_prompt": "..."}}]}}'
```""",
    },
    "stickman_animate": {
        "description": "Map each scene video_prompt to Remotion motion presets (zoom, bounce, slide, sway).",
        "body": f"""# Stickman Animate (Remotion presets)

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/stickman_animate" \\
  -H "Content-Type: application/json" \\
  -d '{{"scenes": [{{"imagePath": "...", "video_prompt": "slow zoom in"}}]}}'
```

Presets: zoom_in, zoom_out, bounce, slide_left, slide_right, idle_sway, pop_in, pan_up.""",
    },
    "stickman_voice": {
        "description": "DeepSeek strips prompts to clean narration paragraphs, then ElevenLabs/Kokoro TTS.",
        "body": f"""# Stickman Voice

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/stickman_voice" \\
  -H "Content-Type: application/json" \\
  -d '{{"scenes": [{{"narration": "First line."}}, {{"narration": "Second line."}}]}}'
```""",
    },
    "stickman_edit": {
        "description": "Remotion StickFigureStory final sync: scenes + voiceover → MP4.",
        "body": f"""# Stickman Edit / Sync

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/stickman_edit" \\
  -H "Content-Type: application/json" \\
  -d '{{"scenes": [...], "voiceover_path": "/data/.../voiceover_optimized.mp3", "render": true}}'
```""",
    },
    "video_template_research": {
        "description": (
            "Discover React/Remotion video templates from the internet. Refresh GitHub metadata, "
            "harvest remotion.dev resources, recommend libraries for a brief."
        ),
        "body": f"""# Video Template Research

Learns from [Remotion resources](https://www.remotion.dev/docs/resources) + GitHub (remocn, remotion-bits, onda, clippkit).

**Refresh from internet:**
```bash
curl -sf -X POST "{WORKER_URL}/video/templates/research" \\
  -H "Content-Type: application/json" \\
  -d '{{"action": "refresh"}}'
```

**Recommend for a brief:**
```bash
curl -sf -X POST "{WORKER_URL}/video/templates/research" \\
  -H "Content-Type: application/json" \\
  -d '{{"brief": "kinetic TikTok stickman explainer", "composition_id": "StickFigureStory"}}'
```

**List catalog:**
```bash
curl -sf -X POST "{WORKER_URL}/video/templates/research" \\
  -H "Content-Type: application/json" \\
  -d '{{"action": "list"}}'
```

Registry: `scripts/video_templates/registry.json`""",
    },
    "shortform_pipeline": {
        "description": (
            "Full Reddit → meme short video → optional AiToEarn publish. "
            "Use for reddit stories, meme shorts, TIFU/AITA faceless videos."
        ),
        "body": f"""# Shortform Pipeline (Reddit → Meme → AiToEarn)

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_pipeline" \\
  -H "Content-Type: application/json" \\
  -d '{{"subreddit":"tifu","time":"week","count":1,"publish":false,"dry_run":false}}'
```

Or worker route:
```bash
curl -sf -X POST "{WORKER_URL}/shortform/pipeline" \\
  -H "Content-Type: application/json" \\
  -d '{{"stage":"pipeline","subreddit":"tifu","count":1,"publish":true}}'
```

Stages via `"stage"`: fetch | script | find_memes | voice | render | publish | status | pipeline.
Set `publish:true` only when ready to fan out via AiToEarn.""",
    },
    "shortform_story_fetch": {
        "description": "Fetch Reddit text stories via RSS for short-form meme videos.",
        "body": f"""# Shortform Story Fetch

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_story_fetch" \\
  -H "Content-Type: application/json" \\
  -d '{{"subreddit":"tifu","time":"week","limit":3}}'
```""",
    },
    "shortform_script": {
        "description": "LLM: Reddit story → meme-tuned scenes with reaction searchTerms.",
        "body": f"""# Shortform Script

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_script" \\
  -H "Content-Type: application/json" \\
  -d '{{"story":{{"title":"...","body":"...","url":"..."}},"style":"meme"}}'
```""",
    },
    "shortform_find_memes": {
        "description": "Agentic Giphy meme picker (LLM ranks candidates) with Pexels fallback.",
        "body": f"""# Shortform Find Memes

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_find_memes" \\
  -H "Content-Type: application/json" \\
  -d '{{"scenes":[{{"text":"...","searchTerms":["shocked face"]}}]}}'
```""",
    },
    "shortform_voice": {
        "description": "OpenAI human TTS + word-timed captions for short-form scenes.",
        "body": f"""# Shortform Voice

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_voice" \\
  -H "Content-Type: application/json" \\
  -d '{{"scenes":[{{"text":"Wait until you hear this..."}}]}}'
```""",
    },
    "shortform_render": {
        "description": "Render Remotion MemeStory MP4 from scenes (TTS + Giphy/Pexels).",
        "body": f"""# Shortform Render

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_render" \\
  -H "Content-Type: application/json" \\
  -d '{{"scenes":[{{"text":"...","searchTerms":["facepalm"]}}]}}'
```""",
    },
    "shortform_publish": {
        "description": "Host local meme MP4 and publish via AiToEarn MCP fanout.",
        "body": f"""# Shortform Publish (AiToEarn)

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_publish" \\
  -H "Content-Type: application/json" \\
  -d '{{"file":"D:/Code/startup/short-form-pipeline/out/meme-x.mp4","title":"...","channels":["tiktok","youtube"],"dry_run":false}}'
```""",
    },
    "shortform_monitor": {
        "description": "Monitor short-form pipeline: recent videos, env keys, AiToEarn accounts.",
        "body": f"""# Shortform Monitor

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_monitor" \\
  -H "Content-Type: application/json" \\
  -d '{{}}'
```""",
    },
    "shortform_anime_theory": {
        "description": (
            "Full anime-theory Shorts pipeline: topic → lore script → Safebooru "
            "stills → Remotion → caption agent → video-frame thumbnail → AiToEarn "
            "publish (TikTok/IG/FB). Pass render_only=true for MP4 only."
        ),
        "body": f"""# Shortform Anime Theory (full pipeline)

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_anime_theory" \\
  -H "Content-Type: application/json" \\
  -d '{{"topic":"How Yuta DESTROYED the Sendai Colony","anime":"Jujutsu Kaisen","publish":true}}'
```

Worker / Hermes:
```bash
curl -sf -X POST "{WORKER_URL}/shortform/anime-theory/pipeline" \\
  -H "Content-Type: application/json" \\
  -d '{{"topic":"...","anime":"Jujutsu Kaisen"}}'

curl -sf -X POST "{WORKER_URL}/hermes/anime-theory-pipeline" \\
  -H "Content-Type: application/json" \\
  -d '{{"topic":"...","anime":"Jujutsu Kaisen","dry_run":true}}'
```

Pipeline stage: `{{"stage":"anime_theory_pipeline","topic":"..."}}`.
Render only: `{{"render_only":true,"topic":"..."}}` or POST `/shortform/anime-theory`.
Optional: `context`, `long`, `reference_url`, `max_seconds`, `show_title`, `publish`, `channels`, `dry_run`.""",
    },
    "shortform_thumbnail": {
        "description": (
            "Propose YouTube Short thumbnail/poster concepts using Hermes-trained "
            "competitor poster style (separate from scriptwriting)."
        ),
        "body": f"""# Shortform Thumbnail

Owned by **shortform-thumbnail** agent (not the scriptwriter).

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_thumbnail" \\
  -H "Content-Type: application/json" \\
  -d '{{"topic":"Why Kenjaku chose Yuji","anime":"Jujutsu Kaisen","hook":"Kenjaku engineered Yuji"}}'
```

Or pipeline stage: `{{"stage":"thumbnail","topic":"..."}}`.
Train style: `python -m reddit_to_script.train_thumbnails --channel @animeinsider64`
Hermes: `POST /hermes/learn-thumbnail-style`.""",
    },
    "shortform_caption": {
        "description": (
            "Write viral title/caption/hashtags for anime-theory Shorts "
            "(shortform-captioner agent) before AiToEarn publish."
        ),
        "body": f"""# Shortform Caption

Owned by **shortform-captioner**.

```bash
curl -sf -X POST "{WORKER_URL}/qwenpaw/skill/shortform_caption" \\
  -H "Content-Type: application/json" \\
  -d '{{"title":"Why Yuta Will NEVER Surpass Gojo","anime":"Jujutsu Kaisen"}}'
```

Publish with auto caption + video-frame cover:
`{{"stage":"publish","file":"...mp4","auto_caption":true,"auto_thumbnail":true}}`.""",
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
