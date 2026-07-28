import React from "react";
import { Composition } from "remotion";
import { MangaRecap, mangaRecapSchema } from "./MangaRecap";
import { BrainrotFeed, brainrotFeedSchema } from "./BrainrotFeed";
import { CharacterEdit, characterEditSchema } from "./CharacterEdit";
import { ChapterRecap, chapterRecapSchema } from "./ChapterRecap";
import { ProductPromo, productPromoSchema, calcProductPromoDuration } from "./ProductPromo";
import {
    StickFigureStory,
    stickFigureStorySchema,
    calcStickFigureStoryDuration,
} from "./StickFigureStory";

const FPS = 30;
const WIDTH = 1080;
const HEIGHT = 1920;
const DEFAULT_DURATION_FRAMES = FPS * 90;

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
                    const TRANSITION_FRAMES = 15;
                    const MIN_DURATION_FRAMES = FPS * 60;
                    const totalPanelFrames = props.panels.reduce(
                        (sum, p) => sum + p.durationInFrames,
                        0,
                    );
                    const transitionOverlap =
                        Math.max(0, props.panels.length - 1) * TRANSITION_FRAMES;
                    const totalFrames = Math.max(
                        MIN_DURATION_FRAMES,
                        totalPanelFrames - transitionOverlap,
                    );
                    return { durationInFrames: totalFrames };
                }}
            />

            <Composition
                id="BrainrotFeed"
                component={BrainrotFeed}
                durationInFrames={FPS * 30}
                fps={FPS}
                width={WIDTH}
                height={HEIGHT}
                schema={brainrotFeedSchema}
                defaultProps={{
                    panelImagePath: "",
                    subtitleText: "This panel goes hard",
                    gameplayVideoPath: "",
                    audioSrc: null,
                    voiceoverSrc: null,
                    panelDurationInFrames: 240,
                }}
            />

            <Composition
                id="CharacterEdit"
                component={CharacterEdit}
                durationInFrames={FPS * 30}
                fps={FPS}
                width={WIDTH}
                height={HEIGHT}
                schema={characterEditSchema}
                defaultProps={{
                    panels: [],
                    audioSrc: null,
                    titleText: "Character Edit",
                    characterName: "",
                    panelDurationFrames: 60,
                }}
                calculateMetadata={({ props }) => {
                    const totalFrames = props.panels.length * props.panelDurationFrames;
                    return { durationInFrames: Math.max(FPS * 15, totalFrames) };
                }}
            />

            <Composition
                id="ChapterRecap"
                component={ChapterRecap}
                durationInFrames={FPS * 120}
                fps={FPS}
                width={WIDTH}
                height={HEIGHT}
                schema={chapterRecapSchema}
                defaultProps={{
                    panels: [],
                    titleText: "Chapter Recap",
                    chapterText: "Chapter 1",
                    audioSrc: null,
                    voiceoverSrc: null,
                    introDurationFrames: 60,
                    outroDurationFrames: 60,
                }}
                calculateMetadata={({ props }) => {
                    const bodyFrames =
                        props.panels.reduce((s, p) => s + p.durationInFrames, 0) -
                        Math.max(0, props.panels.length - 1) * 15;
                    const totalFrames =
                        props.introDurationFrames + bodyFrames + props.outroDurationFrames;
                    return { durationInFrames: Math.max(FPS * 60, totalFrames) };
                }}
            />
            <Composition
                id="ProductPromo"
                component={ProductPromo}
                durationInFrames={FPS * 60}
                fps={FPS}
                width={WIDTH}
                height={HEIGHT}
                schema={productPromoSchema}
                defaultProps={{
                    productName: "Product Name",
                    tagline: "Tagline goes here",
                    brandColor: "#76b900",
                    accentColor: "#0a0a0a",
                    features: [
                        { headline: "Feature One", subtext: "Describe the core benefit" },
                        { headline: "Feature Two", subtext: "Highlight performance or speed" },
                        { headline: "Feature Three", subtext: "Close with social proof or scale" },
                    ],
                    ctaText: "Learn more at example.com",
                    audioSrc: null,
                    sceneDurationFrames: FPS * 12,
                }}
                calculateMetadata={({ props }) => ({
                    durationInFrames: calcProductPromoDuration(props.features.length),
                })}
            />
            <Composition
                id="StickFigureStory"
                component={StickFigureStory}
                durationInFrames={FPS * 60}
                fps={FPS}
                width={WIDTH}
                height={HEIGHT}
                schema={stickFigureStorySchema}
                defaultProps={{
                    scenes: [],
                    voiceoverSrc: null,
                    titleText: "",
                    paperBackgroundOpacity: 0,
                    aspectLabel: "9:16",
                    style: "rico",
                    showCaptions: false,
                    crossfadeFrames: 12,
                }}
                calculateMetadata={({ props }) => ({
                    durationInFrames: Math.max(
                        FPS * 15,
                        calcStickFigureStoryDuration(
                            props.scenes,
                            props.crossfadeFrames ?? 12,
                        ),
                    ),
                })}
            />
        </>
    );
};
