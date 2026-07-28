import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../Background";
import { theme } from "../theme";

export const HookScene: React.FC<{
  line1: string;
  line2: string;
  accent: string;
  bg: string;
}> = ({ line1, line2, accent, bg }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter1 = spring({ frame, fps, config: { damping: 200 } });
  const enter2 = spring({ frame: frame - 10, fps, config: { damping: 200 } });
  const pulse = 1 + Math.sin(frame / 6) * 0.02;

  return (
    <AbsoluteFill>
      <Background accent={accent} bg={bg} />
      <AbsoluteFill className="flex flex-col items-center justify-center px-20">
        <div
          className="mb-8 rounded-full px-8 py-3 text-3xl font-semibold tracking-widest uppercase"
          style={{
            color: bg,
            backgroundColor: accent,
            opacity: enter1,
            transform: `translateY(${interpolate(enter1, [0, 1], [40, 0])}px)`,
          }}
        >
          Did you know?
        </div>
        <div
          className="text-center font-black leading-tight"
          style={{
            color: theme.text,
            fontSize: 96,
            opacity: enter1,
            transform: `translateY(${interpolate(enter1, [0, 1], [60, 0])}px) scale(${pulse})`,
          }}
        >
          {line1}
        </div>
        <div
          className="mt-6 text-center font-bold leading-tight"
          style={{
            color: accent,
            fontSize: 72,
            opacity: enter2,
            transform: `translateY(${interpolate(enter2, [0, 1], [60, 0])}px)`,
          }}
        >
          {line2}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
