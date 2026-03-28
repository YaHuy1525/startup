import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { db, logger } from '../tools/database';

// ─── MusicSelector Agent ──────────────────────────────────────────────────────
// Picks the best TikTok sound for a chapter based on its dominant panel emotion.
// Sound IDs come from the `tiktok_sounds` table, which is populated by
// scripts/fetch_tiktok_sounds.py (runs periodically via n8n or cron).
// ─────────────────────────────────────────────────────────────────────────────

/** Emotion groups that map to each other as fallbacks */
const EMOTION_FALLBACKS: Record<string, string[]> = {
    epic:     ['epic', 'shocking', 'neutral'],
    sad:      ['sad',  'romantic', 'neutral'],
    funny:    ['funny','neutral',  'epic'],
    shocking: ['shocking', 'epic', 'neutral'],
    romantic: ['romantic', 'sad',  'neutral'],
    neutral:  ['neutral',  'epic', 'sad'],
};

function dominantEmotion(panels: any[]): string {
    const counts: Record<string, number> = {};
    for (const p of panels) {
        const e: string = p.emotion ?? 'neutral';
        counts[e] = (counts[e] ?? 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'neutral';
}

export const musicSelector = new Agent({
    name: 'MusicSelector',
    id: 'music-selector',
    instructions: `You pick the best TikTok native sound for a manga short-video.

Steps you MUST follow in order:
1. Call get_chapter_emotion to find the chapter's dominant emotion.
2. Call select_tiktok_sound with the chapterId and the resolved emotion.
3. Report the chosen sound title and author, or warn if no sounds are catalogued.

Emotion → sound mood guidance:
- epic / shocking  → intense orchestral, battle OST, hype rap
- sad              → piano, melancholic ballad, lo-fi
- funny            → upbeat, quirky, meme audio
- romantic         → soft piano, gentle J-pop
- neutral          → popular anime opening, ambient`,

    model: anthropic('claude-3-haiku-20240307'),

    tools: {
        get_chapter_emotion: {
            description: 'Returns the dominant emotion from the chapter\'s selected panels',
            parameters: z.object({ chapterId: z.number().int() }),
            execute: async ({ chapterId }: { chapterId: number }) => {
                const result = await db.query(
                    `SELECT panels
                     FROM selected_panels
                     WHERE chapter_id = $1
                     ORDER BY selected_at DESC
                     LIMIT 1`,
                    [chapterId]
                );
                if (!result.rows[0]) throw new Error(`No selected panels for chapter ${chapterId}`);

                const panels: any[] =
                    typeof result.rows[0].panels === 'string'
                        ? JSON.parse(result.rows[0].panels)
                        : (result.rows[0].panels ?? []);

                const emotion = dominantEmotion(panels);
                const counts: Record<string, number> = {};
                for (const p of panels) {
                    const e: string = p.emotion ?? 'neutral';
                    counts[e] = (counts[e] ?? 0) + 1;
                }

                logger.info('Chapter emotion resolved', { chapterId, emotion, counts });
                return { chapterId, dominantEmotion: emotion, breakdown: counts };
            }
        },

        select_tiktok_sound: {
            description: 'Pick the best TikTok sound from the catalogue for this emotion and save it to selected_panels',
            parameters: z.object({
                chapterId: z.number().int(),
                emotion:   z.string()
            }),
            execute: async ({ chapterId, emotion }: { chapterId: number; emotion: string }) => {
                const fallbacks = EMOTION_FALLBACKS[emotion] ?? ['neutral'];

                // Query: find the most-trending, least-used sound matching any fallback emotion
                const result = await db.query(
                    `SELECT id, tiktok_id, title, author, emotion_tags, trending_rank, use_count
                     FROM tiktok_sounds
                     WHERE is_active = true
                       AND emotion_tags && $1::text[]
                     ORDER BY trending_rank ASC NULLS LAST, use_count ASC
                     LIMIT 1`,
                    [fallbacks]
                );

                if (!result.rows[0]) {
                    logger.warn('No TikTok sounds in catalogue — run scripts/fetch_tiktok_sounds.py', { chapterId, emotion });
                    return {
                        chapterId,
                        emotion,
                        tiktokSoundId: null,
                        title: null,
                        message: 'No sounds catalogued yet. Run: python scripts/fetch_tiktok_sounds.py'
                    };
                }

                const sound = result.rows[0];

                // Save the selection to selected_panels
                await db.query(
                    `UPDATE selected_panels
                     SET tiktok_sound_id = $1, tiktok_sound_title = $2
                     WHERE chapter_id = $3`,
                    [sound.tiktok_id, sound.title, chapterId]
                );

                // Increment use_count so the same sound isn't picked every time
                await db.query(
                    `UPDATE tiktok_sounds SET use_count = use_count + 1 WHERE id = $1`,
                    [sound.id]
                );

                logger.info('TikTok sound selected', {
                    chapterId,
                    emotion,
                    soundId: sound.tiktok_id,
                    title: sound.title
                });

                return {
                    chapterId,
                    emotion,
                    tiktokSoundId: sound.tiktok_id,
                    title: sound.title,
                    author: sound.author,
                    message: `Selected "${sound.title}" by ${sound.author ?? 'Unknown'} (id: ${sound.tiktok_id})`
                };
            }
        }
    }
});

// ─── Programmatic entry point ─────────────────────────────────────────────────

export async function selectMusic(chapterId: number) {
    return musicSelector.generate(
        `Select a TikTok background sound for chapter ID ${chapterId}. Get the emotion first, then pick the best sound.`
    );
}
