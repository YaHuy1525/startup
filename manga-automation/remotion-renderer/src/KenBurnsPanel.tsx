import React from "react";
import { AbsoluteFill, Img, useCurrentFrame, interpolate } from "remotion";

type MotionType = "zoom_center" | "pan_right" | "pan_up";

interface KenBurnsPanelProps {
    imagePath: string;
    motionType: MotionType;
    durationInFrames: number;
}

/**
 * Renders a single manga panel with a cinematic Ken Burns motion effect.
 *
 * Unlike FFmpeg's zoompan filter (which suffers from sub-pixel jitter / Bug #4298),
 * CSS transforms use GPU-accelerated floating-point math, producing perfectly
 * smooth motion without the 8000px pre-scale workaround.
 *
 * Motion types:
 *   zoom_center  → Scale 1.0→1.25 toward center (character reveals, close-ups)
 *   pan_right    → Slow horizontal drift (action flow, wide scenes)
 *   pan_up       → Vertical drift upward (environmental establishing shots)
 */
export const KenBurnsPanel: React.FC<KenBurnsPanelProps> = ({
    imagePath,
    motionType,
    durationInFrames,
}) => {
    const frame = useCurrentFrame();

    // Normalised progress 0→1 over the panel's duration
    const progress = interpolate(frame, [0, durationInFrames], [0, 1], {
        extrapolateRight: "clamp",
    });

    // ── Compute transform based on motion type ─────────────────────────────
    let transform = "";

    switch (motionType) {
        case "zoom_center": {
            // Slow zoom from 1.0× to 1.25× toward the center
            const scale = interpolate(progress, [0, 1], [1, 1.25]);
            transform = `scale(${scale})`;
            break;
        }

        case "pan_right": {
            // Start zoomed to 1.2×, pan from left to right
            // Translate X from 0% to -10% of the container (reveals right side)
            const translateX = interpolate(progress, [0, 1], [0, -10]);
            transform = `scale(1.2) translateX(${translateX}%)`;
            break;
        }

        case "pan_up": {
            // Start zoomed to 1.2×, pan from bottom to top
            const translateY = interpolate(progress, [0, 1], [5, -5]);
            transform = `scale(1.2) translateY(${translateY}%)`;
            break;
        }

        default:
            transform = "scale(1)";
    }

    return (
        <AbsoluteFill
            style={{
                overflow: "hidden",
                backgroundColor: "#000",
            }}
        >
            <Img
                src={imagePath}
                style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    transform,
                    transformOrigin: "center center",
                    willChange: "transform",
                }}
            />
        </AbsoluteFill>
    );
};
