import React from "react";
import { Composition, getInputProps } from "remotion";
import { MangaRecap, MangaRecapProps, mangaRecapSchema } from "./MangaRecap";

// ─── Video Specs ──────────────────────────────────────────────────────────────
const FPS = 30;
const WIDTH = 1080;
const HEIGHT = 1920;

// Default duration for previews (overridden by calculateMetadata at render time)
const DEFAULT_DURATION_FRAMES = FPS * 90; // 90 seconds

export const RemotionRoot: React.FC = () => {
    return (
        <>
            <Composition
                id="MangaRecap"
                component={MangaRecap}
                durationInFrames={DEFAULT_DURATION_FRAMES}
                fps={FPS}
                width={WIDTH}
                height={HEIGHT}
                schema={mangaRecapSchema}
                defaultProps={{
                    panels: [],
                    titleText: "Manga Title",
                    chapterText: "Chapter 1",
                    audioSrc: null,
                    audioDuckingVolume: 0.4,
                }}
                calculateMetadata={({ props }) => {
                    const TRANSITION_FRAMES = 15; // 0.5s crossfade
                    const totalPanelFrames = props.panels.reduce(
                        (sum, p) => sum + p.durationInFrames,
                        0
                    );
                    // Subtract overlapping transition frames (N-1 transitions)
                    const transitionOverlap =
                        Math.max(0, props.panels.length - 1) * TRANSITION_FRAMES;
                    const totalFrames = Math.max(
                        FPS, // Minimum 1 second
                        totalPanelFrames - transitionOverlap
                    );
                    return { durationInFrames: totalFrames };
                }}
            />
        </>
    );
};
