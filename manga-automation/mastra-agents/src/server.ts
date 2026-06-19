import 'dotenv/config';
import express, { Request, Response, NextFunction } from 'express';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { connectDatabases, logger } from './tools/database';
import { detectTrends } from './agents/trendDetector';
import { selectPanels } from './agents/panelSelector';
import { selectMusic } from './agents/musicSelector';
import { generateCaption } from './agents/captionGenerator';
import { optimizeContent } from './agents/contentOptimizer';
import { detectShadowBans } from './agents/shadowBanDetector';
import { fetchTrendingManga, fetchLatestChapter, fetchChapterPages, saveMangaChapter } from './tools/mangadex';
import { downloadPanels } from './tools/scraper';
import { db } from './tools/database';
import { queueManager, QueueStatus } from './tools/queueManager';
import { captionGenerator } from './tools/captionGenerator';
import { hashtagSelector } from './tools/hashtagSelector';
import { chapterAnalyzer } from './tools/chapterAnalyzer';
import cors from 'cors';
import { generateGigDraft } from './agents/gigDraftGenerator';
import { scoreGigDraft } from './agents/gigRubricScorer';
import { generateMangaScript } from './agents/scriptwriter';
import { createProductPromo, productPromoPropsSchema } from './agents/productPromoAgent';
import { isQwenPawBackend, qwenpawAgents, qwenpawChat, qwenpawStatus } from './qwenpaw';

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

const VIDEOS_DIR = process.env.VIDEOS_DIR || '/data/videos';
const REMOTION_DIR = path.join(__dirname, '../remotion-renderer');

// ─── Health Check ─────────────────────────────────────────────────────────────
app.get('/health', async (_req: Request, res: Response) => {
    try {
        await db.query('SELECT 1');
        res.json({ status: 'ok', service: 'manga-agents', timestamp: new Date().toISOString() });
    } catch {
        res.status(503).json({ status: 'error', message: 'DB unavailable' });
    }
});

// ─── Agent Endpoints ──────────────────────────────────────────────────────────

/** POST /agents/detect-trends
 * Queries MangaDex + AniList and saves top 20 trending manga to DB.
 */
app.post('/agents/detect-trends', async (_req: Request, res: Response) => {
    logger.info('Agent: detect-trends triggered');
    try {
        const result = await detectTrends();
        res.json({ success: true, result: result.text });
    } catch (err: any) {
        logger.error('detect-trends failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /agents/select-panels
 * Body: { chapterId: number }
 */
app.post('/agents/select-panels', async (req: Request, res: Response) => {
    const { chapterId } = req.body;
    if (!chapterId) return res.status(400).json({ error: 'chapterId required' });

    logger.info('Agent: select-panels triggered', { chapterId });
    try {
        const result = await selectPanels(Number(chapterId));
        res.json({ success: true, chapterId, result: result.text });
    } catch (err: any) {
        logger.error('select-panels failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /agents/select-music
 * Body: { chapterId: number }
 * Reads selected_panels for the chapter, picks a matching audio track from
 * data/music/<emotion>/, and saves the path to selected_panels.music_path.
 */
app.post('/agents/select-music', async (req: Request, res: Response) => {
    const { chapterId } = req.body;
    if (!chapterId) return res.status(400).json({ error: 'chapterId required' });

    logger.info('Agent: select-music triggered', { chapterId });
    try {
        const result = await selectMusic(Number(chapterId));
        res.json({ success: true, chapterId, result: result.text });
    } catch (err: any) {
        logger.error('select-music failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /agents/generate-caption
 * Body: { videoId: number }
 */
app.post('/agents/generate-caption', async (req: Request, res: Response) => {
    const { videoId } = req.body;
    if (!videoId) return res.status(400).json({ error: 'videoId required' });

    logger.info('Agent: generate-caption triggered', { videoId });
    try {
        const result = await generateCaption(Number(videoId));
        res.json({ success: true, videoId, result: result.text });
    } catch (err: any) {
        logger.error('generate-caption failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /agents/optimize
 * Analytics-based content optimizer.
 */
app.post('/agents/optimize', async (_req: Request, res: Response) => {
    logger.info('Agent: optimize triggered');
    try {
        const result = await optimizeContent();
        res.json({ success: true, result: result.text });
    } catch (err: any) {
        logger.error('optimize failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /agents/detect-shadow-ban
 * Analyses all active TikTok accounts for shadow ban signals.
 */
app.post('/agents/detect-shadow-ban', async (_req: Request, res: Response) => {
    logger.info('Agent: detect-shadow-ban triggered');
    try {
        const result = await detectShadowBans();
        res.json({ success: true, result: result.text });
    } catch (err: any) {
        logger.error('detect-shadow-ban failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /agents/manga-scriptwriter
 * Generates viral brainrot lore scripts
 * Body: { chapterText, chapterTitle, mangaSeries, trendingKeywords, styleWeights }
 */
app.post('/agents/manga-scriptwriter', async (req: Request, res: Response) => {
    const { chapterText, chapterTitle, mangaSeries, trendingKeywords, styleWeights } = req.body;
    if (!chapterText || !mangaSeries) return res.status(400).json({ error: 'chapterText and mangaSeries required' });

    logger.info('Agent: manga-scriptwriter triggered', { mangaSeries });
    try {
        const result = await generateMangaScript(chapterText, chapterTitle, mangaSeries, trendingKeywords, styleWeights);
        res.json({ success: true, script: result });
    } catch (err: any) {
        logger.error('manga-scriptwriter failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

// ─── Pipeline Endpoints (direct data operations) ──────────────────────────────

/** POST /pipeline/fetch-chapters
 * Fetches the latest chapter for each active trending manga and stores panels.
 */
app.post('/pipeline/fetch-chapters', async (_req: Request, res: Response) => {
    logger.info('Pipeline: fetch-chapters started');
    try {
        const mangaResult = await db.query(
            `SELECT id, title, mangadex_id FROM manga
             WHERE is_active = true AND mangadex_id IS NOT NULL
             ORDER BY trending_score DESC LIMIT 20`
        );

        const results = [];

        for (const manga of mangaResult.rows) {
            try {
                const chapter = await fetchLatestChapter.execute({ mangaId: manga.mangadex_id });
                if (!chapter) continue;

                const existing = await db.query(
                    `SELECT id FROM manga_chapters WHERE mangadex_id = $1`,
                    [chapter.id]
                );
                if (existing.rows.length > 0) {
                    results.push({ title: manga.title, status: 'already_processed' });
                    continue;
                }

                const { pages } = await fetchChapterPages.execute({ chapterId: chapter.id });
                const localPaths = await downloadPanels.execute({
                    panelUrls: pages,
                    mangaTitle: manga.title,
                    chapterNumber: chapter.chapterNumber
                });

                const chapterId = await saveMangaChapter.execute({
                    mangaId: manga.id,
                    chapterNumber: chapter.chapterNumber,
                    chapterTitle: chapter.title,
                    mangadexChapterId: chapter.id,
                    panelUrls: pages
                });

                if (localPaths.length > 0) {
                    await db.query(
                        `UPDATE manga_chapters SET local_paths = $1 WHERE id = $2`,
                        [JSON.stringify(localPaths), chapterId]
                    );
                }

                results.push({ title: manga.title, chapterId, panels: pages.length, status: 'fetched' });
            } catch (err: any) {
                results.push({ title: manga.title, status: 'error', error: err.message });
            }
        }

        res.json({ success: true, processed: results.length, results });
    } catch (err: any) {
        logger.error('fetch-chapters failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** GET /pipeline/pending-chapters
 * Returns chapters scraped but not yet panel-selected.
 */
app.get('/pipeline/pending-chapters', async (_req: Request, res: Response) => {
    const result = await db.query(
        `SELECT mc.id, m.title, mc.chapter_number, mc.scraped_at
         FROM manga_chapters mc
         JOIN manga m ON mc.manga_id = m.id
         WHERE mc.processed = false
         ORDER BY mc.scraped_at DESC
         LIMIT 50`
    );
    res.json({ chapters: result.rows });
});

/** GET /pipeline/ready-videos
 * Returns videos with captions that are ready for publishing.
 */
app.get('/pipeline/ready-videos', async (_req: Request, res: Response) => {
    const result = await db.query(
        `SELECT v.id, v.file_path, v.caption, v.hashtags, v.duration_secs,
                m.title AS manga_title
         FROM videos v
         JOIN manga_chapters mc ON v.chapter_id = mc.id
         JOIN manga m           ON mc.manga_id = m.id
         WHERE v.status = 'ready'
           AND v.caption IS NOT NULL
         ORDER BY v.created_at DESC
         LIMIT 20`
    );
    res.json({ videos: result.rows });
});

/** POST /pipeline/mark-published
 * Marks a video as published and stores the platform post ID.
 * Body: { videoId, platform, accountName, platformPostId, platformUrl }
 */
app.post('/pipeline/mark-published', async (req: Request, res: Response) => {
    const { videoId, platform, accountName, platformPostId, platformUrl } = req.body;
    try {
        await db.query(
            `INSERT INTO published_videos (video_id, platform, account_name, platform_post_id, platform_url)
             VALUES ($1, $2, $3, $4, $5)`,
            [videoId, platform, accountName, platformPostId, platformUrl]
        );
        await db.query(`UPDATE videos SET status = 'published' WHERE id = $1`, [videoId]);
        res.json({ success: true });
    } catch (err: any) {
        res.status(500).json({ success: false, error: err.message });
    }
});

/** GET /pipeline/shadow-banned-accounts
 * Returns all currently shadow-banned accounts.
 */
app.get('/pipeline/shadow-banned-accounts', async (_req: Request, res: Response) => {
    const result = await db.query(
        `SELECT id, username, shadow_ban_detected_at, upload_failures, account_status
         FROM tiktok_accounts
         WHERE shadow_banned = true
         ORDER BY shadow_ban_detected_at DESC`
    );
    res.json({ accounts: result.rows });
});

// ─── Dashboard Endpoints ──────────────────────────────────────────────────────

// === Workflows & Analytics ===

// ─── Workflow Management Endpoints ────────────────────────────────────────────

/** GET /api/workflows
 * List all workflow executions with optional filtering
 * Query params: ?status=running&limit=50
 */
app.get('/api/workflows', async (req: Request, res: Response) => {
    const { status, limit = '50' } = req.query;
    
    try {
        let query = 'SELECT * FROM workflow_executions';
        const params: any[] = [];
        
        if (status) {
            query += ' WHERE status = $1';
            params.push(status);
        }
        
        query += ' ORDER BY started_at DESC LIMIT $' + (params.length + 1);
        params.push(parseInt(limit as string));
        
        const result = await db.query(query, params);
        res.json({ workflows: result.rows });
    } catch (err: any) {
        logger.error('Failed to fetch workflows', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** GET /api/workflows/executions/:id
 * Get detailed execution info including all steps
 */
app.get('/api/workflows/executions/:id', async (req: Request, res: Response) => {
    const { id } = req.params;
    
    try {
        const execution = await db.query(
            'SELECT * FROM workflow_executions WHERE id = $1',
            [id]
        );
        
        if (execution.rows.length === 0) {
            return res.status(404).json({ error: 'Execution not found' });
        }
        
        const steps = await db.query(
            'SELECT * FROM workflow_steps WHERE execution_id = $1 ORDER BY step_order ASC',
            [id]
        );
        
        res.json({
            execution: execution.rows[0],
            steps: steps.rows
        });
    } catch (err: any) {
        logger.error('Failed to fetch execution details', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** POST /api/workflows/start
 * Create a new workflow execution record and return its ID.
 * Used by n8n workflows to get an execution_id for subsequent log-step calls.
 * Body: { workflow_name: string }
 */
app.post('/api/workflows/start', async (req: Request, res: Response) => {
    const { workflow_name = 'unnamed' } = req.body;
    try {
        const result = await db.query(
            `INSERT INTO workflow_executions (workflow_name, organization_id, status, started_at)
             VALUES ($1, 1, 'running', NOW()) RETURNING id`,
            [workflow_name]
        );
        res.json({ success: true, execution_id: result.rows[0].id });
    } catch (err: any) {
        logger.error('Failed to start workflow execution', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** POST /api/workflows/:id/run
 * Manually trigger a workflow
 * Body: { input_data?: any }
 */
app.post('/api/workflows/:id/run', async (req: Request, res: Response) => {
    const { id } = req.params;
    const { input_data } = req.body;
    
    logger.info(`Triggering workflow ${id} manually`);
    
    try {
        // Create execution record
        const execution = await db.query(
            `INSERT INTO workflow_executions 
             (workflow_id, workflow_name, organization_id, status, trigger_type, input_data, started_at)
             VALUES ($1, $2, $3, $4, $5, $6, NOW())
             RETURNING id`,
            [id, `Workflow ${id}`, 1, 'running', 'manual', JSON.stringify(input_data || {})]
        );
        
        const executionId = execution.rows[0].id;
        
        // TODO: Trigger n8n webhook here
        // const n8nUrl = `${process.env.N8N_URL}/webhook/${id}`;
        // await fetch(n8nUrl, { method: 'POST', body: JSON.stringify(input_data) });
        
        res.json({ 
            success: true, 
            message: "Workflow triggered successfully",
            execution_id: executionId
        });
    } catch (err: any) {
        logger.error('Failed to trigger workflow', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** POST /api/workflows/log-step
 * Log a workflow step completion (called by n8n workflows)
 * Body: { execution_id, step_name, step_order, status, output_data?, error_message? }
 */
app.post('/api/workflows/log-step', async (req: Request, res: Response) => {
    const { execution_id, step_name, step_order, status, output_data, error_message } = req.body;
    
    if (!execution_id || !step_name) {
        return res.status(400).json({ error: 'execution_id and step_name required' });
    }
    
    try {
        // Check if step already exists
        const existing = await db.query(
            'SELECT id FROM workflow_steps WHERE execution_id = $1 AND step_name = $2',
            [execution_id, step_name]
        );
        
        if (existing.rows.length > 0) {
            // Update existing step
            const completedAt = ['completed', 'failed', 'skipped'].includes(status) ? new Date() : null;
            await db.query(
                `UPDATE workflow_steps 
                 SET status = $2, output_data = $3::jsonb, error_message = $4, completed_at = $5
                 WHERE id = $1`,
                [existing.rows[0].id, status, 
                 JSON.stringify(output_data || {}), error_message || null, completedAt]
            );
        } else {
            // Insert new step
            const completedAt = ['completed', 'failed', 'skipped'].includes(status) ? new Date() : null;
            await db.query(
                `INSERT INTO workflow_steps 
                 (execution_id, step_name, step_order, status, output_data, error_message, started_at, completed_at)
                 VALUES ($1, $2, $3, $4::varchar, $5::jsonb, $6, NOW(), $7)`,
                [execution_id, step_name, step_order || 0, status, 
                 JSON.stringify(output_data || {}), error_message || null, completedAt]
            );
        }
        
        // Update execution status if step failed
        if (status === 'failed') {
            await db.query(
                `UPDATE workflow_executions 
                 SET status = 'failed', error_message = $2, completed_at = NOW()
                 WHERE id = $1`,
                [execution_id, error_message || 'Step failed']
            );
        }
        
        res.json({ success: true });
    } catch (err: any) {
        logger.error('Failed to log workflow step', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** POST /api/workflows/executions/:id/complete
 * Mark a workflow execution as complete
 * Body: { status: 'completed' | 'failed', output_data?, error_message? }
 */
app.post('/api/workflows/executions/:id/complete', async (req: Request, res: Response) => {
    const { id } = req.params;
    const { status, output_data, error_message } = req.body;
    
    if (!['completed', 'failed'].includes(status)) {
        return res.status(400).json({ error: 'status must be completed or failed' });
    }
    
    try {
        const result = await db.query(
            `UPDATE workflow_executions 
             SET status = $2, output_data = $3, error_message = $4, 
                 completed_at = NOW(),
                 duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at)) * 1000
             WHERE id = $1
             RETURNING *`,
            [id, status, JSON.stringify(output_data || {}), error_message]
        );
        
        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Execution not found' });
        }
        
        res.json({ success: true, execution: result.rows[0] });
    } catch (err: any) {
        logger.error('Failed to complete execution', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/analytics', async (_req: Request, res: Response) => {
    try {
        const result = await db.query('SELECT date_trunc(\'day\', created_at) as date, COUNT(*) as posts FROM published_videos GROUP BY 1 ORDER BY 1 DESC LIMIT 30');
        res.json({ analytics: result.rows });
    } catch (err: any) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/tiktok-accounts/:id/proxy', async (req: Request, res: Response) => {
    const { id } = req.params;
    const { proxy_id } = req.body;
    try {
        await db.query('UPDATE tiktok_accounts SET proxy_id = $1 WHERE id = $2', [proxy_id, id]);
        res.json({ success: true });
    } catch (err: any) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/dashboard/manga', async (_req: Request, res: Response) => {
    try {
        const result = await db.query('SELECT * FROM manga ORDER BY id DESC');
        res.json({ manga: result.rows });
    } catch (err: any) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/dashboard/tiktok-accounts', async (_req: Request, res: Response) => {
    try {
        const result = await db.query('SELECT * FROM tiktok_accounts ORDER BY id');
        res.json({ accounts: result.rows });
    } catch (err: any) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/dashboard/videos', async (_req: Request, res: Response) => {
    try {
        const result = await db.query(`
            SELECT v.*, m.title as manga_title, mc.chapter_number
            FROM videos v
            JOIN manga_chapters mc ON v.chapter_id = mc.id
            JOIN manga m ON mc.manga_id = m.id
            ORDER BY v.created_at DESC
        `);
        res.json({ videos: result.rows });
    } catch (err: any) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/dashboard/videos/:id/upload-youtube', async (req: Request, res: Response) => {
    const { id } = req.params;
    try {
        const workerUrl = process.env.PYTHON_WORKER_URL || 'http://localhost:8080';
        const response = await fetch(`${workerUrl}/upload-youtube`, {
            method: 'POST',
            body: JSON.stringify({ video_id: parseInt(id) }),
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await response.json();
        res.json(result);
    } catch (err: any) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/dashboard/manga', async (req: Request, res: Response) => {
    const { title, mangadex_id, tags, status, is_active } = req.body;
    try {
        const result = await db.query(
            `INSERT INTO manga (title, mangadex_id, tags, status, is_active, trending_score, created_at, updated_at)
             VALUES ($1, $2, $3, $4, $5, 100, NOW(), NOW())
             RETURNING id`,
            [title, mangadex_id, tags || '{}', status || 'ongoing', is_active ?? true]
        );
        res.json({ success: true, id: result.rows[0].id });
    } catch (err: any) {
        res.status(500).json({ error: err.message });
    }
});

/** GET /dashboard/clips
 * Unified clip library: rendered/ingested `videos` + YouTube-sourced `arbitrage_assets`,
 * each with its publish history. Optional filters: ?source=video|arbitrage, ?status=...
 */
app.get('/dashboard/clips', async (req: Request, res: Response) => {
    const { source, status } = req.query as { source?: string; status?: string };
    try {
        const result = await db.query(`
            SELECT * FROM (
                SELECT
                    v.id,
                    'video' AS source_type,
                    COALESCE(NULLIF(v.caption, ''), 'Video #' || v.id) AS title,
                    v.file_path AS local_path,
                    v.thumbnail_path,
                    v.duration_secs::numeric AS duration_secs,
                    v.file_size_mb,
                    v.status,
                    NULL::text AS source_url,
                    v.created_at,
                    COALESCE((
                        SELECT json_agg(json_build_object(
                            'platform', pv.platform, 'url', pv.platform_url, 'published_at', pv.published_at
                        ))
                        FROM published_videos pv WHERE pv.video_id = v.id
                    ), '[]'::json) AS published
                FROM videos v
                UNION ALL
                SELECT
                    a.id,
                    'arbitrage' AS source_type,
                    COALESCE(NULLIF(a.youtube_title, ''), 'Clip #' || a.id) AS title,
                    a.local_path,
                    NULL::text AS thumbnail_path,
                    a.duration_secs::numeric AS duration_secs,
                    a.file_size_mb,
                    a.status,
                    a.youtube_url AS source_url,
                    a.created_at,
                    COALESCE((
                        SELECT json_agg(json_build_object(
                            'platform', au.platform, 'url', au.platform_url, 'status', au.status
                        ))
                        FROM arbitrage_uploads au WHERE au.asset_id = a.id
                    ), '[]'::json) AS published
                FROM arbitrage_assets a
            ) clips
            WHERE ($1::text IS NULL OR clips.source_type = $1)
              AND ($2::text IS NULL OR clips.status = $2)
            ORDER BY clips.created_at DESC NULLS LAST
            LIMIT 300
        `, [source || null, status || null]);
        res.json({ clips: result.rows });
    } catch (err: any) {
        res.status(500).json({ error: err.message });
    }
});

/** GET /dashboard/clips/:id?source=video|arbitrage
 * Single clip detail with full publish history (ids overlap across tables, so `source` is required).
 */
app.get('/dashboard/clips/:id', async (req: Request, res: Response) => {
    const { id } = req.params;
    const source = (req.query.source as string) || 'video';
    try {
        if (source === 'arbitrage') {
            const asset = await db.query(
                `SELECT a.*, t.hashtag FROM arbitrage_assets a
                 LEFT JOIN trend_intel t ON a.trend_id = t.id
                 WHERE a.id = $1`,
                [id]
            );
            if (!asset.rows.length) return res.status(404).json({ error: 'clip not found' });
            const uploads = await db.query(
                `SELECT platform, caption, platform_url, platform_post_id, status, error_message, uploaded_at
                 FROM arbitrage_uploads WHERE asset_id = $1 ORDER BY uploaded_at DESC`,
                [id]
            );
            return res.json({ clip: { ...asset.rows[0], source_type: 'arbitrage' }, uploads: uploads.rows });
        }
        const video = await db.query(`SELECT * FROM videos WHERE id = $1`, [id]);
        if (!video.rows.length) return res.status(404).json({ error: 'clip not found' });
        const [published, attempts] = await Promise.all([
            db.query(
                `SELECT platform, account_name, platform_url, platform_post_id, status, published_at
                 FROM published_videos WHERE video_id = $1 ORDER BY published_at DESC`,
                [id]
            ),
            db.query(
                `SELECT platform, success, error_message, tiktok_url, uploaded_at
                 FROM upload_results WHERE video_id = $1 ORDER BY uploaded_at DESC`,
                [id]
            ),
        ]);
        res.json({ clip: { ...video.rows[0], source_type: 'video' }, published: published.rows, attempts: attempts.rows });
    } catch (err: any) {
        res.status(500).json({ error: err.message });
    }
});

/** POST /pipeline/populate-queue
 * Queue all chapters for a manga
 * Body: { manga_id: number }
 */
app.post('/pipeline/populate-queue', async (req: Request, res: Response) => {
    const { manga_id } = req.body;
    if (!manga_id) return res.status(400).json({ error: 'manga_id required' });

    logger.info('Pipeline: populate-queue triggered', { manga_id });
    try {
        const queueEntries = await queueManager.populateQueue(Number(manga_id));
        res.json({
            success: true,
            manga_id,
            queued_count: queueEntries.length,
            queue_ids: queueEntries.map(e => e.id)
        });
    } catch (err: any) {
        logger.error('populate-queue failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /webhook/queue-chapter
 * Manual chapter selection - queue specific chapter(s)
 * Body: { manga_id: number, chapter_number: string, priority?: number }
 *    OR { manga_id: number, start_chapter: string, end_chapter: string, priority?: number }
 */
app.post('/webhook/queue-chapter', async (req: Request, res: Response) => {
    const { manga_id, chapter_number, start_chapter, end_chapter, priority } = req.body;

    if (!manga_id) {
        return res.status(400).json({ error: 'manga_id required' });
    }

    logger.info('Webhook: queue-chapter triggered', { manga_id, chapter_number, start_chapter, end_chapter });

    try {
        // Handle chapter range
        if (start_chapter && end_chapter) {
            const queueEntries = await queueManager.addChapterRange(
                Number(manga_id),
                start_chapter,
                end_chapter,
                priority || 100
            );

            // Calculate queue position for first entry
            const positionResult = await db.query(
                `SELECT COUNT(*) as position 
                 FROM chapter_posting_queue 
                 WHERE status = 'pending' 
                   AND (priority > $1 OR (priority = $1 AND chapter_number < $2))`,
                [queueEntries[0]?.priority || 100, start_chapter]
            );

            return res.json({
                success: true,
                queued_count: queueEntries.length,
                queue_ids: queueEntries.map(e => e.id),
                queue_position: Number(positionResult.rows[0]?.position || 0) + 1
            });
        }

        // Handle single chapter
        if (!chapter_number) {
            return res.status(400).json({
                error: 'Either chapter_number or (start_chapter and end_chapter) required'
            });
        }

        const queueEntry = await queueManager.addChapterWithPriority(
            Number(manga_id),
            chapter_number,
            priority || 100
        );

        // Calculate queue position
        const positionResult = await db.query(
            `SELECT COUNT(*) as position 
             FROM chapter_posting_queue 
             WHERE status = 'pending' 
               AND (priority > $1 OR (priority = $1 AND chapter_number < $2))`,
            [queueEntry.priority, chapter_number]
        );

        res.json({
            success: true,
            queue_id: queueEntry.id,
            queue_position: Number(positionResult.rows[0]?.position || 0) + 1
        });
    } catch (err: any) {
        logger.error('queue-chapter failed', { error: err.message });

        // Check if it's a "not found" error
        if (err.message.includes('not found')) {
            return res.status(404).json({ success: false, error: err.message });
        }

        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /captions/generate
 * Generate viral captions for a video
 * Body: { videoId: number, mangaTitle?: string, chapterNumber?: string, genre?: string, formulaType?: string }
 */
app.post('/captions/generate', async (req: Request, res: Response) => {
    const { videoId, mangaTitle, chapterNumber, genre, formulaType } = req.body;

    if (!videoId) {
        return res.status(400).json({ error: 'videoId required' });
    }

    logger.info('Captions: generate triggered', { videoId });

    try {
        // Fetch video and manga details if not provided
        let captionRequest: any = { mangaTitle, chapterNumber, genre, formulaType };

        if (!mangaTitle || !chapterNumber || !genre) {
            const videoResult = await db.query(
                `SELECT m.title, mc.chapter_number, m.genre
                 FROM videos v
                 JOIN manga_chapters mc ON v.chapter_id = mc.id
                 JOIN manga m ON mc.manga_id = m.id
                 WHERE v.id = $1`,
                [videoId]
            );

            if (videoResult.rows.length === 0) {
                return res.status(404).json({ error: `Video ${videoId} not found` });
            }

            const video = videoResult.rows[0];
            captionRequest = {
                mangaTitle: mangaTitle || video.title,
                chapterNumber: chapterNumber || video.chapter_number,
                genre: genre || video.genre || 'manga',
                formulaType
            };
        }

        // Generate caption
        const caption = await captionGenerator.generateCaption(captionRequest);

        // Select hashtags
        const hashtags = await hashtagSelector.selectHashtags({
            mangaTitle: captionRequest.mangaTitle,
            genre: captionRequest.genre,
            isRecommendation: formulaType === 'recommendation'
        });

        // Update video with caption and hashtags
        await db.query(
            `UPDATE videos 
             SET caption = $1, hashtags = $2
             WHERE id = $3`,
            [caption.text, hashtags, videoId]
        );

        res.json({
            success: true,
            videoId,
            caption: caption.text,
            hashtags,
            formula: caption.formula,
            emojis: caption.emojis
        });
    } catch (err: any) {
        logger.error('generate-caption failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** GET /hashtags/select
 * Select strategic hashtags
 * Query params: ?mangaTitle=...&genre=...&emotionalTone=...&isRecommendation=true/false
 */
app.get('/hashtags/select', async (req: Request, res: Response) => {
    const { mangaTitle, genre, emotionalTone, isRecommendation } = req.query;

    if (!mangaTitle || !genre) {
        return res.status(400).json({ error: 'mangaTitle and genre required' });
    }

    logger.info('Hashtags: select triggered', { mangaTitle, genre });

    try {
        const hashtags = await hashtagSelector.selectHashtags({
            mangaTitle: String(mangaTitle),
            genre: String(genre),
            emotionalTone: emotionalTone ? String(emotionalTone) : undefined,
            isRecommendation: isRecommendation === 'true'
        });

        res.json({
            success: true,
            hashtags
        });
    } catch (err: any) {
        logger.error('select-hashtags failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

// ─── Video Rendering via Remotion ─────────────────────────────────────────────

const PANEL_DURATION_FRAMES = 240; // 8 seconds at 30fps

/**
 * Converts an absolute image path to a base64 data URI so Remotion's Chrome
 * headless can load it without needing an HTTP server to serve /data/.
 */
const imagePathToDataUri = (filePath: string): string => {
    const ext = path.extname(filePath).slice(1).toLowerCase();
    const mimeMap: Record<string, string> = {
        jpg: 'image/jpeg', jpeg: 'image/jpeg',
        png: 'image/png', gif: 'image/gif', webp: 'image/webp',
    };
    const mime = mimeMap[ext] || 'image/jpeg';
    const buf = fs.readFileSync(filePath);
    return `data:${mime};base64,${buf.toString('base64')}`;
};

/** POST /pipeline/render-video
 * Renders a manga recap video using Remotion from the queue.
 * Body: { queueId?: number, templateId?: number, randomTemplate?: boolean }
 *
 * Flow:
 *   1. Get next chapter from queue (or use specified queueId)
 *   2. Analyze chapter to determine if splitting is needed
 *   3. Build Remotion props JSON from panel paths + motion tags
 *   4. Spawn render-video.ts CLI with optional template flags
 *   5. Insert result into videos table
 *   6. Update queue status to 'posted'
 *   7. Return { videoId, filePath, durationSecs, fileSizeMb, template }
 */
app.post('/pipeline/render-video', async (req: Request, res: Response) => {
    const { queueId, templateId, randomTemplate } = req.body;

    logger.info('Pipeline: render-video started', { queueId, templateId, randomTemplate });
    try {
        // 1. Get queue entry (either specified or next in queue)
        let queueEntry;
        if (queueId) {
            const result = await db.query(
                `SELECT * FROM chapter_posting_queue WHERE id = $1`,
                [queueId]
            );
            if (result.rows.length === 0) {
                return res.status(404).json({ error: `Queue entry ${queueId} not found` });
            }
            queueEntry = result.rows[0];
        } else {
            queueEntry = await queueManager.getNextChapter();
            if (!queueEntry) {
                return res.status(404).json({ error: 'No pending chapters in queue' });
            }
        }

        const chapterId = queueEntry.chapter_id;
        const queueEntryId = queueEntry.id;

        // Update queue status to 'processing'
        await queueManager.updateStatus(queueEntryId, QueueStatus.PROCESSING);

        // 2. Fetch chapter data and manga metadata
        // Cast JSONB to text to ensure proper parsing
        const chapterResult = await db.query(
            `SELECT 
                mc.panel_urls::text as panel_urls_text,
                mc.local_paths::text as local_paths_text,
                mc.chapter_number, 
                m.title, 
                m.id as manga_id
             FROM manga_chapters mc
             JOIN manga m ON mc.manga_id = m.id
             WHERE mc.id = $1`,
            [chapterId]
        );

        if (chapterResult.rows.length === 0) {
            await queueManager.updateStatus(queueEntryId, QueueStatus.FAILED);
            return res.status(404).json({ error: `Chapter ${chapterId} not found` });
        }

        const row = chapterResult.rows[0];

        // Parse JSONB text to arrays
        const panelUrls: string[] = JSON.parse(row.panel_urls_text || '[]');
        const localPaths: string[] = JSON.parse(row.local_paths_text || '[]');

        logger.info('Parsed panel data', {
            panelUrlsCount: panelUrls.length,
            localPathsCount: localPaths.length
        });

        if (panelUrls.length === 0) {
            await queueManager.updateStatus(queueEntryId, QueueStatus.FAILED);
            return res.status(400).json({ error: 'No panels found for chapter' });
        }

        // 3. Analyze chapter to determine if splitting is needed
        const splitPlan = await chapterAnalyzer.analyzeChapter(chapterId);

        // If chapter needs splitting and queue entry is for part 1, create additional queue entries
        if (splitPlan.videoCount > 1 && queueEntry.part_number === 1 && queueEntry.total_parts === 1) {
            logger.info(`Chapter ${chapterId} needs splitting into ${splitPlan.videoCount} parts`);
            await queueManager.createSplitChapterEntries(
                row.manga_id,
                chapterId,
                row.chapter_number,
                splitPlan.videoCount,
                queueEntry.priority
            );
        }

        // Get the segment for this part
        const segment = splitPlan.splits.find(s => s.partNumber === queueEntry.part_number) || splitPlan.splits[0];

        // 4. Build Remotion props for this segment
        const segmentPanels = localPaths.slice(segment.startPanel, segment.endPanel + 1);

        if (segmentPanels.length === 0) {
            await queueManager.updateStatus(queueEntryId, QueueStatus.FAILED);
            return res.status(400).json({ error: 'No valid local panel paths found for segment' });
        }

        const remotionPanels = segmentPanels
            .filter((path: string) => path && fs.existsSync(path))
            .map((path: string) => ({
                imagePath: imagePathToDataUri(path),
                motionType: 'zoom_center', // Default motion type
                durationInFrames: PANEL_DURATION_FRAMES,
            }));

        if (remotionPanels.length === 0) {
            await queueManager.updateStatus(queueEntryId, QueueStatus.FAILED);
            return res.status(400).json({ error: 'No valid local panel paths found' });
        }

        const sanitisedTitle = (row.title as string).replace(/[^a-zA-Z0-9]/g, '_');
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const partSuffix = queueEntry.total_parts > 1 ? `_part${queueEntry.part_number}` : '';
        const filename = `${sanitisedTitle}_ch${row.chapter_number}${partSuffix}_${timestamp}.mp4`;
        const outputPath = path.join(VIDEOS_DIR, filename);

        fs.mkdirSync(VIDEOS_DIR, { recursive: true });

        const props = {
            panels: remotionPanels,
            titleText: row.title,
            chapterText: queueEntry.total_parts > 1
                ? `Chapter ${row.chapter_number} - Part ${queueEntry.part_number}/${queueEntry.total_parts}`
                : `Chapter ${row.chapter_number}`,
            audioSrc: null, // Music selection can be added later
            audioDuckingVolume: 0.4,
            templateId: templateId || undefined,
        };

        // 5. Write temp props file and render
        const propsPath = path.join(REMOTION_DIR, `.render-props-${queueEntryId}-${Date.now()}.json`);
        fs.writeFileSync(propsPath, JSON.stringify(props, null, 2));

        logger.info(`Rendering ${remotionPanels.length} panels via Remotion`, { chapterId, queueEntryId, outputPath });

        // Build render command with optional template flags
        let renderCmd = `npx tsx src/render-video.ts --props "${propsPath}" --output "${outputPath}"`;

        if (randomTemplate) {
            renderCmd += ' --random-template';
        }

        const renderOutput = execSync(renderCmd, {
            cwd: REMOTION_DIR,
            encoding: 'utf-8',
            timeout: 10 * 60 * 1000, // 10 min
            maxBuffer: 50 * 1024 * 1024,
        }
        );

        // Clean up props file
        try { fs.unlinkSync(propsPath); } catch { }

        // 6. Parse render output
        const lines = renderOutput.trim().split('\n');
        const lastLine = lines[lines.length - 1];
        const renderResult = JSON.parse(lastLine);

        // 7. Insert into DB
        const videoInsert = await db.query(
            `INSERT INTO videos (chapter_id, file_path, duration_secs, file_size_mb, status, created_at)
             VALUES ($1, $2, $3, $4, 'ready', NOW())
             RETURNING id`,
            [chapterId, renderResult.filePath, renderResult.durationSecs, renderResult.fileSizeMb]
        );

        const videoId = videoInsert.rows[0]?.id;

        // 8. Update queue status to 'posted'
        await queueManager.updateStatus(queueEntryId, QueueStatus.POSTED, videoId);

        logger.info('Video rendered successfully', { videoId, queueEntryId, ...renderResult });

        res.json({
            success: true,
            videoId,
            queueId: queueEntryId,
            filePath: renderResult.filePath,
            durationSecs: renderResult.durationSecs,
            fileSizeMb: renderResult.fileSizeMb,
            template: renderResult.template || null,
            partNumber: queueEntry.part_number,
            totalParts: queueEntry.total_parts
        });
    } catch (err: any) {
        logger.error('render-video failed', { error: err.message, stderr: err.stderr });

        // Update queue status to 'failed' if we have a queueId
        if (queueId) {
            try {
                await queueManager.updateStatus(queueId, QueueStatus.FAILED);
            } catch (updateErr) {
                logger.error('Failed to update queue status to failed', { error: updateErr });
            }
        }

        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /pipeline/render-video-custom
 * Render any Remotion composition with explicit props.
 * Body: {
 *   compositionId: "MangaRecap" | "BrainrotFeed" | "CharacterEdit" | "ChapterRecap",
 *   props: object,
 *   filename?: string,
 *   outputPath?: string
 * }
 */
app.post('/pipeline/render-video-custom', async (req: Request, res: Response) => {
    const {
        compositionId = 'MangaRecap',
        props,
        filename,
        outputPath,
    } = req.body || {};

    if (!props || typeof props !== 'object') {
        return res.status(400).json({ success: false, error: 'props object is required' });
    }

    const allowed = new Set(['MangaRecap', 'BrainrotFeed', 'CharacterEdit', 'ChapterRecap', 'ProductPromo']);
    if (!allowed.has(String(compositionId))) {
        return res.status(400).json({
            success: false,
            error: `Unsupported compositionId: ${compositionId}`,
        });
    }

    try {
        fs.mkdirSync(VIDEOS_DIR, { recursive: true });
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const safeName = String(filename || `${compositionId}_${timestamp}.mp4`).replace(/[^a-zA-Z0-9._-]/g, '_');
        const resolvedOutputPath = outputPath
            ? path.resolve(String(outputPath))
            : path.join(VIDEOS_DIR, safeName);

        const propsPath = path.join(REMOTION_DIR, `.render-custom-${Date.now()}.json`);
        fs.writeFileSync(propsPath, JSON.stringify(props, null, 2));

        const renderCmd = `npx tsx src/render-video.ts --props "${propsPath}" --output "${resolvedOutputPath}" --composition "${compositionId}"`;
        const renderOutput = execSync(renderCmd, {
            cwd: REMOTION_DIR,
            encoding: 'utf-8',
            timeout: 10 * 60 * 1000,
            maxBuffer: 50 * 1024 * 1024,
        });

        try { fs.unlinkSync(propsPath); } catch { }

        const lines = renderOutput.trim().split('\n');
        const lastLine = lines[lines.length - 1];
        const renderResult = JSON.parse(lastLine);

        res.json({
            success: true,
            compositionId,
            filePath: renderResult.filePath,
            durationSecs: renderResult.durationSecs,
            fileSizeMb: renderResult.fileSizeMb,
            template: renderResult.template || null,
        });
    } catch (err: any) {
        logger.error('render-video-custom failed', { error: err.message, stderr: err.stderr });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /agents/product-promo
 * Generates and optionally renders a product promotion video via Remotion ProductPromo composition.
 * Body: { prompt: string, render?: boolean, filename?: string }
 */
app.post('/agents/product-promo', async (req: Request, res: Response) => {
    const { prompt, render = true, filename, props: propsOverride } = req.body;
    if (!prompt && !propsOverride) {
        return res.status(400).json({ error: 'prompt (string) or props (object) is required' });
    }

    logger.info('Agent: product-promo triggered', {
        prompt: typeof prompt === 'string' ? prompt.slice(0, 120) : '(props only)',
        render,
    });
    try {
        let validatedProps;
        if (propsOverride) {
            validatedProps = productPromoPropsSchema.parse(propsOverride);
        }

        const result = await createProductPromo(prompt || 'Product promotion', {
            remotionDir: REMOTION_DIR,
            outputDir: VIDEOS_DIR,
            render: Boolean(render),
            filename,
            props: validatedProps,
        });

        res.json({
            success: true,
            composition: result.composition,
            props: result.props,
            filePath: result.filePath ?? null,
            durationSecs: result.durationSecs ?? null,
            fileSizeMb: result.fileSizeMb ?? null,
        });
    } catch (err: any) {
        logger.error('product-promo failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

// ─── TikTok Account & Proxy Management ────────────────────────────────────────

/** GET /api/tiktok-accounts
 * List all TikTok accounts with proxy information
 * Query params: ?organization_id=1&status=active
 */
app.get('/api/tiktok-accounts', async (req: Request, res: Response) => {
    const { organization_id, status } = req.query;
    
    try {
        let query = `
            SELECT 
                ta.id, ta.username, ta.account_status, ta.shadow_banned,
                ta.upload_failures, ta.last_post_at, ta.shadow_ban_detected_at,
                ta.proxy_id, ta.organization_id, ta.total_posts,
                p.name as proxy_name, p.ip_address as proxy_host, p.port as proxy_port,
                p.country as proxy_country, p.is_active as proxy_active
            FROM tiktok_accounts ta
            LEFT JOIN proxies p ON ta.proxy_id = p.id
            WHERE 1=1
        `;
        const params: any[] = [];
        
        if (organization_id) {
            params.push(organization_id);
            query += ` AND ta.organization_id = $${params.length}`;
        }
        
        if (status) {
            params.push(status);
            query += ` AND ta.account_status = $${params.length}`;
        }
        
        query += ' ORDER BY ta.id ASC';
        
        const result = await db.query(query, params);
        res.json({ accounts: result.rows });
    } catch (err: any) {
        logger.error('Failed to fetch TikTok accounts', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** POST /api/tiktok-accounts
 * Create a new TikTok account with optional proxy assignment
 * Body: { username, cookies_file, organization_id, proxy_id?, account_status? }
 */
app.post('/api/tiktok-accounts', async (req: Request, res: Response) => {
    const { username, cookies_file, organization_id, proxy_id, account_status } = req.body;
    
    if (!username || !organization_id) {
        return res.status(400).json({ error: 'username and organization_id required' });
    }
    
    try {
        const result = await db.query(
            `INSERT INTO tiktok_accounts 
             (username, cookies_file, organization_id, proxy_id, account_status, created_at)
             VALUES ($1, $2, $3, $4, $5, NOW())
             RETURNING id`,
            [username, cookies_file || null, organization_id, proxy_id || null, account_status || 'active']
        );
        
        res.json({ success: true, account_id: result.rows[0].id });
    } catch (err: any) {
        logger.error('Failed to create TikTok account', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** PUT /api/tiktok-accounts/:id
 * Update TikTok account settings
 * Body: { proxy_id?, account_status?, cookies_file? }
 */
app.put('/api/tiktok-accounts/:id', async (req: Request, res: Response) => {
    const { id } = req.params;
    const { proxy_id, account_status, cookies_file } = req.body;
    
    try {
        const updates: string[] = [];
        const params: any[] = [];
        
        if (proxy_id !== undefined) {
            params.push(proxy_id);
            updates.push(`proxy_id = $${params.length}`);
        }
        
        if (account_status) {
            params.push(account_status);
            updates.push(`account_status = $${params.length}`);
        }
        
        if (cookies_file) {
            params.push(cookies_file);
            updates.push(`cookies_file = $${params.length}`);
        }
        
        if (updates.length === 0) {
            return res.status(400).json({ error: 'No fields to update' });
        }
        
        params.push(id);
        const query = `UPDATE tiktok_accounts SET ${updates.join(', ')} WHERE id = $${params.length} RETURNING id`;
        
        const result = await db.query(query, params);
        
        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Account not found' });
        }
        
        res.json({ success: true });
    } catch (err: any) {
        logger.error('Failed to update TikTok account', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** DELETE /api/tiktok-accounts/:id
 * Delete a TikTok account
 */
app.delete('/api/tiktok-accounts/:id', async (req: Request, res: Response) => {
    const { id } = req.params;
    
    try {
        const result = await db.query('DELETE FROM tiktok_accounts WHERE id = $1 RETURNING id', [id]);
        
        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Account not found' });
        }
        
        res.json({ success: true });
    } catch (err: any) {
        logger.error('Failed to delete TikTok account', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** GET /api/proxies
 * List all proxies
 * Query params: ?organization_id=1&is_active=true
 */
app.get('/api/proxies', async (req: Request, res: Response) => {
    const { organization_id, is_active } = req.query;
    
    try {
        let query = `
            SELECT 
                p.*,
                (SELECT COUNT(*) FROM tiktok_accounts ta WHERE ta.proxy_id = p.id) as accounts_count
            FROM proxies p
            WHERE 1=1
        `;
        const params: any[] = [];
        
        if (organization_id) {
            params.push(organization_id);
            query += ` AND p.organization_id = $${params.length}`;
        }
        
        if (is_active !== undefined) {
            params.push(is_active === 'true');
            query += ` AND p.is_active = $${params.length}`;
        }
        
        query += ' ORDER BY p.id ASC';
        
        const result = await db.query(query, params);
        res.json({ proxies: result.rows });
    } catch (err: any) {
        logger.error('Failed to fetch proxies', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** POST /api/proxies
 * Add a new proxy
 * Body: { name, host, port, username?, password?, protocol?, country?, organization_id }
 */
app.post('/api/proxies', async (req: Request, res: Response) => {
    const { name, host, port, username, password, protocol, country, organization_id } = req.body;
    
    if (!host || !port || !organization_id) {
        return res.status(400).json({ error: 'host, port, and organization_id required' });
    }
    
    try {
        const result = await db.query(
            `INSERT INTO proxies 
             (name, ip_address, port, username, password, protocol, country, organization_id, is_active, created_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true, NOW())
             RETURNING id`,
            [name || `${host}:${port}`, host, port, username || null, password || null, 
             protocol || 'http', country || null, organization_id]
        );
        
        res.json({ success: true, proxy_id: result.rows[0].id });
    } catch (err: any) {
        logger.error('Failed to create proxy', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** PUT /api/proxies/:id
 * Update proxy settings
 * Body: { name?, is_active?, username?, password? }
 */
app.put('/api/proxies/:id', async (req: Request, res: Response) => {
    const { id } = req.params;
    const { name, is_active, username, password } = req.body;
    
    try {
        const updates: string[] = [];
        const params: any[] = [];
        
        if (name) {
            params.push(name);
            updates.push(`name = $${params.length}`);
        }
        
        if (is_active !== undefined) {
            params.push(is_active);
            updates.push(`is_active = $${params.length}`);
        }
        
        if (username !== undefined) {
            params.push(username);
            updates.push(`username = $${params.length}`);
        }
        
        if (password !== undefined) {
            params.push(password);
            updates.push(`password = $${params.length}`);
        }
        
        if (updates.length === 0) {
            return res.status(400).json({ error: 'No fields to update' });
        }
        
        params.push(id);
        updates.push(`updated_at = NOW()`);
        const query = `UPDATE proxies SET ${updates.join(', ')} WHERE id = $${params.length} RETURNING id`;
        
        const result = await db.query(query, params);
        
        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Proxy not found' });
        }
        
        res.json({ success: true });
    } catch (err: any) {
        logger.error('Failed to update proxy', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** DELETE /api/proxies/:id
 * Delete a proxy
 */
app.delete('/api/proxies/:id', async (req: Request, res: Response) => {
    const { id } = req.params;
    
    try {
        // Check if proxy is in use
        const inUse = await db.query(
            'SELECT COUNT(*) as count FROM tiktok_accounts WHERE proxy_id = $1',
            [id]
        );
        
        if (parseInt(inUse.rows[0].count) > 0) {
            return res.status(400).json({ 
                error: 'Proxy is currently assigned to TikTok accounts. Unassign first.' 
            });
        }
        
        const result = await db.query('DELETE FROM proxies WHERE id = $1 RETURNING id', [id]);
        
        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Proxy not found' });
        }
        
        res.json({ success: true });
    } catch (err: any) {
        logger.error('Failed to delete proxy', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

/** POST /api/proxies/:id/test
 * Test proxy connection
 */
app.post('/api/proxies/:id/test', async (req: Request, res: Response) => {
    const { id } = req.params;
    
    try {
        const proxyResult = await db.query('SELECT * FROM proxies WHERE id = $1', [id]);
        
        if (proxyResult.rows.length === 0) {
            return res.status(404).json({ error: 'Proxy not found' });
        }
        
        const proxy = proxyResult.rows[0];
        
        // TODO: Implement actual proxy testing logic
        // For now, just return a mock response
        const isWorking = true; // Replace with actual test
        
        if (isWorking) {
            await db.query(
                'UPDATE proxies SET last_success_at = NOW(), failure_count = 0, updated_at = NOW() WHERE id = $1',
                [id]
            );
        } else {
            await db.query(
                'UPDATE proxies SET failure_count = failure_count + 1, updated_at = NOW() WHERE id = $1',
                [id]
            );
        }
        
        res.json({ 
            success: true, 
            proxy_working: isWorking,
            message: isWorking ? 'Proxy connection successful' : 'Proxy connection failed'
        });
    } catch (err: any) {
        logger.error('Failed to test proxy', { error: err.message });
        res.status(500).json({ error: err.message });
    }
});

// ─── Arbitrage Pipeline Endpoints ────────────────────────────────────────────

const WORKER_URL = process.env.PYTHON_WORKER_URL || 'http://python-worker:8080';

const callWorker = async (path: string, body: object = {}) => {
    const r = await fetch(`${WORKER_URL}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    return r.json();
};

// ─── Publishing (manual clip publish + AiToEarn account ops) ──────────────────

/** GET /publish/accounts?platform=tiktok
 * Lists AiToEarn-connected accounts (optionally filtered by platform).
 */
app.get('/publish/accounts', async (req: Request, res: Response) => {
    try {
        const platform = (req.query.platform as string) || undefined;
        const result = await callWorker('/aitoearn/accounts', platform ? { platform } : {});
        const workerBody = (result?.result ?? {}) as Record<string, unknown>;
        const inner = (workerBody?.result ?? workerBody) as Record<string, unknown>;
        const accounts = Array.isArray(inner?.accounts) ? inner.accounts : [];
        const count = typeof inner?.count === 'number' ? inner.count : accounts.length;
        res.json({
            success: result?.success !== false && workerBody?.ok !== false,
            accounts,
            count,
            tool: workerBody?.tool,
            warning: workerBody?.warning,
            hint: workerBody?.hint,
            meta: workerBody?.meta,
            result,
        });
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

/** POST /publish
 * Manually publish a stored clip to chosen platforms/accounts.
 * Body: { clip_id, source_type, channels[], selected_accounts{}, account_ids[],
 *         title, desc, caption, hashtags[], topics[], cover_url, publish_time, yt_privacy }
 */
app.post('/publish', async (req: Request, res: Response) => {
    try {
        const result = await callWorker('/publish/clip', req.body);
        res.json(result);
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

/** GET /publish/status?flow_id=xxx
 * Poll the status of a publishing task created during a publish fanout.
 */
app.get('/publish/status', async (req: Request, res: Response) => {
    const flowId = (req.query.flow_id as string) || (req.query.flowId as string);
    if (!flowId) return res.status(400).json({ error: 'flow_id is required' });
    try {
        const result = await callWorker('/aitoearn/publish/status', { flow_id: flowId });
        res.json(result);
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

// ─── Agent control (QwenPaw or Hermes pipelines) ───────────────────────────────

/** POST /agent/prompt
 * Natural-language order routed to QwenPaw (default) or Hermes fallback.
 * Body: { prompt, agent_id?, source_url?, channels?, selected_accounts?, ... }
 */
app.post('/agent/prompt', async (req: Request, res: Response) => {
    const { prompt, source_url } = req.body || {};
    if (!prompt && !source_url) {
        return res.status(400).json({ error: 'prompt or source_url is required' });
    }

    if (isQwenPawBackend()) {
        try {
            const result = await qwenpawChat(req.body || {});
            res.json(result);
        } catch (err: any) {
            res.status(500).json({ error: err.message, backend: 'qwenpaw' });
        }
        return;
    }

    const hasUrl = !!source_url || /https?:\/\//i.test(String(prompt || ''));
    const route = hasUrl ? '/hermes/link-publish' : '/hermes/discover-publish';
    const body = { objective: prompt, prompt, ...req.body };
    try {
        const result = await callWorker(route, body);
        res.json({ route, backend: 'hermes', ...result });
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

/** GET /agent/status — QwenPaw or Hermes pipeline health snapshot. */
app.get('/agent/status', async (_req: Request, res: Response) => {
    try {
        if (isQwenPawBackend()) {
            const result = await qwenpawStatus();
            return res.json(result);
        }
        const result = await callWorker('/hermes/status', {});
        res.json({ backend: 'hermes', ...result });
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

/** GET /agent/logs?lines=200 — tail agent logs (Hermes file or QwenPaw placeholder). */
app.get('/agent/logs', async (req: Request, res: Response) => {
    const lines = Number(req.query.lines) || 200;
    try {
        if (isQwenPawBackend()) {
            const status = await qwenpawStatus();
            const content = [
                `QwenPaw backend — ${status.console_url || 'unknown'}`,
                `Agents: ${status.agent_count ?? 0}`,
                `AiToEarn: ${status.aitoearn_ok ? 'ok' : 'check config'}`,
                '',
                'Open QwenPaw Console at http://localhost:8088 for full chat logs.',
            ].join('\n');
            return res.json({ backend: 'qwenpaw', result: { content: content.slice(0, lines * 80) } });
        }
        const result = await callWorker('/hermes/log-tail', { lines });
        res.json({ backend: 'hermes', ...result });
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

/** GET /agent/agents — list QwenPaw agents for dashboard picker. */
app.get('/agent/agents', async (_req: Request, res: Response) => {
    try {
        if (isQwenPawBackend()) {
            const result = await qwenpawAgents();
            return res.json(result);
        }
        res.json({
            agents: [{ id: 'hermes', name: 'Hermes Pipeline Agent' }],
            backend: 'hermes',
        });
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

/** POST /agent/pipeline/:name — run a named pipeline (Hermes) or QwenPaw chat task. */
app.post('/agent/pipeline/:name', async (req: Request, res: Response) => {
    const name = req.params.name;
    if (isQwenPawBackend()) {
        const prompts: Record<string, string> = {
            finance: 'Run the finance pipeline: earnings proof → AI video → publish via AiToEarn.',
            viral: 'Run the viral pipeline: discover trends → brief → video → publish.',
            'link-publish': `Publish from link: ${req.body?.source_url || req.body?.video_url || 'use provided URL'}`,
            'discover-publish': `Discover and publish: ${req.body?.objective || req.body?.prompt || ''}`,
            'full-ops': 'Run full arbitrage ops: trends → source → publish → engage → report.',
        };
        const prompt = prompts[name] || `Run pipeline: ${name}`;
        try {
            const result = await qwenpawChat({ ...req.body, prompt, agent_id: 'pipeline-manager' });
            res.json({ pipeline: name, ...result });
        } catch (err: any) { res.status(500).json({ error: err.message }); }
        return;
    }

    const map: Record<string, string> = {
        finance: '/hermes/finance-pipeline',
        viral: '/hermes/viral-pipeline',
        'link-publish': '/hermes/link-publish',
        'discover-publish': '/hermes/discover-publish',
        'full-ops': '/hermes/full-ops',
    };
    const route = map[req.params.name];
    if (!route) return res.status(400).json({ error: `unknown pipeline: ${req.params.name}` });
    try {
        const result = await callWorker(route, req.body || {});
        res.json({ pipeline: req.params.name, ...result });
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

app.post('/arbitrage/discover-trends', async (req: Request, res: Response) => {
    try {
        const result = await callWorker('/arbitrage/discover-trends', req.body);
        res.json(result);
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

app.post('/arbitrage/source-assets', async (req: Request, res: Response) => {
    try {
        const result = await callWorker('/arbitrage/source-assets', req.body);
        res.json(result);
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

app.post('/arbitrage/download', async (req: Request, res: Response) => {
    try {
        const result = await callWorker('/arbitrage/download', req.body);
        res.json(result);
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

app.post('/arbitrage/distribute', async (req: Request, res: Response) => {
    try {
        const result = await callWorker('/arbitrage/distribute', req.body);
        res.json(result);
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

app.post('/arbitrage/yt-to-tiktok', async (req: Request, res: Response) => {
    try {
        const result = await callWorker('/yt-to-tiktok', req.body);
        res.json(result);
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

app.get('/arbitrage/status', async (_req: Request, res: Response) => {
    try {
        const [trends, assets, uploads] = await Promise.all([
            db.query(`SELECT status, COUNT(*) as count FROM trend_intel GROUP BY status`),
            db.query(`SELECT status, COUNT(*) as count FROM arbitrage_assets GROUP BY status`),
            db.query(`SELECT platform, status, COUNT(*) as count FROM arbitrage_uploads GROUP BY platform, status`),
        ]);
        res.json({ trends: trends.rows, assets: assets.rows, uploads: uploads.rows });
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

app.get('/arbitrage/assets', async (req: Request, res: Response) => {
    const { status } = req.query;
    try {
        const result = await db.query(
            `SELECT a.id, t.hashtag, a.youtube_title, a.youtube_url,
                    a.duration_secs, a.file_size_mb, a.status
             FROM arbitrage_assets a
             JOIN trend_intel t ON a.trend_id = t.id
             ${status ? `WHERE a.status = $1` : ''}
             ORDER BY a.id DESC LIMIT 100`,
            status ? [status] : []
        );
        res.json({ assets: result.rows });
    } catch (err: any) { res.status(500).json({ error: err.message }); }
});

// ─── Gig Copilot Endpoints ───────────────────────────────────────────────────

/** POST /gig/task/draft
 * Called by Python worker's gig_prepare.py → generate_draft()
 * Body: { taskPrompt, taskType, platform, rubric?, templateHint? }
 * Response: { draft: string }
 */
app.post('/gig/task/draft', async (req: Request, res: Response) => {
    const { taskPrompt, taskType, platform, rubric, templateHint } = req.body;

    if (!taskPrompt || !taskType || !platform) {
        return res.status(400).json({ error: 'taskPrompt, taskType, and platform are required' });
    }

    logger.info('GigCopilot: draft requested', { platform, taskType });

    try {
        const draft = await generateGigDraft(
            taskPrompt,
            taskType,
            platform,
            rubric ?? {},
            templateHint,
        );
        res.json({ draft, platform, taskType });
    } catch (err: any) {
        logger.error('gig/task/draft failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

/** POST /gig/task/score
 * Called by Python worker's gig_score.py → score_task()
 * Body: { taskPrompt, draftOutput, platform, taskType, rubric? }
 * Response: { score: float, risk_flags: string[], dimension_scores: object }
 */
app.post('/gig/task/score', async (req: Request, res: Response) => {
    const { taskPrompt, draftOutput, platform, taskType, rubric } = req.body;

    if (!taskPrompt || !draftOutput || !platform || !taskType) {
        return res.status(400).json({
            error: 'taskPrompt, draftOutput, platform, and taskType are required',
        });
    }

    logger.info('GigCopilot: score requested', { platform, taskType });

    try {
        const result = await scoreGigDraft(
            taskPrompt,
            draftOutput,
            platform,
            taskType,
            rubric ?? {},
        );
        res.json(result);
    } catch (err: any) {
        logger.error('gig/task/score failed', { error: err.message });
        res.status(500).json({ success: false, error: err.message });
    }
});

// ─── Error Handler ────────────────────────────────────────────────────────────
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
    logger.error('Unhandled error', { error: err.message, stack: err.stack });
    res.status(500).json({ error: 'Internal server error' });
});

// ─── Boot ─────────────────────────────────────────────────────────────────────
const PORT = Number(process.env.PORT ?? 3001);

async function start() {
    await connectDatabases();
    app.listen(PORT, () => {
        logger.info(`Manga Agents server running on port ${PORT}`);
        logger.info('Agents: POST /agents/detect-trends | /agents/select-panels | /agents/select-music | /agents/generate-caption | /agents/optimize | /agents/detect-shadow-ban | /agents/product-promo');
        logger.info('Pipeline: POST /pipeline/fetch-chapters | /pipeline/mark-published | GET /pipeline/pending-chapters | /pipeline/ready-videos | /pipeline/shadow-banned-accounts');
    });
}

start().catch((err) => {
    logger.error('Failed to start server', { error: err.message });
    process.exit(1);
});
