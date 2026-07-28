import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../Background";
import { theme } from "../theme";
import type { ChartBar } from "../schema";

export const ChartScene: React.FC<{
  title: string;
  bars: ChartBar[];
  unit: string;
  accent: string;
  bg: string;
}> = ({ title, bars, unit, accent, bg }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleIn = spring({ frame, fps, config: { damping: 200 } });
  const maxValue = Math.max(...bars.map((b) => b.value), 1);
  const chartHeight = 900;

  return (
    <AbsoluteFill>
      <Background accent={accent} bg={bg} />
      <AbsoluteFill className="flex flex-col items-center justify-center px-20">
        <div
          className="mb-16 text-center font-black leading-tight"
          style={{
            color: theme.text,
            fontSize: 84,
            opacity: titleIn,
            transform: `translateY(${interpolate(titleIn, [0, 1], [40, 0])}px)`,
          }}
        >
          {title}
        </div>

        <div
          className="flex items-end justify-center gap-10"
          style={{ height: chartHeight }}
        >
          {bars.map((bar, i) => {
            const grow = spring({
              frame: frame - 10 - i * 8,
              fps,
              config: { damping: 200 },
            });
            const barHeight = (bar.value / maxValue) * chartHeight * grow;
            const shownValue = Math.round(bar.value * grow);
            return (
              <div key={bar.label} className="flex flex-col items-center" style={{ width: 150 }}>
                <div
                  className="font-black tabular-nums"
                  style={{ color: accent, fontSize: 48, opacity: grow }}
                >
                  {shownValue}
                  {unit}
                </div>
                <div
                  className="mt-4 w-full rounded-t-2xl"
                  style={{
                    height: Math.max(4, barHeight),
                    background: `linear-gradient(180deg, ${accent}, ${theme.accent2})`,
                  }}
                />
                <div
                  className="mt-6 text-center font-semibold"
                  style={{ color: theme.textDim, fontSize: 34 }}
                >
                  {bar.label}
                </div>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
