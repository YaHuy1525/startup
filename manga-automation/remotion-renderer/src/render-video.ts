#!/usr/bin/env node
/**
 * render-video.ts — CLI entry point for the Remotion manga video renderer.
 *
 * Called by the manga-agents server or directly from the command line.
 * Reads a JSON props file and renders a MangaRecap video to disk.
 *
 * Usage:
 *   npx tsx src/render-video.ts --props ./props.json --output ./out/video.mp4
 *   npx tsx src/render-video.ts --props-json '{"panels":[...]}'
 *   npx tsx src/render-video.ts --props ./props.json --template-id 2
 *   npx tsx src/render-video.ts --props ./props.json --random-template
 *
 * Props JSON schema:
 *   {
 *     "panels": [
 *       { "imagePath": "/data/panels/...", "motionType": "zoom_center", "durationInFrames": 240 }
 *     ],
 *     "titleText": "One Piece",
 *     "chapterText": "Chapter 1100",
 *     "audioSrc": "/data/music/dramatic.mp3" | null,
 *     "audioDuckingVolume": 0.4,
 *     "templateId": 1 (optional - overrides CLI flag)
 *   }
 *
 * Output: JSON written to stdout with { filePath, durationSecs, fileSizeMb }
 */
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { Pool } from "pg";

// ─── Interfaces ──────────────────────────────────────────────────────────────
interface VideoTemplate {
    id: number;
    name: string;
    type: string;
    panelDuration: number;
    transitionType: string;
    transitionDuration: number;
    effectsConfig: {
        zoomIntensity: number;
        panDirection: string;
        colorGrading?: string;
        overlayEffects?: string[];
    };
}

// ─── Database Setup ──────────────────────────────────────────────────────────
const _rawDbUrl = process.env.DATABASE_URL || '';
const _safeDbUrl = _rawDbUrl.replace(/:([^:@/]*?)#([^@]*)@/, ':$1%23$2@');

const db = new Pool({
    connectionString: _safeDbUrl,
    max: 5,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 2000,
});

// ─── Template Functions ──────────────────────────────────────────────────────
async function loadTemplate(templateId: number): Promise<VideoTemplate | null> {
    try {
        const result = await db.query(
            `SELECT 
                id,
                name,
                type,
                panel_duration as "panelDuration",
                transition_type as "transitionType",
                transition_duration as "transitionDuration",
                effects_config as "effectsConfig"
             FROM video_templates
             WHERE id = $1`,
            [templateId]
        );

        if (result.rows.length === 0) {
            return null;
        }

        return result.rows[0];
    } catch (error: any) {
        console.error(`Failed to load template ${templateId}: ${error.message}`);
        return null;
    }
}

async function loadRandomTemplate(): Promise<VideoTemplate | null> {
    try {
        const result = await db.query(
            `SELECT 
                id,
                name,
                type,
                panel_duration as "panelDuration",
                transition_type as "transitionType",
                transition_duration as "transitionDuration",
                effects_config as "effectsConfig"
             FROM video_templates
             ORDER BY RANDOM()
             LIMIT 1`
        );

        if (result.rows.length === 0) {
            return null;
        }

        return result.rows[0];
    } catch (error: any) {
        console.error(`Failed to load random template: ${error.message}`);
        return null;
    }
}

async function updateTemplateUsageCount(templateId: number): Promise<void> {
    try {
        await db.query(
            `UPDATE video_templates 
             SET usage_count = usage_count + 1 
             WHERE id = $1`,
            [templateId]
        );
    } catch (error: any) {
        console.error(`Failed to update template usage count: ${error.message}`);
    }
}

function applyTemplateToProps(props: Record<string, unknown>, template: VideoTemplate): Record<string, unknown> {
    const fps = 30; // Standard FPS
    const panels = (props.panels as any[]) || [];
    
    // Apply template panel duration to all panels
    const updatedPanels = panels.map((panel) => ({
        ...panel,
        durationInFrames: Math.round(template.panelDuration * fps),
    }));

    // Apply template effects config to props
    return {
        ...props,
        panels: updatedPanels,
        template: {
            name: template.name,
            type: template.type,
            transitionType: template.transitionType,
            transitionDuration: template.transitionDuration,
            effectsConfig: template.effectsConfig,
        },
    };
}

// ─── Arg Parse ───────────────────────────────────────────────────────────────
const args = process.argv.slice(2);

function getArg(flag: string): string | undefined {
    const idx = args.indexOf(flag);
    return idx !== -1 ? args[idx + 1] : undefined;
}

const propsFile = getArg("--props");
const propsJson = getArg("--props-json");
const outputPath = getArg("--output") || "./out/manga_video.mp4";
const templateIdArg = getArg("--template-id");
const randomTemplate = args.includes("--random-template");

if (!propsFile && !propsJson) {
    console.error("Usage: npx tsx src/render-video.ts --props <file.json> [--output <path>]");
    console.error("   or: npx tsx src/render-video.ts --props-json '<json>' [--output <path>]");
    process.exit(1);
}

// ─── Load & Validate Props ───────────────────────────────────────────────────
let props: Record<string, unknown>;
try {
    if (propsFile) {
        const raw = fs.readFileSync(propsFile, "utf-8");
        props = JSON.parse(raw);
    } else {
        props = JSON.parse(propsJson!);
    }
} catch (err: any) {
    console.error(`Failed to parse props: ${err.message}`);
    process.exit(1);
}

// ─── Load and Apply Video Template ───────────────────────────────────────────
async function main() {
    let template: VideoTemplate | null = null;

    // Determine which template to use (priority: props.templateId > CLI --template-id > --random-template)
    const propsTemplateId = (props as any).templateId;
    
    if (propsTemplateId) {
        console.error(`[render-video] Loading template from props: ${propsTemplateId}`);
        template = await loadTemplate(propsTemplateId);
    } else if (templateIdArg) {
        const templateId = parseInt(templateIdArg, 10);
        if (isNaN(templateId)) {
            console.error(`Invalid template ID: ${templateIdArg}`);
            await db.end();
            process.exit(1);
        }
        console.error(`[render-video] Loading template: ${templateId}`);
        template = await loadTemplate(templateId);
    } else if (randomTemplate) {
        console.error(`[render-video] Loading random template`);
        template = await loadRandomTemplate();
    }

    // Apply template if loaded
    if (template) {
        console.error(`[render-video] Applying template: ${template.name} (${template.type})`);
        props = applyTemplateToProps(props, template);
        
        // Update usage count
        await updateTemplateUsageCount(template.id);
    } else if (propsTemplateId || templateIdArg || randomTemplate) {
        console.error(`[render-video] Warning: Template not found, using default settings`);
    }

    // ─── Write Temp Props File (Remotion CLI requires a file) ────────────────────
    const tempPropsPath = path.join(
        __dirname,
        `../.remotion-props-${Date.now()}.json`
    );
    fs.writeFileSync(tempPropsPath, JSON.stringify(props, null, 2));

    // ─── Ensure Output Directory Exists ──────────────────────────────────────────
    const outDir = path.dirname(path.resolve(outputPath));
    fs.mkdirSync(outDir, { recursive: true });

    // ─── Render ──────────────────────────────────────────────────────────────────
    const entryPoint = path.join(__dirname, "index.ts");
    const resolvedOutput = path.resolve(outputPath);

    const renderCmd = [
        "npx",
        "remotion",
        "render",
        entryPoint,
        "MangaRecap",
        resolvedOutput,
        `--props=${tempPropsPath}`,
        "--codec=h264",
        "--crf=22",
        "--log=error",
    ].join(" ");

    console.error(`[render-video] Rendering to ${resolvedOutput}...`);

    try {
        execSync(renderCmd, {
            cwd: path.join(__dirname, ".."),
            encoding: "utf-8",
            stdio: ["ignore", "pipe", "pipe"],
            maxBuffer: 50 * 1024 * 1024, // 50MB buffer
            timeout: 10 * 60 * 1000, // 10 minute timeout
        });
    } catch (err: any) {
        console.error(`[render-video] Render failed: ${err.stderr || err.message}`);
        // Clean up temp file
        try { fs.unlinkSync(tempPropsPath); } catch { }
        await db.end();
        process.exit(1);
    }

    // Clean up temp props file
    try { fs.unlinkSync(tempPropsPath); } catch { }

    // ─── Get File Info ───────────────────────────────────────────────────────────
    const stat = fs.statSync(resolvedOutput);
    const fileSizeMb = Math.round((stat.size / (1024 * 1024)) * 100) / 100;

    // Try ffprobe for duration, fall back to panel math
    let durationSecs = 0;
    try {
        const ffprobeOut = execSync(
            `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "${resolvedOutput}"`,
            { encoding: "utf-8", timeout: 15000 }
        );
        durationSecs = Math.round(parseFloat(ffprobeOut.trim()) * 100) / 100;
    } catch {
        // Estimate from panel data
        const panels = (props as any).panels || [];
        const totalFrames = panels.reduce(
            (s: number, p: any) => s + (p.durationInFrames || 240),
            0
        );
        const transitionOverlap = Math.max(0, panels.length - 1) * 15;
        durationSecs = Math.round(((totalFrames - transitionOverlap) / 30) * 100) / 100;
    }

    // ─── Output Result ───────────────────────────────────────────────────────────
    const result = {
        filePath: resolvedOutput,
        durationSecs,
        fileSizeMb,
        template: template ? { id: template.id, name: template.name, type: template.type } : null,
    };

    // Close database connection
    await db.end();

    // Write to stdout (this is what the calling process reads)
    console.log(JSON.stringify(result));
}

// Run main function
main().catch((err) => {
    console.error(`[render-video] Fatal error: ${err.message}`);
    db.end().finally(() => process.exit(1));
});
