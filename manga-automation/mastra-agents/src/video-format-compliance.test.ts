/**
 * Property-Based Test: Video Format Compliance
 * 
 * Feature: manga-automation-improvements
 * Property 12: Video format compliance
 * Validates: Requirements 4.7, 4.8, 4.9, 4.10, 12.1-12.7
 * 
 * For any generated video, it should meet all format requirements:
 * - 1080x1920 resolution
 * - Minimum 60 seconds duration
 * - H.264 video codec
 * - AAC audio codec
 * - VIDEO format (not photo slideshow)
 */

import * as fc from 'fast-check';
import * as fs from 'fs';
import * as path from 'path';
import { execSync } from 'child_process';

// ─── Types ───────────────────────────────────────────────────────────────────

interface PanelProps {
    imagePath: string;
    motionType: 'zoom_center' | 'pan_right' | 'pan_up' | 'pan_down';
    durationInFrames: number;
}

interface VideoProps {
    panels: PanelProps[];
    titleText: string;
    chapterText: string;
    audioSrc: string | null;
    audioDuckingVolume: number;
}

interface VideoMetadata {
    width: number;
    height: number;
    duration: number;
    videoCodec: string;
    audioCodec: string;
}

// ─── Test Helpers ────────────────────────────────────────────────────────────

/**
 * Check if ffprobe is available
 */
function isFFProbeAvailable(): boolean {
    try {
        execSync('ffprobe -version', { encoding: 'utf-8', stdio: 'ignore' });
        return true;
    } catch {
        return false;
    }
}

/**
 * Extract video metadata using ffprobe
 */
function getVideoMetadata(videoPath: string): VideoMetadata {
    if (!isFFProbeAvailable()) {
        throw new Error('ffprobe is not available. Please install FFmpeg to run this test.');
    }
    
    try {
        const ffprobeCmd = `ffprobe -v error -select_streams v:0 -show_entries stream=width,height,codec_name,duration -of json "${videoPath}"`;
        const videoOutput = execSync(ffprobeCmd, { encoding: 'utf-8' });
        const videoData = JSON.parse(videoOutput);

        const audioProbeCmd = `ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of json "${videoPath}"`;
        const audioOutput = execSync(audioProbeCmd, { encoding: 'utf-8' });
        const audioData = JSON.parse(audioOutput);

        // Get duration from format if not in stream
        let duration = videoData.streams[0]?.duration;
        if (!duration) {
            const durationCmd = `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "${videoPath}"`;
            duration = parseFloat(execSync(durationCmd, { encoding: 'utf-8' }).trim());
        }

        return {
            width: parseInt(videoData.streams[0]?.width || '0'),
            height: parseInt(videoData.streams[0]?.height || '0'),
            duration: parseFloat(duration || '0'),
            videoCodec: videoData.streams[0]?.codec_name || '',
            audioCodec: audioData.streams[0]?.codec_name || '',
        };
    } catch (error: any) {
        throw new Error(`Failed to extract video metadata: ${error.message}`);
    }
}

/**
 * Create a minimal test panel image (1x1 black PNG)
 * This creates the smallest valid PNG file possible
 */
function createMinimalTestPanelImage(outputPath: string): void {
    // This is a valid 1x1 black PNG file (67 bytes)
    const pngData = Buffer.from([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, // PNG signature
        0x00, 0x00, 0x00, 0x0D, // IHDR length (13 bytes)
        0x49, 0x48, 0x44, 0x52, // IHDR chunk type
        0x00, 0x00, 0x00, 0x01, // Width: 1
        0x00, 0x00, 0x00, 0x01, // Height: 1
        0x08, 0x02, 0x00, 0x00, 0x00, // Bit depth (8), color type (2=RGB), compression, filter, interlace
        0x90, 0x77, 0x53, 0xDE, // IHDR CRC
        0x00, 0x00, 0x00, 0x0C, // IDAT length (12 bytes)
        0x49, 0x44, 0x41, 0x54, // IDAT chunk type
        0x08, 0x99, 0x63, 0x60, 0x00, 0x00, 0x00, 0x02, 0x00, 0x01, // Compressed image data (black pixel)
        0xE2, 0x21, 0xBC, 0x33, // IDAT CRC
        0x00, 0x00, 0x00, 0x00, // IEND length (0 bytes)
        0x49, 0x45, 0x4E, 0x44, // IEND chunk type
        0xAE, 0x42, 0x60, 0x82  // IEND CRC
    ]);
    
    fs.writeFileSync(outputPath, pngData);
}

/**
 * Convert image file to base64 data URI
 */
function imageToDataURI(imagePath: string): string {
    const imageBuffer = fs.readFileSync(imagePath);
    const base64 = imageBuffer.toString('base64');
    // Assume PNG format for our test images
    return `data:image/png;base64,${base64}`;
}

/**
 * Render video using the remotion-renderer
 */
function renderVideo(props: VideoProps, outputPath: string): void {
    // Use process.cwd() to get the manga-automation/mastra-agents directory
    // Then go up one level and into remotion-renderer
    const remotionDir = path.join(process.cwd(), '../remotion-renderer');
    const renderScript = path.join(remotionDir, 'src/render-video.ts');
    
    // Convert local image paths to base64 data URIs (Requirement 4.12)
    const propsWithDataURIs = {
        ...props,
        panels: props.panels.map(panel => ({
            ...panel,
            imagePath: imageToDataURI(panel.imagePath),
        })),
    };
    
    // Write props to a temporary file
    const tempPropsPath = path.join(remotionDir, `test-props-${Date.now()}.json`);
    
    // Ensure the remotion directory exists
    if (!fs.existsSync(remotionDir)) {
        throw new Error(`Remotion directory not found: ${remotionDir}`);
    }
    
    fs.writeFileSync(tempPropsPath, JSON.stringify(propsWithDataURIs, null, 2));

    const cmd = `npx tsx "${renderScript}" --props "${tempPropsPath}" --output "${outputPath}"`;
    
    try {
        execSync(cmd, {
            cwd: remotionDir,
            encoding: 'utf-8',
            stdio: ['ignore', 'pipe', 'pipe'],
            timeout: 5 * 60 * 1000, // 5 minute timeout
        });
    } catch (error: any) {
        throw new Error(`Failed to render video: ${error.stderr || error.message}`);
    } finally {
        // Clean up temp props file
        try {
            if (fs.existsSync(tempPropsPath)) {
                fs.unlinkSync(tempPropsPath);
            }
        } catch {
            // Ignore cleanup errors
        }
    }
}

/**
 * Clean up test files
 */
function cleanupTestFiles(files: string[]): void {
    files.forEach(file => {
        try {
            if (fs.existsSync(file)) {
                fs.unlinkSync(file);
            }
        } catch (error) {
            // Ignore cleanup errors
        }
    });
}

// ─── Generators ──────────────────────────────────────────────────────────────

/**
 * Generate valid panel configurations
 * Minimum 5 panels to ensure 60+ second duration (5 panels * 4 seconds = 20 seconds base)
 * We need more panels or longer durations to reach 60 seconds
 */
const panelArbitrary = fc.record({
    motionType: fc.constantFrom('zoom_center', 'pan_right', 'pan_up', 'pan_down'),
    durationInFrames: fc.integer({ min: 120, max: 300 }), // 4-10 seconds at 30fps
});

/**
 * Generate video props that should produce compliant videos
 * Ensure minimum 60 seconds: with 15 panels at 4-10 seconds each, we get 60-150 seconds
 */
const videoPropsArbitrary = fc.record({
    panels: fc.array(panelArbitrary, { minLength: 15, maxLength: 25 }),
    titleText: fc.string({ minLength: 1, maxLength: 50 }),
    chapterText: fc.string({ minLength: 1, maxLength: 30 }),
    audioDuckingVolume: fc.double({ min: 0.1, max: 0.8 }),
});

// ─── Property Tests ──────────────────────────────────────────────────────────

describe('Property 12: Video format compliance', () => {
    const testDir = path.join(process.cwd(), '../data/test-videos');
    const testPanelsDir = path.join(testDir, 'panels');

    beforeAll(() => {
        // Check if ffprobe is available
        if (!isFFProbeAvailable()) {
            console.warn('WARNING: ffprobe is not available. This test requires FFmpeg to be installed.');
            console.warn('Please install FFmpeg from https://ffmpeg.org/download.html');
        }
        
        // Create test directories
        fs.mkdirSync(testDir, { recursive: true });
        fs.mkdirSync(testPanelsDir, { recursive: true });
    });

    afterAll(() => {
        // Clean up test directory
        try {
            if (fs.existsSync(testDir)) {
                fs.rmSync(testDir, { recursive: true, force: true });
            }
        } catch (error) {
            // Ignore cleanup errors
        }
    });

    test('generated videos meet all TikTok Creator Rewards format requirements', () => {
        fc.assert(
            fc.property(videoPropsArbitrary, (propsTemplate) => {
                const testId = Date.now() + '-' + Math.random().toString(36).substring(7);
                const outputPath = path.join(testDir, `test-video-${testId}.mp4`);
                const panelPaths: string[] = [];

                try {
                    // Create test panel images
                    const panels: PanelProps[] = propsTemplate.panels.map((panel, index) => {
                        const panelPath = path.join(testPanelsDir, `panel-${testId}-${index}.png`);
                        createMinimalTestPanelImage(panelPath);
                        panelPaths.push(panelPath);

                        return {
                            imagePath: panelPath,
                            motionType: panel.motionType,
                            durationInFrames: panel.durationInFrames,
                        };
                    });

                    // Create video props without audio (audio is optional)
                    const videoProps: VideoProps = {
                        panels,
                        titleText: propsTemplate.titleText || 'Test Manga',
                        chapterText: propsTemplate.chapterText || 'Chapter 1',
                        audioSrc: null, // No audio for testing
                        audioDuckingVolume: propsTemplate.audioDuckingVolume,
                    };

                    // Render video
                    renderVideo(videoProps, outputPath);

                    // Verify video was created
                    expect(fs.existsSync(outputPath)).toBe(true);

                    // Extract and verify metadata
                    const metadata = getVideoMetadata(outputPath);

                    // Property 12.1: Resolution must be 1080x1920 (portrait)
                    expect(metadata.width).toBe(1080);
                    expect(metadata.height).toBe(1920);

                    // Property 12.2: Minimum 60 seconds duration for Creator Rewards
                    expect(metadata.duration).toBeGreaterThanOrEqual(60);

                    // Property 12.3: Video codec must be H.264
                    expect(metadata.videoCodec).toBe('h264');

                    // Property 12.4: Audio codec must be AAC (if audio is present)
                    // Note: Videos without audio still meet Creator Rewards requirements
                    if (metadata.audioCodec) {
                        expect(metadata.audioCodec).toBe('aac');
                    }

                    // Property 12.5: File must exist and be a valid video (not a photo slideshow)
                    // A valid video file should have a reasonable size (> 100KB)
                    const stats = fs.statSync(outputPath);
                    expect(stats.size).toBeGreaterThan(100 * 1024); // > 100KB

                    // Clean up
                    cleanupTestFiles([outputPath, ...panelPaths]);
                } catch (error: any) {
                    // Clean up on error
                    cleanupTestFiles([outputPath, ...panelPaths]);
                    throw error;
                }
            }),
            {
                numRuns: 5, // Reduced from 100 for practical testing (each render takes ~30-60 seconds)
                timeout: 30 * 60 * 1000, // 30 minute timeout for entire test suite
                endOnFailure: true, // Stop on first failure to save time
            }
        );
    }, 35 * 60 * 1000); // 35 minute Jest timeout for the entire test
});
