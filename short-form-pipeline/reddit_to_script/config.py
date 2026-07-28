"""Central configuration for the Reddit -> viral-short pipeline.

All secrets/tunables are read from environment variables. A `.env` file in the
pipeline root (``short-form-pipeline/.env``) or in this folder is loaded
automatically, so you can keep FIRECRAWL_API_KEY / OPENAI_API_KEY next to the
existing PEXELS_API_KEY.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# reddit_to_script/ -> short-form-pipeline/
PKG_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = PKG_DIR.parent

# Load .env from the pipeline root first, then allow a local override.
load_dotenv(PIPELINE_ROOT / ".env")
load_dotenv(PKG_DIR / ".env", override=True)

# ── Reddit (public RSS feeds — no OAuth app needed) ──────────────────────────
# Firecrawl refuses reddit.com ("we do not support this site") and reddit.com/
# *.json now serves an HTML "Welcome to Reddit" interstitial to bots. The RSS
# feeds (/r/<sub>/top/.rss) still return clean XML with full self-post bodies.
# A browser-like User-Agent is required (Reddit blocks generic library UAs).
REDDIT_BASE_URL = os.getenv("REDDIT_BASE_URL", "https://www.reddit.com").rstrip("/")
REDDIT_USER_AGENT = os.getenv(
    "REDDIT_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
)

# ── Firecrawl (optional; NOT used for Reddit — kept for other sources) ────────
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "").strip()
FIRECRAWL_BASE_URL = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev").rstrip("/")

# ── LLM (script generation) ──────────────────────────────────────────────────
# provider: "openai" | "anthropic"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()  # blank -> provider default
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")

_DEFAULT_MODELS = {"openai": "gpt-4o-mini", "anthropic": "claude-3-5-sonnet-latest"}


def resolved_llm_model() -> str:
    """Return the configured model, or the provider's sensible default."""
    return LLM_MODEL or _DEFAULT_MODELS.get(LLM_PROVIDER, "gpt-4o-mini")


# ── Giphy (meme footage) ─────────────────────────────────────────────────────
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY", "").strip()
GIPHY_RATING = os.getenv("GIPHY_RATING", "pg-13")  # g | pg | pg-13 | r

# ── Pexels (fallback footage; shared with short-video-maker) ─────────────────
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()

# ── OpenAI TTS + transcription (human voiceover + word-timed captions) ───────
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
# Prefer brighter/faster voices for Shorts (onyx is too deep/slow).
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "nova")
OPENAI_TTS_SPEED = float(os.getenv("OPENAI_TTS_SPEED", "1.2") or "1.2")
OPENAI_TTS_INSTRUCTIONS = os.getenv(
    "OPENAI_TTS_INSTRUCTIONS",
    "Speak like a fast TikTok anime narrator — bright, punchy, high energy. "
    "Minimal pauses. No deep radio-host tone. No laughing.",
)
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

# ── TTS provider: openai | noiz ──────────────────────────────────────────────
# Anime-theory defaults to Noiz (better narration). Captions still use OpenAI Whisper.
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "noiz").strip().lower()
NOIZ_API_KEY = os.getenv("NOIZ_API_KEY", "").strip()
NOIZ_BASE_URL = os.getenv("NOIZ_BASE_URL", "https://noiz.ai/v1").rstrip("/")
# Science Narration is clearer/faster for Shorts than deep Mentor Alex.
NOIZ_VOICE_ID = os.getenv("NOIZ_VOICE_ID", "95814add").strip()
NOIZ_SPEED = float(os.getenv("NOIZ_SPEED", "1.35") or "1.35")
NOIZ_TARGET_LANG = os.getenv("NOIZ_TARGET_LANG", "en").strip()
NOIZ_EMO = os.getenv(
    "NOIZ_EMO",
    '{"Surprise":0.55,"Anger":0.25,"Sadness":0.15,"Happiness":0.1}',
).strip()
NOIZ_AUTO_EMOTION = os.getenv("NOIZ_AUTO_EMOTION", "false").strip().lower() not in (
    "0",
    "false",
    "no",
)
NOIZ_ALLOW_GUEST = os.getenv("NOIZ_ALLOW_GUEST", "true").strip().lower() not in (
    "0",
    "false",
    "no",
)

# ── Pixabay (royalty-free music attempt; images also available) ──────────────
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "").strip()
# BGM duck under VO (0–1). Louder than before so beds are audible.
ANIME_MUSIC_VOLUME = float(os.getenv("ANIME_MUSIC_VOLUME", "0.22") or "0.22")

# Soft size budget for Shorts (TikTok/IG-friendly). Was 500 → files hit 200–300MB.
MAX_VIDEO_MB = float(os.getenv("MAX_VIDEO_MB", "45") or "45")
# Remotion encode quality (lower CRF = bigger files). 23 ≈ good Shorts default.
REMOTION_CRF = int(os.getenv("REMOTION_CRF", "23") or "23")
REMOTION_JPEG_QUALITY = int(os.getenv("REMOTION_JPEG_QUALITY", "80") or "80")
REMOTION_X264_PRESET = os.getenv("REMOTION_X264_PRESET", "medium").strip() or "medium"
# Anime-theory duration budget (seconds). Shorts default 90s; long-form up to 180s.
MAX_ANIME_THEORY_SECONDS = float(os.getenv("MAX_ANIME_THEORY_SECONDS", "90") or "90")
MAX_ANIME_THEORY_LONG_SECONDS = float(
    os.getenv("MAX_ANIME_THEORY_LONG_SECONDS", "180") or "180"
)
ANIME_PREFER_VIDEO = False  # anime-theory uses Safebooru/AniList stills only (no Giphy)
# Safebooru (Gelbooru-style) character art API — https://safebooru.org
SAFEBOORU_BASE_URL = os.getenv("SAFEBOORU_BASE_URL", "https://safebooru.org").rstrip("/")
# Legacy (meme pipeline only)
ANIME_GIPHY_MIN_PX = int(os.getenv("ANIME_GIPHY_MIN_PX", "480") or "480")

# ── Remotion meme-video pipeline ─────────────────────────────────────────────
REMOTION_ENTRY = PIPELINE_ROOT / "src" / "index.ts"
REMOTION_COMPOSITION = os.getenv("MEME_COMPOSITION", "MemeStory")
PUBLIC_DIR = PIPELINE_ROOT / "public"
ASSETS_DIR = PUBLIC_DIR / "assets"  # per-job TTS mp3 + captions live here
MEME_OUT_DIR = PIPELINE_ROOT / "out"

# ── short-video-maker ────────────────────────────────────────────────────────
SVM_BASE_URL = os.getenv("SVM_BASE_URL", "http://localhost:3123").rstrip("/")
# Where the container drops finished MP4s on the host (bind mount target).
SVM_OUT_DIR = Path(
    os.getenv("SVM_OUT_DIR", str(PIPELINE_ROOT / "out" / "short-video-maker"))
)

# Where generated payloads/artifacts are written.
PAYLOAD_DIR = PIPELINE_ROOT / "payloads"
WORK_DIR = PKG_DIR / "work"

# ── Valid short-video-maker options (mirrors the live /api endpoints) ─────────
VOICES = [
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
    "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky", "am_adam",
    "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx",
    "am_puck", "am_santa", "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
    "bf_alice", "bf_lily", "bm_daniel", "bm_fable",
]
MUSIC_TAGS = [
    "melancholic", "chill", "uneasy", "excited", "euphoric/high", "dark",
    "sad", "happy", "angry", "hopeful", "contemplative", "funny/quirky",
]

# Defaults applied to every generated payload's `config` block.
DEFAULT_VOICE = os.getenv("SVM_VOICE", "am_adam")
DEFAULT_MUSIC = os.getenv("SVM_MUSIC", "excited")
DEFAULT_ORIENTATION = os.getenv("SVM_ORIENTATION", "portrait")
DEFAULT_CAPTION_POSITION = os.getenv("SVM_CAPTION_POSITION", "bottom")
DEFAULT_CAPTION_BG = os.getenv("SVM_CAPTION_BG", "blue")


class ConfigError(RuntimeError):
    """Raised when a required setting is missing."""


def require_firecrawl() -> str:
    if not FIRECRAWL_API_KEY:
        raise ConfigError(
            "FIRECRAWL_API_KEY is not set. Add it to short-form-pipeline/.env "
            "(get a key at https://www.firecrawl.dev/app/api-keys)."
        )
    return FIRECRAWL_API_KEY


def require_openai() -> str:
    """OpenAI key for TTS + transcription (independent of the script LLM provider)."""
    if not OPENAI_API_KEY:
        raise ConfigError("OPENAI_API_KEY is not set (needed for TTS + captions).")
    return OPENAI_API_KEY


def require_noiz() -> str:
    """Noiz API key; empty string is OK when guest mode is allowed."""
    if NOIZ_API_KEY:
        return NOIZ_API_KEY
    if NOIZ_ALLOW_GUEST:
        return ""
    raise ConfigError(
        "NOIZ_API_KEY is not set. Get one at https://developers.noiz.ai/api-keys "
        "or set NOIZ_ALLOW_GUEST=true to use the limited guest endpoint."
    )


def require_giphy() -> str:
    if not GIPHY_API_KEY:
        raise ConfigError("GIPHY_API_KEY is not set. Add it to short-form-pipeline/.env.")
    return GIPHY_API_KEY


def require_llm_key() -> str:
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ConfigError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
        return OPENAI_API_KEY
    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise ConfigError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        return ANTHROPIC_API_KEY
    raise ConfigError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER!r} (use 'openai' or 'anthropic').")
