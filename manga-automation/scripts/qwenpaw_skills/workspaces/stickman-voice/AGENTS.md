# Stickman Voice

## Role
Clean narration with DeepSeek, synthesize TTS, trim silence.

## Skill
`stickman_voice`

## Providers
- `auto` (default): try direct ElevenLabs, fall back to **Kie ElevenLabs** on failure (e.g. no credits)
- `kie`: always use Kie ElevenLabs (`KIA_API_KEY`, `KIE_TTS_MODEL`, `KIE_TTS_VOICE`)
- `elevenlabs`: direct ElevenLabs only

## Rules
- Strip image/video prompts before TTS
- Set provider via `voice_provider` flag or `STICKMAN_VOICE_PROVIDER`
- Prefer ElevenLabs voice from `STICKMAN_VOICE_ID`; Kie uses `KIE_TTS_VOICE`
- Always optimize audio unless `optimize_audio: false`
