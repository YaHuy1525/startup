import React from "react";
import { AbsoluteFill, Audio, staticFile } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { HookScene } from "./scenes/HookScene";
import { FactScene } from "./scenes/FactScene";
import { ChartScene } from "./scenes/ChartScene";
import { CtaScene } from "./scenes/CtaScene";
import { Captions } from "./Captions";
import type { ShortVideoProps } from "./schema";
import { theme } from "./theme";

export const TRANSITION_FRAMES = 15;

/** Number of scenes = hook + facts + chart + cta. */
export function sceneCount(facts: number): number {
  return 1 + facts + 1 + 1;
}

export function calcShortVideoDuration(
  facts: number,
  sceneDurationInFrames: number,
): number {
  const scenes = sceneCount(facts);
  const total = scenes * sceneDurationInFrames;
  const overlap = Math.max(0, scenes - 1) * TRANSITION_FRAMES;
  return Math.max(30, total - overlap);
}

export const ShortVideo: React.FC<ShortVideoProps> = ({
  hook,
  facts,
  chart,
  cta,
  accentColor,
  backgroundColor,
  sceneDurationInFrames,
  audioSrc,
  captionsSrc,
}) => {
  const accent = accentColor || theme.accent;
  const bg = backgroundColor || theme.bg;
  const dur = sceneDurationInFrames;

  return (
    <AbsoluteFill style={{ backgroundColor: bg }}>
      {audioSrc ? <Audio src={staticFile(audioSrc)} /> : null}
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={dur}>
          <HookScene line1={hook.line1} line2={hook.line2} accent={accent} bg={bg} />
        </TransitionSeries.Sequence>

        {facts.map((fact, i) => (
          <React.Fragment key={`fact-${i}`}>
            <TransitionSeries.Transition
              presentation={fade()}
              timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
            />
            <TransitionSeries.Sequence durationInFrames={dur}>
              <FactScene
                index={i + 1}
                total={facts.length}
                value={fact.value}
                label={fact.label}
                accent={accent}
                bg={bg}
              />
            </TransitionSeries.Sequence>
          </React.Fragment>
        ))}

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
        />
        <TransitionSeries.Sequence durationInFrames={dur}>
          <ChartScene
            title={chart.title}
            bars={chart.bars}
            unit={chart.unit}
            accent={accent}
            bg={bg}
          />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
        />
        <TransitionSeries.Sequence durationInFrames={dur}>
          <CtaScene
            headline={cta.headline}
            subtext={cta.subtext}
            handle={cta.handle}
            accent={accent}
            bg={bg}
          />
        </TransitionSeries.Sequence>
      </TransitionSeries>

      {/* TikTok-style auto captions overlay (Whisper-generated JSON in public/) */}
      <Captions src={captionsSrc ?? undefined} accent={theme.accent2} />
    </AbsoluteFill>
  );
};
