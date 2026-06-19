import React from "react";
import {
    AbsoluteFill,
    Audio,
    Img,
    Video,
    useCurrentFrame,
    useVideoConfig,
    interpolate,
    Sequence,
} from "remotion";
import { z } from "zod";

export const brainrotFeedSchema = z.object({
    panelImagePath: z.string(),
    subtitleText: z.string(),
    gameplayVideoPath: z.string(),
    audioSrc: z.string().nullable().default(null),
    voiceoverSrc: z.string().nullable().default(null),
    panelDurationInFrames: z.number().int().min(60).default(240),
});

export type BrainrotFeedProps = z.infer<typeof brainrotFeedSchema>;

export const BrainrotFeed: React.FC<BrainrotFeedProps> = ({
    panelImagePath,
    subtitleText,
    gameplayVideoPath,
    audioSrc,
    voiceoverSrc,
    panelDurationInFrames,
}) => {
    const frame = useCurrentFrame();
    const { fps, durationInFrames } = useVideoConfig();

    const panelScale = interpolate(frame, [0, panelDurationInFrames], [1, 1.15], {
        extrapolateRight: "clamp",
    });

    const subtitleOpacity = interpolate(
        frame,
        [0, 15, panelDurationInFrames - 15, panelDurationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
    );

    return (
        <AbsoluteFill style={{ backgroundColor: "#000" }}>
            <div
                style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: 1080,
                    height: 1152,
                    overflow: "hidden",
                }}
            >
                <Img
                    src={panelImagePath}
                    style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                        transform: `scale(${panelScale})`,
                        transformOrigin: "center center",
                    }}
                />
            </div>

            <div
                style={{
                    position: "absolute",
                    top: 1152,
                    left: 0,
                    width: 1080,
                    height: 768,
                    overflow: "hidden",
                }}
            >
                {gameplayVideoPath ? (
                    <Video
                        src={gameplayVideoPath}
                        loop
                        muted
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                ) : null}
            </div>

            <div
                style={{
                    position: "absolute",
                    bottom: 800,
                    left: 40,
                    right: 40,
                    opacity: subtitleOpacity,
                    color: "#fff",
                    fontSize: 36,
                    fontWeight: 700,
                    textAlign: "center",
                    textShadow: "2px 2px 4px rgba(0,0,0,0.9)",
                    backgroundColor: "rgba(0,0,0,0.5)",
                    padding: "16px 24px",
                    borderRadius: 12,
                }}
            >
                {subtitleText}
            </div>

            {audioSrc && (
                <Audio
                    src={audioSrc}
                    volume={(f) => {
                        const fadeStart = durationInFrames - fps * 2;
                        if (f >= fadeStart) {
                            return 0.3 * (1 - (f - fadeStart) / (fps * 2));
                        }
                        return 0.3;
                    }}
                />
            )}

            {voiceoverSrc && (
                <Sequence from={0}>
                    <Audio src={voiceoverSrc} volume={0.8} />
                </Sequence>
            )}
        </AbsoluteFill>
    );
};
