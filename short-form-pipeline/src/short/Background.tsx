import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { theme } from "./theme";

/** Consistent animated backdrop: deep gradient + slow-drifting accent glows. */
export const Background: React.FC<{ accent?: string; bg?: string }> = ({
  accent = theme.accent,
  bg = theme.bg,
}) => {
  const frame = useCurrentFrame();
  const drift = Math.sin(frame / 40) * 40;
  const drift2 = Math.cos(frame / 55) * 50;

  return (
    <AbsoluteFill style={{ backgroundColor: bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${50 + drift / 20}% 22%, ${accent}33, transparent 45%),
                       radial-gradient(circle at ${50 - drift2 / 20}% 82%, ${theme.accent2}22, transparent 45%)`,
        }}
      />
      {/* subtle grid */}
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${theme.textDim}0a 1px, transparent 1px),
                            linear-gradient(90deg, ${theme.textDim}0a 1px, transparent 1px)`,
          backgroundSize: "72px 72px",
          opacity: 0.5,
        }}
      />
    </AbsoluteFill>
  );
};
