import React from "react";
import {
    AbsoluteFill,
    Audio,
    Img,
    OffthreadVideo,
    interpolate,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { z } from "zod";

/** Rico / Beckett AI tutorial look: white bg, black stick figures, slow cinematic zoom. */
export const STICK_CROSSFADE_FRAMES = 12;

export const stickFigureMotionSchema = z.object({
    preset: z
        .enum([
            "zoom_in",
            "zoom_out",
            "bounce",
            "slide_left",
            "slide_right",
            "idle_sway",
            "pop_in",
            "pan_up",
        ])
        .default("zoom_in"),
    intensity: z.number().min(0).max(1.5).default(0.7),
});

export const stickFigureSceneSchema = z.object({
    imagePath: z.string(),
    /** Optional Kie image-to-video clip (mp4 data URI or URL). Plays instead of Ken Burns image. */
    videoSrc: z.string().nullable().optional(),
    caption: z.string().optional(),
    durationInFrames: z.number().int().min(15),
    elementDelayFrames: z.number().int().min(0).default(0),
    motion: stickFigureMotionSchema.optional(),
});

export const stickFigureStorySchema = z.object({
    scenes: z.array(stickFigureSceneSchema).min(1).max(40),
    voiceoverSrc: z.string().nullable().default(null),
    titleText: z.string().optional(),
    /** Kept for backwards compat; Rico style uses pure white (ignored when style=rico). */
    paperBackgroundOpacity: z.number().min(0).max(1).default(0),
    aspectLabel: z.enum(["9:16", "16:9"]).default("9:16"),
    /** rico = viral stickman (white bg, cinematic zoom, captions off by default). */
    style: z.enum(["rico", "paper"]).default("rico"),
    showCaptions: z.boolean().default(false),
    crossfadeFrames: z.number().int().min(0).max(45).default(STICK_CROSSFADE_FRAMES),
});

export type StickFigureStoryProps = z.infer<typeof stickFigureStorySchema>;
export type StickFigureMotion = z.infer<typeof stickFigureMotionSchema>;

function useCinematicTransform(
    frame: number,
    durationInFrames: number,
    motion: StickFigureMotion | undefined,
): { transform: string; opacity: number } {
    const preset = motion?.preset ?? "zoom_in";
    const intensity = motion?.intensity ?? 0.7;
    const progress = durationInFrames <= 0 ? 0 : frame / durationInFrames;
    const local = frame;

    // Soft fade in/out at scene edges (crossfade handles most of the blend)
    const opacity = interpolate(
        frame,
        [0, 8, Math.max(9, durationInFrames - 8), durationInFrames],
        [0.92, 1, 1, 0.92],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
    );

    let scale = 1;
    let translateX = 0;
    let translateY = 0;
    let rotate = 0;

    switch (preset) {
        case "zoom_out":
            scale = interpolate(progress, [0, 1], [1 + 0.12 * intensity, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            break;
        case "bounce":
            translateY = Math.sin(local / 8) * 10 * intensity;
            scale = 1 + Math.abs(Math.sin(local / 8)) * 0.02 * intensity;
            break;
        case "slide_left":
            translateX = interpolate(progress, [0, 0.25, 1], [80 * intensity, 0, -20 * intensity], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            scale = interpolate(progress, [0, 1], [1, 1 + 0.06 * intensity], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            break;
        case "slide_right":
            translateX = interpolate(progress, [0, 0.25, 1], [-80 * intensity, 0, 20 * intensity], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            scale = interpolate(progress, [0, 1], [1, 1 + 0.06 * intensity], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            break;
        case "pan_up":
            translateY = interpolate(progress, [0, 1], [28 * intensity, -28 * intensity], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            scale = interpolate(progress, [0, 1], [1.04, 1.1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            break;
        case "pop_in":
            scale = interpolate(progress, [0, 0.15, 1], [0.92, 1.02, 1 + 0.08 * intensity], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            break;
        case "idle_sway":
            translateX = Math.sin(local / 28) * 6 * intensity;
            rotate = Math.sin(local / 32) * 1.2 * intensity;
            scale = 1 + Math.sin(local / 40) * 0.015 * intensity;
            break;
        case "zoom_in":
        default:
            // Omni Flash-like slow push-in (default Rico look)
            scale = interpolate(progress, [0, 1], [1, 1 + 0.14 * intensity], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            translateY = interpolate(progress, [0, 1], [8 * intensity, -8 * intensity], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
            });
            break;
    }

    return {
        opacity,
        transform: `translate(${translateX}px, ${translateY}px) scale(${scale}) rotate(${rotate}deg)`,
    };
}

const StickScene: React.FC<{
    imagePath: string;
    videoSrc?: string | null;
    caption?: string;
    durationInFrames: number;
    motion?: StickFigureMotion;
    showCaptions: boolean;
    styleMode: "rico" | "paper";
}> = ({ imagePath, videoSrc, caption, durationInFrames, motion, showCaptions, styleMode }) => {
    const frame = useCurrentFrame();
    const { transform, opacity } = useCinematicTransform(frame, durationInFrames, motion);

    const captionOpacity = interpolate(frame, [10, 22], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
    });

    const isRico = styleMode === "rico";
    const hasClip = Boolean(videoSrc);

    return (
        <AbsoluteFill
            style={{
                backgroundColor: isRico ? "#ffffff" : "#efe9dc",
                opacity,
            }}
        >
            {!isRico ? (
                <AbsoluteFill
                    style={{
                        backgroundImage: `
                            linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px),
                            linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px)
                        `,
                        backgroundSize: "24px 24px",
                        opacity: 0.35,
                    }}
                />
            ) : null}

            <AbsoluteFill
                style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: hasClip ? 0 : isRico ? "48px 32px 120px" : "80px 48px 160px",
                }}
            >
                {hasClip ? (
                    <OffthreadVideo
                        src={videoSrc as string}
                        muted
                        style={{
                            width: "100%",
                            height: "100%",
                            objectFit: "cover",
                        }}
                    />
                ) : (
                    <Img
                        src={imagePath}
                        style={{
                            width: isRico ? "92%" : "85%",
                            height: isRico ? "72%" : "55%",
                            maxWidth: "100%",
                            maxHeight: isRico ? "78%" : "55%",
                            objectFit: "contain",
                            transform,
                            transformOrigin: "center center",
                        }}
                    />
                )}
            </AbsoluteFill>

            {showCaptions && caption ? (
                <AbsoluteFill
                    style={{
                        justifyContent: "flex-end",
                        alignItems: "center",
                        paddingBottom: 96,
                        paddingLeft: 48,
                        paddingRight: 48,
                    }}
                >
                    <div
                        style={{
                            color: "#111",
                            fontSize: isRico ? 42 : 36,
                            fontWeight: 700,
                            fontFamily: isRico
                                ? "system-ui, -apple-system, Segoe UI, sans-serif"
                                : "Georgia, 'Times New Roman', serif",
                            textAlign: "center",
                            lineHeight: 1.25,
                            opacity: captionOpacity,
                            maxWidth: 920,
                            textShadow: isRico ? "0 1px 0 rgba(255,255,255,0.8)" : undefined,
                        }}
                    >
                        {caption}
                    </div>
                </AbsoluteFill>
            ) : null}
        </AbsoluteFill>
    );
};

export const calcStickFigureStoryDuration = (
    scenes: StickFigureStoryProps["scenes"],
    crossfadeFrames: number = STICK_CROSSFADE_FRAMES,
): number => {
    if (!scenes.length) return 0;
    const sum = scenes.reduce((s, sc) => s + sc.durationInFrames, 0);
    const overlaps = Math.max(0, scenes.length - 1) * Math.max(0, crossfadeFrames);
    return Math.max(15, sum - overlaps);
};

export const StickFigureStory: React.FC<StickFigureStoryProps> = ({
    scenes,
    voiceoverSrc,
    titleText,
    style = "rico",
    showCaptions = false,
    crossfadeFrames = STICK_CROSSFADE_FRAMES,
}) => {
    const { durationInFrames, fps } = useVideoConfig();
    const xf = Math.max(0, crossfadeFrames);

    return (
        <AbsoluteFill style={{ backgroundColor: style === "rico" ? "#ffffff" : "#efe9dc" }}>
            {titleText ? (
                <AbsoluteFill
                    style={{
                        justifyContent: "flex-start",
                        alignItems: "center",
                        paddingTop: 40,
                        zIndex: 2,
                        pointerEvents: "none",
                    }}
                >
                    <div
                        style={{
                            color: "#222",
                            fontSize: 24,
                            fontWeight: 600,
                            opacity: 0.28,
                            fontFamily: "system-ui, sans-serif",
                        }}
                    >
                        {titleText}
                    </div>
                </AbsoluteFill>
            ) : null}

            <TransitionSeries>
                {scenes.map((scene, index) => (
                    <React.Fragment key={`${scene.imagePath}-${index}`}>
                        <TransitionSeries.Sequence durationInFrames={scene.durationInFrames}>
                            <StickScene
                                imagePath={scene.imagePath}
                                videoSrc={scene.videoSrc}
                                caption={scene.caption}
                                durationInFrames={scene.durationInFrames}
                                motion={scene.motion ?? { preset: "zoom_in", intensity: 0.7 }}
                                showCaptions={showCaptions}
                                styleMode={style}
                            />
                        </TransitionSeries.Sequence>
                        {index < scenes.length - 1 && xf > 0 ? (
                            <TransitionSeries.Transition
                                presentation={fade()}
                                timing={linearTiming({ durationInFrames: xf })}
                            />
                        ) : null}
                    </React.Fragment>
                ))}
            </TransitionSeries>

            {voiceoverSrc ? (
                <Audio
                    src={voiceoverSrc}
                    volume={(f) => {
                        const fadeStart = durationInFrames - fps * 1;
                        if (f >= fadeStart) {
                            return 1 - (f - fadeStart) / fps;
                        }
                        return 1;
                    }}
                />
            ) : null}
        </AbsoluteFill>
    );
};
