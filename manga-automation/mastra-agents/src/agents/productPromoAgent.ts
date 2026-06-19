import { Agent } from '@mastra/core/agent';
import { createAnthropic } from '@ai-sdk/anthropic';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { z } from 'zod';

// --------------------------------------------------------------------------
// Product Promo Agent — Remotion specialist for brand/product promotion videos
// --------------------------------------------------------------------------

export const productPromoPropsSchema = z.object({
    productName: z.string(),
    tagline: z.string(),
    brandColor: z.string().regex(/^#[0-9a-fA-F]{6}$/),
    accentColor: z.string().regex(/^#[0-9a-fA-F]{6}$/),
    features: z.array(z.object({
        headline: z.string().max(80),
        subtext: z.string().max(160),
    })).min(1).max(5),
    ctaText: z.string().max(120),
    audioSrc: z.string().nullable().optional(),
});

export type ProductPromoProps = z.infer<typeof productPromoPropsSchema>;

const LIBRARY_CONTEXT = `
You are a Remotion product-promo video specialist. You design 60s+ vertical (1080x1920) promo videos.

INSTALLED LIBRARIES (use in your creative direction — the renderer maps to these automatically):
- remotion-bits: AnimatedText (word/char stagger, fade, slide, glitch)
- remocn (copy-paste): blur-reveal, typewriter, directional-wipe — in src/components/remocn/
- @remotion/light-leaks: WebGL light leak transitions between scenes
- @remotion/transitions: TransitionSeries + fade for panel sequences
- Tailwind: static layout only — NEVER use animate-* classes

COMPOSITION: ProductPromo
- Intro (5s): product name + tagline with kinetic text
- Features (12s each): headline + subtext per benefit
- CTA (8s): call-to-action with character reveal
- Minimum total duration: 60 seconds (TikTok Creator Rewards)

RULES:
1. brandColor = primary brand hex (e.g. NVIDIA #76b900, Apple #0071e3)
2. accentColor = dark background hex (usually #0a0a0a or #111111)
3. Write punchy, ad-style copy — not paragraphs
4. 3 features is ideal for 60s+ runtime
5. ctaText should include a clear action (visit, buy, try, download)
`;

export const productPromoAgent = new Agent({
    name: 'ProductPromoDirector',
    id: 'product-promo-director',
    instructions: `${LIBRARY_CONTEXT}

Given a user prompt describing a product or brand, output ONLY valid JSON matching this schema:
{
  "productName": "string",
  "tagline": "string",
  "brandColor": "#hex",
  "accentColor": "#hex",
  "features": [{ "headline": "string", "subtext": "string" }],
  "ctaText": "string",
  "audioSrc": null
}

Do not wrap in markdown. Do not add commentary.`,
    model: (() => {
        const baseURL =
            process.env.ANTHROPIC_BASE_URL?.trim() || 'https://api.anthropic.com/v1';
        const client = createAnthropic({
            apiKey: process.env.ANTHROPIC_API_KEY,
            baseURL,
        });
        const modelId =
            process.env.PRODUCT_PROMO_MODEL?.trim() || 'claude-sonnet-4-20250514';
        return client(modelId);
    })(),
});

export interface ProductPromoResult {
    props: ProductPromoProps;
    filePath?: string;
    durationSecs?: number;
    fileSizeMb?: number;
    composition: string;
}

export function loadFallbackPromoProps(prompt: string, remotionDir?: string): ProductPromoProps | null {
    const lower = prompt.toLowerCase();
    const candidates: string[] = [];

    if (/nvidia|rtx/.test(lower)) {
        candidates.push('promo-nvidia-props.json');
    }

    const searchRoots = [
        remotionDir,
        path.join(__dirname, '../remotion-renderer'),
        path.join(__dirname, '../../remotion-renderer'),
    ].filter(Boolean) as string[];

    for (const root of searchRoots) {
        for (const file of candidates) {
            const fullPath = path.join(root, file);
            if (fs.existsSync(fullPath)) {
                const parsed = JSON.parse(fs.readFileSync(fullPath, 'utf-8'));
                return productPromoPropsSchema.parse({
                    ...parsed,
                    audioSrc: parsed.audioSrc ?? null,
                });
            }
        }
    }

    return null;
}

export async function generateProductPromoProps(
    prompt: string,
    options?: { remotionDir?: string },
): Promise<ProductPromoProps> {
    try {
        const result = await productPromoAgent.generate(
            `Create a product promotion video plan for:\n\n${prompt}\n\nReturn JSON only.`,
        );

        const text = result.text.trim();
        const jsonMatch = text.match(/\{[\s\S]*\}/);
        if (!jsonMatch) {
            throw new Error('Agent did not return valid JSON');
        }

        const parsed = JSON.parse(jsonMatch[0]);
        return productPromoPropsSchema.parse({
            ...parsed,
            audioSrc: parsed.audioSrc ?? null,
        });
    } catch (err) {
        const fallback = loadFallbackPromoProps(prompt, options?.remotionDir);
        if (fallback) {
            return fallback;
        }
        throw err;
    }
}

export function renderProductPromo(
    props: ProductPromoProps,
    options: {
        remotionDir: string;
        outputDir: string;
        filename?: string;
    },
): { filePath: string; durationSecs: number; fileSizeMb: number } {
    const { remotionDir, outputDir } = options;
    const safeName = (props.productName || 'promo').replace(/[^a-zA-Z0-9]/g, '_').slice(0, 40);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const filename = options.filename || `${safeName}_promo_${timestamp}.mp4`;
    const outputPath = path.join(outputDir, filename);

    fs.mkdirSync(outputDir, { recursive: true });

    const propsPath = path.join(remotionDir, `.promo-props-${Date.now()}.json`);
    fs.writeFileSync(propsPath, JSON.stringify(props, null, 2));

    const renderCmd = [
        'npx tsx src/render-video.ts',
        `--props "${propsPath}"`,
        '--composition ProductPromo',
        `--output "${outputPath}"`,
    ].join(' ');

    try {
        const renderOutput = execSync(renderCmd, {
            cwd: remotionDir,
            encoding: 'utf-8',
            timeout: 10 * 60 * 1000,
            maxBuffer: 50 * 1024 * 1024,
            env: { ...process.env, DATABASE_URL: process.env.DATABASE_URL || '' },
        });

        const lastLine = renderOutput.trim().split('\n').pop() || '{}';
        const renderResult = JSON.parse(lastLine);

        return {
            filePath: renderResult.filePath || outputPath,
            durationSecs: renderResult.durationSecs,
            fileSizeMb: renderResult.fileSizeMb,
        };
    } finally {
        try { fs.unlinkSync(propsPath); } catch { /* ignore */ }
    }
}

export async function createProductPromo(
    prompt: string,
    options: {
        remotionDir: string;
        outputDir: string;
        render?: boolean;
        filename?: string;
        props?: ProductPromoProps;
    },
): Promise<ProductPromoResult> {
    const props = options.props ?? await generateProductPromoProps(prompt, {
        remotionDir: options.remotionDir,
    });

    const result: ProductPromoResult = {
        props,
        composition: 'ProductPromo',
    };

    if (options.render !== false) {
        const rendered = renderProductPromo(props, options);
        result.filePath = rendered.filePath;
        result.durationSecs = rendered.durationSecs;
        result.fileSizeMb = rendered.fileSizeMb;
    }

    return result;
}
