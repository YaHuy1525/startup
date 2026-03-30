# Video Format Compliance Property Test

## Overview

This property-based test validates **Property 12: Video format compliance** from the manga-automation-improvements specification.

**Validates Requirements:** 4.7, 4.8, 4.9, 4.10, 12.1-12.7

## What It Tests

For any generated video, the test verifies that it meets all TikTok Creator Rewards format requirements:

1. **Resolution**: 1080x1920 (portrait orientation)
2. **Duration**: Minimum 60 seconds
3. **Video Codec**: H.264
4. **Audio Codec**: AAC (when audio is present)
5. **Format**: Valid VIDEO format (not photo slideshow)

## Test Approach

The test uses property-based testing with the `fast-check` library to:

1. Generate random video configurations with 15-25 panels
2. Create test panel images (1x1 black PNG files)
3. Convert images to base64 data URIs (per Requirement 4.12)
4. Render videos using the Remotion renderer
5. Extract and verify video metadata using ffprobe
6. Validate all format requirements

## Prerequisites

### Required Tools

1. **FFmpeg** - Required for video metadata extraction
   - Download from: https://ffmpeg.org/download.html
   - Ensure `ffprobe` is available in your PATH
   
2. **Node.js** - Version 18+ recommended

3. **Dependencies** - Install via `npm install` in the `mastra-agents` directory

### Optional Tools

- **ImageMagick** - Not required (test creates PNG files programmatically)

## Running the Test

```bash
cd manga-automation/mastra-agents
npm test -- video-format-compliance.test.ts
```

## Test Configuration

- **Iterations**: 5 (reduced from 100 for practical testing)
- **Timeout**: 35 minutes per test
- **Panel Count**: 15-25 panels per video
- **Panel Duration**: 4-10 seconds (120-300 frames at 30fps)
- **Stop on Failure**: Yes (endOnFailure: true)

## Known Limitations

1. **No Audio Testing**: The test currently generates videos without audio because ffmpeg is required to create test audio files. The AAC codec verification is conditional - it only checks if audio is present.

2. **Minimal Panel Images**: Test uses 1x1 pixel black PNG images instead of full 1080x1920 images to reduce test execution time and file sizes.

3. **Reduced Iterations**: The test runs 5 iterations instead of the recommended 100 due to the time required to render each video (~30-60 seconds per video).

## Troubleshooting

### Error: "ffprobe is not available"

**Solution**: Install FFmpeg and ensure it's in your system PATH.

- Windows: Download from https://ffmpeg.org/download.html and add to PATH
- Mac: `brew install ffmpeg`
- Linux: `sudo apt-get install ffmpeg`

### Error: "Remotion directory not found"

**Solution**: Ensure you're running the test from the `mastra-agents` directory and that the `remotion-renderer` directory exists at `../remotion-renderer`.

### Error: "Not allowed to load local resource"

**Solution**: This error should not occur as the test converts local file paths to base64 data URIs. If you see this error, check that the `imageToDataURI` function is working correctly.

## Future Improvements

1. **Add Audio Testing**: Create test audio files programmatically or use existing audio files to test AAC codec compliance.

2. **Increase Iterations**: Once the test is stable, increase iterations to 100 for more comprehensive coverage.

3. **Full-Size Images**: Consider using full 1080x1920 test images for more realistic testing.

4. **Parallel Execution**: Run multiple test iterations in parallel to reduce total test time.

## Related Files

- `video-format-compliance.test.ts` - The test implementation
- `../../remotion-renderer/src/render-video.ts` - Video rendering script
- `../../remotion-renderer/src/MangaRecap.tsx` - Remotion composition
- `.kiro/specs/manga-automation-improvements/design.md` - Property 12 specification
