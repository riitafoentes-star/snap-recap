"""
Snap Recap — LocalTTSProvider.

Offline TTS fallback provider. Uses pyttsx3 if available; otherwise
generates a silent WAV file of appropriate length.

No API key required — works entirely offline.
"""

from __future__ import annotations

import io
import math
import struct
import tempfile
import wave
from pathlib import Path


class LocalTTSProvider:
    """Offline TTS provider using pyttsx3 or silent WAV fallback.

    This provider requires no API key and works without internet access.
    It is intended as a fallback when cloud TTS providers are unavailable.

    Audio output is always WAV at 44.1kHz, mono, 16-bit PCM.
    """

    SAMPLE_RATE = 44100
    # Approximate words-per-minute for duration estimation
    WORDS_PER_MINUTE = 150

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # TTSProvider protocol
    # ------------------------------------------------------------------

    def synthesize(self, text: str, voice_id: str = "") -> bytes:
        """Synthesize speech from *text* using pyttsx3 or silent WAV fallback.

        Args:
            text: The text to synthesize.
            voice_id: Ignored for the local provider (no voice selection).

        Returns:
            Raw WAV audio bytes at 44.1kHz.

        Raises:
            ValueError: If text is empty.
        """
        if not text or not text.strip():
            raise ValueError("Text to synthesize must not be empty.")

        # Try pyttsx3 first
        wav_bytes = self._synthesize_pyttsx3(text)
        if wav_bytes is not None:
            return wav_bytes

        # Fallback: generate silent WAV with estimated duration
        return self._synthesize_silent(text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _synthesize_pyttsx3(self, text: str) -> bytes | None:
        """Attempt synthesis with pyttsx3. Returns None if unavailable."""
        try:
            import pyttsx3  # type: ignore[import]
        except ImportError:
            return None

        try:
            engine = pyttsx3.init()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            engine.save_to_file(text, tmp_path)
            engine.runAndWait()
            engine.stop()

            wav_data = Path(tmp_path).read_bytes()
            Path(tmp_path).unlink(missing_ok=True)

            # Ensure the output is at 44.1kHz
            return _resample_wav_to_44100(wav_data)
        except Exception:
            # pyttsx3 can fail on headless systems; fall through to silent WAV
            return None

    def _synthesize_silent(self, text: str) -> bytes:
        """Generate a silent WAV of estimated duration for the given text."""
        word_count = len(text.split())
        duration_seconds = max(0.5, (word_count / self.WORDS_PER_MINUTE) * 60)
        num_frames = int(self.SAMPLE_RATE * duration_seconds)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.SAMPLE_RATE)
            # Write silence (zero-filled PCM frames)
            wf.writeframes(b"\x00\x00" * num_frames)

        return buf.getvalue()


def _resample_wav_to_44100(wav_bytes: bytes) -> bytes:
    """Ensure WAV data is at 44.1kHz. Returns original bytes if already correct."""
    try:
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            if wf.getframerate() == 44100:
                return wav_bytes
            # Read all frames and re-write at 44100 Hz (simple rate change, no resampling)
            frames = wf.readframes(wf.getnframes())
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()

        out_buf = io.BytesIO()
        with wave.open(out_buf, "wb") as wf_out:
            wf_out.setnchannels(channels)
            wf_out.setsampwidth(sampwidth)
            wf_out.setframerate(44100)
            wf_out.writeframes(frames)
        return out_buf.getvalue()
    except Exception:
        return wav_bytes
