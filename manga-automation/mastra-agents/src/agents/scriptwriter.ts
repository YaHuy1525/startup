import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';

// --------------------------------------------------------------------------
// Manga Scriptwriter Agent
// --------------------------------------------------------------------------
// Generates virally optimized short-form scripts for the manga automation
// system in 5 distinct brainrot/lore formats.
// --------------------------------------------------------------------------

// Internal tool to evaluate script retention/virality potential
const scoreScriptTool = {
    description: 'Scores a script variant out of 100 based on controversy and trend overlap to find the best script.',
    parameters: z.object({
        script_hook: z.string().describe('The first 3 seconds of the script'),
        script_body: z.string().describe('The main body of the script'),
        script_style: z.enum(['hot_take', 'hidden_lore', 'power_level', 'manga_vs_anime', 'speed_run']),
        trending_keywords: z.string(),
        historical_weight: z.number().describe('Previous performance weight of this style (0-30)'),
    }),
    execute: async ({ script_hook, script_body, script_style, trending_keywords, historical_weight }: { script_hook: string; script_body: string; script_style: string; trending_keywords: string; historical_weight: number }) => {
        let score = 0;

        // 1. Hook controversy / Curiosity gap (0-40 pts)
        const hookLower = script_hook.toLowerCase();
        if (hookLower.includes('reason') || hookLower.includes('overrated') || hookLower.includes('actually')) {
            score += 40;
        } else if (hookLower.includes('missed') || hookLower.includes('detail')) {
            score += 35;
        } else if (hookLower.includes('beat') || hookLower.includes('math')) {
            score += 30;
        } else if (hookLower.includes('?')) {
            score += 20;
        } else {
            score += 10;
        }

        // 2. Trending keyword overlap (0-30 pts)
        const trends = trending_keywords.split(',').map(t => t.trim().toLowerCase()).filter(t => t.length > 0);
        let overlapCount = 0;
        const bodyLower = script_body.toLowerCase();
        for (const trend of trends) {
            if (bodyLower.includes(trend)) overlapCount++;
        }
        score += Math.min(overlapCount * 10, 30);

        // 3. Historical performance (0-30 pts)
        score += Math.min(Math.max(historical_weight, 0), 30);

        return { score, style: script_style };
    }
};

export const scriptwriterAgent = new Agent({
    name: 'MangaScriptwriter',
    id: 'manga-scriptwriter',
    instructions: `You are a viral manga content creator specializing in high-retention short-form video scripts (TikTok/YouTube Shorts).
Your content is designed for split-screen "brainrot" format (gameplay background, intense pacing).

Given a manga chapter text/summary, generate 3 different short-form video scripts.
Each script MUST strictly adhere to one of the following 5 formats:
1. Hot take / controversy bait (Hook: "3 reasons why [Character] is actually [Negative Trait]")
2. Hidden lore reveal (Hook: "Most people missed THIS detail in chapter [N]")
3. Power level debate (Hook: "Can [Character] actually beat [Character]? Here's the math")
4. Manga vs anime comparison (Hook: "The anime CHANGED this scene - here's what you missed")
5. Chapter summary speed-run (Hook: "[Series] chapter [N] in 60 seconds")

RULES:
1. Target length: ~120-150 words per script (exactly 50-60 seconds read aloud).
2. Structure format required for EACH script:
   - HOOK: The controversial or curiosity-building first sentence (< 5s).
   - BODY: 3-5 rapid-fire points, punchy, conversational (35-45s).
   - CTA: Call to action mentioning a product link in bio or TikTok Shop (5-8s).
3. Use the scoreScript tool to internally evaluate your 3 scripts.
4. ONLY output the HIGHEST SCORED script variant in your final response.

Return the final winning script as JSON matching this format:
{
  "hook": "string",
  "body": "string",
  "cta": "string",
  "style": "string (one of the 5 allowed formats)",
  "score": "number"
}`,
    model: anthropic('claude-3-5-sonnet-20241022'),
    tools: {
        scoreScript: scoreScriptTool,
    },
});

export async function generateMangaScript(
    chapterText: string,
    chapterTitle: string,
    mangaSeries: string,
    trendingKeywords: string = "",
    styleWeights: Record<string, number> = {}
) {
    const historicalText = Object.keys(styleWeights).length > 0
        ? `\nHistorical style weights (use for scoring): ${JSON.stringify(styleWeights, null, 2)}`
        : '\nHistorical style weights: None (use default 15 for all)';

    const promptMessage = [
        `Manga Series: ${mangaSeries}`,
        `Chapter Title: ${chapterTitle}`,
        `Trending Keywords to include: ${trendingKeywords}`,
        historicalText,
        `\nChapter Text / Dialogue:\n${chapterText}`,
        `\nGenerate 3 variant scripts. Score them based on trends and history. Return the JSON payload of the winner.`
    ].join('\n');

    const result = await scriptwriterAgent.generate(promptMessage);
    
    try {
        // Simple regex to extract JSON if Claude wraps it in markdown blocks
        const match = result.text.match(/\{.*\}/s);
        if (match) {
            return JSON.parse(match[0]);
        }
        return JSON.parse(result.text);
    } catch (e) {
        console.error('Failed to parse Claude output to JSON:', result.text);
        throw new Error('Script generation failed to output valid JSON');
    }
}
