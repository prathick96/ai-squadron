"""
packages/tools/elevenlabs_client.py
ElevenLabs TTS client — async voice synthesis for the Media pipeline.

When ELEVENLABS_API_KEY is set: calls the real API and writes an MP3 to disk.
When unset: callers fall back to a mock voice_package (no error raised here).

Docs: https://elevenlabs.io/docs/api-reference/text-to-speech
"""
from __future__ import annotations

import os
from pathlib import Path

_BASE_URL = "https://api.elevenlabs.io/v1"

# Rachel (voice ID stable across ElevenLabs public catalog)
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_MODEL = "eleven_multilingual_v2"

# MP3 at 128 kbps ≈ 16 KB/sec — used to estimate duration from byte count
_BYTES_PER_SEC = 16_000


def elevenlabs_available() -> bool:
    """True when ELEVENLABS_API_KEY is configured (not a placeholder)."""
    key = os.getenv("ELEVENLABS_API_KEY", "")
    return bool(key and len(key) > 10 and not key.startswith("your_"))


async def synthesize_speech(
    text: str,
    output_path: Path,
    voice_id: str = DEFAULT_VOICE_ID,
    model: str = DEFAULT_MODEL,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
) -> float:
    """
    Synthesize speech from text and write an MP3 to output_path.

    Returns estimated duration_sec (derived from file size at 128 kbps).
    Raises RuntimeError on API errors so callers can decide to fall back.
    """
    import httpx

    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{_BASE_URL}/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": model,
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                },
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"ElevenLabs {resp.status_code}: {resp.text[:200]}"
            )
        audio_bytes = resp.content

    output_path.write_bytes(audio_bytes)
    return round(len(audio_bytes) / _BYTES_PER_SEC, 1)
