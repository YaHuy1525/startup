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
import cors from 'cors';

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

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

// ─── Video Rendering via Remotion ─────────────────────────────────────────────

const VIDEOS_DIR = process.env.VIDEOS_DIR || '/data/videos';
const REMOTION_DIR = path.join(__dirname, '../remotion-renderer');
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
 * Renders a manga recap video using Remotion instead of FFmpeg.
 * Body: { chapterId: number }
 *
 * Flow:
 *   1. Query selected_panels for the chapter
 *   2. Build Remotion props JSON from panel paths + motion tags
 *   3. Spawn render-video.ts CLI
 *   4. Insert result into videos table
 *   5. Return { videoId, filePath, durationSecs, fileSizeMb }
 */
app.post('/pipeline/render-video', async (req: Request, res: Response) => {
    const { chapterId } = req.body;
    if (!chapterId) return res.status(400).json({ error: 'chapterId required' });

    logger.info('Pipeline: render-video started', { chapterId });
    try {
        // 1. Fetch selected panels + manga metadata
        const panelResult = await db.query(
            `SELECT sp.panels, sp.music_path, m.title, mc.chapter_number
             FROM selected_panels sp
             JOIN manga_chapters mc ON sp.chapter_id = mc.id
             JOIN manga m ON mc.manga_id = m.id
             WHERE sp.chapter_id = $1
             ORDER BY sp.selected_at DESC
             LIMIT 1`,
            [chapterId]
        );

        if (panelResult.rows.length === 0) {
            return res.status(404).json({ error: `No selected panels for chapter ${chapterId}` });
        }

        const row = panelResult.rows[0];
        const panels: any[] = typeof row.panels === 'string' ? JSON.parse(row.panels) : (row.panels || []);

        if (panels.length === 0) {
            return res.status(400).json({ error: 'Empty panel selection' });
        }

        // 2. Build Remotion props
        const remotionPanels = panels
            .filter((p: any) => p.localPath && fs.existsSync(p.localPath))
            .map((p: any) => ({
                imagePath: imagePathToDataUri(p.localPath),
                motionType: p.motionType || 'zoom_center',
                durationInFrames: PANEL_DURATION_FRAMES,
            }));

        if (remotionPanels.length === 0) {
            return res.status(400).json({ error: 'No valid local panel paths found' });
        }

        const sanitisedTitle = (row.title as string).replace(/[^a-zA-Z0-9]/g, '_');
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const filename = `${sanitisedTitle}_ch${row.chapter_number}_${timestamp}.mp4`;
        const outputPath = path.join(VIDEOS_DIR, filename);

        fs.mkdirSync(VIDEOS_DIR, { recursive: true });

        const props = {
            panels: remotionPanels,
            titleText: row.title,
            chapterText: `Chapter ${row.chapter_number}`,
            audioSrc: row.music_path || null,
            audioDuckingVolume: 0.4,
        };

        // 3. Write temp props file and render
        const propsPath = path.join(REMOTION_DIR, `.render-props-${chapterId}-${Date.now()}.json`);
        fs.writeFileSync(propsPath, JSON.stringify(props, null, 2));

        logger.info(`Rendering ${remotionPanels.length} panels via Remotion`, { chapterId, outputPath });

        const renderOutput = execSync(
            `npx tsx src/render-video.ts --props "${propsPath}" --output "${outputPath}"`,
            {
                cwd: REMOTION_DIR,
                encoding: 'utf-8',
                timeout: 10 * 60 * 1000, // 10 min
                maxBuffer: 50 * 1024 * 1024,
            }
        );

        // Clean up props file
        try { fs.unlinkSync(propsPath); } catch { }

        // 4. Parse render output
        const lines = renderOutput.trim().split('\n');
        const lastLine = lines[lines.length - 1];
        const renderResult = JSON.parse(lastLine);

        // 5. Insert into DB
        const videoInsert = await db.query(
            `INSERT INTO videos (chapter_id, file_path, duration_secs, file_size_mb, status, created_at)
             VALUES ($1, $2, $3, $4, 'ready', NOW())
             RETURNING id`,
            [chapterId, renderResult.filePath, renderResult.durationSecs, renderResult.fileSizeMb]
        );

        const videoId = videoInsert.rows[0]?.id;
        logger.info('Video rendered successfully', { videoId, ...renderResult });

        res.json({
            success: true,
            videoId,
            filePath: renderResult.filePath,
            durationSecs: renderResult.durationSecs,
            fileSizeMb: renderResult.fileSizeMb,
        });
    } catch (err: any) {
        logger.error('render-video failed', { error: err.message, stderr: err.stderr });
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
        logger.info('Agents: POST /agents/detect-trends | /agents/select-panels | /agents/select-music | /agents/generate-caption | /agents/optimize | /agents/detect-shadow-ban');
        logger.info('Pipeline: POST /pipeline/fetch-chapters | /pipeline/mark-published | GET /pipeline/pending-chapters | /pipeline/ready-videos | /pipeline/shadow-banned-accounts');
    });
}

start().catch((err) => {
    logger.error('Failed to start server', { error: err.message });
    process.exit(1);
});
