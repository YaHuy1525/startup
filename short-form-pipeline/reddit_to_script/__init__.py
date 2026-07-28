"""Reddit -> AI script -> short-video-maker pipeline.

Fetches Reddit stories with Firecrawl (no Reddit API key required), rewrites
them into short-video-maker payloads with a swappable LLM, and renders them
through the existing short-video-maker container.
"""

__all__ = [
    "config",
    "firecrawl_client",
    "llm_client",
    "fetch_reddit",
    "generate_script",
    "submit_video",
    # meme-video path (OpenAI voice + Giphy footage + Remotion)
    "footage",
    "tts",
    "make_meme_video",
]
