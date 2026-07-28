import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Loop,
  OffthreadVideo,
  Series,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { Captions } from "./Captions";
import type { AnimeTheoryProps, AnimeTheoryScene } from "./schema";
import { theme } from "./theme";

export function calcAnimeTheoryDuration(
  scenes: { durationInFrames: number }[],
  tailFrames: number,
): number {
  const total = scenes.reduce((sum, s) => sum + s.durationInFrames, 0);
  return Math.max(1, total + tailFrames);
}

/** Slow Ken Burns zoom/pan on a still — classic anime-theory Shorts look. */
const KenBurnsStill: React.FC<{
  src: string;
  durationInFrames: number;
  motion: "zoom_in" | "zoom_out" | "pan_left" | "pan_right";
}> = ({ src, durationInFrames, motion }) => {
  const frame = useCurrentFrame();
  const t = durationInFrames <= 1 ? 0 : frame / durationInFrames;

  let scale = 1;
  let tx = 0;
  let ty = 0;
  switch (motion) {
    case "zoom_out":
      scale = interpolate(t, [0, 1], [1.18, 1.02]);
      break;
    case "pan_left":
      scale = 1.14;
      tx = interpolate(t, [0, 1], [4, -4]);
      break;
    case "pan_right":
      scale = 1.14;
      tx = interpolate(t, [0, 1], [-4, 4]);
      break;
    default:
      scale = interpolate(t, [0, 1], [1.02, 1.16]);
      ty = interpolate(t, [0, 1], [1, -1]);
  }

  return (
    <AbsoluteFill style={{ overflow: "hidden", backgroundColor: "#050508" }}>
      {/* Soft blurred fill behind letterboxed art */}
      <AbsoluteFill>
        <Img
          src={src}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            filter: "blur(36px) brightness(0.35) saturate(1.15)",
            transform: "scale(1.2)",
          }}
        />
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <Img
          src={src}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `translate(${tx}%, ${ty}%) scale(${scale})`,
          }}
        />
      </AbsoluteFill>
      {/* Bottom vignette so captions pop */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.35) 0%, transparent 22%, transparent 55%, rgba(0,0,0,0.72) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

const SceneVisual: React.FC<{ scene: AnimeTheoryScene; index: number }> = ({
  scene,
  index,
}) => {
  const motions: Array<"zoom_in" | "zoom_out" | "pan_left" | "pan_right"> = [
    "zoom_in",
    "pan_left",
    "zoom_out",
    "pan_right",
  ];
  const motion = motions[index % motions.length];
  const mediaUrl = staticFile(scene.mediaSrc);

  if (scene.kind === "video") {
    const clipFrames = Math.max(1, scene.clipDurationInFrames ?? 60);
    return (
      <AbsoluteFill style={{ backgroundColor: "#050508" }}>
        <AbsoluteFill>
          <Loop durationInFrames={clipFrames}>
            <OffthreadVideo
              src={mediaUrl}
              muted
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
                filter: "blur(40px) brightness(0.4)",
                transform: "scale(1.25)",
              }}
            />
          </Loop>
        </AbsoluteFill>
        <AbsoluteFill>
          <Loop durationInFrames={clipFrames}>
            <OffthreadVideo
              src={mediaUrl}
              muted
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </Loop>
        </AbsoluteFill>
        <AbsoluteFill
          style={{
            background:
              "linear-gradient(180deg, rgba(0,0,0,0.3) 0%, transparent 25%, transparent 55%, rgba(0,0,0,0.7) 100%)",
          }}
        />
        <Audio src={staticFile(scene.audioSrc)} />
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill>
      <KenBurnsStill src={mediaUrl} durationInFrames={scene.durationInFrames} motion={motion} />
      <Audio src={staticFile(scene.audioSrc)} />
    </AbsoluteFill>
  );
};

/** Anime-theory Shorts: stills/clips per beat + scene VO + word captions. */
export const AnimeTheory: React.FC<AnimeTheoryProps> = ({
  scenes,
  captionsSrc,
  title,
  musicSrc,
  musicVolume = 0.14,
}) => {
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      {title ? (
        <AbsoluteFill
          style={{
            justifyContent: "flex-start",
            alignItems: "center",
            paddingTop: 96,
            zIndex: 2,
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              color: theme.text,
              fontSize: 36,
              fontWeight: 800,
              letterSpacing: 1,
              textTransform: "uppercase",
              opacity: 0.85,
              textShadow: "0 2px 12px rgba(0,0,0,0.8)",
              maxWidth: 920,
              textAlign: "center",
              padding: "0 24px",
            }}
          >
            {title}
          </div>
        </AbsoluteFill>
      ) : null}

      {musicSrc ? (
        <Audio src={staticFile(musicSrc)} volume={musicVolume} loop />
      ) : null}

      <Series>
        {scenes.map((scene, i) => (
          <Series.Sequence key={i} durationInFrames={scene.durationInFrames}>
            <SceneVisual scene={scene} index={i} />
          </Series.Sequence>
        ))}
      </Series>

      <Captions src={captionsSrc ?? undefined} accent="#FFD166" />
    </AbsoluteFill>
  );
};
