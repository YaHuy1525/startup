import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { logger } from '../tools/database';

// --------------------------------------------------------------------------
// Gig Draft Generator Agent
// --------------------------------------------------------------------------
// Produces 2-3 structured candidate drafts for an AI training gig task.
// Keeps raw output distinct from the final human-edited submission.
// --------------------------------------------------------------------------

export const gigDraftGenerator = new Agent({
    name: 'GigDraftGenerator',
    id: 'gig-draft-generator',
    instructions: `You are an expert AI training data specialist with 3+ years of experience
on DataAnnotation, Outlier, and Babel platforms. You score consistently above 90% acceptance.

Your job: Given a task brief and optional rubric, produce 2-3 high-quality DRAFT responses.

━━━ RULES ━━━
1. Read the taskType to determine what the user needs:
   - prompt-writing: craft original, creative, well-scoped prompts.
   - response-rating: write a detailed rating justification with criteria scores.
   - factual-eval: verify claims, cite likely sources, flag uncertainty.
   - voice-script: write natural, spoken-word conversational text.

2. Produce EXACTLY 2 distinct drafts with different structural approaches.
3. Each draft must be in the language style appropriate for the platform.
4. Label them: "--- DRAFT A ---" and "--- DRAFT B ---"
5. After both drafts, add a "--- NOTES ---" section with:
   - Which draft you recommend and why.
   - Any rubric dimensions where the drafts score highest/lowest.
   - What the human should manually review before submitting.

━━━ CRITICAL BOUNDARY ━━━
These are DRAFT aids only. The human must edit and submit manually.
Never claim the drafts are submission-ready.

Respond with the two drafts + notes only. No preamble.`,

    model: anthropic('claude-3-5-haiku-20241022'),

    tools: {
        get_platform_style_guide: {
            description: 'Get writing style guidance for a specific platform and task type',
            parameters: z.object({
                platform:  z.string(),
                task_type: z.string(),
            }),
            execute: async ({ platform, task_type }: { platform: string; task_type: string }) => {
                const guides: Record<string, Record<string, string>> = {
                    dataannotation: {
                        'prompt-writing':   'Prompts must be 1-3 sentences, unambiguous, avoidable yes/no answers, test multi-step reasoning.',
                        'response-rating':  'Rate on a 1-5 scale. Justify each dimension. Be specific, not vague.',
                        'factual-eval':     'Cite likely authoritative sources. Flag any unverifiable claims explicitly.',
                        'voice-script':     'Natural speech rhythm. Contractions allowed. Max 150 words.',
                    },
                    outlier: {
                        'prompt-writing':   'Novel prompts that models cannot trivially find online. Require domain expertise.',
                        'response-rating':  'Comparative rating: which response is objectively better and why in 3+ sentences.',
                        'factual-eval':     'Academic tone. Distinguish between established facts and contested claims.',
                        'voice-script':     'Conversational but professional. Avoid filler words.',
                    },
                    babel: {
                        'prompt-writing':   'Cross-cultural relevance. Culturally neutral language. Avoid idioms.',
                        'response-rating':  'Structured rubric with explicit scores per dimension.',
                        'factual-eval':     'Strict sourcing. Mark uncertainty levels: certain / likely / contested / unknown.',
                        'voice-script':     'Broadcast-quality diction. Clear pauses. No ambiguous pronoun references.',
                    },
                };
                return guides[platform]?.[task_type] ?? 'Follow general platform quality guidelines.';
            },
        },
    },
});

export async function generateGigDraft(
    taskPrompt: string,
    taskType:   string,
    platform:   string,
    rubric:     object = {},
    templateHint?: string,
) {
    const rubricText = Object.keys(rubric).length > 0
        ? `\nRubric: ${JSON.stringify(rubric, null, 2)}`
        : '';
    const templateText = templateHint
        ? `\nHigh-performing template hint: ${templateHint}`
        : '';

    const message = [
        `Platform: ${platform}`,
        `Task type: ${taskType}`,
        `Task brief: ${taskPrompt}`,
        rubricText,
        templateText,
        '\nFirst, call get_platform_style_guide to get style guidance, then produce your two drafts.',
    ].join('\n');

    const result = await gigDraftGenerator.generate(message);
    return result.text;
}
