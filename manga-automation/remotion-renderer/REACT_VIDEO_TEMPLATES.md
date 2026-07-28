# React video templates for agents

Agents use **`video_template_research`** to learn from the internet and pick the right React/Remotion stack before rendering.

## Quick commands

```bash
# Refresh from GitHub + remotion.dev
curl -sf -X POST "http://localhost:18080/video/templates/research" \
  -H "Content-Type: application/json" \
  -d '{"action":"refresh"}'

# Recommend templates for a brief
curl -sf -X POST "http://localhost:18080/video/templates/research" \
  -H "Content-Type: application/json" \
  -d '{"brief":"viral stickman TikTok explainer with kinetic captions"}'

# QwenPaw skill
curl -sf -X POST "http://localhost:18080/qwenpaw/skill/video_template_research" \
  -H "Content-Type: application/json" \
  -d '{"action":"recommend","brief":"SaaS product launch 60s vertical","composition_id":"ProductPromo"}'
```

## Ecosystem map (2026)

| Source | Type | Agent use |
|--------|------|-----------|
| [Remocn](https://remocn.dev) | shadcn registry | Product demos, blur-reveal, typewriter, wipes |
| [Remotion Bits](https://remotion-bits.dev) | npm + jsrepo + MCP | `npx remotion-bits find "text reveal"` |
| [Onda](https://onda.video) | 70 components | `npx ondajs add fade-in` |
| [Clippkit](https://clippkit.com) | scene blocks | Intros, split-screen |
| [Captions Themes](https://github.com/vshukla7/remotion-captions-themes) | kinetic captions | Shorts / stickman narration |
| [Remotion resources](https://www.remotion.dev/docs/resources) | official index | Audiogram, TTS, SwiftClip |

## Internal compositions

| ID | Best template stack |
|----|----------------------|
| `StickFigureStory` | captions themes + remotion-tts + internal stickman pipeline |
| `ProductPromo` | remocn + remotion-bits + light-leaks |
| `MangaRecap` | remotion-bits transitions |
| `BrainrotFeed` | captions themes + clippkit layouts |

## Registry file

`scripts/video_templates/registry.json` — updated by `action: refresh`.

Optional: set `GITHUB_TOKEN` in `.env` for higher GitHub API rate limits when refreshing.

## Agent

Register **video-template-director** via `python scripts/qwenpaw_skills/bootstrap_qwenpaw.py`.
