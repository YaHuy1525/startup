# AGENTIC DIRECTIVE — manga-remotion-renderer

> Remotion-based manga video renderer. Generates 1080x1920 vertical manga recap videos
> with Ken Burns effects, crossfade transitions, and audio.

## CODING ENVIRONMENT

- Node.js project, TypeScript + React (Remotion)
- Run `npm test` for tests, `npm run build` to bundle
- Remotion version: 4.0.477
- TailwindCSS available via `@remotion/tailwind`

## PROJECT STRUCTURE

```
src/
  index.ts          — registerRoot entry point
  Root.tsx           — Composition registry (add new compositions here)
  MangaRecap.tsx     — Main manga recap: pan sequence + crossfade + title + audio
  KenBurnsPanel.tsx  — Per-panel CSS transform animations (zoom/pan)
  TitleOverlay.tsx   — Fade-in/out title + chapter text
  BrainrotFeed.tsx   — Split-screen: panel top 60% + gameplay bottom 40%
  CharacterEdit.tsx  — Fast-cut character montage
  ChapterRecap.tsx   — Long-form recap with voiceover + progress bar
  render-video.ts    — CLI entry (called by mastra-agents server)
  render-video.test.ts — Property-based tests
```

## ARCHITECTURE CONVENTIONS

### Composition Pattern
1. Define a Zod schema for props in the composition file
2. Export the schema, type, and React component
3. Register in Root.tsx with `<Composition>` including `schema`, `defaultProps`, `calculateMetadata`
4. Video: 1080x1920 vertical, 30fps, minimum 60s (TikTok Creator Rewards)

### Animation Rules (CRITICAL)
- ALWAYS use `useCurrentFrame()` + `interpolate()` for animations
- NEVER use CSS transitions or CSS animations — they don't render
- NEVER use Tailwind animation classes (`animate-*`) — they don't render
- Use Tailwind ONLY for static styling (colors, layout, typography, spacing)
- Dynamic properties (opacity, transform, scale) MUST use inline `style` with `interpolate()` values

### Image Handling
- Panel images are passed as absolute paths or data URIs in props
- Use `<Img>` from remotion, NOT `<img>`
- Apply transforms via inline `style` prop
- `objectFit: "cover"` with `width/height: "100%"` for full-bleed panels

### Audio
- `<Audio>` from remotion for background music
- Volume ducking via function: `volume={(f) => { ... }}`
- Fade out in last 2 seconds using `durationInFrames` from `useVideoConfig()`

### Transitions
- Use `<TransitionSeries>` from `@remotion/transitions`
- crossfade: `import { fade } from "@remotion/transitions/fade"`
- Timing: `linearTiming({ durationInFrames: 15 })` — 0.5s at 30fps

## INTEGRATION WITH mastra-agents

- `render-video.ts` is called via `execSync` from mastra-agents server
- It reads props from a JSON file, renders via `npx remotion render`, outputs JSON to stdout
- Database connection: PostgreSQL via `pg` Pool, connection from `DATABASE_URL` env var
- Templates: `video_templates` table — loads by ID or random, applies to props
- DO NOT change the render-video.ts stdout format: `{ filePath, durationSecs, fileSizeMb, template }`

## COMPOSITIONS

| ID | Component | Purpose |
|----|-----------|---------|
| MangaRecap | MangaRecap.tsx | Panel sequence with crossfade + title + audio |
| BrainrotFeed | BrainrotFeed.tsx | Split-screen: panel top 60% + gameplay bottom 40% + voiceover |
| CharacterEdit | CharacterEdit.tsx | Fast-cut character montage with spring entrances |
| ChapterRecap | ChapterRecap.tsx | Long-form recap with voiceover, dialogue popups, progress bar |

## QUALITY GATES

- [ ] `npm run build` succeeds
- [ ] `npm test` passes
- [ ] No CSS transitions/animations (only interpolate)
- [ ] No Tailwind animation classes
- [ ] Zod schemas for all composition props
- [ ] 60s minimum video duration
