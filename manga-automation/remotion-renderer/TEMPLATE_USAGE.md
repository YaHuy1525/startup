# Video Template Usage Guide

## Overview

The render-video.ts script now supports loading video templates from the database to apply consistent styling, effects, and timing to manga videos.

## Features

1. **Load specific template by ID**: Apply a specific video template configuration
2. **Random template selection**: Randomly select a template for variety
3. **Template in props**: Specify template ID directly in the props JSON
4. **Automatic usage tracking**: Template usage counts are automatically incremented

## Usage Examples

### 1. Using a Specific Template (CLI)

```bash
npx tsx src/render-video.ts \
  --props ./props.json \
  --output ./out/video.mp4 \
  --template-id 2
```

### 2. Using Random Template (CLI)

```bash
npx tsx src/render-video.ts \
  --props ./props.json \
  --output ./out/video.mp4 \
  --random-template
```

### 3. Specifying Template in Props JSON

```json
{
  "panels": [
    { "imagePath": "/data/panels/panel1.jpg", "motionType": "zoom_center", "durationInFrames": 240 }
  ],
  "titleText": "One Piece",
  "chapterText": "Chapter 1100",
  "audioSrc": "/data/music/dramatic.mp3",
  "audioDuckingVolume": 0.4,
  "templateId": 1
}
```

### 4. Default Behavior (No Template)

If no template is specified, the script uses the default panel durations from the props:

```bash
npx tsx src/render-video.ts \
  --props ./props.json \
  --output ./out/video.mp4
```

## Template Priority

When multiple template sources are specified, the priority is:

1. `templateId` in props JSON (highest priority)
2. `--template-id` CLI flag
3. `--random-template` CLI flag
4. No template (use default settings)

## Template Configuration

Templates are stored in the `video_templates` database table with the following structure:

- **id**: Unique template identifier
- **name**: Human-readable template name (e.g., "Emotional Scene")
- **type**: Template type (emotional_scene, character_edit, recommendation, etc.)
- **panel_duration**: Seconds per panel (e.g., 4)
- **transition_type**: Type of transition (crossfade, slide, zoom, wipe)
- **transition_duration**: Duration of transitions in seconds (e.g., 0.5)
- **effects_config**: JSON configuration for effects:
  - `zoomIntensity`: Zoom level (1.0 = no zoom, 1.2 = 20% zoom)
  - `panDirection`: Pan direction (random, left-to-right, top-to-bottom)
  - `colorGrading`: Optional color grading preset
  - `overlayEffects`: Optional array of overlay effects

## Available Templates

The system comes with 5 pre-configured templates:

1. **Emotional Scene** (ID: 1)
   - Type: emotional_scene
   - Panel Duration: 5 seconds
   - Transition: crossfade (0.5s)
   - Effects: Subtle zoom (1.15x), random pan, desaturated colors

2. **Character Edit** (ID: 2)
   - Type: character_edit
   - Panel Duration: 3 seconds
   - Transition: slide (0.3s)
   - Effects: Strong zoom (1.3x), left-to-right pan, vignette

3. **Manga Recommendation** (ID: 3)
   - Type: recommendation
   - Panel Duration: 4 seconds
   - Transition: zoom (0.4s)
   - Effects: Moderate zoom (1.2x), top-to-bottom pan

4. **Panel Appreciation** (ID: 4)
   - Type: panel_appreciation
   - Panel Duration: 8 seconds
   - Transition: zoom (0.5s)
   - Effects: Strong zoom (1.4x), random pan

5. **Fast Paced Action** (ID: 5)
   - Type: character_edit
   - Panel Duration: 2 seconds
   - Transition: wipe (0.2s)
   - Effects: Moderate zoom (1.25x), random pan, motion blur

## Output

The script outputs JSON to stdout with the following structure:

```json
{
  "filePath": "/absolute/path/to/video.mp4",
  "durationSecs": 125.5,
  "fileSizeMb": 45.2,
  "template": {
    "id": 2,
    "name": "Character Edit",
    "type": "character_edit"
  }
}
```

If no template was used, the `template` field will be `null`.

## Environment Variables

The script requires the `DATABASE_URL` environment variable to connect to the PostgreSQL database:

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/manga_automation"
```

## Error Handling

- If a specified template ID is not found, the script logs a warning and continues with default settings
- If the database connection fails, template loading is skipped and default settings are used
- Database connection errors are logged to stderr but don't cause the render to fail

## Integration with Backend

When calling from the backend API, you can specify the template in the props:

```typescript
const props = {
  panels: [...],
  titleText: "One Piece",
  chapterText: "Chapter 1100",
  audioSrc: "/data/music/dramatic.mp3",
  templateId: 2  // Use Character Edit template
};

const result = await renderVideo(props, outputPath);
```

## Requirements Satisfied

This implementation satisfies the following requirements:

- **Requirement 5.1-5.5**: Support for different video templates (emotional scene, character edit, recommendation, etc.)
- **Requirement 5.6**: Random template selection when not specified
- **Requirement 5.7**: Template configurations stored in database for easy modification
