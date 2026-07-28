import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../Background";
import { theme } from "../theme";

/** Splits a value like "70%" or "3.5x" into number + suffix for a count-up effect. */
function splitValue(value: string): { num: number; prefix: string; suffix: string } {
  const match = value.match(/^([^\d.-]*)(-?\d*\.?\d+)(.*)$/);
  if (!match) return { num: NaN, prefix: value, suffix: "" };
  return { prefix: match[1] || "", num: parseFloat(match[2]), suffix: match[3] || "" };
}

export const FactScene: React.FC<{
  index: number;
  total: number;
  value: string;
  label: string;
  accent: string;
  bg: string;
}> = ({ index, total, value, label, accent, bg }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const cardIn = spring({ frame, fps, config: { damping: 200 } });
  const labelIn = spring({ frame: frame - 12, fps, config: { damping: 200 } });

  const { num, prefix, suffix } = splitValue(value);
  const countProgress = interpolate(frame, [4, 34], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const decimals = Number.isInteger(num) ? 0 : 1;
  const shown = Number.isNaN(num)
    ? value
    : `${prefix}${(num * countProgress).toFixed(decimals)}${suffix}`;

  return (
    <AbsoluteFill>
      <Background accent={accent} bg={bg} />
      <AbsoluteFill className="flex flex-col items-center justify-center px-20">
        <div
          className="mb-10 text-4xl font-bold uppercase tracking-[0.3em]"
          style={{ color: theme.textDim, opacity: cardIn }}
        >
          Fact {index} / {total}
        </div>

        <div
          className="flex w-full flex-col items-center rounded-[48px] px-16 py-20"
          style={{
            backgroundColor: theme.bgAccent,
            border: `2px solid ${accent}55`,
            boxShadow: `0 0 120px ${accent}22`,
            opacity: cardIn,
            transform: `translateY(${interpolate(cardIn, [0, 1], [80, 0])}px)`,
          }}
        >
          <div
            className="font-black tabular-nums"
            style={{ color: accent, fontSize: 200, lineHeight: 1 }}
          >
            {shown}
          </div>
        </div>

        <div
          className="mt-12 max-w-[900px] text-center font-bold leading-snug"
          style={{
            color: theme.text,
            fontSize: 60,
            opacity: labelIn,
            transform: `translateY(${interpolate(labelIn, [0, 1], [40, 0])}px)`,
          }}
        >
          {label}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
