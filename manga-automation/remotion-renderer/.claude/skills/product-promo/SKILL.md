---
name: product-promo
description: Specialist agent for Remotion product promotion videos using remotion-bits, remocn, light-leaks, and ProductPromo composition.
metadata:
  tags: remotion, promo, product, remotion-bits, remocn, light-leaks
---

## When to use

Use when the user wants a **product**, **brand**, or **SaaS** promotion video — not manga recaps.

## Installed stack

| Tool | Install | Role |
|------|---------|------|
| remotion-bits | `npm install remotion-bits` | AnimatedText, particles, gradients |
| remocn | `npx shadcn add @remocn/<name>` | blur-reveal, typewriter, directional-wipe |
| @remotion/light-leaks | `npm i @remotion/light-leaks@4.0.477` | Scene transition overlays |
| remotion-ui | `npx remotion-ui init` | Title cards, lower thirds (optional) |

## Composition: ProductPromo

Registered in `src/Root.tsx`. Props schema in `src/ProductPromo.tsx`.

```bash
npx tsx src/render-video.ts --composition ProductPromo --props promo-props.json --output out/promo.mp4
```

## Agent API

```bash
curl -X POST http://localhost:3001/agents/product-promo \
  -H "Content-Type: application/json" \
  -d '{"prompt": "60s NVIDIA RTX promo for AI creators", "render": true}'
```

## QwenPaw skill

```bash
curl -X POST http://localhost:18080/qwenpaw/skill/product_promo \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Promo for a note-taking SaaS with purple brand"}'
```

## Animation rules (CRITICAL)

- Use `useCurrentFrame()` + `interpolate()` / `spring()` only
- NO CSS transitions, NO Tailwind `animate-*`
- Dynamic opacity/transform via inline `style`

## CLI discovery (remotion-bits)

```bash
npx remotion-bits find "text reveal" --limit 5
npx remotion-bits fetch bit-fade-in --json
```
