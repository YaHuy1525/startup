import * as fc from 'fast-check';
import { QueueManager, QueueStatus } from './queueManager';
import { db } from './database';

// Mock the database module
jest.mock('./database', () => ({
  db: {
    query: jest.fn(),
  },
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('QueueManager Property Tests', () => {
  let queueManager: QueueManager;

  beforeEach(() => {
    queueManager = new QueueManager();
    jest.clearAllMocks();
  });

  // Feature: manga-automation-improvements, Property 2: Chronological queue ordering
  // **Validates: Requirements 1.2, 2.2**
  test('Property 2: populateQueue stores chapters in chronological order (oldest-to-latest)', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate manga ID
        fc.integer({ min: 1, max: 1000 }),
        // Generate array of chapters with random chapter numbers
        fc.array(
          fc.record({
            id: fc.integer({ min: 1, max: 100000 }),
            chapter_number: fc.float({ min: 1, max: 500, noNaN: true }),
          }),
          { minLength: 2, maxLength: 20 }
        ),
        async (mangaId, chapters) => {
          // Sort chapters by chapter_number to simulate database ORDER BY
          const sortedChapters = [...chapters].sort(
            (a, b) => a.chapter_number - b.chapter_number
          );

          // Mock database responses
          const mockDbQuery = db.query as jest.MockedFunction<any>;
          
          // First call: SELECT chapters ordered by chapter_number ASC
          mockDbQuery.mockResolvedValueOnce({
            rows: sortedChapters,
            command: 'SELECT',
            rowCount: sortedChapters.length,
            oid: 0,
            fields: [],
          });

          // Subsequent calls: INSERT for each chapter
          sortedChapters.forEach((chapter, index) => {
            mockDbQuery.mockResolvedValueOnce({
              rows: [{
                id: index + 1,
                manga_id: mangaId,
                chapter_id: chapter.id,
                chapter_number: chapter.chapter_number.toString(),
                priority: 0,
                status: QueueStatus.PENDING,
                scheduled_for: null,
                posted_at: null,
                video_id: null,
                part_number: 1,
                total_parts: 1,
                created_at: new Date(),
                updated_at: new Date(),
              }],
              command: 'INSERT',
              rowCount: 1,
              oid: 0,
              fields: [],
            });
          });

          // Execute populateQueue
          const result = await queueManager.populateQueue(mangaId);

          // Property: All chapters should be in chronological order (chapter_number ASC)
          for (let i = 0; i < result.length - 1; i++) {
            const currentChapterNum = parseFloat(result[i].chapter_number);
            const nextChapterNum = parseFloat(result[i + 1].chapter_number);
            
            // Verify chronological ordering
            expect(currentChapterNum).toBeLessThanOrEqual(nextChapterNum);
          }

          // Verify all chapters were queued
          expect(result.length).toBe(sortedChapters.length);

          // Verify the SELECT query used ORDER BY chapter_number ASC
          const selectCall = mockDbQuery.mock.calls[0];
          expect(selectCall[0]).toContain('ORDER BY chapter_number ASC');
        }
      ),
      { numRuns: 100 }
    );
  });

  // Feature: manga-automation-improvements, Property 7: Priority-based ordering
  // **Validates: Requirements 2.5, 2.6**
  test('Property 7: getNextChapter returns highest priority entry, then lowest chapter_number', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate array of queue entries with varying priorities and chapter numbers
        fc.array(
          fc.record({
            id: fc.integer({ min: 1, max: 100000 }),
            manga_id: fc.integer({ min: 1, max: 1000 }),
            chapter_id: fc.integer({ min: 1, max: 100000 }),
            chapter_number: fc.float({ min: 1, max: 500, noNaN: true }),
            priority: fc.integer({ min: 0, max: 100 }),
            status: fc.constant(QueueStatus.PENDING),
          }),
          { minLength: 2, maxLength: 30 }
        ),
        async (queueEntries) => {
          // Mock database response
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // Sort entries by priority DESC, then chapter_number ASC (same as SQL ORDER BY)
          const sortedEntries = [...queueEntries].sort((a, b) => {
            if (a.priority !== b.priority) {
              return b.priority - a.priority; // DESC
            }
            return a.chapter_number - b.chapter_number; // ASC
          });

          // Mock getNextChapter to return the first entry from sorted list
          const expectedEntry = {
            ...sortedEntries[0],
            chapter_number: sortedEntries[0].chapter_number.toString(),
            scheduled_for: null,
            posted_at: null,
            video_id: null,
            part_number: 1,
            total_parts: 1,
            created_at: new Date(),
            updated_at: new Date(),
          };

          mockDbQuery.mockResolvedValueOnce({
            rows: [expectedEntry],
            command: 'SELECT',
            rowCount: 1,
            oid: 0,
            fields: [],
          });

          // Execute getNextChapter
          const result = await queueManager.getNextChapter();

          // Property: Result should be the entry with highest priority
          expect(result).not.toBeNull();
          expect(result!.priority).toBe(sortedEntries[0].priority);
          expect(parseFloat(result!.chapter_number)).toBeCloseTo(sortedEntries[0].chapter_number, 5);

          // Property: Among entries with same priority, should have lowest chapter_number
          const sameHighestPriority = sortedEntries.filter(
            e => e.priority === sortedEntries[0].priority
          );
          const lowestChapterInPriority = Math.min(
            ...sameHighestPriority.map(e => e.chapter_number)
          );
          expect(parseFloat(result!.chapter_number)).toBeCloseTo(lowestChapterInPriority, 5);

          // Verify the SELECT query used correct ORDER BY
          const selectCall = mockDbQuery.mock.calls[0];
          expect(selectCall[0]).toContain('ORDER BY priority DESC, chapter_number ASC');
        }
      ),
      { numRuns: 100 }
    );
  });

  // Feature: manga-automation-improvements, Property 6: Unique chapter constraint
  // **Validates: Requirements 2.3**
  test('Property 6: Adding same chapter twice updates existing entry, never creates duplicates', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate manga ID, chapter data, and two different priorities
        fc.integer({ min: 1, max: 1000 }),
        fc.record({
          id: fc.integer({ min: 1, max: 100000 }),
          chapter_number: fc.float({ min: 1, max: 500, noNaN: true }),
        }),
        fc.integer({ min: 0, max: 50 }),
        fc.integer({ min: 51, max: 100 }),
        async (mangaId, chapter, firstPriority, secondPriority) => {
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // First call: addChapterWithPriority - SELECT to find chapter ID
          mockDbQuery.mockResolvedValueOnce({
            rows: [{ id: chapter.id }],
            command: 'SELECT',
            rowCount: 1,
            oid: 0,
            fields: [],
          });

          // Second call: INSERT with ON CONFLICT (first add)
          const firstQueueEntry = {
            id: 1,
            manga_id: mangaId,
            chapter_id: chapter.id,
            chapter_number: chapter.chapter_number.toString(),
            priority: firstPriority,
            status: QueueStatus.PENDING,
            scheduled_for: null,
            posted_at: null,
            video_id: null,
            part_number: 1,
            total_parts: 1,
            created_at: new Date(),
            updated_at: new Date(),
          };

          mockDbQuery.mockResolvedValueOnce({
            rows: [firstQueueEntry],
            command: 'INSERT',
            rowCount: 1,
            oid: 0,
            fields: [],
          });

          // Execute first addChapterWithPriority
          const firstResult = await queueManager.addChapterWithPriority(
            mangaId,
            chapter.chapter_number.toString(),
            firstPriority
          );

          // Verify first entry was created
          expect(firstResult.chapter_id).toBe(chapter.id);
          expect(firstResult.priority).toBe(firstPriority);

          // Third call: SELECT to find chapter ID (second add)
          mockDbQuery.mockResolvedValueOnce({
            rows: [{ id: chapter.id }],
            command: 'SELECT',
            rowCount: 1,
            oid: 0,
            fields: [],
          });

          // Fourth call: INSERT with ON CONFLICT DO UPDATE (second add)
          // This simulates the database updating the existing entry
          const updatedQueueEntry = {
            ...firstQueueEntry,
            priority: secondPriority,
            updated_at: new Date(),
          };

          mockDbQuery.mockResolvedValueOnce({
            rows: [updatedQueueEntry],
            command: 'INSERT',
            rowCount: 1,
            oid: 0,
            fields: [],
          });

          // Execute second addChapterWithPriority with different priority
          const secondResult = await queueManager.addChapterWithPriority(
            mangaId,
            chapter.chapter_number.toString(),
            secondPriority
          );

          // Property: Same chapter_id should be returned (no duplicate)
          expect(secondResult.chapter_id).toBe(firstResult.chapter_id);
          expect(secondResult.chapter_id).toBe(chapter.id);

          // Property: Priority should be updated to the new value
          expect(secondResult.priority).toBe(secondPriority);

          // Property: The queue entry ID should remain the same (update, not insert)
          expect(secondResult.id).toBe(firstResult.id);

          // Verify the INSERT query uses ON CONFLICT clause
          const insertCalls = mockDbQuery.mock.calls.filter(
            (call: any) => typeof call[0] === 'string' && call[0].includes('INSERT INTO chapter_posting_queue')
          );
          expect(insertCalls.length).toBeGreaterThanOrEqual(2);
          
          // Both INSERT calls should have ON CONFLICT clause
          insertCalls.forEach((call: any) => {
            expect(call[0]).toContain('ON CONFLICT');
            expect(call[0]).toContain('DO UPDATE');
          });
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('QueueManager Unit Tests - Edge Cases', () => {
  let queueManager: QueueManager;

  beforeEach(() => {
    queueManager = new QueueManager();
    jest.clearAllMocks();
  });

  test('Empty queue returns null', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    // Mock empty queue response
    mockDbQuery.mockResolvedValueOnce({
      rows: [],
      command: 'SELECT',
      rowCount: 0,
      oid: 0,
      fields: [],
    });

    const result = await queueManager.getNextChapter();

    expect(result).toBeNull();
    expect(mockDbQuery).toHaveBeenCalledWith(
      expect.stringContaining('WHERE status = $1'),
      [QueueStatus.PENDING]
    );
  });

  test('Single chapter queue returns that chapter', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    const singleChapter = {
      id: 1,
      manga_id: 42,
      chapter_id: 100,
      chapter_number: '1',
      priority: 0,
      status: QueueStatus.PENDING,
      scheduled_for: null,
      posted_at: null,
      video_id: null,
      part_number: 1,
      total_parts: 1,
      created_at: new Date(),
      updated_at: new Date(),
    };

    // Mock single chapter response
    mockDbQuery.mockResolvedValueOnce({
      rows: [singleChapter],
      command: 'SELECT',
      rowCount: 1,
      oid: 0,
      fields: [],
    });

    const result = await queueManager.getNextChapter();

    expect(result).not.toBeNull();
    expect(result).toEqual(singleChapter);
    expect(result!.chapter_number).toBe('1');
    expect(result!.manga_id).toBe(42);
  });

  test('Queue with all posted chapters returns null', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    // Mock empty response (no pending chapters, all are posted)
    mockDbQuery.mockResolvedValueOnce({
      rows: [],
      command: 'SELECT',
      rowCount: 0,
      oid: 0,
      fields: [],
    });

    const result = await queueManager.getNextChapter();

    expect(result).toBeNull();
    
    // Verify the query filters by PENDING status
    expect(mockDbQuery).toHaveBeenCalledWith(
      expect.stringContaining('WHERE status = $1'),
      [QueueStatus.PENDING]
    );
  });
});
