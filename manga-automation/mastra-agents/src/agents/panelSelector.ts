import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import Anthropic from '@anthropic-ai/sdk';
import { z } from 'zod';
import { db, logger } from '../tools/database';
import { panelToBase64 } from '../tools/scraper';
import type { PanelAnalysis, SelectedPanel } from '../types';

const vision = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// --------------------------------------------------------------------------
// Programmatic Panel Selector orchestrator
// --------------------------------------------------------------------------
// Uses Claude Vision natively to score panels, orchestrated via code
// instead of relying on the Agent loop.
// --------------------------------------------------------------------------

const fetchChapterPanels = async ({ chapterId }: { chapterId: number }) => {
    const result = await db.query(
        `SELECT mc.panel_urls, mc.local_paths, m.title, mc.chapter_number
         FROM manga_chapters mc
         JOIN manga m ON mc.manga_id = m.id
         WHERE mc.id = $1`,
        [chapterId]
    );
    if (!result.rows[0]) throw new Error(`Chapter ${chapterId} not found`);
    const row = result.rows[0];
    const urls: string[] = typeof row.panel_urls === 'string' ? JSON.parse(row.panel_urls) : (row.panel_urls ?? []);
    const locals: string[] = typeof row.local_paths === 'string' ? JSON.parse(row.local_paths) : (row.local_paths ?? []);
    return {
        mangaTitle: row.title,
        chapterNumber: row.chapter_number,
        panels: urls.map((url, i) => ({ index: i, url, localPath: locals[i] ?? null }))
    };
};

const analyzePanel = async ({ source, panelIndex }: { source: string; panelIndex: number }): Promise<PanelAnalysis> => {
    try {
        const { base64, mediaType } = await panelToBase64.execute({ source });

        const response = await vision.messages.create({
            model: 'claude-3-5-sonnet-20241022',
            max_tokens: 500,
            messages: [{
                role: 'user',
                content: [
                    {
                        type: 'image',
                        source: { type: 'base64', media_type: mediaType as any, data: base64 }
                    },
                    {
                        type: 'text',
                        text: `You are an elite anime/manga video editor and social media retention analyst.
Your objective is to evaluate this manga panel for a high-retention vertical short-form video.

Score it 0-100 based on:
- Visual Clarity (Mobile-First): Bold subjects, expressive character physiology, high-kinetic action. Strictly avoid text-heavy panels with excessive dialogue bubbles (illegible on mobile).
- Emotional Gravity: Panels evoking epic, devastating, shocking, or romantic reactions score highest.
- Narrative Hook: Does this panel create a "curiosity gap" that compels the viewer to keep watching?
- Standalone Impact: Can a viewer appreciate it without chapter context?

Also determine the optimal MOTION EFFECT for this panel when rendered as video:
- "zoom_center" → for character reveals, close-ups, emotional moments
- "pan_right"   → for action sequences, wide battle scenes, horizontal flow
- "pan_up"      → for vertical establishing shots, tall environments, dramatic reveals

And assign a primary AUDIO MOOD tag for background music selection:
- "phonk" → intense action, fight scenes, power-ups
- "melancholic_piano" → sad moments, deaths, emotional flashbacks
- "lofi" → slice of life, calm, comedic
- "intense_synth" → dark fantasy, suspense, psychological

Reply with ONLY a JSON object (no other text, no markdown fences):
{"score":75,"reasoning":"Dynamic action pose with strong lighting contrast","emotion":"epic","hasDialogue":false,"dialogueText":null,"recommended":true,"motionType":"zoom_center","audioMood":"phonk"}

emotion must be exactly one of: epic, sad, funny, shocking, romantic, neutral
motionType must be one of: zoom_center, pan_right, pan_up
audioMood must be one of: phonk, melancholic_piano, lofi, intense_synth`
                    }
                ]
            }]
        });

        const raw = response.content[0].type === 'text' ? response.content[0].text : '{}';
        // Strip markdown fences if model adds them anyway
        const cleanJson = raw.replace(/```json\s*/gi, '').replace(/```/g, '').trim();

        // If response is an apology/refusal rather than JSON, assign a neutral mid-score
        if (!cleanJson.startsWith('{')) {
            logger.warn(`Panel ${panelIndex} returned non-JSON response, assigning default score`);
            return { score: 40, reasoning: 'Model returned non-JSON', emotion: 'neutral', hasDialogue: false, recommended: true, motionType: 'zoom_center', audioMood: 'phonk' };
        }

        const parsed = JSON.parse(cleanJson);
        return {
            score: parsed.score ?? 50,
            reasoning: parsed.reasoning ?? '',
            emotion: parsed.emotion ?? 'neutral',
            hasDialogue: parsed.hasDialogue ?? false,
            dialogueText: parsed.dialogueText,
            recommended: parsed.recommended ?? (parsed.score >= 60),
            motionType: parsed.motionType ?? 'zoom_center',
            audioMood: parsed.audioMood ?? 'phonk',
        };
    } catch (err: any) {
        logger.warn(`Panel ${panelIndex} analysis failed: ${err.message}`);
        // Return a passing default score so pipeline doesn't stall completely
        return { score: 40, reasoning: 'Analysis failed', emotion: 'neutral', hasDialogue: false, recommended: true, motionType: 'zoom_center', audioMood: 'phonk' };
    }
};

const saveSelectedPanels = async (params: { chapterId: number; selectedPanels: SelectedPanel[] }) => {
    const avgScore = params.selectedPanels.length > 0 ? (params.selectedPanels.reduce((s, p) => s + p.score, 0) / params.selectedPanels.length) : 0;

    const result = await db.query(
        `INSERT INTO selected_panels (chapter_id, panels, selection_score)
         VALUES ($1, $2, $3)
         ON CONFLICT DO NOTHING
         RETURNING id`,
        [params.chapterId, JSON.stringify(params.selectedPanels), avgScore]
    );

    await db.query(
        `UPDATE manga_chapters SET processed = true WHERE id = $1`,
        [params.chapterId]
    );

    logger.info('Panels selected', {
        chapterId: params.chapterId,
        count: params.selectedPanels.length,
        avgScore: avgScore.toFixed(1)
    });

    return { selectionId: result.rows[0]?.id, count: params.selectedPanels.length, avgScore };
};

export async function selectPanels(chapterId: number) {
    logger.info(`Starting programmed panel selection for chapter ${chapterId}...`);

    // 1. Fetch Panels
    const chapter = await fetchChapterPanels({ chapterId });
    logger.info(`Fetched ${chapter.panels.length} panels for ${chapter.mangaTitle}`);

    // Sample up to 15 evenly spaced panels for analysis (produces 10 selections for ≥60s videos)
    const count = chapter.panels.length;
    const stride = Math.max(1, Math.floor(count / 15));
    const panelsToAnalyze = chapter.panels.filter((_, i) => i % stride === 0).slice(0, 15);

    const analyzed: SelectedPanel[] = [];

    // 2. Map and analyze serially to avoid rate limit spikes
    for (const p of panelsToAnalyze) {
        logger.info(`Analyzing panel ${p.index} via Vision API...`);
        const result = await analyzePanel({ source: p.localPath || p.url, panelIndex: p.index });

        analyzed.push({
            panelIndex: p.index,
            url: p.url,
            localPath: p.localPath ?? undefined,
            ...result
        });

        // small delay for anthropic rate limit
        await new Promise(r => setTimeout(r, 600));
    }

    // 3. Select top 10 for ≥60s video (10 panels × 8s = 80s - transitions ≈ 75s)
    const topPanels = analyzed
        .filter(p => p.score > 10)
        .sort((a, b) => b.score - a.score)
        .slice(0, 10);

    // 4. Save
    await saveSelectedPanels({ chapterId, selectedPanels: topPanels });

    return {
        text: `Successfully analyzed and selected ${topPanels.length} best panels for chapter ${chapterId}. Avg Score: ${(topPanels.reduce((a, b) => a + b.score, 0) / (topPanels.length || 1)).toFixed(1)}.`
    };
}

// Keep a dummy agent object to satisfy existing imports if any
export const panelSelector = new Agent({
    name: 'PanelSelector',
    id: 'panel-selector',
    instructions: 'Dummy agent. We use a programmed loop for reliability.',
    model: anthropic('claude-3-haiku-20240307')
});
