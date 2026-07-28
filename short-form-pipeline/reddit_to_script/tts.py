"""Human voiceover + word-timed captions.

TTS providers:
  * ``noiz`` (default) — Noiz AI lifelike narration; falls back to guest endpoint
    when ``NOIZ_API_KEY`` is missing and ``NOIZ_ALLOW_GUEST=true``.
  * ``openai`` — OpenAI gpt-4o-mini-tts / legacy TTS.

Captions always use OpenAI Whisper transcription (word timings), so
``OPENAI_API_KEY`` is still required even when Noiz generates the voice.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from pathlib import Path

import requests

from . import config


class TTSError(RuntimeError):
    """Raised when TTS or transcription fails."""


@dataclass
class Word:
    word: str
    start: float  # seconds
    end: float


@dataclass
class SceneAudio:
    """Result of synthesizing + transcribing one scene."""

    path: Path
    duration: float  # seconds
    words: list[Word]
    provider: str = "openai"


def _normalize_noiz_key(api_key: str) -> str:
    """Noiz expects a base64-looking Authorization header value."""
    key = api_key.strip()
    if not key:
        return key
    padded = key + ("=" * (-len(key) % 4))
    try:
        decoded = base64.b64decode(padded, validate=True)
        canonical = base64.b64encode(decoded).decode("ascii").rstrip("=")
        if decoded and canonical == key.rstrip("="):
            return key
    except binascii.Error:
        pass
    return base64.b64encode(key.encode("utf-8")).decode("ascii")


def synthesize_openai(text: str, out_path: Path, *, timeout: int = 120) -> Path:
    """Generate speech via OpenAI into ``out_path`` (mp3)."""
    api_key = config.require_openai()
    payload = {
        "model": config.OPENAI_TTS_MODEL,
        "voice": config.OPENAI_TTS_VOICE,
        "input": text,
        "response_format": "mp3",
    }
    # `speed` is supported on tts-1 / tts-1-hd; gpt-4o-* uses instructions for pace.
    model = config.OPENAI_TTS_MODEL.lower()
    if model.startswith("tts-"):
        payload["speed"] = float(getattr(config, "OPENAI_TTS_SPEED", 1.2) or 1.2)
    if "gpt-4o" in model:
        payload["instructions"] = config.OPENAI_TTS_INSTRUCTIONS
        # Nudge pace in instructions when speed param unavailable
        spd = float(getattr(config, "OPENAI_TTS_SPEED", 1.2) or 1.2)
        if spd >= 1.15:
            payload["instructions"] = (
                f"{config.OPENAI_TTS_INSTRUCTIONS} Speak about {spd:.0%} normal speed — "
                "tight gaps, almost no trailing silence."
            )

    resp = requests.post(
        f"{config.OPENAI_BASE_URL}/audio/speech",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    if not resp.ok:
        raise TTSError(f"OpenAI TTS {resp.status_code}: {resp.text[:300]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)
    return out_path


def emotion_enhance(text: str, *, timeout: int = 60) -> str:
    """Ask Noiz to annotate text with emotion tags (authenticated only)."""
    api_key = config.NOIZ_API_KEY
    if not api_key:
        return text
    resp = requests.post(
        f"{config.NOIZ_BASE_URL}/emotion-enhance",
        headers={
            "Authorization": _normalize_noiz_key(api_key),
            "Content-Type": "application/json",
        },
        json={"text": text},
        timeout=timeout,
    )
    if not resp.ok:
        print(f"  [noiz] emotion-enhance {resp.status_code}; using raw text", flush=True)
        return text
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    enhanced = ((body.get("data") or {}).get("emotion_enhance") or "").strip()
    return enhanced or text


def synthesize_noiz(
    text: str,
    out_path: Path,
    *,
    voice_id: str | None = None,
    emotion: dict | None = None,
    timeout: int = 120,
) -> Path:
    """Generate speech via Noiz AI (authenticated or guest) into ``out_path`` (mp3)."""
    voice = (voice_id or config.NOIZ_VOICE_ID or "").strip()
    if not voice:
        raise TTSError("NOIZ_VOICE_ID is required for Noiz TTS.")

    speak_text = text
    api_key = config.NOIZ_API_KEY
    if api_key and getattr(config, "NOIZ_AUTO_EMOTION", True):
        speak_text = emotion_enhance(text, timeout=min(timeout, 60))

    fmt = "mp3"
    data = {
        "text": speak_text,
        "voice_id": voice,
        "output_format": fmt,
        "speed": str(config.NOIZ_SPEED),
        "trim_silence": "true",
    }
    if config.NOIZ_TARGET_LANG:
        data["target_lang"] = config.NOIZ_TARGET_LANG

    emo = emotion
    if emo is None and config.NOIZ_EMO:
        try:
            emo = json.loads(config.NOIZ_EMO)
        except json.JSONDecodeError:
            emo = None

    if api_key:
        if emo:
            data["emo"] = json.dumps(emo)
        print(
            f"  [noiz] voice={voice} speed={config.NOIZ_SPEED} emo={'yes' if emo else 'no'}",
            flush=True,
        )
        resp = requests.post(
            f"{config.NOIZ_BASE_URL}/text-to-speech",
            headers={"Authorization": _normalize_noiz_key(api_key)},
            data=data,
            timeout=timeout,
        )
        if not resp.ok:
            raise TTSError(f"Noiz TTS {resp.status_code}: {resp.text[:300]}")
    else:
        if not config.NOIZ_ALLOW_GUEST:
            raise TTSError("NOIZ_API_KEY missing and guest mode disabled.")
        print(f"  [noiz-guest] voice={voice} speed={config.NOIZ_SPEED}", flush=True)
        resp = requests.post(
            f"{config.NOIZ_BASE_URL}/guest/text-to-speech",
            data={
                "text": text,
                "voice_id": voice,
                "output_format": fmt,
                "speed": str(config.NOIZ_SPEED),
            },
            timeout=timeout,
        )
        if not resp.ok:
            root = config.NOIZ_BASE_URL
            if root.endswith("/v1"):
                root = root[:-3]
            resp = requests.post(
                f"{root}/api/v1/guest/text-to-speech",
                data={
                    "text": text,
                    "voice_id": voice,
                    "output_format": fmt,
                    "speed": str(config.NOIZ_SPEED),
                },
                timeout=timeout,
            )
            if not resp.ok:
                raise TTSError(f"Noiz guest TTS {resp.status_code}: {resp.text[:300]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() != ".mp3":
        out_path = out_path.with_suffix(".mp3")
    content = resp.content
    # Noiz sometimes returns HTTP 200 with JSON error bodies (e.g. 402 credits).
    ctype = (resp.headers.get("content-type") or "").lower()
    if "json" in ctype or content[:1] in (b"{", b"["):
        try:
            err = json.loads(content.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            err = {"raw": content[:200].decode("utf-8", errors="replace")}
        raise TTSError(f"Noiz TTS returned error payload: {err}")
    if len(content) < 500:
        raise TTSError(f"Noiz TTS returned tiny/invalid audio ({len(content)} bytes).")
    out_path.write_bytes(content)
    return out_path


def synthesize(text: str, out_path: Path, *, timeout: int = 120) -> Path:
    """Generate speech using ``TTS_PROVIDER`` (noiz | openai)."""
    provider = config.TTS_PROVIDER
    if provider == "noiz":
        try:
            return synthesize_noiz(text, out_path, timeout=timeout)
        except TTSError as exc:
            print(f"  Noiz TTS failed ({exc}); trying guest...", flush=True)
            prev_key = config.NOIZ_API_KEY
            try:
                # Temporarily force guest path when authenticated credits are gone.
                config.NOIZ_API_KEY = ""
                if config.NOIZ_ALLOW_GUEST:
                    return synthesize_noiz(text, out_path, timeout=timeout)
            except TTSError as guest_exc:
                print(f"  Noiz guest failed ({guest_exc}); falling back to OpenAI...", flush=True)
            finally:
                config.NOIZ_API_KEY = prev_key
            return synthesize_openai(text, out_path, timeout=timeout)
    if provider == "openai":
        return synthesize_openai(text, out_path, timeout=timeout)
    raise TTSError(f"Unsupported TTS_PROVIDER={provider!r} (use 'noiz' or 'openai').")


def transcribe(audio_path: Path, *, timeout: int = 120) -> tuple[float, list[Word]]:
    """Return (duration_seconds, words) for an audio file via OpenAI transcription."""
    api_key = config.require_openai()
    with audio_path.open("rb") as fh:
        resp = requests.post(
            f"{config.OPENAI_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, fh, "audio/mpeg")},
            data={
                "model": config.OPENAI_TRANSCRIBE_MODEL,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
            },
            timeout=timeout,
        )
    if not resp.ok:
        raise TTSError(f"OpenAI transcription {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    words = [
        Word(word=w.get("word", ""), start=float(w.get("start", 0)), end=float(w.get("end", 0)))
        for w in data.get("words", [])
    ]
    duration = float(data.get("duration") or (words[-1].end if words else 0.0))
    if duration <= 0:
        raise TTSError(f"Transcription returned zero duration for {audio_path.name}.")
    return duration, words


def voice_scene(text: str, out_path: Path) -> SceneAudio:
    """Synthesize + transcribe one scene, returning audio path, duration, words."""
    synthesize(text, out_path)
    duration, words = transcribe(out_path)
    return SceneAudio(
        path=out_path,
        duration=duration,
        words=words,
        provider=config.TTS_PROVIDER,
    )
