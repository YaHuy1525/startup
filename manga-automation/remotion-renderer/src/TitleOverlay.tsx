import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";

interface TitleOverlayProps {
    titleText: string;
    chapterText: string;
    fadeInFrames?: number;  // Default 10 (~0.33s)
    holdFrames?: number;    // Default 70 (~2.33s)
    fadeOutFrames?: number; // Default 10 (~0.33s)
}

/**
 * Displays the manga title and chapter number as a centered overlay
 * during the first ~3 seconds of the video.
 *
 * Replaces FFmpeg's drawtext filter with styled React components
 * and smooth opacity interpolation.
 */
export const TitleOverlay: React.FC<TitleOverlayProps> = ({
    titleText,
    chapterText,
    fadeInFrames = 10,
    holdFrames = 70,
    fadeOutFrames = 10,
}) => {
    const frame = useCurrentFrame();
    const totalFrames = fadeInFrames + holdFrames + fadeOutFrames;

    // Don't render after the overlay period
    if (frame > totalFrames) return null;

    // Compute opacity: fade in → hold → fade out
    const opacity = interpolate(
        frame,
        [0, fadeInFrames, fadeInFrames + holdFrames, totalFrames],
        [0, 1, 1, 0],
        { extrapolateRight: "clamp" }
    );

    return (
        <AbsoluteFill
            style={{
                justifyContent: "flex-start",
                alignItems: "center",
                paddingTop: 80,
                opacity,
                pointerEvents: "none",
            }}
        >
            {/* Manga Title */}
            <div
                style={{
                    color: "#FFFFFF",
                    fontSize: 52,
                    fontWeight: 800,
                    fontFamily:
                        "'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
                    textAlign: "center",
                    textShadow: "3px 3px 6px rgba(0,0,0,0.85)",
                    maxWidth: "90%",
                    lineHeight: 1.2,
                }}
            >
                {titleText}
            </div>

            {/* Chapter Number */}
            <div
                style={{
                    color: "#FFFFFF",
                    fontSize: 36,
                    fontWeight: 400,
                    fontFamily:
                        "'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
                    textAlign: "center",
                    textShadow: "2px 2px 4px rgba(0,0,0,0.80)",
                    marginTop: 16,
                }}
            >
                {chapterText}
            </div>
        </AbsoluteFill>
    );
};
