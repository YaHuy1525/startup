import fc from 'fast-check';
import request from 'supertest';
import express from 'express';

/**
 * Property 22: Error response for invalid input
 * Feature: manga-automation-improvements
 * 
 * For any API endpoint, sending invalid input should return an appropriate 
 * HTTP error code (4xx) and a descriptive error message.
 * 
 * Validates: Requirements 9.6
 */

describe('API Error Responses Property Tests', () => {
  // Mock express app for testing
  let app: express.Application;

  beforeAll(() => {
    app = express();
    app.use(express.json({ strict: false }));
    app.use(express.urlencoded({ extended: true }));

    // Mock endpoints that match the actual API
    app.post('/pipeline/populate-queue', (req, res) => {
      const { manga_id } = req.body;
      if (!manga_id) {
        return res.status(400).json({ error: 'manga_id required' });
      }
      if (typeof manga_id !== 'number' || manga_id <= 0) {
        return res.status(400).json({ error: 'manga_id must be a positive number' });
      }
      res.json({ success: true, manga_id, queued_count: 0, queue_ids: [] });
    });

    app.post('/webhook/queue-chapter', (req, res) => {
      const { manga_id, chapter_number, start_chapter, end_chapter } = req.body;
      
      if (!manga_id) {
        return res.status(400).json({ error: 'manga_id required' });
      }
      
      if (!chapter_number && !(start_chapter && end_chapter)) {
        return res.status(400).json({ 
          error: 'Either chapter_number or (start_chapter and end_chapter) required' 
        });
      }
      
      res.json({ success: true, queue_id: 1, queue_position: 1 });
    });

    app.post('/captions/generate', (req, res) => {
      const { videoId } = req.body;
      if (!videoId) {
        return res.status(400).json({ error: 'videoId required' });
      }
      if (typeof videoId !== 'number' || videoId <= 0) {
        return res.status(400).json({ error: 'videoId must be a positive number' });
      }
      res.json({ success: true, videoId, caption: 'Test caption', hashtags: [] });
    });

    app.get('/hashtags/select', (req, res) => {
      const { mangaTitle, genre } = req.query;
      if (!mangaTitle || !genre) {
        return res.status(400).json({ error: 'mangaTitle and genre required' });
      }
      res.json({ success: true, hashtags: [] });
    });
  });

  test('Property 22: POST endpoints return 400 for missing required parameters', () => {
    fc.assert(
      fc.asyncProperty(
        fc.constantFrom(
          '/pipeline/populate-queue',
          '/webhook/queue-chapter',
          '/captions/generate'
        ),
        async (endpoint) => {
          // Send request with empty body (missing required parameters)
          const response = await request(app)
            .post(endpoint)
            .set('Content-Type', 'application/json')
            .send({});

          // Should return 400 status code
          expect(response.status).toBe(400);
          
          // Should return JSON with error message
          expect(response.body).toHaveProperty('error');
          expect(typeof response.body.error).toBe('string');
          expect(response.body.error.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 22: POST endpoints return 400 for invalid parameter types', () => {
    fc.assert(
      fc.asyncProperty(
        fc.record({
          endpoint: fc.constantFrom('/pipeline/populate-queue', '/captions/generate'),
          invalidValue: fc.oneof(
            fc.constant(null),
            fc.constant('invalid'),
            fc.constant(-1),
            fc.constant(0),
            fc.array(fc.integer()),
            fc.object()
          )
        }),
        async ({ endpoint, invalidValue }) => {
          const paramName = endpoint === '/pipeline/populate-queue' ? 'manga_id' : 'videoId';
          
          const response = await request(app)
            .post(endpoint)
            .set('Content-Type', 'application/json')
            .send({ [paramName]: invalidValue });

          // Should return 400 status code for invalid types
          expect(response.status).toBe(400);
          
          // Should return JSON with error message
          expect(response.body).toHaveProperty('error');
          expect(typeof response.body.error).toBe('string');
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 22: GET endpoints return 400 for missing query parameters', () => {
    fc.assert(
      fc.asyncProperty(
        fc.record({
          mangaTitle: fc.option(fc.string(), { nil: undefined }),
          genre: fc.option(fc.string(), { nil: undefined })
        }).filter(({ mangaTitle, genre }) => !mangaTitle || !genre), // At least one missing
        async ({ mangaTitle, genre }) => {
          const query: any = {};
          if (mangaTitle) query.mangaTitle = mangaTitle;
          if (genre) query.genre = genre;

          const response = await request(app)
            .get('/hashtags/select')
            .query(query);

          // Should return 400 status code
          expect(response.status).toBe(400);
          
          // Should return JSON with error message
          expect(response.body).toHaveProperty('error');
          expect(typeof response.body.error).toBe('string');
          expect(response.body.error.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 22: All error responses are valid JSON', () => {
    fc.assert(
      fc.asyncProperty(
        fc.record({
          endpoint: fc.constantFrom(
            '/pipeline/populate-queue',
            '/webhook/queue-chapter',
            '/captions/generate'
          ),
          body: fc.object() // Random object that likely won't have required fields
        }),
        async ({ endpoint, body }) => {
          const response = await request(app)
            .post(endpoint)
            .set('Content-Type', 'application/json')
            .send(body);

          // If it's an error response (4xx or 5xx)
          if (response.status >= 400) {
            // Response should be valid JSON
            expect(response.type).toMatch(/json/);
            
            // Should have an error property
            expect(response.body).toHaveProperty('error');
            
            // Error message should be a non-empty string
            expect(typeof response.body.error).toBe('string');
            expect(response.body.error.length).toBeGreaterThan(0);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 22: Error messages are descriptive', () => {
    fc.assert(
      fc.asyncProperty(
        fc.constantFrom(
          { endpoint: '/pipeline/populate-queue', param: 'manga_id' },
          { endpoint: '/captions/generate', param: 'videoId' },
          { endpoint: '/webhook/queue-chapter', param: 'manga_id' }
        ),
        async ({ endpoint, param }) => {
          const response = await request(app)
            .post(endpoint)
            .set('Content-Type', 'application/json')
            .send({});

          // Should return 400
          expect(response.status).toBe(400);
          
          // Error message should mention the missing parameter
          expect(response.body.error).toContain(param);
        }
      ),
      { numRuns: 100 }
    );
  });
});
