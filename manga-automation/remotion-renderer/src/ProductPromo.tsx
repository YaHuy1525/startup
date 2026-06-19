import React from "react";
import {
    AbsoluteFill,
    Audio,
    interpolate,
    Sequence,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";
import { LightLeak } from "@remotion/light-leaks";
import { AnimatedText } from "remotion-bits";
import { BlurReveal } from "./components/remocn/blur-reveal";
import { Typewriter } from "./components/remocn/typewriter";
import { z } from "zod";

const FPS = 30;
const INTRO_FRAMES = FPS * 5;
const FEATURE_FRAMES = FPS * 12;
const CTA_FRAMES = FPS * 8;
const LIGHT_LEAK_FRAMES = 20;

export const productPromoFeatureSchema = z.object({
    headline: z.string(),
    subtext: z.string(),
});

export const productPromoSchema = z.object({
    productName: z.string(),
    tagline: z.string(),
    brandColor: z.string().default("#76b900"),
    accentColor: z.string().default("#0a0a0a"),
    features: z.array(productPromoFeatureSchema).min(1).max(5),
    ctaText: z.string(),
    audioSrc: z.string().nullable().default(null),
    sceneDurationFrames: z.number().int().min(60).default(FEATURE_FRAMES),
});

export type ProductPromoProps = z.infer<typeof productPromoSchema>;

const GradientBackground: React.FC<{
    brandColor: string;
    accentColor: string;
    variant?: number;
}> = ({ brandColor, accentColor, variant = 0 }) => {
    const frame = useCurrentFrame();
    const glow = interpolate(frame % (FPS * 4), [0, FPS * 2, FPS * 4], [0.15, 0.35, 0.15]);
    const angle = 135 + variant * 30;

    return (
        <AbsoluteFill style={{ backgroundColor: accentColor }}>
            <AbsoluteFill
                style={{
                    background: `linear-gradient(${angle}deg, ${accentColor} 0%, ${brandColor} 50%, ${accentColor} 100%)`,
                    opacity: 0.55 + glow,
                }}
            />
        </AbsoluteFill>
    );
};

const IntroScene: React.FC<{
    productName: string;
    tagline: string;
    brandColor: string;
    accentColor: string;
}> = ({ productName, tagline, brandColor, accentColor }) => (
    <AbsoluteFill>
        <GradientBackground brandColor={brandColor} accentColor={accentColor} />
        <AbsoluteFill
            style={{
                justifyContent: "center",
                alignItems: "center",
                padding: 64,
                gap: 32,
            }}
        >
            <AnimatedText
                transition={{
                    opacity: [0, 1],
                    y: [40, 0],
                    split: "word",
                    splitStagger: 3,
                }}
                style={{
                    color: "#ffffff",
                    fontSize: 72,
                    fontWeight: 800,
                    textAlign: "center",
                    lineHeight: 1.1,
                }}
            >
                {productName}
            </AnimatedText>
            <BlurReveal
                text={tagline}
                fontSize={36}
                fontWeight={500}
                color={brandColor}
                blur={12}
                background="transparent"
                inline
            />
        </AbsoluteFill>
    </AbsoluteFill>
);

const FeatureScene: React.FC<{
    headline: string;
    subtext: string;
    brandColor: string;
    accentColor: string;
    index: number;
}> = ({ headline, subtext, brandColor, accentColor, index }) => (
    <AbsoluteFill>
        <GradientBackground brandColor={brandColor} accentColor={accentColor} variant={index + 1} />
        <AbsoluteFill
            style={{
                justifyContent: "center",
                alignItems: "flex-start",
                padding: "0 72px",
                gap: 24,
            }}
        >
            <AnimatedText
                transition={{
                    opacity: [0, 1],
                    x: [-60, 0],
                    split: "word",
                    splitStagger: 2,
                }}
                style={{
                    color: "#ffffff",
                    fontSize: 56,
                    fontWeight: 700,
                    lineHeight: 1.15,
                }}
            >
                {headline}
            </AnimatedText>
            <AnimatedText
                transition={{
                    opacity: [0, 1],
                    y: [20, 0],
                    delay: 20,
                }}
                style={{
                    color: "rgba(255,255,255,0.85)",
                    fontSize: 32,
                    fontWeight: 400,
                    lineHeight: 1.35,
                    maxWidth: 900,
                }}
            >
                {subtext}
            </AnimatedText>
        </AbsoluteFill>
    </AbsoluteFill>
);

const CtaScene: React.FC<{
    ctaText: string;
    brandColor: string;
    accentColor: string;
}> = ({ ctaText, brandColor, accentColor }) => (
    <AbsoluteFill style={{ backgroundColor: accentColor }}>
        <AbsoluteFill
            style={{
                justifyContent: "center",
                alignItems: "center",
                padding: 64,
            }}
        >
            <Typewriter
                text={ctaText}
                fontSize={44}
                fontWeight={600}
                color="#ffffff"
                cursorColor={brandColor}
                charsPerSecond={28}
                background="transparent"
            />
        </AbsoluteFill>
    </AbsoluteFill>
);

export const calcProductPromoDuration = (featureCount: number): number => {
    const MIN_DURATION = FPS * 60;
    const featuresTotal = featureCount * FEATURE_FRAMES;
    const total = INTRO_FRAMES + featuresTotal + CTA_FRAMES;
    return Math.max(MIN_DURATION, total);
};

export const ProductPromo: React.FC<ProductPromoProps> = ({
    productName,
    tagline,
    brandColor,
    accentColor,
    features,
    ctaText,
    audioSrc,
}) => {
    const { durationInFrames, fps } = useVideoConfig();

    let cursor = 0;
    const scenes: Array<{ from: number; duration: number; node: React.ReactNode }> = [];

    scenes.push({
        from: cursor,
        duration: INTRO_FRAMES,
        node: (
            <IntroScene
                productName={productName}
                tagline={tagline}
                brandColor={brandColor}
                accentColor={accentColor}
            />
        ),
    });
    cursor += INTRO_FRAMES;

    features.forEach((feature, index) => {
        scenes.push({
            from: cursor,
            duration: FEATURE_FRAMES,
            node: (
                <FeatureScene
                    headline={feature.headline}
                    subtext={feature.subtext}
                    brandColor={brandColor}
                    accentColor={accentColor}
                    index={index}
                />
            ),
        });
        cursor += FEATURE_FRAMES;
    });

    scenes.push({
        from: cursor,
        duration: CTA_FRAMES,
        node: (
            <CtaScene ctaText={ctaText} brandColor={brandColor} accentColor={accentColor} />
        ),
    });

    const transitionPoints = scenes.slice(0, -1).map((scene) => scene.from + scene.duration - LIGHT_LEAK_FRAMES / 2);

    return (
        <AbsoluteFill style={{ backgroundColor: accentColor }}>
            {scenes.map((scene, i) => (
                <Sequence key={i} from={scene.from} durationInFrames={scene.duration}>
                    {scene.node}
                </Sequence>
            ))}

            {transitionPoints.map((from, i) => (
                <Sequence key={`leak-${i}`} from={from} durationInFrames={LIGHT_LEAK_FRAMES}>
                    <AbsoluteFill>
                        <LightLeak
                            durationInFrames={LIGHT_LEAK_FRAMES}
                            seed={i + 1}
                            hueShift={i % 2 === 0 ? 90 : 120}
                        />
                    </AbsoluteFill>
                </Sequence>
            ))}

            {audioSrc && (
                <Audio
                    src={audioSrc}
                    volume={(f) => {
                        const fadeStart = durationInFrames - fps * 2;
                        if (f >= fadeStart) {
                            return 0.35 * (1 - (f - fadeStart) / (fps * 2));
                        }
                        return 0.35;
                    }}
                />
            )}
        </AbsoluteFill>
    );
};
