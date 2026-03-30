import * as fc from 'fast-check';
import { CaptionGenerator, FormulaType } from './captionGenerator';
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

describe('CaptionGenerator Property Tests', () => {
  let captionGenerator: CaptionGenerator;

  beforeEach(() => {
    captionGenerator = new CaptionGenerator();
    jest.clearAllMocks();
  });

  // Feature: manga-automation-improvements, Property 18: Caption formula randomization
  // **Validates: Requirements 6.6**
  test('Property 18: Multiple caption generations without specified formulas use different formulas', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate array of caption requests
        fc.array(
          fc.record({
            mangaTitle: fc.string({ minLength: 3, maxLength: 50 }),
            chapterNumber: fc.integer({ min: 1, max: 500 }).map(n => n.toString()),
            genre: fc.constantFrom('action', 'romance', 'comedy', 'drama', 'fantasy'),
          }),
          { minLength: 10, maxLength: 20 }
        ),
        async (requests) => {
          const mockDbQuery = db.query as jest.MockedFunction<any>;
          const formulaTypes = Object.values(FormulaType);
          const usedFormulas = new Set<FormulaType>();

          // For each request, mock a random formula response
          for (let i = 0; i < requests.length; i++) {
            const randomFormulaType = formulaTypes[i % formulaTypes.length];
            
            mockDbQuery.mockResolvedValueOnce({
              rows: [{
                id: i + 1,
                formula_type: randomFormulaType,
                template: `Test template for {manga} chapter {chapter}`,
                emoji_suggestions: ['😊', '🔥', '💯'],
              }],
              command: 'SELECT',
              rowCount: 1,
              oid: 0,
              fields: [],
            });

            const caption = await captionGenerator.generateCaption(requests[i]);
            usedFormulas.add(caption.formula);
          }

          // Property: Multiple different formulas should be used across the sequence
          // With 10-20 requests and 5 formula types, we should see at least 2 different formulas
          expect(usedFormulas.size).toBeGreaterThanOrEqual(2);

          // Verify that getRandomFormula was called (ORDER BY RANDOM())
          const randomCalls = mockDbQuery.mock.calls.filter(
            (call: any) => typeof call[0] === 'string' && call[0].includes('ORDER BY RANDOM()')
          );
          expect(randomCalls.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  // Feature: manga-automation-improvements, Property 19: Emoji count constraint
  // **Validates: Requirements 6.7**
  test('Property 19: Generated captions contain between 1 and 3 emojis', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate caption request
        fc.record({
          mangaTitle: fc.string({ minLength: 3, maxLength: 50 }),
          chapterNumber: fc.integer({ min: 1, max: 500 }).map(n => n.toString()),
          genre: fc.constantFrom('action', 'romance', 'comedy', 'drama', 'fantasy'),
          formulaType: fc.constantFrom(...Object.values(FormulaType)),
        }),
        // Generate emoji suggestions (3-10 emojis)
        fc.array(
          fc.constantFrom('😊', '🔥', '💯', '😭', '💔', '🤔', '❤️', '👇', '📚', '🎉'),
          { minLength: 3, maxLength: 10 }
        ),
        async (request, emojiSuggestions) => {
          const mockDbQuery = db.query as jest.MockedFunction<any>;

          // Mock formula response
          mockDbQuery.mockResolvedValueOnce({
            rows: [{
              id: 1,
              formula_type: request.formulaType,
              template: `{manga} chapter {chapter} is amazing`,
              emoji_suggestions: emojiSuggestions,
            }],
            command: 'SELECT',
            rowCount: 1,
            oid: 0,
            fields: [],
          });

          // Generate caption
          const caption = await captionGenerator.generateCaption(request);

          // Property: Caption should contain between 1 and 3 emojis
          expect(caption.emojis.length).toBeGreaterThanOrEqual(1);
          expect(caption.emojis.length).toBeLessThanOrEqual(3);

          // Property: All selected emojis should be from the suggestions
          caption.emojis.forEach(emoji => {
            expect(emojiSuggestions).toContain(emoji);
          });

          // Property: Caption text should contain the selected emojis
          caption.emojis.forEach(emoji => {
            expect(caption.text).toContain(emoji);
          });
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('CaptionGenerator Unit Tests - Edge Cases', () => {
  let captionGenerator: CaptionGenerator;

  beforeEach(() => {
    captionGenerator = new CaptionGenerator();
    jest.clearAllMocks();
  });

  test('Empty manga title uses fallback', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    // Mock formula response
    mockDbQuery.mockResolvedValueOnce({
      rows: [{
        id: 1,
        formula_type: FormulaType.EMOTIONAL_HOOK,
        template: 'This scene from {manga} broke me',
        emoji_suggestions: ['💔', '😭'],
      }],
      command: 'SELECT',
      rowCount: 1,
      oid: 0,
      fields: [],
    });

    const caption = await captionGenerator.generateCaption({
      mangaTitle: '',
      chapterNumber: '5',
      genre: 'action',
    });

    // Should use fallback "this manga" when manga title is empty
    expect(caption.text).toContain('this manga');
    expect(caption.emojis.length).toBeGreaterThanOrEqual(1);
    expect(caption.emojis.length).toBeLessThanOrEqual(3);
  });

  test('Missing emoji suggestions uses defaults', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    // Mock formula response with empty emoji suggestions
    mockDbQuery.mockResolvedValueOnce({
      rows: [{
        id: 1,
        formula_type: FormulaType.RECOMMENDATION,
        template: 'You NEED to read {manga}',
        emoji_suggestions: [],
      }],
      command: 'SELECT',
      rowCount: 1,
      oid: 0,
      fields: [],
    });

    const caption = await captionGenerator.generateCaption({
      mangaTitle: 'One Piece',
      chapterNumber: '1000',
      genre: 'action',
    });

    // Should use default emoji when suggestions are empty
    expect(caption.emojis.length).toBeGreaterThanOrEqual(1);
    expect(caption.emojis).toContain('📚');
    expect(caption.text).toContain('📚');
  });

  test('Invalid formula type falls back to random', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    // First call: getFormulaByType returns empty (no formula found)
    mockDbQuery.mockResolvedValueOnce({
      rows: [],
      command: 'SELECT',
      rowCount: 0,
      oid: 0,
      fields: [],
    });

    // Second call: getRandomFormula returns a formula
    mockDbQuery.mockResolvedValueOnce({
      rows: [{
        id: 1,
        formula_type: FormulaType.STATEMENT_EMOJI,
        template: '{manga} hits different',
        emoji_suggestions: ['🔥', '💯'],
      }],
      command: 'SELECT',
      rowCount: 1,
      oid: 0,
      fields: [],
    });

    const caption = await captionGenerator.generateCaption({
      mangaTitle: 'Naruto',
      chapterNumber: '700',
      genre: 'action',
      formulaType: 'invalid_type' as FormulaType,
    });

    // Should fall back to random formula
    expect(caption.text).toContain('Naruto');
    expect(caption.formula).toBe(FormulaType.STATEMENT_EMOJI);
    expect(caption.emojis.length).toBeGreaterThanOrEqual(1);
    expect(caption.emojis.length).toBeLessThanOrEqual(3);

    // Verify fallback was triggered
    const calls = mockDbQuery.mock.calls;
    expect(calls.length).toBe(2); // First call failed, second call succeeded
  });

  test('Template with {emoji} placeholder inserts emojis correctly', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    // Mock formula with {emoji} placeholder
    mockDbQuery.mockResolvedValueOnce({
      rows: [{
        id: 1,
        formula_type: FormulaType.EMOTIONAL_HOOK,
        template: '{manga} chapter {chapter} {emoji}',
        emoji_suggestions: ['💔', '😭', '🥺'],
      }],
      command: 'SELECT',
      rowCount: 1,
      oid: 0,
      fields: [],
    });

    const caption = await captionGenerator.generateCaption({
      mangaTitle: 'Attack on Titan',
      chapterNumber: '139',
      genre: 'action',
    });

    // Should replace {emoji} placeholder with selected emojis
    expect(caption.text).toContain('Attack on Titan');
    expect(caption.text).toContain('139');
    expect(caption.text).not.toContain('{emoji}');
    
    // Should contain at least one of the selected emojis
    const hasEmoji = caption.emojis.some(emoji => caption.text.includes(emoji));
    expect(hasEmoji).toBe(true);
  });

  test('Template without {emoji} placeholder appends emojis at end', async () => {
    const mockDbQuery = db.query as jest.MockedFunction<any>;

    // Mock formula without {emoji} placeholder
    mockDbQuery.mockResolvedValueOnce({
      rows: [{
        id: 1,
        formula_type: FormulaType.QUESTION,
        template: 'Who is your favorite character in {manga}?',
        emoji_suggestions: ['🤔', '❤️', '👇'],
      }],
      command: 'SELECT',
      rowCount: 1,
      oid: 0,
      fields: [],
    });

    const caption = await captionGenerator.generateCaption({
      mangaTitle: 'My Hero Academia',
      chapterNumber: '350',
      genre: 'action',
    });

    // Should append emojis at the end
    expect(caption.text).toContain('My Hero Academia');
    
    // Emojis should be at the end of the text
    const textWithoutEmojis = 'Who is your favorite character in My Hero Academia?';
    expect(caption.text).toContain(textWithoutEmojis);
    
    // Should contain the selected emojis
    caption.emojis.forEach(emoji => {
      expect(caption.text).toContain(emoji);
    });
  });
});
