# Stickman viral video workflow

Two paths:

1. **Flow (recommended)** — DeepSeek script + Remotion animate/edit (no Google Flow / Omni Flash)
2. **Legacy Canva** — ElevenLabs + storyboard hints + manual Canva assets + Remotion

## Flow style (Beckett AI / Rico look)

Output matches the [viral stickman AI tutorial](https://youtu.be/YTiroa9TlpI) end result:

- Pure **white** background, **black** stick figures (bold outlines)
- Full-bleed scenes with **slow cinematic zoom** (Omni Flash feel)
- Soft **crossfades** between scenes
- **Captions off** by default (voice-led narration)
- DeepSeek scripts biased to philosophical / motivational POV

Pass `"style": "paper"` + `"show_captions": true` for the older Canva-paper look.

### AI panel library

Scene stills are generated with OpenRouter (Gemini Flash Image by default), classified by action, and reused:

```bash
# List categorized library
curl -sf -X POST "http://localhost:18080/stickman/panels" -H "Content-Type: application/json" -d '{}'

# Generate + file under an action category
curl -sf -X POST "http://localhost:18080/stickman/panels" \
  -H "Content-Type: application/json" \
  -d '{"narration": "Nobody is thinking about them as much as they imagined", "force": true}'
```

Library path: `/data/videos/stickman-panel-library/<action>/*.png` + `registry.json`.

---

## Flow pipeline (DeepSeek + Remotion)

Maps the tutorial steps to agents:

| Step | Agent | Skill |
|------|-------|-------|
| 1 Character reference | `stickman-character-ref` | `stickman_character_ref` |
| 2 Topics + script | `stickman-scriptwriter` | `stickman_script` (DeepSeek) |
| 3 Scene stills | `stickman-scene-artist` | `stickman_scene_images` |
| 4 Animate | `stickman-animator` | `stickman_animate` (Remotion presets or Kie clips) |
| 5 Voiceover | `stickman-voice` | `stickman_voice` (direct or Kie ElevenLabs) |
| 6 Edit / sync | `stickman-editor` | `stickman_edit` |

Orchestrator: **`stickman-director`** via skill `stickman_flow`.

### AI Frame Sequencing Pipeline (Kie models)

One prompt → Kie assets → Remotion compiles. Two animation modes:

- **`remotion_motion`** (default): static Kie panels + cinematic Ken Burns motion.
- **`kie_clips`**: each panel is turned into a real moving clip via Kie image-to-video
  (Grok Imagine / Kling / Seedance / Veo). Remotion sequences the clips + voiceover.

All assets come from **one Kie key** (`KIA_API_KEY`):
image (Nano Banana 2) · video (image-to-video) · voice (ElevenLabs).

```bash
# One-prompt agentic video, fully animated with Kie clips + Kie voice
curl -sf -X POST "http://localhost:18080/stickman/flow" \
  -H "Content-Type: application/json" \
  -d '{
    "duration_secs": 30,
    "topic_hint": "why procrastination is actually useful",
    "auto_pick_topic": true,
    "animate_clips": true,
    "voice": true,
    "voice_provider": "kie",
    "render": true
  }'
```

Flags: `animate_clips` (bool), `video_model`, `clip_duration_secs`, `clip_resolution`,
`voice_provider` (`auto|kie|elevenlabs`). Kie video jobs poll for minutes per clip.

```bash
# Full autonomous run (auto-picks first topic; placeholders if no image API)
curl -sf -X POST "http://localhost:18080/stickman/flow" \
  -H "Content-Type: application/json" \
  -d '{
    "duration_secs": 60,
    "topic_hint": "why procrastination is actually useful",
    "auto_pick_topic": true,
    "render": true
  }'

# Human-in-the-loop: get 20 topics first
curl -sf -X POST "http://localhost:18080/stickman/flow" \
  -H "Content-Type: application/json" \
  -d '{"duration_secs": 60, "topic_hint": "AI side hustles", "auto_pick_topic": false}'

# Then continue with chosen topic
curl -sf -X POST "http://localhost:18080/stickman/flow" \
  -H "Content-Type: application/json" \
  -d '{
    "duration_secs": 60,
    "topic": "Your chosen topic",
    "auto_pick_topic": false,
    "character_ref_url": "https://example.com/stickman.png",
    "render": true
  }'
```

### Env

| Variable | Purpose |
|----------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek chat (topics, script, clean narration) |
| `DEEPSEEK_MODEL` | Default `deepseek-chat` |
| `KIA_API_KEY` / `KIE_API_KEY` | Kie.ai Bearer key (primary image API) |
| `STICKMAN_IMAGE_PROVIDER` | `auto` (Kie if key set) \| `kie` \| `openrouter` |
| `STICKMAN_IMAGE_MODEL` | Default `nano-banana-2` (Kie Nano Banana 2) |
| `STICKMAN_PANEL_QUALITY` | `premium` (nano-banana-2 → pro) or `fast` |
| `STICKMAN_IMAGE_RESOLUTION` | Kie: `1K` / `2K` / `4K` |
| `STICKMAN_PANEL_LIBRARY_DIR` | Action-categorized panel library |
| `OPEN_ROUTER` | Fallback image gen + DeepSeek chat fallback |
| `STICKMAN_ANIMATE_PROVIDER` | `none` (Ken Burns) \| `kie` (image-to-video clips) |
| `STICKMAN_VIDEO_MODEL` | Default `grok-imagine/image-to-video` |
| `STICKMAN_VIDEO_RESOLUTION` / `STICKMAN_VIDEO_CLIP_SECS` | Clip res / length |
| `STICKMAN_VOICE_PROVIDER` | `auto` \| `kie` \| `elevenlabs` |
| `KIE_TTS_MODEL` / `KIE_TTS_VOICE` | Kie ElevenLabs model + voice id |
| `STICKMAN_VOICE_ID` / `ELEVENLABS_*` | Direct TTS |
| `STICKMAN_ASSETS_DIR` | Job folders + scene PNGs |
| `STICKMAN_OUTPUT_DIR` | Rendered MP4s |

### Panel quality (premium vs basic)

Research-backed default for viral Rico-style shorts:

1. **API:** Kie.ai (`KIA_API_KEY`) → Nano Banana 2 / Pro; OpenRouter fallback if `STICKMAN_IMAGE_PROVIDER=auto`
2. **Model:** `nano-banana-2` → `nano-banana-pro`
3. **Prompts:** Rico style lock + cinematic `prompt_hint` per action (pose, framing, mood)
4. **Library:** Premium runs skip old basic panels; pass `"force": true` / `force_regenerate_panels: true` to refresh
5. **Motion:** Remotion intensity default `0.7` (stronger cinematic zoom/pan)

```bash
# Force one premium panel
curl -sf -X POST "http://localhost:18080/stickman/panels" \
  -H "Content-Type: application/json" \
  -d '{"narration":"alone in a crowd","force":true,"action":"crowd"}'
```

### Remotion motion presets

`video_prompt` → `{preset, intensity}` on each scene:

`zoom_in`, `zoom_out`, `bounce`, `slide_left`, `slide_right`, `idle_sway`, `pop_in`, `pan_up`

Composition: `StickFigureStory` in `remotion-renderer/src/StickFigureStory.tsx`.

### QwenPaw bootstrap

```bash
python scripts/qwenpaw_skills/bootstrap_qwenpaw.py
# or single agent:
python scripts/qwenpaw_skills/bootstrap_qwenpaw.py --agent stickman-director
```

### Files

| Path | Role |
|------|------|
| `scripts/stickman_flow_pipeline.py` | Flow orchestrator |
| `scripts/utils/deepseek_client.py` | DeepSeek / OpenRouter chat |
| `scripts/qwenpaw_skills/stickman_flow.py` | Orchestrator skill |
| `scripts/qwenpaw_skills/stickman_*.py` | Specialist skills |
| `remotion-renderer/src/StickFigureStory.tsx` | Remotion composition + motion |

---

## Legacy Canva path

Reference tutorial: [YouTube — viral stickman animation in Canva](https://youtu.be/b2k4xoXv3S4)

```bash
curl -sf -X POST "http://localhost:18080/stickman/workflow" \
  -H "Content-Type: application/json" \
  -d @scripts/test_stickman_request.json
```

After exporting stick-figure PNGs to `data/stickman-assets/` (`scene-01.png`, …):

```bash
curl -sf -X POST "http://localhost:18080/stickman/workflow" \
  -H "Content-Type: application/json" \
  -d '{
    "script": "Your script here...",
    "render": true,
    "assets_dir": "/data/stickman-assets",
    "filename": "stickman-demo.mp4"
  }'
```

Skill: `stickman_video` (Canva hints + optional Remotion render).
