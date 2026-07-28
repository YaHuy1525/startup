import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../Background";
import { theme } from "../theme";

export const CtaScene: React.FC<{
  headline: string;
  subtext: string;
  handle: string;
  accent: string;
  bg: string;
}> = ({ headline, subtext, handle, accent, bg }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const pop = spring({ frame, fps, config: { damping: 12, mass: 0.6 } });
  const subIn = spring({ frame: frame - 12, fps, config: { damping: 200 } });
  const handleIn = spring({ frame: frame - 24, fps, config: { damping: 200 } });
  const arrowBounce = Math.sin(frame / 5) * 12;

  return (
    <AbsoluteFill>
      <Background accent={accent} bg={bg} />
      <AbsoluteFill className="flex flex-col items-center justify-center px-20">
        <div
          className="text-center font-black leading-tight"
          style={{
            color: theme.text,
            fontSize: 104,
            opacity: interpolate(pop, [0, 1], [0, 1]),
            transform: `scale(${interpolate(pop, [0, 1], [0.6, 1])})`,
          }}
        >
          {headline}
        </div>

        <div
          className="mt-8 max-w-[900px] text-center font-medium"
          style={{
            color: theme.textDim,
            fontSize: 48,
            opacity: subIn,
            transform: `translateY(${interpolate(subIn, [0, 1], [40, 0])}px)`,
          }}
        >
          {subtext}
        </div>

        <div
          className="mt-16 flex items-center gap-5 rounded-full px-12 py-6"
          style={{
            backgroundColor: accent,
            opacity: handleIn,
            transform: `translateY(${interpolate(handleIn, [0, 1], [50, 0]) - arrowBounce * handleIn}px)`,
          }}
        >
          <span className="font-black" style={{ color: bg, fontSize: 56 }}>
            {handle}
          </span>
        </div>

        <div
          className="mt-10 font-black"
          style={{
            color: accent,
            fontSize: 80,
            opacity: handleIn,
            transform: `translateY(${arrowBounce}px)`,
          }}
        >
          ↑
        </div>
        <div className="font-semibold" style={{ color: theme.textDim, fontSize: 36, opacity: handleIn }}>
          Follow for more
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
