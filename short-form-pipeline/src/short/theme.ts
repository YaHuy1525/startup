/** Shared visual system for the short-form video (keep consistent across scenes). */
export const FPS = 30;
export const WIDTH = 1080;
export const HEIGHT = 1920;

export const theme = {
  bg: "#0B1020",
  bgAccent: "#131A33",
  text: "#F5F7FF",
  textDim: "#9AA6C7",
  accent: "#5B8CFF",
  accent2: "#22D3A6",
  danger: "#FF5C7A",
};

/** Default per-scene length in frames (2.5s at 30fps). */
export const SCENE = FPS * 3;
