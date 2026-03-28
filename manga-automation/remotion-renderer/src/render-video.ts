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
 *
 * Props JSON schema:
 *   {
 *     "panels": [
 *       { "imagePath": "/data/panels/...", "motionType": "zoom_center", "durationInFrames": 240 }
 *     ],
 *     "titleText": "One Piece",
 *     "chapterText": "Chapter 1100",
 *     "audioSrc": "/data/music/dramatic.mp3" | null,
 *     "audioDuckingVolume": 0.4
 *   }
 *
 * Output: JSON written to stdout with { filePath, durationSecs, fileSizeMb }
 */
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

// ─── Arg Parse ───────────────────────────────────────────────────────────────
const args = process.argv.slice(2);

function getArg(flag: string): string | undefined {
    const idx = args.indexOf(flag);
    return idx !== -1 ? args[idx + 1] : undefined;
}

const propsFile = getArg("--props");
const propsJson = getArg("--props-json");
const outputPath = getArg("--output") || "./out/manga_video.mp4";

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
};

// Write to stdout (this is what the calling process reads)
console.log(JSON.stringify(result));
