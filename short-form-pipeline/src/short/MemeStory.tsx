import React from "react";
import {
  AbsoluteFill,
  Audio,
  Loop,
  OffthreadVideo,
  Series,
  staticFile,
} from "remotion";
import { Captions } from "./Captions";
import type { MemeScene, MemeStoryProps } from "./schema";
import { theme } from "./theme";

/** Total video length = sum of scene lengths + a short tail hold. */
export function calcMemeStoryDuration(
  scenes: { durationInFrames: number }[],
  tailFrames: number,
): number {
  const total = scenes.reduce((sum, s) => sum + s.durationInFrames, 0);
  return Math.max(1, total + tailFrames);
}

/**
 * A single scene: background clip + its own voiceover.
 * - Giphy memes are letterboxed (contain) on a blurred fill so nothing crops.
 * - Pexels stock footage fills the frame (cover), since it's shot as video.
 */
const SceneClip: React.FC<{ scene: MemeScene }> = ({ scene }) => {
  const isMeme = scene.source === "giphy";
  const videoUrl = staticFile(scene.videoSrc);
  const clipFrames = Math.max(1, scene.clipDurationInFrames);
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Blurred, scaled-up fill so portrait frame is never empty. */}
      <AbsoluteFill>
        <Loop durationInFrames={clipFrames}>
          <OffthreadVideo
            src={videoUrl}
            muted
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "blur(48px) brightness(0.45)",
              transform: "scale(1.25)",
            }}
          />
        </Loop>
      </AbsoluteFill>

      {/* Foreground clip. */}
      <AbsoluteFill
        style={{
          justifyContent: isMeme ? "flex-start" : "center",
          alignItems: "center",
          paddingTop: isMeme ? 240 : 0,
        }}
      >
        <Loop durationInFrames={clipFrames}>
          <OffthreadVideo
            src={videoUrl}
            muted
            style={
              isMeme
                ? { width: "100%", height: "auto", maxHeight: "60%", objectFit: "contain" }
                : { width: "100%", height: "100%", objectFit: "cover" }
            }
          />
        </Loop>
      </AbsoluteFill>

      <Audio src={staticFile(scene.audioSrc)} />
    </AbsoluteFill>
  );
};

/** Meme-story short: sequenced meme/stock scenes + global word captions. */
export const MemeStory: React.FC<MemeStoryProps> = ({ scenes, captionsSrc }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      <Series>
        {scenes.map((scene, i) => (
          <Series.Sequence key={i} durationInFrames={scene.durationInFrames}>
            <SceneClip scene={scene} />
          </Series.Sequence>
        ))}
      </Series>

      {/* Word-by-word captions overlaid across the whole timeline. */}
      <Captions src={captionsSrc ?? undefined} accent={theme.accent2} />
    </AbsoluteFill>
  );
};
