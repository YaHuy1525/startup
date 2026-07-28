import { z } from "zod";
import { theme } from "./theme";

export const factSchema = z.object({
  /** Big number or short value, e.g. "70%" or "3.5x". */
  value: z.string(),
  /** One-line description of the fact. */
  label: z.string(),
});

export const chartBarSchema = z.object({
  label: z.string(),
  /** 0-100 relative height. */
  value: z.number().min(0).max(100),
});

export const shortVideoSchema = z.object({
  hook: z.object({
    line1: z.string(),
    line2: z.string(),
  }),
  facts: z.array(factSchema).min(1).max(5),
  chart: z.object({
    title: z.string(),
    bars: z.array(chartBarSchema).min(2).max(6),
    unit: z.string().default(""),
  }),
  cta: z.object({
    headline: z.string(),
    subtext: z.string(),
    handle: z.string(),
  }),
  accentColor: z.string().default(theme.accent),
  backgroundColor: z.string().default(theme.bg),
  /** Frames per scene (hook, each fact, chart, cta). */
  sceneDurationInFrames: z.number().int().min(30).default(90),
  /** Optional voiceover audio in public/ (e.g. "voiceover.mp3"). */
  audioSrc: z.string().nullable().default(null),
  /** Optional Whisper captions JSON in public/ (e.g. "captions.json"). */
  captionsSrc: z.string().nullable().default(null),
});

export type ShortVideoProps = z.infer<typeof shortVideoSchema>;
export type Fact = z.infer<typeof factSchema>;
export type ChartBar = z.infer<typeof chartBarSchema>;

/** One scene of a meme-story video: a background clip + its own voiceover. */
export const memeSceneSchema = z.object({
  /** Voiceover audio in public/ (e.g. "assets/job123/scene-01.mp3"). */
  audioSrc: z.string(),
  /** Background clip URL (Giphy meme mp4 or Pexels stock mp4). */
  videoSrc: z.string(),
  /** Where the clip came from — drives fit (contain memes, cover stock). */
  source: z.enum(["giphy", "pexels"]).default("giphy"),
  /** How long this scene runs, in frames. */
  durationInFrames: z.number().int().min(1),
  /** Native length of the clip in frames, used to loop it seamlessly. */
  clipDurationInFrames: z.number().int().min(1).default(60),
});

export const memeStorySchema = z.object({
  scenes: z.array(memeSceneSchema).min(1),
  /** TikTok-style word captions JSON in public/ (Caption[]). */
  captionsSrc: z.string().nullable().default(null),
  /** Extra frames held after the last scene. */
  tailFrames: z.number().int().min(0).default(30),
});

export type MemeStoryProps = z.infer<typeof memeStorySchema>;
export type MemeScene = z.infer<typeof memeSceneSchema>;

/** One beat of an anime-theory Short: still or clip + voiceover. */
export const animeTheorySceneSchema = z.object({
  audioSrc: z.string(),
  /** Image (jpg/png/webp) or mp4 path under public/. */
  mediaSrc: z.string(),
  kind: z.enum(["image", "video"]).default("image"),
  source: z
    .enum([
      "safebooru",
      "anilist_character",
      "anilist_cover",
      "anilist_banner",
      "giphy",
      "local",
    ])
    .default("safebooru"),
  durationInFrames: z.number().int().min(1),
  /** Native clip length in frames (video only; used for looping). */
  clipDurationInFrames: z.number().int().min(1).optional(),
});

export const animeTheorySchema = z.object({
  scenes: z.array(animeTheorySceneSchema).min(1),
  captionsSrc: z.string().nullable().default(null),
  tailFrames: z.number().int().min(0).default(30),
  /** Optional top title overlay (series / theory name). */
  title: z.string().nullable().default(null),
  /** Optional looping background music under public/ (e.g. "music/dark.wav"). */
  musicSrc: z.string().nullable().default(null),
  /** Background music volume 0–1 (keep low under VO). */
  musicVolume: z.number().min(0).max(1).default(0.14),
});

export type AnimeTheoryProps = z.infer<typeof animeTheorySchema>;
export type AnimeTheoryScene = z.infer<typeof animeTheorySceneSchema>;

/** YouTube poster / Shorts cover still (Hermes thumbnail agent). */
export const animeTheoryThumbnailSchema = z.object({
  imageSrc: z.string(),
  overlayText: z.string().min(1).max(48),
  layout: z
    .enum(["single_face_closeup", "versus_split", "face_plus_prop"])
    .default("single_face_closeup"),
  accentColor: z.string().default("#FFCC00"),
  vignette: z.boolean().default(true),
});

export type AnimeTheoryThumbnailProps = z.infer<typeof animeTheoryThumbnailSchema>;
