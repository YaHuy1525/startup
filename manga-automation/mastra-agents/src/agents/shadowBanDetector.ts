import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { db, logger } from '../tools/database';

// --------------------------------------------------------------------------
// Shadow Ban Detector Agent
// --------------------------------------------------------------------------
// Analyses TikTok account analytics to detect shadow bans using both
// quantitative FYP-ratio checks and Claude's qualitative pattern analysis.
// --------------------------------------------------------------------------

const FYP_THRESHOLD = parseFloat(process.env.SHADOW_BAN_FYP_THRESHOLD ?? '0.10');

export const shadowBanDetector = new Agent({
    name: 'ShadowBanDetector',
    id: 'shadow-ban-detector',
    instructions: `You are a TikTok growth analyst specialising in shadow ban detection.

Your mission: Identify which accounts are shadow-banned by analysing analytics data.

Shadow ban indicators (flag if ANY are present for 5+ consecutive posts):
1. FYP views < 10% of total views (primary signal)
2. Views dropped > 80% compared to account average
3. Zero new follower gains for 7+ days
4. Comments disabled or severely reduced
5. Views plateau at exactly the same number (capped)

Process:
1. Call fetch_all_account_analytics to get performance data
2. For each account, compute FYP%, engagement rate, and trend direction
3. Identify shadow banned accounts (FYP < threshold)
4. Call update_account_status to flag each affected account
5. Return a clear summary: how many accounts checked, how many flagged

Be conservative: only flag if you have strong evidence (multiple signals).
False positives cause unnecessary disruption.`,

    model: anthropic('claude-3-haiku-20240307'),

    tools: {
        fetch_all_account_analytics: {
            description: 'Fetch recent analytics for all active TikTok accounts',
            parameters: z.object({
                days: z.number().int().min(1).max(30).default(7),
                min_posts: z.number().int().default(5)
            }),
            execute: async ({ days, min_posts }: { days: number; min_posts: number }) => {
                const result = await db.query(`
                    SELECT
                        ta.id                   AS account_id,
                        ta.username,
                        ta.shadow_banned,
                        ta.upload_failures,
                        ta.total_posts,
                        ta.last_post_at,
                        COUNT(pv.id)            AS post_count,
                        AVG(va.views)           AS avg_views,
                        AVG(va.fyp_views)       AS avg_fyp_views,
                        AVG(va.likes)           AS avg_likes,
                        AVG(va.comments)        AS avg_comments,
                        CASE
                            WHEN AVG(va.views) > 0
                            THEN AVG(va.fyp_views::float / NULLIF(va.views, 0))
                            ELSE NULL
                        END                     AS fyp_ratio,
                        JSON_AGG(
                            JSON_BUILD_OBJECT(
                                'views',        va.views,
                                'fyp_views',    va.fyp_views,
                                'likes',        va.likes,
                                'published_at', pv.published_at
                            ) ORDER BY pv.published_at DESC
                        ) FILTER (WHERE va.id IS NOT NULL) AS recent_posts
                    FROM tiktok_accounts ta
                    LEFT JOIN published_videos pv
                        ON pv.account_id = ta.id
                        AND pv.published_at >= NOW() - INTERVAL '${days} days'
                    LEFT JOIN video_analytics va ON va.published_video_id = pv.id
                    WHERE ta.account_status != 'banned'
                    GROUP BY ta.id
                    HAVING COUNT(pv.id) >= ${min_posts}
                `);

                return result.rows.map(row => ({
                    accountId: row.account_id,
                    username: row.username,
                    currentlyShadowBanned: row.shadow_banned,
                    totalPosts: row.total_posts,
                    uploadFailures: row.upload_failures,
                    lastPostAt: row.last_post_at,
                    postCount: row.post_count,
                    avgViews: Math.round(row.avg_views ?? 0),
                    avgFypViews: Math.round(row.avg_fyp_views ?? 0),
                    avgLikes: Math.round(row.avg_likes ?? 0),
                    fypRatio: row.fyp_ratio != null ? parseFloat(row.fyp_ratio).toFixed(4) : null,
                    fypThreshold: FYP_THRESHOLD,
                    recentPosts: row.recent_posts ?? []
                }));
            }
        },

        update_account_status: {
            description: 'Flag or clear shadow ban for a TikTok account',
            parameters: z.object({
                accountId: z.number().int(),
                shadowBanned: z.boolean(),
                reason: z.string(),
                fypPercentage: z.number().optional()
            }),
            execute: async ({
                accountId,
                shadowBanned,
                reason,
                fypPercentage
            }: {
                accountId: number;
                shadowBanned: boolean;
                reason: string;
                fypPercentage?: number;
            }) => {
                if (shadowBanned) {
                    await db.query(
                        `UPDATE tiktok_accounts
                         SET shadow_banned = true,
                             shadow_ban_detected_at = NOW(),
                             account_status = 'paused'
                         WHERE id = $1`,
                        [accountId]
                    );
                    await db.query(
                        `INSERT INTO shadow_ban_events
                             (account_id, detected_at, detection_method, fyp_percentage, notes)
                         VALUES ($1, NOW(), 'ai_analysis', $2, $3)`,
                        [accountId, fypPercentage ?? null, reason]
                    );
                    logger.warn(`Account id=${accountId} flagged as shadow-banned`, { reason });
                } else {
                    await db.query(
                        `UPDATE tiktok_accounts
                         SET shadow_banned = false,
                             shadow_ban_detected_at = NULL,
                             account_status = 'active'
                         WHERE id = $1`,
                        [accountId]
                    );
                    await db.query(
                        `UPDATE shadow_ban_events
                         SET resolved_at = NOW(), notes = COALESCE(notes, '') || ' | Resolved: ' || $2
                         WHERE account_id = $1 AND resolved_at IS NULL`,
                        [accountId, reason]
                    );
                    logger.info(`Account id=${accountId} shadow-ban cleared`, { reason });
                }

                return { accountId, shadowBanned, updated: true };
            }
        },

        fetch_account_history: {
            description: 'Get shadow ban event history for an account',
            parameters: z.object({ accountId: z.number().int() }),
            execute: async ({ accountId }: { accountId: number }) => {
                const result = await db.query(
                    `SELECT detected_at, resolved_at, detection_method, fyp_percentage, notes
                     FROM shadow_ban_events
                     WHERE account_id = $1
                     ORDER BY detected_at DESC
                     LIMIT 10`,
                    [accountId]
                );
                return result.rows;
            }
        }
    }
});

export async function detectShadowBans() {
    return shadowBanDetector.generate(
        `Analyse all TikTok account analytics for the past 7 days.
        Identify any shadow-banned accounts (FYP ratio < ${FYP_THRESHOLD}).
        Update their status and return a summary of findings.`
    );
}
