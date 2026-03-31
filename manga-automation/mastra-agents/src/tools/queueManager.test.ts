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

  // Feature: manga-automation-improvements, Property 1: Complete chapter retrieval
  // **Validates: Requirements 1.1**
  test('Property 1: populateQueue retrieves all chapters regardless of publication date', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate manga ID
        fc.integer({ min: 1, max: 1000 }),
        // Generate array of chapters with random publication dates
        // Use uniqueArray to ensure distinct chapter IDs
        fc.uniqueArray(
          fc.record({
            id: fc.integer({ min: 1, max: 100000 }),
            chapter_number: fc.float({ min: 1, max: 500, noNaN: true }),
            // Generate random publication dates spanning multiple years
            published_at: fc.date({ 
              min: new Date('2020-01-01'), 
              max: new Date('2024-12-31') 
            }),
          }),
          {
            minLength: 5,
            maxLength: 50,
            selector: (item) => item.id, // Ensure unique IDs
          }
        ),
        async (mangaId, chapters) => {
          // Clear mocks for this iteration
          jest.clearAllMocks();
          
          // Sort chapters by chapter_number to simulate database ORDER BY
          const sortedChapters = [...chapters].sort(
            (a, b) => a.chapter_number - b.chapter_number
          );

          // Mock database responses
          const mockDbQuery = db.query as jest.MockedFunction<any>;
          
          // First call: SELECT chapters ordered by chapter_number ASC
          // This query should NOT filter by publication date
          mockDbQuery.mockResolvedValueOnce({
            rows: sortedChapters.map(c => ({
              id: c.id,
              chapter_number: c.chapter_number,
            })),
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

          // Property 1: ALL chapters should be retrieved, regardless of publication date
          expect(result.length).toBe(chapters.length);

          // Property 2: No chapters should be filtered out based on date
          const retrievedChapterIds = new Set(result.map(r => r.chapter_id));
          chapters.forEach(chapter => {
            expect(retrievedChapterIds.has(chapter.id)).toBe(true);
          });

          // Property 3: The SELECT query should NOT contain date filtering
          const selectCall = mockDbQuery.mock.calls[0];
          expect(selectCall[0]).not.toContain('published_at');
          expect(selectCall[0]).not.toContain('publication_date');
          // Should only filter by manga_id, not by date
          expect(selectCall[0]).toContain('WHERE manga_id = $1');
          expect(selectCall[0]).toContain('ORDER BY chapter_number ASC');

          // Property 4: The query should only filter by manga_id, not by date
          expect(selectCall[1][0]).toBe(mangaId);

          // Property 5: Old chapters (e.g., from 2020-2021) should be included
          const oldChapters = chapters.filter(c => c.published_at.getFullYear() <= 2021);
          if (oldChapters.length > 0) {
            const oldChapterIds = new Set(oldChapters.map(c => c.id));
            const retrievedOldChapters = result.filter(r => oldChapterIds.has(r.chapter_id));
            expect(retrievedOldChapters.length).toBe(oldChapters.length);
          }

          // Property 6: Recent chapters (e.g., from 2024) should be included
          const recentChapters = chapters.filter(c => c.published_at.getFullYear() >= 2024);
          if (recentChapters.length > 0) {
            const recentChapterIds = new Set(recentChapters.map(c => c.id));
            const retrievedRecentChapters = result.filter(r => recentChapterIds.has(r.chapter_id));
            expect(retrievedRecentChapters.length).toBe(recentChapters.length);
          }
        }
      ),
      { numRuns: 100 }
    );
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

  // Feature: manga-automation-improvements, Property 8: Idempotent manual selection
  // **Validates: Requirements 3.2, 3.6**
  test('Property 8: Calling addChapterWithPriority multiple times does not create duplicates', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate manga ID and chapter data
        fc.integer({ min: 1, max: 1000 }),
        fc.record({
          id: fc.integer({ min: 1, max: 100000 }),
          chapter_number: fc.float({ min: 1, max: 500, noNaN: true }),
        }),
        fc.integer({ min: 50, max: 150 }), // priority
        fc.integer({ min: 2, max: 5 }), // number of times to call
        async (mangaId, chapter, priority, callCount) => {
          // Clear mocks before this test iteration
          jest.clearAllMocks();
          
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          const queueEntryId = 1; // Same ID should be returned each time

          // For each call to addChapterWithPriority
          for (let i = 0; i < callCount; i++) {
            // First: SELECT to find chapter ID
            mockDbQuery.mockResolvedValueOnce({
              rows: [{ id: chapter.id }],
              command: 'SELECT',
              rowCount: 1,
              oid: 0,
              fields: [],
            });

            // Second: INSERT with ON CONFLICT DO UPDATE
            const queueEntry = {
              id: queueEntryId, // Same ID every time (no duplicate)
              manga_id: mangaId,
              chapter_id: chapter.id,
              chapter_number: chapter.chapter_number.toString(),
              priority: priority,
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
              rows: [queueEntry],
              command: 'INSERT',
              rowCount: 1,
              oid: 0,
              fields: [],
            });
          }

          // Call addChapterWithPriority multiple times
          const results = [];
          for (let i = 0; i < callCount; i++) {
            const result = await queueManager.addChapterWithPriority(
              mangaId,
              chapter.chapter_number.toString(),
              priority
            );
            results.push(result);
          }

          // Property 1: All calls should return the same queue entry ID (no duplicates)
          const uniqueIds = new Set(results.map(r => r.id));
          expect(uniqueIds.size).toBe(1);
          expect(results[0].id).toBe(queueEntryId);

          // Property 2: All calls should return the same chapter_id
          const uniqueChapterIds = new Set(results.map(r => r.chapter_id));
          expect(uniqueChapterIds.size).toBe(1);
          expect(results[0].chapter_id).toBe(chapter.id);

          // Property 3: Priority should remain consistent
          results.forEach(result => {
            expect(result.priority).toBe(priority);
          });

          // Property 4: Verify ON CONFLICT clause is used in all INSERT queries
          const insertCalls = mockDbQuery.mock.calls.filter(
            (call: any) => typeof call[0] === 'string' && call[0].includes('INSERT INTO chapter_posting_queue')
          );
          expect(insertCalls.length).toBe(callCount);
          
          insertCalls.forEach((call: any) => {
            expect(call[0]).toContain('ON CONFLICT');
            expect(call[0]).toContain('DO UPDATE');
          });
        }
      ),
      { numRuns: 100 }
    );
  });

  // Feature: manga-automation-improvements, Property 10: Bulk chapter range queuing
  // **Validates: Requirements 3.5**
  test('Property 10: addChapterRange queues all chapters in range with correct ordering', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate manga ID
        fc.integer({ min: 1, max: 1000 }),
        // Generate a range of chapter numbers (start and end)
        fc.integer({ min: 1, max: 100 }).chain(start =>
          fc.record({
            start: fc.constant(start),
            end: fc.integer({ min: start, max: start + 50 }),
          })
        ),
        // Generate priority
        fc.integer({ min: 0, max: 150 }),
        async (mangaId, chapterRange, priority) => {
          // Clear mocks before this test iteration
          jest.clearAllMocks();
          
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // Generate chapters in the range
          const chaptersInRange = [];
          for (let i = chapterRange.start; i <= chapterRange.end; i++) {
            chaptersInRange.push({
              id: 1000 + i,
              chapter_number: i.toString(),
            });
          }

          // Mock the SELECT query that fetches chapters in range
          mockDbQuery.mockResolvedValueOnce({
            rows: chaptersInRange,
            command: 'SELECT',
            rowCount: chaptersInRange.length,
            oid: 0,
            fields: [],
          });

          // Mock INSERT queries for each chapter
          chaptersInRange.forEach((chapter, index) => {
            mockDbQuery.mockResolvedValueOnce({
              rows: [{
                id: index + 1,
                manga_id: mangaId,
                chapter_id: chapter.id,
                chapter_number: chapter.chapter_number,
                priority: priority,
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

          // Execute addChapterRange
          const result = await queueManager.addChapterRange(
            mangaId,
            chapterRange.start.toString(),
            chapterRange.end.toString(),
            priority
          );

          // Property 1: All chapters in the range should be queued
          expect(result.length).toBe(chaptersInRange.length);

          // Property 2: No chapters should be skipped
          const expectedChapterNumbers = chaptersInRange.map(c => c.chapter_number);
          const actualChapterNumbers = result.map(r => r.chapter_number);
          expect(actualChapterNumbers).toEqual(expectedChapterNumbers);

          // Property 3: Chapters should be in correct order (ascending)
          for (let i = 0; i < result.length - 1; i++) {
            const currentNum = parseFloat(result[i].chapter_number);
            const nextNum = parseFloat(result[i + 1].chapter_number);
            expect(currentNum).toBeLessThan(nextNum);
          }

          // Property 4: No duplicates should exist
          const chapterIds = result.map(r => r.chapter_id);
          const uniqueChapterIds = new Set(chapterIds);
          expect(uniqueChapterIds.size).toBe(chapterIds.length);

          // Property 5: All entries should have the same priority
          result.forEach(entry => {
            expect(entry.priority).toBe(priority);
          });

          // Property 6: All entries should have the same manga_id
          result.forEach(entry => {
            expect(entry.manga_id).toBe(mangaId);
          });

          // Property 7: All entries should be in PENDING status
          result.forEach(entry => {
            expect(entry.status).toBe(QueueStatus.PENDING);
          });

          // Verify the SELECT query uses correct range filtering
          const selectCall = mockDbQuery.mock.calls[0];
          expect(selectCall[0]).toContain('WHERE manga_id = $1');
          expect(selectCall[0]).toContain('chapter_number >= $2');
          expect(selectCall[0]).toContain('chapter_number <= $3');
          expect(selectCall[0]).toContain('ORDER BY chapter_number ASC');
          
          // Verify parameters
          expect(selectCall[1][0]).toBe(mangaId);
          expect(selectCall[1][1]).toBe(chapterRange.start.toString());
          expect(selectCall[1][2]).toBe(chapterRange.end.toString());

          // Property 8: If range is empty (start > end shouldn't happen due to generator),
          // but if no chapters exist in DB, result should be empty
          if (chaptersInRange.length === 0) {
            expect(result.length).toBe(0);
          }

          // Property 9: First chapter in result should match start of range
          if (result.length > 0) {
            expect(result[0].chapter_number).toBe(chapterRange.start.toString());
          }

          // Property 10: Last chapter in result should match end of range
          if (result.length > 0) {
            expect(result[result.length - 1].chapter_number).toBe(chapterRange.end.toString());
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  // Feature: manga-automation-improvements, Property 3: Posted status prevents reposting
  // **Validates: Requirements 1.3, 2.4**
  test('Property 3: Chapters with status=posted are never returned by getNextChapter()', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate array of queue entries with mixed statuses
        fc.array(
          fc.record({
            id: fc.integer({ min: 1, max: 100000 }),
            manga_id: fc.integer({ min: 1, max: 1000 }),
            chapter_id: fc.integer({ min: 1, max: 100000 }),
            chapter_number: fc.float({ min: 1, max: 500, noNaN: true }),
            priority: fc.integer({ min: 0, max: 100 }),
            // Generate mix of pending and posted statuses
            status: fc.constantFrom(QueueStatus.PENDING, QueueStatus.POSTED),
          }),
          { minLength: 5, maxLength: 50 }
        ),
        async (queueEntries) => {
          // Clear mocks for this iteration
          jest.clearAllMocks();
          
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // Filter to get only pending entries
          const pendingEntries = queueEntries.filter(e => e.status === QueueStatus.PENDING);
          const postedEntries = queueEntries.filter(e => e.status === QueueStatus.POSTED);

          // If there are pending entries, getNextChapter should return one
          if (pendingEntries.length > 0) {
            // Sort pending entries by priority DESC, chapter_number ASC
            const sortedPending = [...pendingEntries].sort((a, b) => {
              if (a.priority !== b.priority) {
                return b.priority - a.priority; // DESC
              }
              return a.chapter_number - b.chapter_number; // ASC
            });

            const expectedEntry = {
              ...sortedPending[0],
              chapter_number: sortedPending[0].chapter_number.toString(),
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

            const result = await queueManager.getNextChapter();

            // Property 1: Result should not be null when pending entries exist
            expect(result).not.toBeNull();

            // Property 2: Result MUST have status PENDING, never POSTED
            // This is the core property: posted chapters are never returned
            expect(result!.status).toBe(QueueStatus.PENDING);
            expect(result!.status).not.toBe(QueueStatus.POSTED);

            // Property 3: Verify the SQL query filters by PENDING status
            const selectCall = mockDbQuery.mock.calls[0];
            expect(selectCall[0]).toContain('WHERE status = $1');
            expect(selectCall[1][0]).toBe(QueueStatus.PENDING);

            // Property 4: The query should explicitly exclude posted entries
            // by only selecting PENDING status
            expect(selectCall[1][0]).not.toBe(QueueStatus.POSTED);
          } else {
            // If no pending entries, getNextChapter should return null
            mockDbQuery.mockResolvedValueOnce({
              rows: [],
              command: 'SELECT',
              rowCount: 0,
              oid: 0,
              fields: [],
            });

            const result = await queueManager.getNextChapter();

            // Property 5: When all chapters are posted, result should be null
            expect(result).toBeNull();

            // Property 6: Even if posted entries exist, they should not be returned
            // because the query filters by status=PENDING
            if (postedEntries.length > 0) {
              expect(result).toBeNull();
            }

            // Property 7: Verify the query still filters by PENDING status
            const selectCall = mockDbQuery.mock.calls[0];
            expect(selectCall[0]).toContain('WHERE status = $1');
            expect(selectCall[1][0]).toBe(QueueStatus.PENDING);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  // Feature: manga-automation-improvements, Property 4: Oldest unposted chapter selection
  // **Validates: Requirements 1.4**
  test('Property 4: getNextChapter returns oldest unposted chapter (lowest chapter_number with highest priority)', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate array of queue entries with varying priorities and chapter numbers
        // Some will be pending, some posted
        fc.array(
          fc.record({
            id: fc.integer({ min: 1, max: 100000 }),
            manga_id: fc.integer({ min: 1, max: 1000 }),
            chapter_id: fc.integer({ min: 1, max: 100000 }),
            chapter_number: fc.float({ min: 1, max: 500, noNaN: true }),
            priority: fc.integer({ min: 0, max: 100 }),
            // Mix of pending and posted statuses
            status: fc.constantFrom(QueueStatus.PENDING, QueueStatus.POSTED, QueueStatus.PROCESSING),
          }),
          { minLength: 3, maxLength: 50 }
        ),
        async (queueEntries) => {
          // Clear mocks for this iteration
          jest.clearAllMocks();
          
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // Filter to get only unposted (pending) entries
          const unpostedEntries = queueEntries.filter(e => e.status === QueueStatus.PENDING);

          // If there are unposted entries, getNextChapter should return the oldest one
          if (unpostedEntries.length > 0) {
            // Sort unposted entries by priority DESC (highest first), then chapter_number ASC (lowest first)
            const sortedUnposted = [...unpostedEntries].sort((a, b) => {
              if (a.priority !== b.priority) {
                return b.priority - a.priority; // DESC - higher priority first
              }
              return a.chapter_number - b.chapter_number; // ASC - lower chapter number first
            });

            // The oldest unposted chapter is the first one after sorting
            const oldestUnposted = sortedUnposted[0];

            const expectedEntry = {
              ...oldestUnposted,
              chapter_number: oldestUnposted.chapter_number.toString(),
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

            const result = await queueManager.getNextChapter();

            // Property 1: Result should not be null when unposted entries exist
            expect(result).not.toBeNull();

            // Property 2: Result MUST be the oldest unposted chapter (lowest chapter_number among highest priority)
            expect(result!.status).toBe(QueueStatus.PENDING);
            expect(result!.priority).toBe(oldestUnposted.priority);
            expect(parseFloat(result!.chapter_number)).toBeCloseTo(oldestUnposted.chapter_number, 5);

            // Property 3: Among all unposted entries with the same highest priority, 
            // the returned chapter should have the lowest chapter_number
            const highestPriority = Math.max(...unpostedEntries.map(e => e.priority));
            const entriesWithHighestPriority = unpostedEntries.filter(e => e.priority === highestPriority);
            const lowestChapterInHighestPriority = Math.min(...entriesWithHighestPriority.map(e => e.chapter_number));
            
            expect(result!.priority).toBe(highestPriority);
            expect(parseFloat(result!.chapter_number)).toBeCloseTo(lowestChapterInHighestPriority, 5);

            // Property 4: No posted or processing chapter should be returned
            expect(result!.status).not.toBe(QueueStatus.POSTED);
            expect(result!.status).not.toBe(QueueStatus.PROCESSING);

            // Property 5: Verify the SQL query filters by PENDING status and orders correctly
            const selectCall = mockDbQuery.mock.calls[0];
            expect(selectCall[0]).toContain('WHERE status = $1');
            expect(selectCall[0]).toContain('ORDER BY priority DESC, chapter_number ASC');
            expect(selectCall[1][0]).toBe(QueueStatus.PENDING);

            // Property 6: For a given priority level, no unposted chapter with a lower chapter_number should exist
            const sameOrHigherPriorityEntries = unpostedEntries.filter(e => e.priority >= result!.priority);
            const lowerChapterNumbers = sameOrHigherPriorityEntries.filter(e => {
              if (e.priority > result!.priority) return true;
              if (e.priority === result!.priority && e.chapter_number < parseFloat(result!.chapter_number)) return true;
              return false;
            });
            
            // If there are entries with higher priority or same priority but lower chapter number,
            // they should not exist (the returned chapter should be the first)
            expect(lowerChapterNumbers.length).toBe(0);

            // Property 7: The returned chapter should be the absolute first in the sorted order
            expect(result!.chapter_id).toBe(oldestUnposted.chapter_id);
          } else {
            // If no unposted entries, getNextChapter should return null
            mockDbQuery.mockResolvedValueOnce({
              rows: [],
              command: 'SELECT',
              rowCount: 0,
              oid: 0,
              fields: [],
            });

            const result = await queueManager.getNextChapter();

            // Property 8: When all chapters are posted or processing, result should be null
            expect(result).toBeNull();

            // Property 9: Verify the query still filters by PENDING status
            const selectCall = mockDbQuery.mock.calls[0];
            expect(selectCall[0]).toContain('WHERE status = $1');
            expect(selectCall[1][0]).toBe(QueueStatus.PENDING);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  // Feature: manga-automation-improvements, Property 9: Queue position calculation
  // **Validates: Requirements 3.4**
  test('Property 9: Queue position calculation is correct based on priority and chapter_number ordering', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate array of existing queue entries
        fc.array(
          fc.record({
            id: fc.integer({ min: 1, max: 100000 }),
            manga_id: fc.integer({ min: 1, max: 1000 }),
            chapter_id: fc.integer({ min: 1, max: 100000 }),
            chapter_number: fc.float({ min: 1, max: 500, noNaN: true }),
            priority: fc.integer({ min: 0, max: 100 }),
            status: fc.constant(QueueStatus.PENDING),
          }),
          { minLength: 0, maxLength: 30 }
        ),
        // Generate a new chapter to add
        fc.record({
          chapter_number: fc.float({ min: 1, max: 500, noNaN: true }),
          priority: fc.integer({ min: 0, max: 100 }),
        }),
        async (existingQueue, newChapter) => {
          // Clear mocks before this test iteration
          jest.clearAllMocks();
          
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // Calculate expected position manually
          // Count how many entries come before the new chapter
          const entriesBeforeNew = existingQueue.filter(entry => {
            // Higher priority comes first
            if (entry.priority > newChapter.priority) {
              return true;
            }
            // Same priority, lower chapter_number comes first
            if (entry.priority === newChapter.priority && entry.chapter_number < newChapter.chapter_number) {
              return true;
            }
            return false;
          });

          const expectedPosition = entriesBeforeNew.length + 1;

          // Mock the database query response
          mockDbQuery.mockResolvedValueOnce({
            rows: [{ position: entriesBeforeNew.length }],
            command: 'SELECT',
            rowCount: 1,
            oid: 0,
            fields: [],
          });

          // Execute calculateQueuePosition
          const actualPosition = await queueManager.calculateQueuePosition(
            newChapter.priority,
            newChapter.chapter_number.toString()
          );

          // Property: The calculated position should match the expected position
          expect(actualPosition).toBe(expectedPosition);

          // Verify the SQL query uses correct logic
          const selectCall = mockDbQuery.mock.calls[0];
          expect(selectCall[0]).toContain('WHERE status = $1');
          expect(selectCall[0]).toContain('priority > $2');
          expect(selectCall[0]).toContain('priority = $2 AND chapter_number < $3');
          
          // Verify parameters are correct
          expect(selectCall[1][0]).toBe(QueueStatus.PENDING);
          expect(selectCall[1][1]).toBe(newChapter.priority);
          expect(selectCall[1][2]).toBe(newChapter.chapter_number.toString());

          // Property: Position should always be at least 1
          expect(actualPosition).toBeGreaterThanOrEqual(1);

          // Property: Position should not exceed queue size + 1
          expect(actualPosition).toBeLessThanOrEqual(existingQueue.length + 1);

          // Property: If new chapter has highest priority and lowest chapter_number, position should be 1
          const hasHighestPriority = existingQueue.every(e => e.priority <= newChapter.priority);
          const hasLowestChapterNum = existingQueue
            .filter(e => e.priority === newChapter.priority)
            .every(e => e.chapter_number >= newChapter.chapter_number);
          
          if (hasHighestPriority && hasLowestChapterNum) {
            expect(actualPosition).toBe(1);
          }

          // Property: If new chapter has lowest priority and highest chapter_number, position should be last
          const hasLowestPriority = existingQueue.every(e => e.priority >= newChapter.priority);
          const hasHighestChapterNum = existingQueue
            .filter(e => e.priority === newChapter.priority)
            .every(e => e.chapter_number <= newChapter.chapter_number);
          
          if (hasLowestPriority && hasHighestChapterNum && existingQueue.length > 0) {
            expect(actualPosition).toBe(existingQueue.length + 1);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  // Feature: manga-automation-improvements, Property 5: Cross-manga queue progression
  // **Validates: Requirements 1.6**
  test('Property 5: When all chapters from first manga are posted, getNextChapter returns chapter from second manga', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate two different manga IDs
        fc.integer({ min: 1, max: 1000 }),
        fc.integer({ min: 1001, max: 2000 }),
        // Generate chapters for first manga (all will be posted)
        fc.array(
          fc.record({
            id: fc.integer({ min: 1, max: 50000 }),
            chapter_number: fc.float({ min: 1, max: 100, noNaN: true }),
          }),
          { minLength: 2, maxLength: 10 }
        ),
        // Generate chapters for second manga (all will be pending)
        fc.array(
          fc.record({
            id: fc.integer({ min: 50001, max: 100000 }),
            chapter_number: fc.float({ min: 1, max: 100, noNaN: true }),
          }),
          { minLength: 2, maxLength: 10 }
        ),
        async (manga1Id, manga2Id, manga1Chapters, manga2Chapters) => {
          // Clear mocks for this iteration
          jest.clearAllMocks();
          
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // Sort chapters for both manga by chapter_number
          const sortedManga1 = [...manga1Chapters].sort((a, b) => a.chapter_number - b.chapter_number);
          const sortedManga2 = [...manga2Chapters].sort((a, b) => a.chapter_number - b.chapter_number);

          // Create queue entries for manga 1 (all POSTED)
          const manga1QueueEntries = sortedManga1.map((chapter, index) => ({
            id: index + 1,
            manga_id: manga1Id,
            chapter_id: chapter.id,
            chapter_number: chapter.chapter_number.toString(),
            priority: 0,
            status: QueueStatus.POSTED, // All chapters from manga 1 are posted
            scheduled_for: null,
            posted_at: new Date(),
            video_id: 1000 + index,
            part_number: 1,
            total_parts: 1,
            created_at: new Date(),
            updated_at: new Date(),
          }));

          // Create queue entries for manga 2 (all PENDING)
          const manga2QueueEntries = sortedManga2.map((chapter, index) => ({
            id: 100 + index,
            manga_id: manga2Id,
            chapter_id: chapter.id,
            chapter_number: chapter.chapter_number.toString(),
            priority: 0,
            status: QueueStatus.PENDING, // All chapters from manga 2 are pending
            scheduled_for: null,
            posted_at: null,
            video_id: null,
            part_number: 1,
            total_parts: 1,
            created_at: new Date(),
            updated_at: new Date(),
          }));

          // getNextChapter should return the first pending chapter from manga 2
          // (since all manga 1 chapters are posted)
          const expectedNextChapter = manga2QueueEntries[0];

          mockDbQuery.mockResolvedValueOnce({
            rows: [expectedNextChapter],
            command: 'SELECT',
            rowCount: 1,
            oid: 0,
            fields: [],
          });

          // Execute getNextChapter
          const result = await queueManager.getNextChapter();

          // Property 1: Result should not be null (there are pending chapters from manga 2)
          expect(result).not.toBeNull();

          // Property 2: Result MUST be from manga 2, NOT manga 1
          // This is the core property: queue progresses across manga series
          expect(result!.manga_id).toBe(manga2Id);
          expect(result!.manga_id).not.toBe(manga1Id);

          // Property 3: Result should be PENDING status (not posted)
          expect(result!.status).toBe(QueueStatus.PENDING);

          // Property 4: Result should be the first chapter from manga 2 (lowest chapter_number)
          expect(result!.chapter_id).toBe(sortedManga2[0].id);
          expect(parseFloat(result!.chapter_number)).toBeCloseTo(sortedManga2[0].chapter_number, 5);

          // Property 5: Verify the SQL query filters by PENDING status
          // This ensures posted chapters from manga 1 are excluded
          const selectCall = mockDbQuery.mock.calls[0];
          expect(selectCall[0]).toContain('WHERE status = $1');
          expect(selectCall[1][0]).toBe(QueueStatus.PENDING);

          // Property 6: The query should order by priority DESC, chapter_number ASC
          // This ensures fair progression across manga (no manga is favored)
          expect(selectCall[0]).toContain('ORDER BY priority DESC, chapter_number ASC');

          // Property 7: No chapter from manga 1 should be returned
          // (all are posted, so they're filtered out)
          const manga1ChapterIds = new Set(sortedManga1.map(c => c.id));
          expect(manga1ChapterIds.has(result!.chapter_id)).toBe(false);

          // Property 8: The returned chapter should be from the set of pending chapters
          const manga2ChapterIds = new Set(sortedManga2.map(c => c.id));
          expect(manga2ChapterIds.has(result!.chapter_id)).toBe(true);
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
