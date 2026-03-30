import { db, logger } from './database';

// ─── Interfaces ──────────────────────────────────────────────────────────────

export enum HashtagTier {
  MEGA = 1,      // #fyp, #foryou
  CORE = 2,      // #manga, #anime, #animetiktok
  NICHE = 3,     // #mangarecommendation, #shonen
  SPECIFIC = 4   // #onepiece, #naruto
}

export interface Hashtag {
  id: number;
  tag: string;
  tier: HashtagTier;
  category: string;
  views_estimate: number;
}

export interface HashtagRequest {
  mangaTitle: string;
  genre: string;
  emotionalTone?: string;
  isRecommendation?: boolean;
}

// ─── HashtagSelector Class ───────────────────────────────────────────────────

export class HashtagSelector {
  /**
   * Select hashtags for video
   * @param request - Hashtag selection request
   * @returns Array of selected hashtag strings
   */
  async selectHashtags(request: HashtagRequest): Promise<string[]> {
    try {
      logger.info(`Selecting hashtags for ${request.mangaTitle} (${request.genre})`);

      const selectedTags: string[] = [];

      // Select exactly 1 mega hashtag (tier 1)
      const megaHashtags = await this.getHashtagsByTier(HashtagTier.MEGA);
      if (megaHashtags.length > 0) {
        const megaTag = megaHashtags[Math.floor(Math.random() * megaHashtags.length)];
        selectedTags.push(megaTag.tag);
      }

      // Select 2-3 core hashtags (tier 2)
      const coreHashtags = await this.getHashtagsByTier(HashtagTier.CORE);
      const coreCount = Math.floor(Math.random() * 2) + 2; // 2 or 3
      const selectedCore = this.selectRandomTags(coreHashtags, coreCount);
      selectedTags.push(...selectedCore.map(h => h.tag));

      // Select 1-2 niche hashtags (tier 3 or 4)
      const nicheHashtags = await this.getHashtagsByTier(HashtagTier.NICHE);
      const specificHashtags = await this.getHashtagsByTier(HashtagTier.SPECIFIC);
      const combinedNiche = [...nicheHashtags, ...specificHashtags];
      
      // Filter by genre if possible
      const genreFiltered = combinedNiche.filter(h => 
        h.category.toLowerCase() === request.genre.toLowerCase() ||
        h.tag.toLowerCase().includes(request.genre.toLowerCase())
      );
      
      const nichePool = genreFiltered.length > 0 ? genreFiltered : combinedNiche;
      const nicheCount = Math.floor(Math.random() * 2) + 1; // 1 or 2
      const selectedNiche = this.selectRandomTags(nichePool, nicheCount);
      selectedTags.push(...selectedNiche.map(h => h.tag));

      // Ensure total is 3-5 hashtags
      const finalTags = selectedTags.slice(0, 5);

      logger.info(`Selected hashtags: ${finalTags.join(', ')}`);

      return finalTags;
    } catch (error) {
      logger.error('Error selecting hashtags', { error, request });
      throw error;
    }
  }

  /**
   * Get hashtags by tier
   * @param tier - Hashtag tier to retrieve
   * @returns Array of hashtags in the specified tier
   */
  async getHashtagsByTier(tier: HashtagTier): Promise<Hashtag[]> {
    try {
      const result = await db.query(
        `SELECT * FROM hashtags 
         WHERE tier = $1 
         ORDER BY views_estimate DESC`,
        [tier]
      );

      return result.rows;
    } catch (error) {
      logger.error('Error getting hashtags by tier', { error, tier });
      throw error;
    }
  }

  /**
   * Track hashtag performance
   * @param hashtag - Hashtag string (with #)
   * @param views - Number of views
   * @param engagement - Engagement metric
   */
  async trackPerformance(hashtag: string, views: number, engagement: number): Promise<void> {
    try {
      await db.query(
        `UPDATE hashtags 
         SET usage_count = usage_count + 1,
             avg_views = COALESCE(
               (avg_views * usage_count + $2) / (usage_count + 1),
               $2
             )
         WHERE tag = $1`,
        [hashtag, views]
      );

      logger.info(`Tracked performance for ${hashtag}: ${views} views`);
    } catch (error) {
      logger.error('Error tracking hashtag performance', { error, hashtag, views, engagement });
      throw error;
    }
  }

  /**
   * Select random tags from array
   * @param tags - Array of hashtags
   * @param count - Number of tags to select
   * @returns Array of randomly selected hashtags
   */
  private selectRandomTags(tags: Hashtag[], count: number): Hashtag[] {
    if (tags.length === 0) return [];
    
    const shuffled = [...tags].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, Math.min(count, tags.length));
  }
}

// Export singleton instance
export const hashtagSelector = new HashtagSelector();
