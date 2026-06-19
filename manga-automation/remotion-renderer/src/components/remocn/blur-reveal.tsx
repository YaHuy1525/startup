"use client";

import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export interface BlurRevealProps {
  text: string;
  className?: string;
  blur?: number;
  fontSize?: number;
  color?: string;
  fontWeight?: number;
  speed?: number;
  background?: string;
  inline?: boolean;
}

export function BlurReveal({
  text,
  className,
  blur = 10,
  fontSize = 48,
  color = "#171717",
  fontWeight = 600,
  speed = 1,
  background = "transparent",
  inline = false,
}: BlurRevealProps) {
  const frame = useCurrentFrame() * speed;
  const { durationInFrames } = useVideoConfig();

  const opacity = interpolate(frame, [0, durationInFrames * 0.6], [0, 1], {
    extrapolateRight: "clamp",
  });

  const blurAmount = interpolate(
    frame,
    [0, durationInFrames * 0.6],
    [blur, 0],
    { extrapolateRight: "clamp" },
  );

  return (
    <div
      style={{
        position: inline ? "relative" : "absolute",
        inset: inline ? undefined : 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background,
        width: inline ? "100%" : undefined,
      }}
    >
      <span
        className={className}
        style={{
          opacity,
          filter: `blur(${blurAmount}px)`,
          fontSize,
          fontWeight,
          color,
          letterSpacing: "-0.05em",
          fontFamily:
            "var(--font-geist-sans), -apple-system, BlinkMacSystemFont, sans-serif",
        }}
      >
        {text}
      </span>
    </div>
  );
}
