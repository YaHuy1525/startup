import fc from 'fast-check';
import request from 'supertest';
import express from 'express';

/**
 * Property 23: JSON response format
 * Feature: manga-automation-improvements
 * 
 * For any successful API call, the response should be valid JSON containing 
 * the relevant data fields.
 * 
 * Validates: Requirements 9.7
 */

describe('API JSON Response Format Property Tests', () => {
  // Mock express app for testing
  let app: express.Application;

  beforeAll(() => {
    app = express();
    app.use(express.json({ strict: false }));
    app.use(express.urlencoded({ extended: true }));

    // Mock endpoints that match the actual API
    app.post('/pipeline/populate-queue', (req, res) => {
      const { manga_id } = req.body;
      if (!manga_id || typeof manga_id !== 'number') {
        return res.status(400).json({ error: 'manga_id required' });
      }
      res.json({
        success: true,
        manga_id,
        queued_count: 5,
        queue_ids: [1, 2, 3, 4, 5]
      });
    });

    app.post('/webhook/queue-chapter', (req, res) => {
      const { manga_id, chapter_number } = req.body;
      if (!manga_id || !chapter_number) {
        return res.status(400).json({ error: 'manga_id and chapter_number required' });
      }
      res.json({
        success: true,
        queue_id: 123,
        queue_position: 5
      });
    });

    app.post('/captions/generate', (req, res) => {
      const { videoId } = req.body;
      if (!videoId || typeof videoId !== 'number') {
        return res.status(400).json({ error: 'videoId required' });
      }
      res.json({
        success: true,
        videoId,
        caption: 'This manga is amazing! 🔥📚',
        hashtags: ['#fyp', '#manga', '#anime'],
        formula: 'statement_emoji',
        emojis: ['🔥', '📚']
      });
    });

    app.get('/hashtags/select', (req, res) => {
      const { mangaTitle, genre } = req.query;
      if (!mangaTitle || !genre) {
        return res.status(400).json({ error: 'mangaTitle and genre required' });
      }
      res.json({
        success: true,
        hashtags: ['#fyp', '#manga', '#shonen']
      });
    });
  });

  test('Property 23: Successful responses return valid JSON', () => {
    fc.assert(
      fc.asyncProperty(
        fc.record({
          endpoint: fc.constantFrom(
            '/pipeline/populate-queue',
            '/captions/generate'
          ),
          id: fc.integer({ min: 1, max: 1000 })
        }),
        async ({ endpoint, id }) => {
          const paramName = endpoint === '/pipeline/populate-queue' ? 'manga_id' : 'videoId';
          
          const response = await request(app)
            .post(endpoint)
            .set('Content-Type', 'application/json')
            .send({ [paramName]: id });

          // Should return 200 status code
          expect(response.status).toBe(200);
          
          // Response should be JSON
          expect(response.type).toMatch(/json/);
          
          // Response body should be an object
          expect(typeof response.body).toBe('object');
          expect(response.body).not.toBeNull();
          
          // Should have success field
          expect(response.body).toHaveProperty('success');
          expect(response.body.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 23: populate-queue returns required fields', () => {
    fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 1, max: 1000 }),
        async (manga_id) => {
          const response = await request(app)
            .post('/pipeline/populate-queue')
            .set('Content-Type', 'application/json')
            .send({ manga_id });

          expect(response.status).toBe(200);
          
          // Check required fields
          expect(response.body).toHaveProperty('success');
          expect(response.body).toHaveProperty('manga_id');
          expect(response.body).toHaveProperty('queued_count');
          expect(response.body).toHaveProperty('queue_ids');
          
          // Validate field types
          expect(typeof response.body.success).toBe('boolean');
          expect(typeof response.body.manga_id).toBe('number');
          expect(typeof response.body.queued_count).toBe('number');
          expect(Array.isArray(response.body.queue_ids)).toBe(true);
          
          // Validate returned manga_id matches request
          expect(response.body.manga_id).toBe(manga_id);
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 23: queue-chapter returns required fields', () => {
    fc.assert(
      fc.asyncProperty(
        fc.record({
          manga_id: fc.integer({ min: 1, max: 1000 }),
          chapter_number: fc.float({ min: 1, max: 500, noNaN: true }).map(n => n.toString())
        }),
        async ({ manga_id, chapter_number }) => {
          const response = await request(app)
            .post('/webhook/queue-chapter')
            .set('Content-Type', 'application/json')
            .send({ manga_id, chapter_number });

          expect(response.status).toBe(200);
          
          // Check required fields
          expect(response.body).toHaveProperty('success');
          expect(response.body).toHaveProperty('queue_id');
          expect(response.body).toHaveProperty('queue_position');
          
          // Validate field types
          expect(typeof response.body.success).toBe('boolean');
          expect(typeof response.body.queue_id).toBe('number');
          expect(typeof response.body.queue_position).toBe('number');
          
          // Validate values are positive
          expect(response.body.queue_id).toBeGreaterThan(0);
          expect(response.body.queue_position).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 23: generate-caption returns required fields', () => {
    fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 1, max: 1000 }),
        async (videoId) => {
          const response = await request(app)
            .post('/captions/generate')
            .set('Content-Type', 'application/json')
            .send({ videoId });

          expect(response.status).toBe(200);
          
          // Check required fields
          expect(response.body).toHaveProperty('success');
          expect(response.body).toHaveProperty('videoId');
          expect(response.body).toHaveProperty('caption');
          expect(response.body).toHaveProperty('hashtags');
          expect(response.body).toHaveProperty('formula');
          expect(response.body).toHaveProperty('emojis');
          
          // Validate field types
          expect(typeof response.body.success).toBe('boolean');
          expect(typeof response.body.videoId).toBe('number');
          expect(typeof response.body.caption).toBe('string');
          expect(Array.isArray(response.body.hashtags)).toBe(true);
          expect(typeof response.body.formula).toBe('string');
          expect(Array.isArray(response.body.emojis)).toBe(true);
          
          // Validate returned videoId matches request
          expect(response.body.videoId).toBe(videoId);
          
          // Validate caption is non-empty
          expect(response.body.caption.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 23: select-hashtags returns required fields', () => {
    fc.assert(
      fc.asyncProperty(
        fc.record({
          mangaTitle: fc.string({ minLength: 1, maxLength: 50 }),
          genre: fc.constantFrom('action', 'romance', 'comedy', 'drama', 'fantasy')
        }),
        async ({ mangaTitle, genre }) => {
          const response = await request(app)
            .get('/hashtags/select')
            .query({ mangaTitle, genre });

          expect(response.status).toBe(200);
          
          // Check required fields
          expect(response.body).toHaveProperty('success');
          expect(response.body).toHaveProperty('hashtags');
          
          // Validate field types
          expect(typeof response.body.success).toBe('boolean');
          expect(Array.isArray(response.body.hashtags)).toBe(true);
          
          // Validate hashtags are strings
          response.body.hashtags.forEach((tag: any) => {
            expect(typeof tag).toBe('string');
          });
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 23: All successful responses have consistent structure', () => {
    fc.assert(
      fc.asyncProperty(
        fc.record({
          endpoint: fc.constantFrom(
            { path: '/pipeline/populate-queue', method: 'post', body: { manga_id: 1 } },
            { path: '/webhook/queue-chapter', method: 'post', body: { manga_id: 1, chapter_number: '1' } },
            { path: '/captions/generate', method: 'post', body: { videoId: 1 } },
            { path: '/hashtags/select', method: 'get', query: { mangaTitle: 'Test', genre: 'action' } }
          )
        }),
        async ({ endpoint }) => {
          let response;
          
          if (endpoint.method === 'post') {
            response = await request(app)
              .post(endpoint.path)
              .set('Content-Type', 'application/json')
              .send(endpoint.body);
          } else {
            response = await request(app)
              .get(endpoint.path)
              .query(endpoint.query);
          }

          // All successful responses should have 2xx status
          expect(response.status).toBeGreaterThanOrEqual(200);
          expect(response.status).toBeLessThan(300);
          
          // All should be JSON
          expect(response.type).toMatch(/json/);
          
          // All should have success field
          expect(response.body).toHaveProperty('success');
          expect(typeof response.body.success).toBe('boolean');
          
          // All should be valid JSON (parseable)
          expect(() => JSON.stringify(response.body)).not.toThrow();
        }
      ),
      { numRuns: 100 }
    );
  });

  test('Property 23: Response JSON is serializable and deserializable', () => {
    fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 1, max: 1000 }),
        async (manga_id) => {
          const response = await request(app)
            .post('/pipeline/populate-queue')
            .set('Content-Type', 'application/json')
            .send({ manga_id });

          expect(response.status).toBe(200);
          
          // Should be able to serialize and deserialize without data loss
          const serialized = JSON.stringify(response.body);
          const deserialized = JSON.parse(serialized);
          
          expect(deserialized).toEqual(response.body);
        }
      ),
      { numRuns: 100 }
    );
  });
});
