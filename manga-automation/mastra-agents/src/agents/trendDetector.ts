import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { db, getCached, logger } from '../tools/database';
import { fetchTrendingManga, fetchAniListTrending } from '../tools/mangadex';

// --------------------------------------------------------------------------
// Trend Detector Agent
// --------------------------------------------------------------------------
// Queries MangaDex and AniList to identify the top trending manga series,
// scores them, and upserts results into the `manga` DB table.
// --------------------------------------------------------------------------

export const trendDetector = new Agent({
    name: 'TrendDetector',
    id: 'trend-detector',
    instructions: `You are a manga trend analyst for a viral social media content studio.

Your mission: Find the TOP 20 currently trending manga series across all platforms.

Process:
1. Call fetch_trending_manga to get MangaDex popularity rankings
2. Call fetch_anilist_trending to get AniList trending data
3. Merge both lists, deduplicate by title, and compute a combined trending score
4. For each title, calculate:
   - viral_potential (0-10): How likely is this to blow up on TikTok/Reels?
   - content_availability: Does MangaDex have English chapters?
   - audience_size: Is this well-known enough to have viewers?
5. Call save_trending_manga to persist the top 20

Focus on series with BOTH high popularity AND recent chapters. Completed series with active fan bases (AOT, Demon Slayer) outperform obscure ongoing series.`,

    model: anthropic('claude-3-haiku-20240307'),

    tools: {
        fetch_trending_manga: {
            description: fetchTrendingManga.description,
            parameters: fetchTrendingManga.schema,
            execute: fetchTrendingManga.execute
        },

        fetch_anilist_trending: {
            description: fetchAniListTrending.description,
            parameters: fetchAniListTrending.schema,
            execute: fetchAniListTrending.execute
        },

        save_trending_manga: {
            description: 'Upsert trending manga results into the database',
            parameters: z.object({
                results: z.array(z.object({
                    title: z.string(),
                    mangadexId: z.string().optional(),
                    anilistId: z.number().optional(),
                    genre: z.string().optional(),
                    tags: z.array(z.string()).optional(),
                    trendingScore: z.number().min(0).max(100)
                }))
            }),
            execute: async ({ results }: { results: any[] }) => {
                let saved = 0;
                for (const manga of results) {
                    try {
                        await db.query(
                            `INSERT INTO manga (title, mangadex_id, anilist_id, genre, tags, trending_score, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())
               ON CONFLICT (title) DO UPDATE SET
                 mangadex_id    = COALESCE(EXCLUDED.mangadex_id, manga.mangadex_id),
                 anilist_id     = COALESCE(EXCLUDED.anilist_id, manga.anilist_id),
                 trending_score = EXCLUDED.trending_score,
                 updated_at     = NOW()`,
                            [
                                manga.title,
                                manga.mangadexId ?? null,
                                manga.anilistId ?? null,
                                manga.genre ?? null,
                                manga.tags ?? [],
                                manga.trendingScore
                            ]
                        );
                        saved++;
                    } catch (err: any) {
                        logger.warn('Failed to save manga', { title: manga.title, error: err.message });
                    }
                }
                logger.info(`Saved ${saved}/${results.length} trending manga`);
                return { saved, total: results.length };
            }
        }
    }
});

export async function detectTrends() {
    return trendDetector.generate(
        'Analyze trending manga from MangaDex and AniList. Save the top 20 most viral-potential series.'
    );
}
