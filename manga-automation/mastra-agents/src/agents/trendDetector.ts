import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { db, getCached, logger } from '../tools/database';

// --------------------------------------------------------------------------
// Trend Detector Agent (AiToEarn — cross-domain)
// --------------------------------------------------------------------------
// Detects trending topics across ALL categories (tech, gaming, finance,
// fiction, anime, movies, art, tiktok_trending) using the genesis_categories
// table and cross-platform trend sources. Replaces the manga-only pipeline
// with general-purpose trend discovery.
// --------------------------------------------------------------------------

export const trendDetector = new Agent({
    name: 'TrendDetector',
    id: 'trend-detector',
    instructions: `You are a cross-domain trend analyst for an AI content marketing system (AiToEarn).

Your mission: Find the TOP 20 trending topics across ALL configured categories from
TikTok, Reddit, YouTube, and X/Twitter. Do NOT limit yourself to anime/manga —
cover tech, gaming, finance, fiction, movies, art, and viral TikTok content.

Process:
1. Call fetch_categories to get all active genesis_categories with their subreddits
   and TikTok hashtags
2. Call fetch_trend_intel to get the most recent trends from the trend_intel table
   (these are already populated by the Python fetchers)
3. For each category, calculate:
   - viral_potential (0-10): Based on trend_velocity and confidence
   - content_availability: Can we source/create content for this topic?
   - audience_size: Total post_count and avg_views
4. Call save_trending_topics to persist the top 20 cross-domain trends

Prioritize HIGH VELOCITY trends (fast-rising) over absolute volume. A topic with
100k posts growing fast is better than 1M posts that's been stale for weeks.`,

    model: anthropic('claude-3-haiku-20240307'),

    tools: {
        fetch_categories: {
            description: 'Get all active genesis categories with their subreddits and TikTok hashtags',
            parameters: z.object({}),
            execute: async () => {
                const rows = await db.query(
                    `SELECT id, slug, display_name, subreddits, tiktok_hashtags
                     FROM genesis_categories WHERE is_active = true`
                );
                return { categories: rows.rows };
            },
        },

        fetch_trend_intel: {
            description: 'Get the most recent cross-domain trends from trend_intel',
            parameters: z.object({
                limit: z.number().optional().default(50),
            }),
            execute: async ({ limit }: { limit?: number }) => {
                const rows = await db.query(
                    `SELECT ti.*, gc.slug AS category_slug, gc.display_name AS category_name
                     FROM trend_intel ti
                     LEFT JOIN genesis_categories gc ON gc.id = ti.category_id
                     WHERE ti.status IN ('new', 'sourcing')
                     ORDER BY COALESCE(ti.trend_velocity, 0) DESC,
                              COALESCE(ti.confidence, 0) DESC
                     LIMIT $1`,
                    [limit ?? 50]
                );
                return { trends: rows.rows };
            },
        },

        save_trending_topics: {
            description: 'Upsert ranked trending topics with category assignment',
            parameters: z.object({
                results: z.array(z.object({
                    topic: z.string(),
                    category_id: z.number().optional(),
                    category_slug: z.string().optional(),
                    viral_potential: z.number().min(0).max(10),
                    confidence: z.number().min(0).max(1),
                    reason: z.string().optional(),
                })),
            }),
            execute: async ({ results }: { results: any[] }) => {
                let saved = 0;
                for (const t of results) {
                    try {
                        await db.query(
                            `INSERT INTO trend_intel
                             (hashtag, confidence, trend_velocity, status, discovered_at, category_id)
                             VALUES ($1, $2, $3, 'new', NOW(),
                               (SELECT id FROM genesis_categories WHERE slug = $4 LIMIT 1))
                             ON CONFLICT (hashtag, region) DO UPDATE SET
                               confidence = EXCLUDED.confidence,
                               last_researched_at = NOW()`,
                            [t.topic, t.confidence, t.viral_potential / 10, t.category_slug ?? null]
                        );
                        saved++;
                    } catch (err: any) {
                        logger.warn('Failed to save trend', { topic: t.topic, error: err.message });
                    }
                }
                logger.info(`Saved ${saved}/${results.length} cross-domain trends`);
                return { saved, total: results.length };
            },
        },
    },
});

export async function detectTrends() {
    return trendDetector.generate(
        'Analyze trending topics across ALL categories (tech, gaming, finance, fiction, anime, movies, art, tiktok). ' +
        'Fetch categories, then fetch trend intel, then save the top 20 most viral-potential topics with category assignments.'
    );
}
