import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { db, logger } from '../tools/database';

// --------------------------------------------------------------------------
// Content Optimizer Agent
// --------------------------------------------------------------------------
// Scrapes analytics, identifies what panel types and emotions drive views,
// and updates the panel_scores table so future selection improves.
// --------------------------------------------------------------------------

export const contentOptimizer = new Agent({
    name: 'ContentOptimizer',
    id: 'content-optimizer',
    instructions: `You are a data-driven manga content strategist.

Your role: Analyze what's working and update scoring weights for future content.

Analysis process:
1. Fetch recent video performance data (last 7 days)
2. Group by: manga series, emotion type, post time, platform
3. Identify top performers (top 20% by views)
4. Calculate which panel emotions drive most engagement
5. Update panel_scores table with learned weights
6. Generate a performance report

Insights to look for:
- Which manga series get most views (push more)
- Which emotion type (epic/sad/funny) resonates most per platform
- Optimal time ranges (already determined by n8n schedule but validate)
- Caption patterns that drive comments

Output format expectation:
- Clear summary of winners/losers
- Specific recommendation changes
- Updated scoring weights`,

    model: anthropic('claude-3-haiku-20240307'),

    tools: {
        fetch_performance_data: {
            description: 'Fetch analytics for videos published in the last N days',
            parameters: z.object({ days: z.number().int().min(1).max(30).default(7) }),
            execute: async ({ days }: { days: number }) => {
                const result = await db.query(`
          SELECT
            m.title                    AS manga_title,
            m.genre,
            sp.panels,
            pv.platform,
            va.views,
            va.likes,
            va.comments,
            va.shares,
            pv.published_at
          FROM video_analytics va
          JOIN published_videos pv ON va.published_video_id = pv.id
          JOIN videos v           ON pv.video_id = v.id
          JOIN manga_chapters mc  ON v.chapter_id = mc.id
          JOIN manga m            ON mc.manga_id = m.id
          JOIN selected_panels sp ON mc.id = sp.chapter_id
          WHERE va.scraped_at >= NOW() - INTERVAL '${days} days'
          ORDER BY va.views DESC
          LIMIT 200
        `);

                return result.rows.map(row => ({
                    mangaTitle: row.manga_title,
                    genre: row.genre,
                    platform: row.platform,
                    views: row.views,
                    likes: row.likes,
                    comments: row.comments,
                    shares: row.shares,
                    dominantEmotion: getDominantEmotion(JSON.parse(row.panels ?? '[]')),
                    publishedAt: row.published_at
                }));
            }
        },

        update_panel_scores: {
            description: 'Update emotion-based scoring weights based on analytics',
            parameters: z.object({
                scores: z.array(z.object({
                    mangaTitle: z.string().optional(),
                    emotionType: z.string(),
                    avgViews: z.number().int(),
                    sampleCount: z.number().int()
                }))
            }),
            execute: async ({ scores }: { scores: any[] }) => {
                for (const score of scores) {
                    const manga = score.mangaTitle
                        ? await db.query('SELECT id FROM manga WHERE title = $1', [score.mangaTitle])
                        : null;
                    const mangaId = manga?.rows[0]?.id ?? null;

                    await db.query(`
            INSERT INTO panel_scores (manga_id, emotion_type, avg_views, sample_count, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (manga_id, emotion_type)
            DO UPDATE SET
              avg_views    = $3,
              sample_count = $4,
              updated_at   = NOW()
          `, [mangaId, score.emotionType, score.avgViews, score.sampleCount]);
                }
                logger.info(`Updated ${scores.length} panel score weights`);
                return { updated: scores.length };
            }
        },

        fetch_top_performers: {
            description: 'Get the best-performing manga series in the last 30 days',
            parameters: z.object({ limit: z.number().int().default(10) }),
            execute: async ({ limit }: { limit: number }) => {
                const result = await db.query(`
          SELECT
            m.title,
            AVG(va.views) AS avg_views,
            SUM(va.views) AS total_views,
            COUNT(*)      AS video_count
          FROM video_analytics va
          JOIN published_videos pv ON va.published_video_id = pv.id
          JOIN videos v           ON pv.video_id = v.id
          JOIN manga_chapters mc  ON v.chapter_id = mc.id
          JOIN manga m            ON mc.manga_id = m.id
          WHERE va.scraped_at >= NOW() - INTERVAL '30 days'
          GROUP BY m.id, m.title
          ORDER BY avg_views DESC
          LIMIT $1
        `, [limit]);
                return result.rows;
            }
        }
    }
});

// Helper: get dominant emotion from panel selection JSON
function getDominantEmotion(panels: any[]): string {
    if (!panels.length) return 'neutral';
    const counts: Record<string, number> = {};
    for (const p of panels) counts[p.emotion] = (counts[p.emotion] ?? 0) + 1;
    return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'neutral';
}

export async function optimizeContent() {
    return contentOptimizer.generate(
        'Analyze last 7 days of video performance. Update scoring weights and return an optimization report.'
    );
}
