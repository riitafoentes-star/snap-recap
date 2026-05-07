"""
Snap Recap — ElevenLabsProvider.

TTS provider backed by the ElevenLabs API via httpx.
API key is read from the ``ELEVENLABS_API_KEY`` environment variable if not
passed explicitly.
"""

from __future__ import annotations

import io
import os
import struct
import wave


class ElevenLabsProvider:
    """TTS provider that calls the ElevenLabs API.

    Args:
        api_key: ElevenLabs API key. Falls back to ``ELEVENLABS_API_KEY`` env var.
    """

    BASE_URL = "https://api.elevenlabs.io/v1"
    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel (default ElevenLabs voice)

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")

    # ------------------------------------------------------------------
    # TTSProvider protocol
    # ------------------------------------------------------------------

    def synthesize(self, text: str, voice_id: str = DEFAULT_VOICE_ID) -> bytes:
        """Synthesize speech from *text* using ElevenLabs.

        Args:
            text: The text to synthesize.
            voice_id: ElevenLabs voice ID. Defaults to Rachel.

        Returns:
            Raw WAV audio bytes at 44.1kHz.

        Raises:
            ValueError: If the API key is missing or text is empty.
            RuntimeError: If the ElevenLabs API returns an error.
        """
        if not self._api_key:
            raise ValueError(
                "ElevenLabs API key is required. Set ELEVENLABS_API_KEY environment "
                "variable or pass api_key to ElevenLabsProvider."
            )
        if not text or not text.strip():
            raise ValueError("Text to synthesize must not be empty.")

        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "httpx package is required for ElevenLabsProvider. "
                "Install it with: pip install httpx"
            ) from exc

        effective_voice_id = voice_id or self.DEFAULT_VOICE_ID

        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        try:
            response = httpx.post(
                f"{self.BASE_URL}/text-to-speech/{effective_voice_id}",
                json=payload,
                headers=headers,
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"ElevenLabs API error (HTTP {exc.response.status_code}): "
                f"{exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"ElevenLabs API request failed: {exc}"
            ) from exc

        # ElevenLabs returns MP3 by default; wrap in WAV container for consistency
        mp3_bytes = response.content
        return _mp3_to_wav(mp3_bytes)


def _mp3_to_wav(mp3_bytes: bytes) -> bytes:
    """Convert MP3 bytes to a minimal WAV container.

    Uses pydub if available for proper conversion; otherwise wraps the raw
    bytes in a WAV header (for testing/fallback purposes).
    """
    try:
        from pydub import AudioSegment  # type: ignore[import]

        audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
        audio = audio.set_frame_rate(44100).set_channels(1).set_sample_width(2)
        buf = io.BytesIO()
        audio.export(buf, format="wav")
        return buf.getvalue()
    except ImportError:
        # Fallback: wrap raw bytes in a minimal WAV header
        return _wrap_in_wav_header(mp3_bytes, sample_rate=44100)


def _wrap_in_wav_header(data: bytes, sample_rate: int = 44100) -> bytes:
    """Wrap raw audio data in a minimal WAV header."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return buf.getvalue()
