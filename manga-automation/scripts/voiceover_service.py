#!/usr/bin/env python3
"""
Voiceover synthesis service with pluggable providers:
- elevenlabs (cloud)
- kokoro (local via kokoro-js runner)
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import requests

from scripts.utils.logger import setup_logger

logger = setup_logger("voiceover_service")

DEFAULT_PROVIDER = os.environ.get("VOICE_PROVIDER", "elevenlabs").lower()
OUTPUT_DIR = os.environ.get("VOICEOVER_DIR", "/data/voiceovers")


def _ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def _safe_filename(prefix: str, ext: str) -> str:
    import time

    return f"{prefix}_{int(time.time() * 1000)}.{ext}"


def synthesize_elevenlabs(
    text: str,
    voice_id: str | None = None,
    model_id: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return {"success": False, "error": "ELEVENLABS_API_KEY not set"}

    selected_voice = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "")
    if not selected_voice:
        return {"success": False, "error": "ELEVENLABS_VOICE_ID missing (or pass voice_id)"}

    selected_model = model_id or os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    _ensure_dir(OUTPUT_DIR)
    output_path = output_path or str(Path(OUTPUT_DIR) / _safe_filename("voiceover_elevenlabs", "mp3"))

    endpoint = f"https://api.elevenlabs.io/v1/text-to-speech/{selected_voice}/stream"
    payload = {
        "text": text,
        "model_id": selected_model,
        "voice_settings": {
            "stability": float(os.environ.get("ELEVENLABS_STABILITY", "0.5")),
            "similarity_boost": float(os.environ.get("ELEVENLABS_SIMILARITY_BOOST", "0.75")),
        },
    }
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    try:
        r = requests.post(endpoint, headers=headers, json=payload, timeout=90)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(r.content)
        return {
            "success": True,
            "provider": "elevenlabs",
            "model_id": selected_model,
            "voice_id": selected_voice,
            "output_path": output_path,
            "bytes": len(r.content),
        }
    except Exception as exc:
        return {"success": False, "provider": "elevenlabs", "error": str(exc)}


def synthesize_kokoro(
    text: str,
    voice: str | None = None,
    dtype: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    _ensure_dir(OUTPUT_DIR)
    output_path = output_path or str(Path(OUTPUT_DIR) / _safe_filename("voiceover_kokoro", "wav"))
    runner = os.environ.get("KOKORO_RUNNER_PATH", "/app/scripts/kokoro_tts_runner.mjs")
    selected_voice = voice or os.environ.get("KOKORO_VOICE", "af_sky")
    selected_dtype = dtype or os.environ.get("KOKORO_DTYPE", "q8")
    model_id = os.environ.get("KOKORO_MODEL_ID", "onnx-community/Kokoro-82M-v1.0-ONNX")
    node_bin = os.environ.get("NODE_BIN", "node")

    cmd = [
        node_bin,
        runner,
        "--text",
        text,
        "--output",
        output_path,
        "--voice",
        selected_voice,
        "--dtype",
        selected_dtype,
        "--model",
        model_id,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return {
                "success": False,
                "provider": "kokoro",
                "error": proc.stderr.strip() or proc.stdout.strip() or f"kokoro runner exit {proc.returncode}",
            }
        payload = {}
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except Exception:
                payload = {"raw_stdout": proc.stdout.strip()}
        return {
            "success": True,
            "provider": "kokoro",
            "voice": selected_voice,
            "dtype": selected_dtype,
            "output_path": output_path,
            **payload,
        }
    except Exception as exc:
        return {"success": False, "provider": "kokoro", "error": str(exc)}


def synthesize(
    text: str,
    provider: str | None = None,
    voice_id: str | None = None,
    model_id: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    selected = (provider or DEFAULT_PROVIDER).lower()
    if not text or not text.strip():
        return {"success": False, "error": "text is required"}

    if selected == "elevenlabs":
        result = synthesize_elevenlabs(text=text, voice_id=voice_id, model_id=model_id, output_path=output_path)
        if result.get("success"):
            return result
        # fallback to kokoro when configured or requested by policy
        if os.environ.get("VOICE_ENABLE_FALLBACK", "true").lower() in {"1", "true", "yes"}:
            logger.warning(f"ElevenLabs failed, falling back to Kokoro: {result.get('error')}")
            fallback = synthesize_kokoro(text=text, output_path=output_path)
            fallback["fallback_from"] = "elevenlabs"
            return fallback
        return result

    if selected in {"kokoro", "kokoro-js"}:
        return synthesize_kokoro(text=text, output_path=output_path)

    return {"success": False, "error": f"Unsupported provider: {selected}"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--voice-id", default="")
    parser.add_argument("--model-id", default="")
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()

    out = synthesize(
        text=args.text,
        provider=args.provider,
        voice_id=args.voice_id or None,
        model_id=args.model_id or None,
        output_path=args.output_path or None,
    )
    print(json.dumps(out, ensure_ascii=False))
