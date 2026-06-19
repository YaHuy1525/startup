import React from "react";
import {
    AbsoluteFill,
    Audio,
    Img,
    Sequence,
    useCurrentFrame,
    useVideoConfig,
    interpolate,
    spring,
} from "remotion";
import { z } from "zod";

export const characterEditPanelSchema = z.object({
    imagePath: z.string(),
    caption: z.string().optional(),
});

export const characterEditSchema = z.object({
    panels: z.array(characterEditPanelSchema).min(1).max(20),
    audioSrc: z.string().nullable().default(null),
    titleText: z.string(),
    characterName: z.string(),
    panelDurationFrames: z.number().int().min(30).default(60),
});

export type CharacterEditProps = z.infer<typeof characterEditSchema>;

const CharacterPanel: React.FC<{
    imagePath: string;
    caption?: string;
    panelDurationFrames: number;
}> = ({ imagePath, caption, panelDurationFrames }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();

    const entrance = spring({
        frame,
        fps,
        config: { damping: 12, stiffness: 100 },
        durationInFrames: 15,
    });

    const scale = interpolate(entrance, [0, 1], [1.3, 1]);
    const opacity = interpolate(frame, [panelDurationFrames - 8, panelDurationFrames], [1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
    });

    return (
        <AbsoluteFill style={{ backgroundColor: "#000", opacity }}>
            <Img
                src={imagePath}
                style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    transform: `scale(${scale})`,
                    filter: "brightness(0.9) contrast(1.1)",
                }}
            />
            {caption && (
                <div
                    style={{
                        position: "absolute",
                        bottom: 120,
                        left: 40,
                        right: 40,
                        color: "#fff",
                        fontSize: 28,
                        fontWeight: 600,
                        textShadow: "3px 3px 6px rgba(0,0,0,0.9)",
                        textAlign: "center",
                        opacity: entrance,
                    }}
                >
                    {caption}
                </div>
            )}
        </AbsoluteFill>
    );
};

export const CharacterEdit: React.FC<CharacterEditProps> = ({
    panels,
    audioSrc,
    titleText,
    characterName,
    panelDurationFrames,
}) => {
    const { fps, durationInFrames } = useVideoConfig();
    const currentFrame = useCurrentFrame();
    const totalEditFrames = Math.max(1, panelDurationFrames * panels.length);
    const fadeInEnd = Math.min(15, Math.max(1, totalEditFrames - 1));
    const fadeOutStart = Math.max(fadeInEnd + 1, totalEditFrames - 15);
    const titleOpacity = interpolate(
        currentFrame,
        [0, fadeInEnd, fadeOutStart, totalEditFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
    );

    return (
        <AbsoluteFill style={{ backgroundColor: "#000" }}>
            {panels.map((panel, i) => (
                <Sequence key={i} from={i * panelDurationFrames} durationInFrames={panelDurationFrames}>
                    <CharacterPanel
                        imagePath={panel.imagePath}
                        caption={panel.caption}
                        panelDurationFrames={panelDurationFrames}
                    />
                </Sequence>
            ))}

            <div
                style={{
                    position: "absolute",
                    top: 60,
                    left: 40,
                    opacity: titleOpacity,
                    backgroundColor: "rgba(230,36,94,0.85)",
                    padding: "12px 24px",
                    borderRadius: 8,
                }}
            >
                <span style={{ color: "#fff", fontSize: 24, fontWeight: 700 }}>{titleText}</span>
                {characterName && (
                    <span style={{ color: "rgba(255,255,255,0.8)", fontSize: 18, marginLeft: 12 }}>
                        — {characterName}
                    </span>
                )}
            </div>

            {audioSrc && (
                <Audio
                    src={audioSrc}
                    volume={(f) => {
                        const fadeStart = durationInFrames - fps * 2;
                        if (f >= fadeStart) return 0.4 * (1 - (f - fadeStart) / (fps * 2));
                        return 0.4;
                    }}
                />
            )}
        </AbsoluteFill>
    );
};
