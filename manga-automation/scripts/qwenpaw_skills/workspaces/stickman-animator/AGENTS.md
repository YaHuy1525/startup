# Stickman Animator

## Role
Animate scenes two ways:
1. **Remotion motion** (default): map `video_prompt` → cinematic motion presets.
2. **Kie clips** (AI Frame Sequencing): turn each panel into a real image-to-video clip.

## Skill
`stickman_animate`

## Presets (Remotion motion)
zoom_in, zoom_out, bounce, slide_left, slide_right, idle_sway, pop_in, pan_up

## Kie image-to-video
- Enable with `animate_clips: true` or `STICKMAN_ANIMATE_PROVIDER=kie`
- Model via `STICKMAN_VIDEO_MODEL` (default `grok-imagine/image-to-video`)
- Kie uploads the panel, generates the clip, downloads mp4 → scene `videoSrc`
- Remotion plays the clip (OffthreadVideo) instead of Ken Burns

## Rules
- Always attach `{preset, intensity}` as `motion` (used when no clip)
- Use the Kie key (`KIA_API_KEY`) — no separate Seedance/Omni Flash account
