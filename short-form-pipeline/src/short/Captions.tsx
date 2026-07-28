import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  AbsoluteFill,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  useDelayRender,
} from "remotion";
import {
  createTikTokStyleCaptions,
  type Caption,
  type TikTokPage,
} from "@remotion/captions";
import { theme } from "./theme";

const SWITCH_CAPTIONS_EVERY_MS = 1000;
const HIGHLIGHT_COLOR = theme.accent2;

/** TikTok-style word-by-word caption page with active-word highlight. */
const CaptionPage: React.FC<{ page: TikTokPage; accent: string }> = ({ page, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const absoluteTimeMs = page.startMs + (frame / fps) * 1000;

  return (
    <AbsoluteFill
      style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 320 }}
    >
      <div
        className="px-12 text-center"
        style={{
          fontSize: 76,
          fontWeight: 900,
          lineHeight: 1.15,
          maxWidth: 900,
          whiteSpace: "pre",
          textWrap: "balance" as React.CSSProperties["textWrap"],
        }}
      >
        {page.tokens.map((token) => {
          const isActive = token.fromMs <= absoluteTimeMs && token.toMs > absoluteTimeMs;
          return (
            <span
              key={`${token.fromMs}-${token.text}`}
              style={{
                color: isActive ? accent : theme.text,
                textShadow: "0 6px 24px rgba(0,0,0,0.6), 0 2px 0 rgba(0,0,0,0.9)",
                transform: isActive ? "scale(1.06)" : "scale(1)",
                display: "inline-block",
              }}
            >
              {token.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/**
 * Loads a captions JSON from public/ and renders TikTok-style pages.
 * Missing/failed file is non-fatal (video renders without captions).
 */
export const Captions: React.FC<{ src?: string; accent?: string }> = ({
  src,
  accent = HIGHLIGHT_COLOR,
}) => {
  const { fps } = useVideoConfig();
  const [captions, setCaptions] = useState<Caption[] | null>(null);
  const { delayRender, continueRender } = useDelayRender();
  const [handle] = useState(() => delayRender("fetch-captions"));

  const fetchCaptions = useCallback(async () => {
    if (!src) {
      setCaptions([]);
      continueRender(handle);
      return;
    }
    try {
      const response = await fetch(staticFile(src));
      if (!response.ok) throw new Error(`captions ${response.status}`);
      setCaptions(await response.json());
    } catch {
      // Non-fatal: render the video without captions.
      setCaptions([]);
    } finally {
      continueRender(handle);
    }
  }, [src, continueRender, handle]);

  useEffect(() => {
    fetchCaptions();
  }, [fetchCaptions]);

  const pages = useMemo(() => {
    if (!captions || captions.length === 0) return [];
    return createTikTokStyleCaptions({
      captions,
      combineTokensWithinMilliseconds: SWITCH_CAPTIONS_EVERY_MS,
    }).pages;
  }, [captions]);

  if (!captions || pages.length === 0) return null;

  return (
    <AbsoluteFill>
      {pages.map((page, index) => {
        const nextPage = pages[index + 1] ?? null;
        const startFrame = (page.startMs / 1000) * fps;
        const endFrame = Math.min(
          nextPage ? (nextPage.startMs / 1000) * fps : Infinity,
          startFrame + (SWITCH_CAPTIONS_EVERY_MS / 1000) * fps,
        );
        const durationInFrames = endFrame - startFrame;
        if (durationInFrames <= 0) return null;
        return (
          <Sequence key={index} from={startFrame} durationInFrames={durationInFrames}>
            <CaptionPage page={page} accent={accent} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
