import React from "react";
import {
    AbsoluteFill,
    Audio,
    Img,
    staticFile,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";
import {
    TransitionSeries,
    linearTiming,
} from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { z } from "zod";
import { KenBurnsPanel } from "./KenBurnsPanel";
import { TitleOverlay } from "./TitleOverlay";

// ─── Schema ──────────────────────────────────────────────────────────────────
export const panelSchema = z.object({
    imagePath: z.string(), // Absolute path or URL to panel image
    motionType: z
        .enum(["zoom_center", "pan_right", "pan_up"])
        .default("zoom_center"),
    durationInFrames: z.number().int().min(30).default(240), // 8s at 30fps
});

export const mangaRecapSchema = z.object({
    panels: z.array(panelSchema),
    titleText: z.string(),
    chapterText: z.string(),
    audioSrc: z.string().nullable().default(null),
    audioDuckingVolume: z.number().min(0).max(1).default(0.4),
});

export type PanelProps = z.infer<typeof panelSchema>;
export type MangaRecapProps = z.infer<typeof mangaRecapSchema>;

// ─── Transition Config ───────────────────────────────────────────────────────
const TRANSITION_DURATION_FRAMES = 15; // 0.5 seconds at 30fps

// ─── Main Composition ────────────────────────────────────────────────────────
export const MangaRecap: React.FC<MangaRecapProps> = ({
    panels,
    titleText,
    chapterText,
    audioSrc,
    audioDuckingVolume,
}) => {
    const { fps, durationInFrames } = useVideoConfig();

    // Guard: nothing to render
    if (panels.length === 0) {
        return (
            <AbsoluteFill
                style={{ backgroundColor: "#000", justifyContent: "center", alignItems: "center" }}
            >
                <span style={{ color: "#555", fontSize: 36 }}>No panels provided</span>
            </AbsoluteFill>
        );
    }

    return (
        <AbsoluteFill style={{ backgroundColor: "#000" }}>
            {/* ── Panel Sequence with Crossfade Transitions ──────────────────── */}
            <TransitionSeries>
                {panels.map((panel, index) => (
                    <React.Fragment key={index}>
                        <TransitionSeries.Sequence durationInFrames={panel.durationInFrames}>
                            <KenBurnsPanel
                                imagePath={panel.imagePath}
                                motionType={panel.motionType}
                                durationInFrames={panel.durationInFrames}
                            />
                        </TransitionSeries.Sequence>
                        {/* Add fade transition between panels (not after last) */}
                        {index < panels.length - 1 && (
                            <TransitionSeries.Transition
                                presentation={fade()}
                                timing={linearTiming({
                                    durationInFrames: TRANSITION_DURATION_FRAMES,
                                })}
                            />
                        )}
                    </React.Fragment>
                ))}
            </TransitionSeries>

            {/* ── Title Overlay (first 3 seconds) ────────────────────────────── */}
            <TitleOverlay
                titleText={titleText}
                chapterText={chapterText}
                fadeInFrames={10}
                holdFrames={70}
                fadeOutFrames={10}
            />

            {/* ── Background Audio ───────────────────────────────────────────── */}
            {audioSrc && (
                <Audio
                    src={audioSrc}
                    volume={(f) => {
                        // Fade out in last 2 seconds
                        const fadeOutStart = durationInFrames - fps * 2;
                        if (f >= fadeOutStart) {
                            const progress = (f - fadeOutStart) / (fps * 2);
                            return audioDuckingVolume * (1 - progress);
                        }
                        return audioDuckingVolume;
                    }}
                />
            )}
        </AbsoluteFill>
    );
};
