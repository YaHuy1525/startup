# Manga Automation — Technical Guide

> Reference for coding agents & developers maintaining the manga-to-video pipeline.

## Architecture Overview

```
n8n (cron)
  │
  ├─► TrendDetector Agent  → manga table
  ├─► /pipeline/fetch-chapters → download panels
  ├─► PanelSelector Agent (Claude Vision) → selected_panels
  ├─► /pipeline/render-video (Remotion) → videos
  ├─► CaptionGenerator Agent → caption + hashtags
  └─► upload_tiktok.py (Playwright) → TikTok
```

### Services

| Service | Port | Purpose |
|---|---|---|
| PostgreSQL 15 | 5434 | Primary database |
| Redis 7 | 6380 | API cache |
| manga-agents | 3001 | Mastra AI agents + Remotion renderer |
| python-worker | 8080 | Scraping, upload, analytics |
| n8n | 5679 | Workflow orchestrator |

---

## TikTok CRP Requirements (2026)

| Requirement | Value |
|---|---|
| Minimum duration | **60 seconds** |
| Originality | Must be original content (not re-upload) |
| Qualified views | From unique, real accounts in eligible regions |
| RPM range | $0.20–$1.00+ depending on retention |

**Our target: 10 panels × 8s = ~75s net after transitions.**

---

## Video Rendering (Remotion)

The renderer lives in `remotion-renderer/` and produces 1080×1920 vertical MP4s at 30fps.

### Pipeline

1. Server receives `POST /pipeline/render-video { chapterId }`
2. Queries `selected_panels` for panel paths + motion tags
3. Builds JSON props → spawns `render-video.ts`
4. Remotion renders via Chrome Headless Shell
5. Output MP4 inserted into `videos` table

### Components

| Component | Purpose |
|---|---|
| `MangaRecap.tsx` | Root composition: TransitionSeries + audio |
| `KenBurnsPanel.tsx` | CSS transform Ken Burns (no FFmpeg jitter) |
| `TitleOverlay.tsx` | Fade-in/hold/fade-out title card |

### Motion Types

| Type | Effect | Best for |
|---|---|---|
| `zoom_center` | Scale 1.0→1.25 | Character reveals, close-ups |
| `pan_right` | Horizontal drift | Action scenes, wide panels |
| `pan_up` | Vertical drift | Establishing shots, tall scenes |

---

## AI Agents

### Panel Selector

- Analyses up to 15 evenly-spaced panels via Claude Vision
- Selects top 10 by engagement score
- Outputs: `score`, `emotion`, `motionType`, `audioMood`
- Motion types inform Remotion rendering
- Audio mood informs music selection

### Caption Generator

Uses the **3-5 Rule** hashtag architecture:
1. Broad category: `#mangatok`
2. Targeted sub-niche: `#mangarecommendation`
3. Trending temporal: `#2026recap`
4-5. Hyper-specific: manga title + character names

**Anti-spam**: Never use `#fyp`, `#viral`, `#foryoupage`.

Caption must end with an engagement-trigger **question** for comment velocity.

---

## Key Files

| File | Purpose |
|---|---|
| `remotion-renderer/src/MangaRecap.tsx` | Video composition |
| `remotion-renderer/src/render-video.ts` | CLI render script |
| `mastra-agents/src/server.ts` | Express API + render endpoint |
| `mastra-agents/src/agents/panelSelector.ts` | Claude Vision panel scoring |
| `mastra-agents/src/agents/captionGenerator.ts` | Caption + hashtag generation |
| `scripts/generate_video.py` | Python entry point (calls Remotion or FFmpeg) |
| `n8n-workflows/02_video_generation.json` | Video gen workflow |
| `scripts-bash/generate_manga_video.sh` | **DEPRECATED** FFmpeg fallback |

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `VIDEOS_DIR` | `/data/videos` | Video output directory |
| `PANELS_DIR` | `/data/panels` | Panel image storage |
| `MANGA_AGENTS_URL` | `http://localhost:3001` | Agents server URL |
| `VIDEO_MIN_DURATION_SECONDS` | `60` | Minimum video duration |
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `DATABASE_URL` | — | PostgreSQL connection string |

---

## Deployment

```bash
# Build and start all services
docker compose up -d --build

# Verify health
curl http://localhost:3001/health
curl http://localhost:8080/health

# Test render endpoint
curl -X POST http://localhost:3001/pipeline/render-video \
  -H "Content-Type: application/json" \
  -d '{"chapterId": 1}'
```
