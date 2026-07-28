import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import type { AnimeTheoryThumbnailProps } from "./schema";

/**
 * YouTube poster still (1280×720) — Hermes thumbnail-memory driven.
 * Render: npx remotion still ... AnimeTheoryThumbnail out.jpg --props=...
 */
export const AnimeTheoryThumbnail: React.FC<AnimeTheoryThumbnailProps> = ({
  imageSrc,
  overlayText,
  layout = "single_face_closeup",
  accentColor = "#FFCC00",
  vignette = true,
}) => {
  const frame = useCurrentFrame();
  const pulse = interpolate(frame, [0, 1], [1, 1.02], {
    extrapolateRight: "clamp",
  });

  const isVersus = layout === "versus_split";
  const textShadow = "0 2px 0 #000, 0 4px 12px rgba(0,0,0,0.85)";

  return (
    <AbsoluteFill style={{ backgroundColor: "#050508" }}>
      <AbsoluteFill
        style={{
          transform: `scale(${pulse})`,
          overflow: "hidden",
        }}
      >
        <Img
          src={staticFile(imageSrc)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: isVersus ? "center center" : "center 20%",
            filter: "saturate(1.25) contrast(1.08)",
          }}
        />
      </AbsoluteFill>

      {vignette ? (
        <AbsoluteFill
          style={{
            background:
              "radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.72) 100%)",
          }}
        />
      ) : null}

      <AbsoluteFill
        style={{
          justifyContent: "flex-start",
          alignItems: layout === "face_plus_prop" ? "flex-end" : "flex-start",
          padding: "48px 56px",
          paddingRight: 120, // clear YT timestamp corner on 16:9 browse
        }}
      >
        <div
          style={{
            maxWidth: "78%",
            fontFamily: "Impact, Haettenschweiler, Arial Black, sans-serif",
            fontSize: overlayText.length > 28 ? 64 : 78,
            lineHeight: 1.05,
            fontWeight: 900,
            color: "#FFFFFF",
            textTransform: "uppercase",
            letterSpacing: 1,
            textShadow,
            WebkitTextStroke: `3px ${accentColor}`,
            paintOrder: "stroke fill",
          }}
        >
          {overlayText}
        </div>
      </AbsoluteFill>

      {isVersus ? (
        <AbsoluteFill
          style={{
            justifyContent: "center",
            alignItems: "center",
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              fontFamily: "Impact, Arial Black, sans-serif",
              fontSize: 96,
              color: accentColor,
              textShadow,
              fontWeight: 900,
            }}
          >
            VS
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
