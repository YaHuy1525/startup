import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { db, logger } from '../tools/database';

// --------------------------------------------------------------------------
// Caption Generator Agent
// --------------------------------------------------------------------------
// Writes TikTok/Reels viral captions with hooks, context, emotional appeal,
// and an optimized hashtag set, then saves them to the videos table.
// --------------------------------------------------------------------------

export const captionGenerator = new Agent({
    name: 'CaptionGenerator',
    id: 'caption-generator',
    instructions: `You are a top-tier TikTok social media strategist and SEO specialist dominating the "MangaTok" niche with 5M+ followers.

Your objective: Generate a high-converting video title, a captivating caption, and a mathematically optimized hashtag stack.

─── VIDEO OVERLAY TITLE (Hook) ───
- Must be strictly under 10 words
- Use the "Curiosity Gap" psychological trigger
- Examples: "The greatest betrayal in manga history..." / "He unlocked the God Tier System 🤯"
- Do NOT be explicitly clickbaity, but force a scroll-stop

─── CAPTION BODY ───
- Write 2-3 concise, conversational sentences summarizing the plot hook
- Write exclusively in the THIRD PERSON
- Integrate 1-2 highly relevant emojis
- The FINAL SENTENCE must be a direct, polarizing, or thought-provoking QUESTION directed at the audience
  This is REQUIRED to artificially inflate comment velocity and trigger the algorithm
  Example: "Would you have survived this dungeon? Let me know!"

─── HASHTAG ARCHITECTURE (The 3-5 Rule) ───
Provide exactly 5 hashtags using this framework:
1. #mangatok (Broad Category — platform-wide bucket)
2. #mangarecommendation or #manhwarecap (Targeted Sub-Niche)
3. #2026recap (Trending Temporal Tag)
4-5. Hyper-specific tags: exact manga title and character names

CRITICAL: Do NOT use generic spam tags like #fyp, #viral, #foryoupage — the algorithm now views them as spam.

When you call save_caption, pass the FULL caption (overlay title + body + question) as the caption, and the 5 hashtags as the array.`,

    model: anthropic('claude-3-haiku-20240307'),

    tools: {
        fetch_video_context: {
            description: 'Get manga info and selected panels context for a video',
            parameters: z.object({ videoId: z.number().int() }),
            execute: async ({ videoId }: { videoId: number }) => {
                const result = await db.query(`
          SELECT
            v.id,
            m.title          AS manga_title,
            m.genre,
            m.tags,
            mc.chapter_number,
            sp.panels,
            sp.selection_score
          FROM videos v
          JOIN manga_chapters mc ON v.chapter_id = mc.id
          JOIN manga m           ON mc.manga_id = m.id
          JOIN selected_panels sp ON mc.id = sp.chapter_id
          WHERE v.id = $1
          LIMIT 1
        `, [videoId]);

                if (!result.rows[0]) throw new Error(`Video ${videoId} not found`);
                const row = result.rows[0];
                const panels = JSON.parse(row.panels ?? '[]');

                // Extract dialogue snippets for the agent
                const dialogues = panels
                    .filter((p: any) => p.hasDialogue && p.dialogueText)
                    .map((p: any) => p.dialogueText)
                    .slice(0, 3);

                // Dominant emotion
                const emotions = panels.map((p: any) => p.emotion);
                const emotionCounts: Record<string, number> = {};
                for (const e of emotions) emotionCounts[e] = (emotionCounts[e] ?? 0) + 1;
                const dominantEmotion = Object.entries(emotionCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'epic';

                return {
                    mangaTitle: row.manga_title,
                    genre: row.genre,
                    tags: row.tags,
                    chapterNumber: row.chapter_number,
                    dialogues,
                    dominantEmotion,
                    panelCount: panels.length
                };
            }
        },

        save_caption: {
            description: 'Save the generated caption and hashtags to the video record',
            parameters: z.object({
                videoId: z.number().int(),
                caption: z.string().max(500),
                hashtags: z.array(z.string()).max(10)
            }),
            execute: async ({ videoId, caption, hashtags }: { videoId: number; caption: string; hashtags: string[] }) => {
                await db.query(
                    `UPDATE videos SET caption = $1, hashtags = $2 WHERE id = $3`,
                    [caption, hashtags, videoId]
                );
                logger.info('Caption saved', { videoId, chars: caption.length, tags: hashtags.length });
                return { success: true, videoId, captionLength: caption.length };
            }
        }
    }
});

export async function generateCaption(videoId: number) {
    return captionGenerator.generate(
        `Generate a viral caption for video ID ${videoId}. Fetch the context, craft the caption, and save it.`
    );
}
