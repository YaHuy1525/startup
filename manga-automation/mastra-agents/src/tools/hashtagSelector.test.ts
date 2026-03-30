import * as fc from 'fast-check';
import { HashtagSelector, HashtagTier, Hashtag } from './hashtagSelector';
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

describe('HashtagSelector Property Tests', () => {
  let hashtagSelector: HashtagSelector;

  beforeEach(() => {
    hashtagSelector = new HashtagSelector();
    jest.clearAllMocks();
  });

  // Feature: manga-automation-improvements, Property 20: Hashtag composition compliance
  // **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
  test('Property 20: Selected hashtag set contains exactly 1 mega, 2-3 core, 1-2 niche, total 3-5', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate hashtag request
        fc.record({
          mangaTitle: fc.string({ minLength: 3, maxLength: 50 }),
          genre: fc.constantFrom('action', 'romance', 'comedy', 'drama', 'fantasy'),
          emotionalTone: fc.option(fc.constantFrom('sad', 'exciting', 'funny', 'intense'), { nil: undefined }),
          isRecommendation: fc.boolean(),
        }),
        async (request) => {
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // Mock mega hashtags (tier 1)
          const megaHashtags: Hashtag[] = [
            { id: 1, tag: '#fyp', tier: HashtagTier.MEGA, category: 'general', views_estimate: 1000000000000 },
            { id: 2, tag: '#foryou', tier: HashtagTier.MEGA, category: 'general', views_estimate: 900000000000 },
          ];

          // Mock core hashtags (tier 2)
          const coreHashtags: Hashtag[] = [
            { id: 3, tag: '#manga', tier: HashtagTier.CORE, category: 'general', views_estimate: 50000000000 },
            { id: 4, tag: '#anime', tier: HashtagTier.CORE, category: 'general', views_estimate: 100000000000 },
            { id: 5, tag: '#animetiktok', tier: HashtagTier.CORE, category: 'general', views_estimate: 30000000000 },
          ];

          // Mock niche hashtags (tier 3)
          const nicheHashtags: Hashtag[] = [
            { id: 6, tag: '#shonen', tier: HashtagTier.NICHE, category: 'action', views_estimate: 10000000000 },
            { id: 7, tag: '#shoujo', tier: HashtagTier.NICHE, category: 'romance', views_estimate: 5000000000 },
          ];

          // Mock specific hashtags (tier 4)
          const specificHashtags: Hashtag[] = [
            { id: 8, tag: '#onepiece', tier: HashtagTier.SPECIFIC, category: 'action', views_estimate: 8000000000 },
            { id: 9, tag: '#naruto', tier: HashtagTier.SPECIFIC, category: 'action', views_estimate: 7000000000 },
          ];

          // Setup mock responses for each tier query
          mockDbQuery
            .mockResolvedValueOnce({ rows: megaHashtags, command: 'SELECT', rowCount: megaHashtags.length, oid: 0, fields: [] })
            .mockResolvedValueOnce({ rows: coreHashtags, command: 'SELECT', rowCount: coreHashtags.length, oid: 0, fields: [] })
            .mockResolvedValueOnce({ rows: nicheHashtags, command: 'SELECT', rowCount: nicheHashtags.length, oid: 0, fields: [] })
            .mockResolvedValueOnce({ rows: specificHashtags, command: 'SELECT', rowCount: specificHashtags.length, oid: 0, fields: [] });

          // Select hashtags
          const selectedTags = await hashtagSelector.selectHashtags(request);

          // Property 1: Total hashtags should be between 3 and 5
          expect(selectedTags.length).toBeGreaterThanOrEqual(3);
          expect(selectedTags.length).toBeLessThanOrEqual(5);

          // Property 2: Should contain exactly 1 mega hashtag
          const megaCount = selectedTags.filter(tag => 
            megaHashtags.some(h => h.tag === tag)
          ).length;
          expect(megaCount).toBe(1);

          // Property 3: Should contain 2-3 core hashtags
          const coreCount = selectedTags.filter(tag => 
            coreHashtags.some(h => h.tag === tag)
          ).length;
          expect(coreCount).toBeGreaterThanOrEqual(2);
          expect(coreCount).toBeLessThanOrEqual(3);

          // Property 4: Should contain 1-2 niche/specific hashtags
          const nicheCount = selectedTags.filter(tag => 
            [...nicheHashtags, ...specificHashtags].some(h => h.tag === tag)
          ).length;
          expect(nicheCount).toBeGreaterThanOrEqual(1);
          expect(nicheCount).toBeLessThanOrEqual(2);

          // Property 5: All tags should be unique
          const uniqueTags = new Set(selectedTags);
          expect(uniqueTags.size).toBe(selectedTags.length);

          // Property 6: All tags should start with #
          selectedTags.forEach(tag => {
            expect(tag).toMatch(/^#/);
          });
        }
      ),
      { numRuns: 100 }
    );
  });

  // Feature: manga-automation-improvements, Property 21: Genre-specific hashtag selection
  // **Validates: Requirements 7.6**
  test('Property 21: Different manga genres result in genre-specific hashtags', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate hashtag request with specific genre
        fc.record({
          mangaTitle: fc.string({ minLength: 3, maxLength: 50 }),
          genre: fc.constantFrom('action', 'romance', 'comedy', 'drama', 'fantasy'),
        }),
        async (request) => {
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // Mock mega hashtags (tier 1)
          const megaHashtags: Hashtag[] = [
            { id: 1, tag: '#fyp', tier: HashtagTier.MEGA, category: 'general', views_estimate: 1000000000000 },
          ];

          // Mock core hashtags (tier 2)
          const coreHashtags: Hashtag[] = [
            { id: 3, tag: '#manga', tier: HashtagTier.CORE, category: 'general', views_estimate: 50000000000 },
            { id: 4, tag: '#anime', tier: HashtagTier.CORE, category: 'general', views_estimate: 100000000000 },
          ];

          // Mock genre-specific niche hashtags - each genre has its own hashtag
          const nicheHashtags: Hashtag[] = [
            { id: 6, tag: '#shonen', tier: HashtagTier.NICHE, category: 'action', views_estimate: 10000000000 },
            { id: 7, tag: '#shoujo', tier: HashtagTier.NICHE, category: 'romance', views_estimate: 5000000000 },
            { id: 8, tag: '#comedymanga', tier: HashtagTier.NICHE, category: 'comedy', views_estimate: 4000000000 },
            { id: 9, tag: '#dramamanga', tier: HashtagTier.NICHE, category: 'drama', views_estimate: 3000000000 },
            { id: 10, tag: '#fantasymanga', tier: HashtagTier.NICHE, category: 'fantasy', views_estimate: 6000000000 },
            { id: 11, tag: '#general', tier: HashtagTier.NICHE, category: 'general', views_estimate: 2000000000 },
          ];

          const specificHashtags: Hashtag[] = [];

          // Setup mock responses
          mockDbQuery
            .mockResolvedValueOnce({ rows: megaHashtags, command: 'SELECT', rowCount: megaHashtags.length, oid: 0, fields: [] })
            .mockResolvedValueOnce({ rows: coreHashtags, command: 'SELECT', rowCount: coreHashtags.length, oid: 0, fields: [] })
            .mockResolvedValueOnce({ rows: nicheHashtags, command: 'SELECT', rowCount: nicheHashtags.length, oid: 0, fields: [] })
            .mockResolvedValueOnce({ rows: specificHashtags, command: 'SELECT', rowCount: specificHashtags.length, oid: 0, fields: [] });

          const selectedTags = await hashtagSelector.selectHashtags(request);

          // Property: When genre-specific hashtags exist, the selector should consider them
          // The algorithm filters by genre, so genre-specific hashtags should be prioritized
          
          // Get the genre-specific hashtags that match the request genre
          const genreSpecificHashtags = nicheHashtags.filter(h => 
            h.category.toLowerCase() === request.genre.toLowerCase()
          );

          // If genre-specific hashtags exist, at least one should be selected
          // (since the algorithm filters by genre first)
          if (genreSpecificHashtags.length > 0) {
            const hasGenreSpecific = selectedTags.some(tag => 
              genreSpecificHashtags.some(h => h.tag === tag)
            );
            
            // Property: Genre-specific hashtags should be selected when available
            expect(hasGenreSpecific).toBe(true);
          }

          // Property: All selected tags should be valid hashtags
          selectedTags.forEach(tag => {
            expect(tag).toMatch(/^#/);
          });
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('HashtagSelector Unit Tests - Edge Cases', () => {
  let hashtagSelector: HashtagSelector;

  beforeEach(() => {
    hashtagSelector = new HashtagSelector();
    jest.clearAllMocks();
  });

  test('Empty hashtag database returns empty array', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    // Mock empty responses for all tiers
    mockDbQuery
      .mockResolvedValueOnce({ rows: [], command: 'SELECT', rowCount: 0, oid: 0, fields: [] })
      .mockResolvedValueOnce({ rows: [], command: 'SELECT', rowCount: 0, oid: 0, fields: [] })
      .mockResolvedValueOnce({ rows: [], command: 'SELECT', rowCount: 0, oid: 0, fields: [] })
      .mockResolvedValueOnce({ rows: [], command: 'SELECT', rowCount: 0, oid: 0, fields: [] });

    const tags = await hashtagSelector.selectHashtags({
      mangaTitle: 'One Piece',
      genre: 'action',
    });

    // Should return empty array when no hashtags available
    expect(tags).toEqual([]);
  });

  test('Single tier available uses only that tier', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    // Only mega hashtags available
    const megaHashtags: Hashtag[] = [
      { id: 1, tag: '#fyp', tier: HashtagTier.MEGA, category: 'general', views_estimate: 1000000000000 },
    ];

    mockDbQuery
      .mockResolvedValueOnce({ rows: megaHashtags, command: 'SELECT', rowCount: 1, oid: 0, fields: [] })
      .mockResolvedValueOnce({ rows: [], command: 'SELECT', rowCount: 0, oid: 0, fields: [] })
      .mockResolvedValueOnce({ rows: [], command: 'SELECT', rowCount: 0, oid: 0, fields: [] })
      .mockResolvedValueOnce({ rows: [], command: 'SELECT', rowCount: 0, oid: 0, fields: [] });

    const tags = await hashtagSelector.selectHashtags({
      mangaTitle: 'Naruto',
      genre: 'action',
    });

    // Should only contain the mega hashtag
    expect(tags.length).toBe(1);
    expect(tags[0]).toBe('#fyp');
  });

  test('Genre not found uses general hashtags', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    const megaHashtags: Hashtag[] = [
      { id: 1, tag: '#fyp', tier: HashtagTier.MEGA, category: 'general', views_estimate: 1000000000000 },
    ];

    const coreHashtags: Hashtag[] = [
      { id: 3, tag: '#manga', tier: HashtagTier.CORE, category: 'general', views_estimate: 50000000000 },
      { id: 4, tag: '#anime', tier: HashtagTier.CORE, category: 'general', views_estimate: 100000000000 },
    ];

    // Niche hashtags with different genres
    const nicheHashtags: Hashtag[] = [
      { id: 6, tag: '#shonen', tier: HashtagTier.NICHE, category: 'action', views_estimate: 10000000000 },
      { id: 7, tag: '#shoujo', tier: HashtagTier.NICHE, category: 'romance', views_estimate: 5000000000 },
    ];

    const specificHashtags: Hashtag[] = [];

    mockDbQuery
      .mockResolvedValueOnce({ rows: megaHashtags, command: 'SELECT', rowCount: 1, oid: 0, fields: [] })
      .mockResolvedValueOnce({ rows: coreHashtags, command: 'SELECT', rowCount: 2, oid: 0, fields: [] })
      .mockResolvedValueOnce({ rows: nicheHashtags, command: 'SELECT', rowCount: 2, oid: 0, fields: [] })
      .mockResolvedValueOnce({ rows: specificHashtags, command: 'SELECT', rowCount: 0, oid: 0, fields: [] });

    const tags = await hashtagSelector.selectHashtags({
      mangaTitle: 'Unknown Manga',
      genre: 'unknown_genre', // Genre not in database
    });

    // Should still return hashtags (fallback to available niche hashtags)
    expect(tags.length).toBeGreaterThanOrEqual(3);
    expect(tags.length).toBeLessThanOrEqual(5);
    
    // Should contain mega and core hashtags
    expect(tags).toContain('#fyp');
    expect(tags.some(tag => ['#manga', '#anime'].includes(tag))).toBe(true);
  });

  test('trackPerformance updates hashtag usage and views', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    mockDbQuery.mockResolvedValueOnce({
      command: 'UPDATE',
      rowCount: 1,
      oid: 0,
      fields: [],
      rows: [],
    });

    await hashtagSelector.trackPerformance('#fyp', 10000, 500);

    // Verify UPDATE query was called with correct parameters
    expect(mockDbQuery).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE hashtags'),
      ['#fyp', 10000]
    );
  });

  test('getHashtagsByTier returns hashtags ordered by views', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    const hashtags: Hashtag[] = [
      { id: 1, tag: '#fyp', tier: HashtagTier.MEGA, category: 'general', views_estimate: 1000000000000 },
      { id: 2, tag: '#foryou', tier: HashtagTier.MEGA, category: 'general', views_estimate: 900000000000 },
    ];

    mockDbQuery.mockResolvedValueOnce({
      rows: hashtags,
      command: 'SELECT',
      rowCount: 2,
      oid: 0,
      fields: [],
    });

    const result = await hashtagSelector.getHashtagsByTier(HashtagTier.MEGA);

    // Verify query includes ORDER BY views_estimate DESC
    expect(mockDbQuery).toHaveBeenCalledWith(
      expect.stringContaining('ORDER BY views_estimate DESC'),
      [HashtagTier.MEGA]
    );

    expect(result).toEqual(hashtags);
  });
});
