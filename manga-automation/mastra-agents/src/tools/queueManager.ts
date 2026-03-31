import { db, logger } from './database';

// ─── Interfaces ──────────────────────────────────────────────────────────────

export enum QueueStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  POSTED = 'posted',
  FAILED = 'failed'
}

export interface QueueEntry {
  id: number;
  manga_id: number;
  chapter_id: number;
  chapter_number: string;
  priority: number;
  status: QueueStatus;
  scheduled_for: Date | null;
  posted_at: Date | null;
  video_id: number | null;
  part_number: number;
  total_parts: number;
  created_at: Date;
  updated_at: Date;
}

// ─── QueueManager Class ──────────────────────────────────────────────────────

export class QueueManager {
  /**
   * Populate queue with all chapters for a manga
   * @param mangaId - The manga ID to populate chapters for
   * @returns Array of created queue entries
   */
  async populateQueue(mangaId: number): Promise<QueueEntry[]> {
    try {
      logger.info(`Populating queue for manga ${mangaId}`);

      // Fetch all chapters for the manga ordered by chapter_number ASC
      const chaptersResult = await db.query(
        `SELECT id, chapter_number 
         FROM manga_chapters 
         WHERE manga_id = $1 
         ORDER BY chapter_number ASC`,
        [mangaId]
      );

      if (chaptersResult.rows.length === 0) {
        logger.warn(`No chapters found for manga ${mangaId}`);
        return [];
      }

      const queueEntries: QueueEntry[] = [];

      // Insert chapters into queue with ON CONFLICT to handle duplicates
      for (const chapter of chaptersResult.rows) {
        const insertResult = await db.query(
          `INSERT INTO chapter_posting_queue 
           (manga_id, chapter_id, chapter_number, priority, status, part_number, total_parts)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           ON CONFLICT (chapter_id, part_number) 
           DO UPDATE SET 
             priority = EXCLUDED.priority,
             updated_at = NOW()
           RETURNING *`,
          [mangaId, chapter.id, chapter.chapter_number, 0, QueueStatus.PENDING, 1, 1]
        );

        queueEntries.push(insertResult.rows[0]);
      }

      logger.info(`Populated ${queueEntries.length} chapters for manga ${mangaId}`);
      return queueEntries;
    } catch (error) {
      logger.error(`Error populating queue for manga ${mangaId}`, { error });
      throw error;
    }
  }

  /**
   * Get next chapter to post based on priority and chapter number
   * @returns Next queue entry or null if queue is empty
   */
  async getNextChapter(): Promise<QueueEntry | null> {
    try {
      const result = await db.query(
        `SELECT * FROM chapter_posting_queue
         WHERE status = $1
         ORDER BY priority DESC, chapter_number ASC
         LIMIT 1`,
        [QueueStatus.PENDING]
      );

      if (result.rows.length === 0) {
        logger.info('No pending chapters in queue');
        return null;
      }

      return result.rows[0];
    } catch (error) {
      logger.error('Error getting next chapter from queue', { error });
      throw error;
    }
  }

  /**
   * Add chapter with priority (for manual selection)
   * @param mangaId - The manga ID
   * @param chapterNumber - The chapter number
   * @param priority - Priority level (default: 100)
   * @returns Created or updated queue entry
   */
  async addChapterWithPriority(
    mangaId: number,
    chapterNumber: string,
    priority: number = 100
  ): Promise<QueueEntry> {
    try {
      logger.info(`Adding chapter ${chapterNumber} for manga ${mangaId} with priority ${priority}`);

      // First, find the chapter ID
      const chapterResult = await db.query(
        `SELECT id FROM manga_chapters 
         WHERE manga_id = $1 AND chapter_number = $2`,
        [mangaId, chapterNumber]
      );

      logger.info(`Chapter lookup result`, { 
        mangaId, 
        chapterNumber, 
        rowCount: chapterResult.rows.length,
        foundId: chapterResult.rows[0]?.id 
      });

      if (chapterResult.rows.length === 0) {
        throw new Error(`Chapter ${chapterNumber} not found for manga ${mangaId}`);
      }

      const chapterId = chapterResult.rows[0].id;

      // Insert or update the queue entry
      const result = await db.query(
        `INSERT INTO chapter_posting_queue 
         (manga_id, chapter_id, chapter_number, priority, status, part_number, total_parts)
         VALUES ($1, $2, $3, $4, $5, $6, $7)
         ON CONFLICT (chapter_id, part_number) 
         DO UPDATE SET 
           priority = EXCLUDED.priority,
           updated_at = NOW()
         RETURNING *`,
        [mangaId, chapterId, chapterNumber, priority, QueueStatus.PENDING, 1, 1]
      );

      logger.info(`Added/updated chapter ${chapterNumber} in queue with ID ${result.rows[0].id}`);
      return result.rows[0];
    } catch (error) {
      logger.error(`Error adding chapter with priority`, { error, mangaId, chapterNumber });
      throw error;
    }
  }

  /**
   * Update queue entry status
   * @param queueId - The queue entry ID
   * @param status - New status
   * @param videoId - Optional video ID (for posted status)
   */
  async updateStatus(
    queueId: number,
    status: QueueStatus,
    videoId?: number
  ): Promise<void> {
    try {
      const updates: string[] = ['status = $2', 'updated_at = NOW()'];
      const params: any[] = [queueId, status];

      if (status === QueueStatus.POSTED) {
        updates.push('posted_at = NOW()');
        if (videoId) {
          updates.push(`video_id = $${params.length + 1}`);
          params.push(videoId);
        }
      }

      await db.query(
        `UPDATE chapter_posting_queue 
         SET ${updates.join(', ')}
         WHERE id = $1`,
        params
      );

      logger.info(`Updated queue entry ${queueId} to status ${status}`);
    } catch (error) {
      logger.error(`Error updating queue status`, { error, queueId, status });
      throw error;
    }
  }

  /**
   * Add bulk chapters (for chapter ranges)
   * @param mangaId - The manga ID
   * @param startChapter - Start chapter number
   * @param endChapter - End chapter number
   * @param priority - Priority level (default: 100)
   * @returns Array of created queue entries
   */
  async addChapterRange(
    mangaId: number,
    startChapter: string,
    endChapter: string,
    priority: number = 100
  ): Promise<QueueEntry[]> {
    try {
      logger.info(`Adding chapter range ${startChapter}-${endChapter} for manga ${mangaId}`);

      // Fetch chapters in the range
      const chaptersResult = await db.query(
        `SELECT id, chapter_number 
         FROM manga_chapters 
         WHERE manga_id = $1 
           AND chapter_number >= $2 
           AND chapter_number <= $3
         ORDER BY chapter_number ASC`,
        [mangaId, startChapter, endChapter]
      );

      if (chaptersResult.rows.length === 0) {
        logger.warn(`No chapters found in range ${startChapter}-${endChapter} for manga ${mangaId}`);
        return [];
      }

      const queueEntries: QueueEntry[] = [];

      // Insert chapters into queue
      for (const chapter of chaptersResult.rows) {
        const insertResult = await db.query(
          `INSERT INTO chapter_posting_queue 
           (manga_id, chapter_id, chapter_number, priority, status, part_number, total_parts)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           ON CONFLICT (chapter_id, part_number) 
           DO UPDATE SET 
             priority = EXCLUDED.priority,
             updated_at = NOW()
           RETURNING *`,
          [mangaId, chapter.id, chapter.chapter_number, priority, QueueStatus.PENDING, 1, 1]
        );

        queueEntries.push(insertResult.rows[0]);
      }

      logger.info(`Added ${queueEntries.length} chapters to queue for range ${startChapter}-${endChapter}`);
      return queueEntries;
    } catch (error) {
      logger.error(`Error adding chapter range`, { error, mangaId, startChapter, endChapter });
      throw error;
    }
  }

  /**
   * Create queue entries from a VideoSplitPlan
   * When a chapter is split into multiple parts, this creates N queue entries
   * @param mangaId - The manga ID
   * @param chapterId - The chapter ID
   * @param chapterNumber - The chapter number
   * @param videoCount - Number of video parts
   * @param priority - Priority level (default: 0)
   * @returns Array of created queue entries
   */
  async createSplitChapterEntries(
    mangaId: number,
    chapterId: number,
    chapterNumber: string,
    videoCount: number,
    priority: number = 0
  ): Promise<QueueEntry[]> {
    try {
      logger.info(`Creating ${videoCount} queue entries for split chapter ${chapterNumber}`);

      const queueEntries: QueueEntry[] = [];

      // Create one queue entry for each video part
      for (let partNumber = 1; partNumber <= videoCount; partNumber++) {
        const insertResult = await db.query(
          `INSERT INTO chapter_posting_queue 
           (manga_id, chapter_id, chapter_number, priority, status, part_number, total_parts)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           ON CONFLICT (chapter_id, part_number) 
           DO UPDATE SET 
             priority = EXCLUDED.priority,
             total_parts = EXCLUDED.total_parts,
             updated_at = NOW()
           RETURNING *`,
          [mangaId, chapterId, chapterNumber, priority, QueueStatus.PENDING, partNumber, videoCount]
        );

        queueEntries.push(insertResult.rows[0]);
      }

      logger.info(`Created ${queueEntries.length} queue entries for split chapter ${chapterNumber}`);
      return queueEntries;
    } catch (error) {
      logger.error(`Error creating split chapter entries`, { error, mangaId, chapterId, chapterNumber, videoCount });
      throw error;
    }
  }

  /**
   * Calculate queue position for a chapter based on priority and chapter_number
   * Position is determined by counting how many pending chapters come before it
   * @param priority - The priority of the chapter
   * @param chapterNumber - The chapter number
   * @returns Queue position (1-indexed)
   */
  async calculateQueuePosition(priority: number, chapterNumber: string): Promise<number> {
    try {
      // Count how many pending chapters come before this one
      // Higher priority comes first, then lower chapter_number
      const result = await db.query(
        `SELECT COUNT(*) as position 
         FROM chapter_posting_queue 
         WHERE status = $1 
           AND (priority > $2 OR (priority = $2 AND chapter_number < $3))`,
        [QueueStatus.PENDING, priority, chapterNumber]
      );

      // Position is count + 1 (1-indexed)
      return Number(result.rows[0]?.position || 0) + 1;
    } catch (error) {
      logger.error(`Error calculating queue position`, { error, priority, chapterNumber });
      throw error;
    }
  }
}

// Export singleton instance
export const queueManager = new QueueManager();
