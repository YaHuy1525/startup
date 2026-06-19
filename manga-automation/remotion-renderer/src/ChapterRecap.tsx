import React from "react";
import {
    AbsoluteFill,
    Audio,
    Img,
    useCurrentFrame,
    useVideoConfig,
    interpolate,
} from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { z } from "zod";

export const chapterRecapPanelSchema = z.object({
    imagePath: z.string(),
    dialogueText: z.string().optional(),
    durationInFrames: z.number().int().min(60).default(180),
    motionType: z.enum(["zoom_center", "pan_right", "pan_up"]).default("zoom_center"),
});

export const chapterRecapSchema = z.object({
    panels: z.array(chapterRecapPanelSchema).min(1),
    titleText: z.string(),
    chapterText: z.string(),
    audioSrc: z.string().nullable().default(null),
    voiceoverSrc: z.string().nullable().default(null),
    introDurationFrames: z.number().int().default(60),
    outroDurationFrames: z.number().int().default(60),
});

export type ChapterRecapProps = z.infer<typeof chapterRecapSchema>;

const PanelScene: React.FC<{
    imagePath: string;
    dialogueText?: string;
    durationInFrames: number;
    motionType: "zoom_center" | "pan_right" | "pan_up";
}> = ({ imagePath, dialogueText, durationInFrames, motionType }) => {
    const frame = useCurrentFrame();

    const scale =
        motionType === "zoom_center"
            ? interpolate(frame, [0, durationInFrames], [1, 1.2], { extrapolateRight: "clamp" })
            : 1.1;

    const dialogueOpacity = dialogueText
        ? interpolate(
              frame,
              [10, 25, durationInFrames - 10, durationInFrames],
              [0, 1, 1, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
          )
        : 0;

    return (
        <AbsoluteFill style={{ backgroundColor: "#000", overflow: "hidden" }}>
            <Img
                src={imagePath}
                style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    transform: `scale(${scale})`,
                }}
            />
            {dialogueText && (
                <div
                    style={{
                        position: "absolute",
                        bottom: 160,
                        left: 40,
                        right: 40,
                        color: "#fff",
                        fontSize: 32,
                        fontWeight: 600,
                        textShadow: "2px 2px 6px rgba(0,0,0,0.9)",
                        textAlign: "center",
                        backgroundColor: "rgba(0,0,0,0.6)",
                        padding: "12px 20px",
                        borderRadius: 8,
                        opacity: dialogueOpacity,
                    }}
                >
                    {dialogueText}
                </div>
            )}
        </AbsoluteFill>
    );
};

const ProgressBar: React.FC<{ progress: number }> = ({ progress }) => (
    <div
        style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: 4,
            backgroundColor: "rgba(255,255,255,0.2)",
        }}
    >
        <div
            style={{
                height: "100%",
                width: `${progress * 100}%`,
                backgroundColor: "#e6245e",
            }}
        />
    </div>
);

export const ChapterRecap: React.FC<ChapterRecapProps> = ({
    panels,
    titleText,
    chapterText,
    audioSrc,
    voiceoverSrc,
    introDurationFrames,
    outroDurationFrames,
}) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();

    const bodyFrames =
        panels.reduce((s, p) => s + p.durationInFrames, 0) -
        Math.max(0, panels.length - 1) * 15;
    const totalFrames = introDurationFrames + bodyFrames + outroDurationFrames;

    const progress = interpolate(frame, [0, totalFrames], [0, 1], {
        extrapolateRight: "clamp",
    });

    const isIntro = frame < introDurationFrames;
    const introOpacity = interpolate(
        frame,
        [introDurationFrames - 10, introDurationFrames],
        [1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
    );

    return (
        <AbsoluteFill style={{ backgroundColor: "#0a0a0a" }}>
            <TransitionSeries>
                {panels.map((panel, i) => (
                    <React.Fragment key={i}>
                        <TransitionSeries.Sequence durationInFrames={panel.durationInFrames}>
                            <PanelScene
                                imagePath={panel.imagePath}
                                dialogueText={panel.dialogueText}
                                durationInFrames={panel.durationInFrames}
                                motionType={panel.motionType}
                            />
                        </TransitionSeries.Sequence>
                        {i < panels.length - 1 && (
                            <TransitionSeries.Transition
                                presentation={fade()}
                                timing={linearTiming({ durationInFrames: 15 })}
                            />
                        )}
                    </React.Fragment>
                ))}
            </TransitionSeries>

            {isIntro && (
                <AbsoluteFill
                    style={{
                        justifyContent: "center",
                        alignItems: "center",
                        opacity: introOpacity,
                        backgroundColor: "rgba(10,10,10,0.95)",
                    }}
                >
                    <span
                        style={{
                            color: "#e6245e",
                            fontSize: 56,
                            fontWeight: 800,
                            textAlign: "center",
                            padding: "0 60px",
                        }}
                    >
                        {titleText}
                    </span>
                    <span style={{ color: "#fff", fontSize: 36, fontWeight: 400, marginTop: 16 }}>
                        {chapterText}
                    </span>
                </AbsoluteFill>
            )}

            <ProgressBar progress={progress} />

            {audioSrc && (
                <Audio
                    src={audioSrc}
                    volume={(f) => {
                        const fadeStart = totalFrames - fps * 2;
                        if (f >= fadeStart) return 0.35 * (1 - (f - fadeStart) / (fps * 2));
                        return 0.35;
                    }}
                />
            )}
            {voiceoverSrc && <Audio src={voiceoverSrc} volume={0.8} />}
        </AbsoluteFill>
    );
};
