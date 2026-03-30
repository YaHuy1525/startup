# Task 5.3: Video Template Support - Implementation Summary

## Overview
Updated render-video.ts to support loading video templates from the database, applying template-specific effects and transitions, and supporting random template selection.

## Changes Made

### 1. render-video.ts
**File**: `manga-automation/remotion-renderer/src/render-video.ts`

**New Features**:
- Added database connection using `pg` Pool
- Implemented `loadTemplate(templateId)` function to load specific templates
- Implemented `loadRandomTemplate()` function for random template selection
- Implemented `updateTemplateUsageCount(templateId)` to track template usage
- Implemented `applyTemplateToProps()` to apply template settings to video props
- Added CLI flags: `--template-id <id>` and `--random-template`
- Added support for `templateId` in props JSON
- Enhanced output JSON to include template information

**Template Priority**:
1. `templateId` in props JSON (highest)
2. `--template-id` CLI flag
3. `--random-template` CLI flag
4. No template (default settings)

**Database Integration**:
- Connects to PostgreSQL using DATABASE_URL environment variable
- Queries `video_templates` table for template configurations
- Updates `usage_count` when templates are used
- Graceful fallback to default settings if database unavailable

### 2. package.json
**File**: `manga-automation/remotion-renderer/package.json`

**Dependencies Added**:
- `pg`: ^8.11.3 (PostgreSQL client)
- `@types/pg`: ^8.11.0 (TypeScript types)

### 3. server.ts
**File**: `manga-automation/mastra-agents/src/server.ts`

**API Endpoint Updates**:
- Updated POST `/pipeline/render-video` to accept optional parameters:
  - `templateId`: number (optional) - Specific template ID to use
  - `randomTemplate`: boolean (optional) - Use random template selection
- Enhanced response to include template information
- Updated render command to pass template flags to render-video.ts

**Request Body**:
```json
{
  "chapterId": 123,
  "templateId": 2,           // Optional
  "randomTemplate": false    // Optional
}
```

**Response**:
```json
{
  "success": true,
  "videoId": 456,
  "filePath": "/path/to/video.mp4",
  "durationSecs": 125.5,
  "fileSizeMb": 45.2,
  "template": {
    "id": 2,
    "name": "Character Edit",
    "type": "character_edit"
  }
}
```

## Requirements Satisfied

✅ **Requirement 5.1-5.5**: Support for different video templates
- Emotional scene compilation template
- Character edit template
- Manga recommendation template
- Top list template (via database)
- Panel appreciation template

✅ **Requirement 5.6**: Random template selection
- Implemented `--random-template` flag
- Random selection via SQL `ORDER BY RANDOM()`

✅ **Requirement 5.7**: Template configurations stored in database
- Templates loaded from `video_templates` table
- Easy modification without code changes
- Usage tracking for analytics

## Usage Examples

### CLI Usage

```bash
# Use specific template
npx tsx src/render-video.ts --props ./props.json --template-id 2

# Use random template
npx tsx src/render-video.ts --props ./props.json --random-template

# Template in props JSON
npx tsx src/render-video.ts --props ./props.json
# where props.json contains: { "templateId": 1, ... }
```

### API Usage

```bash
# Use specific template
curl -X POST http://localhost:3000/pipeline/render-video \
  -H "Content-Type: application/json" \
  -d '{"chapterId": 123, "templateId": 2}'

# Use random template
curl -X POST http://localhost:3000/pipeline/render-video \
  -H "Content-Type: application/json" \
  -d '{"chapterId": 123, "randomTemplate": true}'
```

## Installation

Before using the new template features, install dependencies:

```bash
cd manga-automation/remotion-renderer
npm install
```

## Environment Variables

Ensure `DATABASE_URL` is set:

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/manga_automation"
```

## Testing

The implementation includes:
- Error handling for missing templates
- Graceful fallback to default settings
- Database connection error handling
- Template usage tracking
- Proper cleanup of database connections

## Next Steps

1. Install dependencies: `npm install` in remotion-renderer directory
2. Verify database connection and templates exist
3. Test with different template IDs
4. Test random template selection
5. Monitor template usage counts for analytics

## Documentation

Created additional documentation:
- `TEMPLATE_USAGE.md`: Comprehensive usage guide
- This changelog: Implementation summary
