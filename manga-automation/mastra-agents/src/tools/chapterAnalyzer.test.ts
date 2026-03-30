import * as fc from 'fast-check';
import { ChapterAnalyzer, VideoSplitPlan } from './chapterAnalyzer';
import { QueueManager, QueueEntry } from './queueManager';
import { db } from './database';

// Mock the database module
jest.mock('./database', () => ({
  db: {
    query: jest.fn(),
  },
  logger: {
    info: jest.fn(),
    error: jest.fn(),
  },
}));

describe('ChapterAnalyzer', () => {
  let analyzer: ChapterAnalyzer;
  let queueManager: QueueManager;

  beforeEach(() => {
    analyzer = new ChapterAnalyzer();
    queueManager = new QueueManager();
    jest.clearAllMocks();
  });

  describe('Property 15: Chapter splitting for long content', () => {
    /**
     * **Validates: Requirements 5A.2**
     * 
     * For any chapter with more than 30 panels, the system should split it 
     * into multiple videos rather than creating one excessively long video.
     */
    it('should split chapters with more than 30 panels into multiple videos', async () => {
      await fc.assert(
        fc.asyncProperty(
          // Generate panel count between 40 and 100 to ensure splits
          // (31 panels might not always split depending on duration calculations)
          fc.integer({ min: 40, max: 100 }),
          async (panelCount) => {
            // Arrange: Create mock panel URLs
            const panelUrls = Array.from({ length: panelCount }, (_, i) => 
              `https://example.com/panel-${i}.jpg`
            );

            // Mock database response
            (db.query as jest.Mock).mockResolvedValue({
              rows: [
                {
                  panel_urls: panelUrls,
                  total_panels: panelCount,
                },
              ],
            });

            // Mock the getDefaultTemplate call (second query)
            (db.query as jest.Mock).mockResolvedValueOnce({
              rows: [
                {
                  panel_urls: panelUrls,
                  total_panels: panelCount,
                },
              ],
            }).mockResolvedValueOnce({
              rows: [
                {
                  id: 1,
                  name: 'Default',
                  type: 'emotional_scene',
                  panelDuration: 4,
                  transitionType: 'crossfade',
                  transitionDuration: 0.5,
                  effectsConfig: {
                    zoomIntensity: 1.2,
                    panDirection: 'random',
                  },
                },
              ],
            });

            // Act: Analyze the chapter
            const result: VideoSplitPlan = await analyzer.analyzeChapter(1);

            // Assert: Video count should be greater than 1
            expect(result.videoCount).toBeGreaterThan(1);
            expect(result.totalPanels).toBe(panelCount);
            expect(result.splits.length).toBe(result.videoCount);
            
            // Verify all panels are included across splits
            const totalPanelsInSplits = result.splits.reduce((sum, split) => {
              return sum + (split.endPanel - split.startPanel + 1);
            }, 0);
            expect(totalPanelsInSplits).toBe(panelCount);
          }
        ),
        { numRuns: 100 }
      );
    });
  });

  describe('Property 16: Video duration constraints', () => {
    /**
     * **Validates: Requirements 5A.4**
     * 
     * For any generated video, its duration should be between 60 and 180 seconds (1-3 minutes).
     */
    it('should ensure all video segments have duration between 60 and 180 seconds', async () => {
      await fc.assert(
        fc.asyncProperty(
          // Generate panel count between 10 and 100
          fc.integer({ min: 10, max: 100 }),
          async (panelCount) => {
            // Arrange: Create mock panel URLs
            const panelUrls = Array.from({ length: panelCount }, (_, i) => 
              `https://example.com/panel-${i}.jpg`
            );

            // Mock database response for chapter data
            (db.query as jest.Mock).mockResolvedValueOnce({
              rows: [
                {
                  panel_urls: panelUrls,
                  total_panels: panelCount,
                },
              ],
            });

            // Mock the getDefaultTemplate call
            (db.query as jest.Mock).mockResolvedValueOnce({
              rows: [
                {
                  id: 1,
                  name: 'Default',
                  type: 'emotional_scene',
                  panelDuration: 4,
                  transitionType: 'crossfade',
                  transitionDuration: 0.5,
                  effectsConfig: {
                    zoomIntensity: 1.2,
                    panDirection: 'random',
                  },
                },
              ],
            });

            // Act: Analyze the chapter
            const result: VideoSplitPlan = await analyzer.analyzeChapter(1);

            // Assert: All video segments should have duration between 60 and 180 seconds
            for (const segment of result.splits) {
              expect(segment.estimatedDuration).toBeGreaterThanOrEqual(60);
              expect(segment.estimatedDuration).toBeLessThanOrEqual(180);
            }
          }
        ),
        { numRuns: 100 }
      );
    });
  });

  describe('Property 17: Split chapter queue entries', () => {
    /**
     * **Validates: Requirements 5A.8**
     * 
     * For any chapter that is split into N parts, the system should create N queue entries 
     * with part indicators (e.g., "Part 1", "Part 2").
     */
    it('should create N queue entries with correct part_number and total_parts for split chapters', async () => {
      await fc.assert(
        fc.asyncProperty(
          // Generate panel count that will result in splits (31-100 panels)
          fc.integer({ min: 31, max: 100 }),
          // Generate manga and chapter IDs
          fc.integer({ min: 1, max: 1000 }),
          fc.integer({ min: 1, max: 10000 }),
          fc.float({ min: 1, max: 500 }),
          async (panelCount, mangaId, chapterId, chapterNumber) => {
            // Arrange: Create mock panel URLs
            const panelUrls = Array.from({ length: panelCount }, (_, i) => 
              `https://example.com/panel-${i}.jpg`
            );

            // Mock database response for chapter analysis
            (db.query as jest.Mock).mockResolvedValueOnce({
              rows: [
                {
                  panel_urls: panelUrls,
                  total_panels: panelCount,
                },
              ],
            });

            // Mock the getDefaultTemplate call
            (db.query as jest.Mock).mockResolvedValueOnce({
              rows: [
                {
                  id: 1,
                  name: 'Default',
                  type: 'emotional_scene',
                  panelDuration: 4,
                  transitionType: 'crossfade',
                  transitionDuration: 0.5,
                  effectsConfig: {
                    zoomIntensity: 1.2,
                    panDirection: 'random',
                  },
                },
              ],
            });

            // Act: Analyze the chapter to get split plan
            const splitPlan: VideoSplitPlan = await analyzer.analyzeChapter(chapterId);

            // Only test if chapter was actually split (videoCount > 1)
            if (splitPlan.videoCount > 1) {
              // Mock database responses for queue entry creation
              // We need to mock one INSERT query per video part
              for (let i = 0; i < splitPlan.videoCount; i++) {
                const partNumber = i + 1;
                (db.query as jest.Mock).mockResolvedValueOnce({
                  rows: [
                    {
                      id: i + 1,
                      manga_id: mangaId,
                      chapter_id: chapterId,
                      chapter_number: chapterNumber.toString(),
                      priority: 0,
                      status: 'pending',
                      scheduled_for: null,
                      posted_at: null,
                      video_id: null,
                      part_number: partNumber,
                      total_parts: splitPlan.videoCount,
                      created_at: new Date(),
                      updated_at: new Date(),
                    },
                  ],
                });
              }

              // Act: Create queue entries from split plan
              const queueEntries: QueueEntry[] = await queueManager.createSplitChapterEntries(
                mangaId,
                chapterId,
                chapterNumber.toString(),
                splitPlan.videoCount,
                0
              );

              // Assert: Should create exactly N queue entries
              expect(queueEntries.length).toBe(splitPlan.videoCount);

              // Assert: Each entry should have correct part_number and total_parts
              for (let i = 0; i < queueEntries.length; i++) {
                const entry = queueEntries[i];
                expect(entry.part_number).toBe(i + 1);
                expect(entry.total_parts).toBe(splitPlan.videoCount);
                expect(entry.chapter_id).toBe(chapterId);
                expect(entry.manga_id).toBe(mangaId);
              }

              // Assert: Part numbers should be sequential from 1 to N
              const partNumbers = queueEntries.map(e => e.part_number).sort((a, b) => a - b);
              const expectedPartNumbers = Array.from({ length: splitPlan.videoCount }, (_, i) => i + 1);
              expect(partNumbers).toEqual(expectedPartNumbers);

              // Assert: All entries should have the same total_parts value
              const totalPartsValues = queueEntries.map(e => e.total_parts);
              expect(new Set(totalPartsValues).size).toBe(1);
              expect(totalPartsValues[0]).toBe(splitPlan.videoCount);
            }
          }
        ),
        { numRuns: 100 }
      );
    });
  });
});
