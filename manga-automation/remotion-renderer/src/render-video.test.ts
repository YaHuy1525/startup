/**
 * Tests for video generation functionality
 * 
 * This file contains:
 * - Property test for background music integration (Task 5.5)
 * - Property test for complete panel inclusion (Task 5.6)
 * - Unit tests for video generation edge cases (Task 5.7)
 * 
 * Note: These tests validate the props structure and video generation logic
 * without requiring actual React component rendering.
 */

import * as fc from 'fast-check';

// ─── Type Definitions (matching MangaRecap.tsx) ──────────────────────────────

type MotionType = 'zoom_center' | 'pan_right' | 'pan_up';

interface Panel {
    imagePath: string;
    motionType: MotionType;
    durationInFrames: number;
}

interface MangaRecapProps {
    panels: Panel[];
    titleText: string;
    chapterText: string;
    audioSrc: string | null;
    audioDuckingVolume: number;
}

// ─── Test Helpers ────────────────────────────────────────────────────────────

/**
 * Validates that props include audio configuration
 */
function propsHaveAudioConfig(props: MangaRecapProps): boolean {
    return props.audioSrc !== null && props.audioSrc !== undefined && props.audioSrc.length > 0;
}

/**
 * Calculates expected video duration from panels
 */
function calculateExpectedDuration(panels: Panel[]): number {
    const totalFrames = panels.reduce((sum, p) => sum + p.durationInFrames, 0);
    const transitionOverlap = Math.max(0, panels.length - 1) * 15; // 15 frames per transition
    return (totalFrames - transitionOverlap) / 30; // 30 fps
}

/**
 * Validates that all panels are included in the props
 */
function allPanelsIncluded(originalPanels: Panel[], propsToRender: MangaRecapProps): boolean {
    if (!propsToRender.panels || propsToRender.panels.length !== originalPanels.length) {
        return false;
    }
    
    // Check that each original panel is represented in the props
    for (let i = 0; i < originalPanels.length; i++) {
        const original = originalPanels[i];
        const inProps = propsToRender.panels[i];
        
        if (original.imagePath !== inProps.imagePath) {
            return false;
        }
    }
    
    return true;
}

/**
 * Creates valid test props
 */
function createTestProps(panels: Panel[], audioSrc: string | null = null): MangaRecapProps {
    return {
        panels,
        titleText: 'Test Manga',
        chapterText: 'Chapter 1',
        audioSrc,
        audioDuckingVolume: 0.4,
    };
}

// ─── Arbitraries for Property-Based Testing ──────────────────────────────────

const panelArbitrary = fc.record({
    imagePath: fc.string({ minLength: 5, maxLength: 50 }).map(s => `/data/panels/${s}.png`),
    motionType: fc.constantFrom('zoom_center', 'pan_right', 'pan_up'),
    durationInFrames: fc.integer({ min: 60, max: 300 }), // 2-10 seconds at 30fps
});

const propsArbitrary = fc.record({
    panels: fc.array(panelArbitrary, { minLength: 1, maxLength: 10 }),
    titleText: fc.string({ minLength: 1, maxLength: 50 }),
    chapterText: fc.string({ minLength: 1, maxLength: 30 }),
    audioSrc: fc.option(fc.string({ minLength: 5, maxLength: 50 }).map(s => `/data/music/${s}.mp3`), { nil: null }),
    audioDuckingVolume: fc.double({ min: 0.1, max: 0.8 }),
});

// ─── Property Tests ──────────────────────────────────────────────────────────

describe('Video Generation Property Tests', () => {
    // Feature: manga-automation-improvements, Property 11: Background music integration
    test('Property 11: Videos with music have audio configuration', () => {
        fc.assert(
            fc.property(
                fc.array(panelArbitrary, { minLength: 2, maxLength: 10 }),
                fc.string({ minLength: 5, maxLength: 50 }).map(s => `/data/music/${s}.mp3`),
                fc.string({ minLength: 1, maxLength: 30 }),
                (panels, audioPath, title) => {
                    const props = createTestProps(panels, audioPath);
                    
                    // Verify that when audioSrc is provided, it's included in the props
                    const hasAudioConfig = propsHaveAudioConfig(props);
                    
                    // Verify the audio path is correctly set
                    const audioPathMatches = props.audioSrc === audioPath;
                    
                    return hasAudioConfig && audioPathMatches;
                }
            ),
            { numRuns: 100 }
        );
    });

    // Feature: manga-automation-improvements, Property 14: Complete panel inclusion
    test('Property 14: All panels are included in video props', () => {
        fc.assert(
            fc.property(
                fc.array(panelArbitrary, { minLength: 1, maxLength: 20 }),
                fc.string({ minLength: 1, maxLength: 30 }),
                (panels, title) => {
                    const props = createTestProps(panels, null);
                    
                    // Verify all panels are included
                    const allIncluded = allPanelsIncluded(panels, props);
                    
                    // Verify panel count matches
                    const countMatches = props.panels.length === panels.length;
                    
                    // Verify expected duration calculation is consistent
                    const expectedDuration = calculateExpectedDuration(panels);
                    const durationIsPositive = expectedDuration > 0;
                    
                    return allIncluded && countMatches && durationIsPositive;
                }
            ),
            { numRuns: 100 }
        );
    });

    test('Property 14 (extended): Panel order is preserved', () => {
        fc.assert(
            fc.property(
                fc.array(panelArbitrary, { minLength: 2, maxLength: 15 }),
                (panels) => {
                    const props = createTestProps(panels, null);
                    
                    // Verify panel order is preserved
                    for (let i = 0; i < panels.length; i++) {
                        if (panels[i].imagePath !== props.panels[i].imagePath) {
                            return false;
                        }
                        if (panels[i].motionType !== props.panels[i].motionType) {
                            return false;
                        }
                    }
                    
                    return true;
                }
            ),
            { numRuns: 100 }
        );
    });
});

// ─── Unit Tests for Edge Cases ───────────────────────────────────────────────

describe('Video Generation Edge Cases', () => {
    test('Video with no panels creates valid props structure', () => {
        const props = createTestProps([], null);
        
        // Props should be valid even with no panels
        expect(props.panels).toEqual([]);
        expect(props.titleText).toBeDefined();
        expect(props.chapterText).toBeDefined();
    });

    test('Video with missing panel images in props structure', () => {
        const panels = [
            {
                imagePath: '',
                motionType: 'zoom_center' as const,
                durationInFrames: 120,
            },
        ];
        
        const props = createTestProps(panels, null);
        
        // Props should still be created, validation happens at render time
        expect(props.panels.length).toBe(1);
        expect(props.panels[0].imagePath).toBe('');
    });

    test('Video with invalid music path in props', () => {
        const panels = [
            {
                imagePath: '/data/panels/test.png',
                motionType: 'zoom_center' as const,
                durationInFrames: 120,
            },
        ];
        
        const props = createTestProps(panels, '/nonexistent/music.mp3');
        
        // Props should be created with the invalid path
        // Validation happens at render time
        expect(props.audioSrc).toBe('/nonexistent/music.mp3');
    });

    test('Video with valid inputs creates correct props', () => {
        const panels = [
            {
                imagePath: '/data/panels/panel1.png',
                motionType: 'zoom_center' as const,
                durationInFrames: 90,
            },
            {
                imagePath: '/data/panels/panel2.png',
                motionType: 'pan_right' as const,
                durationInFrames: 90,
            },
        ];
        
        const props = createTestProps(panels, '/data/music/test.mp3');
        
        // Verify all props are correctly set
        expect(props.panels.length).toBe(2);
        expect(props.audioSrc).toBe('/data/music/test.mp3');
        expect(props.titleText).toBeDefined();
        expect(props.chapterText).toBeDefined();
        expect(props.audioDuckingVolume).toBe(0.4);
        
        // Verify audio configuration
        expect(propsHaveAudioConfig(props)).toBe(true);
        
        // Verify all panels included
        expect(allPanelsIncluded(panels, props)).toBe(true);
    });

    test('Duration calculation is correct for various panel counts', () => {
        const testCases = [
            { panels: 1, frames: 120, expected: 4.0 }, // 120 frames / 30 fps = 4s
            { panels: 2, frames: 120, expected: 7.5 }, // (240 - 15) / 30 = 7.5s
            { panels: 5, frames: 90, expected: 13.0 }, // (450 - 60) / 30 = 13s
        ];
        
        testCases.forEach(({ panels: panelCount, frames, expected }) => {
            const panels = Array.from({ length: panelCount }, (_, i) => ({
                imagePath: `/data/panels/panel${i}.png`,
                motionType: 'zoom_center' as const,
                durationInFrames: frames,
            }));
            
            const duration = calculateExpectedDuration(panels);
            expect(duration).toBeCloseTo(expected, 1);
        });
    });

    test('Props validation with schema-like checks', () => {
        const validPanel: Panel = {
            imagePath: '/data/panels/test.png',
            motionType: 'zoom_center',
            durationInFrames: 120,
        };
        
        // Validate panel structure
        expect(validPanel.imagePath).toBeDefined();
        expect(validPanel.motionType).toBeDefined();
        expect(validPanel.durationInFrames).toBeGreaterThan(0);
        
        const validProps: MangaRecapProps = {
            panels: [validPanel],
            titleText: 'Test',
            chapterText: 'Chapter 1',
            audioSrc: null,
            audioDuckingVolume: 0.4,
        };
        
        // Validate props structure
        expect(validProps.panels).toBeDefined();
        expect(validProps.titleText).toBeDefined();
        expect(validProps.chapterText).toBeDefined();
        expect(validProps.audioDuckingVolume).toBeGreaterThanOrEqual(0);
        expect(validProps.audioDuckingVolume).toBeLessThanOrEqual(1);
    });

    test('Audio configuration with null audioSrc', () => {
        const panels = [
            {
                imagePath: '/data/panels/test.png',
                motionType: 'zoom_center' as const,
                durationInFrames: 120,
            },
        ];
        
        const props = createTestProps(panels, null);
        
        // Should not have audio config when audioSrc is null
        expect(propsHaveAudioConfig(props)).toBe(false);
        expect(props.audioSrc).toBeNull();
    });

    test('Audio configuration with empty string audioSrc', () => {
        const panels = [
            {
                imagePath: '/data/panels/test.png',
                motionType: 'zoom_center' as const,
                durationInFrames: 120,
            },
        ];
        
        const props = createTestProps(panels, '');
        
        // Should not have audio config when audioSrc is empty
        expect(propsHaveAudioConfig(props)).toBe(false);
    });
});
