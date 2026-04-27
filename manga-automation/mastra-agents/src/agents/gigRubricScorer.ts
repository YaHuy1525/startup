import { Agent } from '@mastra/core/agent';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { logger } from '../tools/database';

// --------------------------------------------------------------------------
// Gig Rubric Scorer Agent  (combines rubricScoringAgent + qualityGuardAgent)
// --------------------------------------------------------------------------
// Scores a draft against rubric dimensions and flags quality / risk issues.
// Returns a numeric score (0–1) and a list of risk flag strings.
// --------------------------------------------------------------------------

export const gigRubricScorer = new Agent({
    name: 'GigRubricScorer',
    id: 'gig-rubric-scorer',
    instructions: `You are a strict quality evaluator for AI training gig platforms.

Your task: Given a task prompt, a draft response, and an optional rubric, output a JSON object with:
- "score": a float from 0.0 to 1.0 (weighted average of rubric dimensions, or your best estimate if no rubric)
- "risk_flags": an array of strings describing specific issues (empty array if none)
- "dimension_scores": an object with per-dimension scores if a rubric was provided

━━━ SCORING GUIDELINES ━━━
- 0.9–1.0  Excellent: clear, complete, well-reasoned, no issues.
- 0.75–0.89 Good: minor improvements possible but submission-ready.
- 0.60–0.74 Acceptable: needs targeted revision before submitting.
- Below 0.60 Poor: significant rework needed.

━━━ RISK FLAGS TO DETECT ━━━
- "hallucination_risk" — contains specific claims that may be fabricated
- "unsupported_factual_claim" — factual assertion without verifiable basis
- "shallow_reasoning" — surface-level answer without depth
- "instruction_mismatch" — draft does not match the task type or brief
- "ambiguous_language" — unclear phrasing that could be misinterpreted
- "policy_risk" — content that might violate platform guidelines
- "too_short" — draft is significantly below expected length
- "too_long" — draft exceeds reasonable platform expectations

━━━ OUTPUT FORMAT ━━━
Respond ONLY with a valid JSON object. No markdown, no preamble.
Example:
{
  "score": 0.82,
  "risk_flags": ["shallow_reasoning"],
  "dimension_scores": {
    "clarity": 0.90,
    "creativity": 0.75,
    "difficulty": 0.80,
    "safety": 1.00,
    "coverage": 0.65
  }
}`,

    model: anthropic('claude-3-5-haiku-20241022'),

    tools: {
        check_factual_risk: {
            description: 'Check if a text contains specific factual claims that might be unverifiable',
            parameters: z.object({ text: z.string() }),
            execute: async ({ text }: { text: string }) => {
                // Heuristic signals for hallucination/unsupported claims
                const riskPatterns = [
                    /\b(studies show|research proves|scientists found|experts say)\b/gi,
                    /\b(\d{4})\s*(study|research|paper|survey)\b/gi,
                    /\b(always|never|every|all|none|100%|0%)\b/gi,
                    /\b(the only|the best|the fastest|the most)\b/gi,
                ];
                const flags: string[] = [];
                for (const pattern of riskPatterns) {
                    const matches = text.match(pattern);
                    if (matches && matches.length > 0) {
                        flags.push(`Found potentially unsupported claim: "${matches[0]}"`);
                    }
                }
                return { risk_signals: flags, count: flags.length };
            },
        },
    },
});

export interface ScoringResult {
    score:            number;
    risk_flags:       string[];
    dimension_scores: Record<string, number>;
}

export async function scoreGigDraft(
    taskPrompt:  string,
    draftOutput: string,
    platform:    string,
    taskType:    string,
    rubric:      object = {},
): Promise<ScoringResult> {
    const rubricText = Object.keys(rubric).length > 0
        ? `\nRubric dimensions: ${JSON.stringify(rubric, null, 2)}`
        : '\n(No rubric provided — use your best judgment for this platform/task type.)';

    const message = [
        `Platform: ${platform}`,
        `Task type: ${taskType}`,
        `Task prompt: ${taskPrompt}`,
        rubricText,
        `\nDraft to evaluate:\n${draftOutput}`,
        '\nFirst call check_factual_risk on the draft, then output your JSON scoring result.',
    ].join('\n');

    const result = await gigRubricScorer.generate(message);

    try {
        // Strip any markdown fences if present
        const cleaned = result.text.replace(/```json?\n?/g, '').replace(/```\n?/g, '').trim();
        const parsed: ScoringResult = JSON.parse(cleaned);
        logger.info('GigRubricScorer result', {
            platform, taskType,
            score: parsed.score,
            flags: parsed.risk_flags?.length ?? 0,
        });
        return parsed;
    } catch (err: any) {
        logger.error('GigRubricScorer failed to parse JSON', { error: err.message, raw: result.text });
        return { score: 0.0, risk_flags: ['scoring_parse_error'], dimension_scores: {} };
    }
}
