# Stickman Video Prompter

## Role
The **prompting brain** of the AI Frame Sequencing Pipeline. Turns a *story* or
premise into a shot list: what each frame shows and how it moves.

## Skill
`stickman_video_prompter`

## Output per scene
- `narration` — one spoken sentence (calm, honest, first-person)
- `image_prompt` — storyboard STILL: subject + pose + prop + framing + mood
- `video_prompt` — camera move + character motion + timing (restrained, cinematic)
- `action` — one reuse category (`crowd`, `mirror`, `phone`, `thinking`, `sitting`,
  `shouting`, `running`, `helping`, `journey`, …)

## Flow
1. Read the story/premise (`story`, `premise`, or `topic`)
2. Build an emotional arc: tension → avoidance → peak → turn → hope
3. Emit exactly `scene_count` scenes (sized to `duration_secs`)
4. Hand scenes to `stickman_flow` → Kie panels/clips → Remotion compile

## Rules
- Prefer slow, restrained, cinematic motion in `video_prompt`
- Keep narration short enough to speak in one clip (~6s)
- Always map each scene to a valid `action` for panel reuse
- DeepSeek-powered; falls back to a built-in storyboard if the LLM is down
