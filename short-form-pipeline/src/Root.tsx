import "./index.css";
import { Composition } from "remotion";
import { MyComposition } from "./Composition";
import { ShortVideo, calcShortVideoDuration } from "./short/ShortVideo";
import { MemeStory, calcMemeStoryDuration } from "./short/MemeStory";
import { AnimeTheory, calcAnimeTheoryDuration } from "./short/AnimeTheory";
import { AnimeTheoryThumbnail } from "./short/AnimeTheoryThumbnail";
import {
  shortVideoSchema,
  memeStorySchema,
  animeTheorySchema,
  animeTheoryThumbnailSchema,
} from "./short/schema";
import { FPS, WIDTH, HEIGHT, theme } from "./short/theme";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ShortVideo"
        component={ShortVideo}
        schema={shortVideoSchema}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        durationInFrames={FPS * 20}
        defaultProps={{
          hook: {
            line1: "Your brain burns",
            line2: "20% of your energy",
          },
          facts: [
            { value: "86", label: "billion neurons firing every second" },
            { value: "70,000", label: "thoughts you have per day" },
            { value: "2%", label: "of body weight, 20% of the calories" },
          ],
          chart: {
            title: "Where your energy goes",
            unit: "%",
            bars: [
              { label: "Brain", value: 20 },
              { label: "Liver", value: 21 },
              { label: "Muscle", value: 22 },
              { label: "Heart", value: 9 },
            ],
          },
          cta: {
            headline: "Feed your brain",
            subtext: "One new fact every day.",
            handle: "@yourhandle",
          },
          accentColor: theme.accent,
          backgroundColor: theme.bg,
          sceneDurationInFrames: 90,
          audioSrc: null,
          captionsSrc: "captions.json",
        }}
        calculateMetadata={({ props }) => ({
          durationInFrames: calcShortVideoDuration(
            props.facts.length,
            props.sceneDurationInFrames,
          ),
        })}
      />

      {/* Reddit-story meme video: meme/stock scenes + human voiceover + captions. */}
      <Composition
        id="MemeStory"
        component={MemeStory}
        schema={memeStorySchema}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        durationInFrames={FPS * 20}
        defaultProps={{
          scenes: [
            {
              audioSrc: "assets/sample/scene-01.mp3",
              videoSrc: "assets/sample/scene-01.mp4",
              source: "giphy" as const,
              durationInFrames: FPS * 4,
            },
          ],
          captionsSrc: null,
          tailFrames: 30,
        }}
        calculateMetadata={({ props }) => ({
          durationInFrames: calcMemeStoryDuration(props.scenes, props.tailFrames),
        })}
      />

      <Composition
        id="AnimeTheory"
        component={AnimeTheory}
        schema={animeTheorySchema}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        durationInFrames={FPS * 45}
        defaultProps={{
          scenes: [
            {
              audioSrc: "assets/sample/scene-01.mp3",
              mediaSrc: "assets/sample/scene-01.jpg",
              kind: "image" as const,
              source: "anilist_cover" as const,
              durationInFrames: FPS * 4,
            },
          ],
          captionsSrc: null,
          tailFrames: 30,
          title: "ANIME THEORY",
          musicSrc: null,
          musicVolume: 0.14,
        }}
        calculateMetadata={({ props }) => ({
          durationInFrames: calcAnimeTheoryDuration(props.scenes, props.tailFrames),
        })}
      />

      {/* 16:9 YouTube poster — Hermes thumbnail-memory + Remotion still */}
      <Composition
        id="AnimeTheoryThumbnail"
        component={AnimeTheoryThumbnail}
        schema={animeTheoryThumbnailSchema}
        fps={FPS}
        width={1280}
        height={720}
        durationInFrames={1}
        defaultProps={{
          imageSrc: "assets/sample/scene-01.jpg",
          overlayText: "WHY KENJAKU CHOSE YUJI",
          layout: "single_face_closeup" as const,
          accentColor: "#FFCC00",
          vignette: true,
        }}
      />

      <MyComposition />
    </>
  );
};
