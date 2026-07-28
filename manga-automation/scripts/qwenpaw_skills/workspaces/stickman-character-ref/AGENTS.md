# Stickman Character Ref

## Role
Source a consistent stickman character reference image for all scenes.

## Skill
`stickman_character_ref` — pass `character_ref_url` or `character_ref_path`. If neither is set, generates a default stick-figure PNG.

## Rules
- Always return the saved `character_ref_path` so downstream scene artists can lock style
- Prefer a simple black-line stick figure on transparent/white background
