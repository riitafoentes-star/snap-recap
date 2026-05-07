"""
Snap Recap — VoiceGenerator

Synthesises audio for each ScriptSegment using a TTSProvider.
Returns a list of AudioSegments in WAV 44.1kHz format.
"""

from __future__ import annotations

import io
import logging
import struct
import sys
import os
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import List

from models import AudioSegment, IntelligenceConfig, Script, ScriptSegment
from providers.base import TTSProvider

logger = logging.getLogger(__name__)


def _parse_wav_duration(wav_bytes: bytes) -> tuple[float, int]:
    """Parse WAV bytes and return (duration_seconds, sample_rate).

    Falls back to (0.0, 44100) if the bytes are not a valid WAV file.
    """
    try:
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            n_frames = wf.getnframes()
            sample_rate = wf.getframerate()
            if sample_rate > 0:
                duration = n_frames / sample_rate
            else:
                duration = 0.0
            return duration, sample_rate
    except Exception:
        # Not a valid WAV — estimate from byte length assuming 44100 Hz, 16-bit mono
        sample_rate = 44100
        bytes_per_sample = 2  # 16-bit
        n_channels = 1
        n_samples = len(wav_bytes) / (bytes_per_sample * n_channels)
        duration = n_samples / sample_rate
        return duration, sample_rate


def _ensure_wav_44100(wav_bytes: bytes) -> bytes:
    """Ensure the WAV bytes are at 44.1kHz.  Re-encodes if necessary.

    If the input is not a valid WAV or already at 44100 Hz, returns it
    unchanged (or wrapped in a minimal WAV header).
    """
    try:
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            sample_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())

        if sample_rate == 44100:
            return wav_bytes

        # Simple linear resampling to 44100 Hz
        import numpy as np

        dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
        dtype = dtype_map.get(sampwidth, np.int16)
        audio = np.frombuffer(frames, dtype=dtype)

        if n_channels > 1:
            audio = audio.reshape(-1, n_channels)

        # Resample
        ratio = 44100 / sample_rate
        new_length = int(len(audio) * ratio)
        indices = np.linspace(0, len(audio) - 1, new_length)
        resampled = np.interp(indices, np.arange(len(audio)), audio.astype(np.float64)).astype(dtype)

        out_buf = io.BytesIO()
        with wave.open(out_buf, "wb") as wf_out:
            wf_out.setnchannels(n_channels)
            wf_out.setsampwidth(sampwidth)
            wf_out.setframerate(44100)
            wf_out.writeframes(resampled.tobytes())
        return out_buf.getvalue()

    except Exception:
        # Cannot parse — wrap raw bytes in a WAV header at 44100 Hz
        out_buf = io.BytesIO()
        with wave.open(out_buf, "wb") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(44100)
            wf_out.writeframes(wav_bytes)
        return out_buf.getvalue()


class VoiceGenerator:
    """Synthesises audio for each ScriptSegment using a TTSProvider.

    Args:
        config: IntelligenceConfig with tts_voice_id and other settings.
    """

    def __init__(self, config: IntelligenceConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def synthesize(self, script: Script, provider: TTSProvider) -> List[AudioSegment]:
        """Synthesise audio for every segment in *script*.

        For each ScriptSegment:
        1. Call ``provider.synthesize(segment.narration, config.tts_voice_id)``.
        2. Parse the returned WAV bytes to get the actual duration.
        3. Ensure the audio is in WAV 44.1kHz format.

        Args:
            script: Script produced by ScriptGenerator.
            provider: TTSProvider to use for synthesis.

        Returns:
            List of AudioSegments with ``len == len(script.segments)``.

        Raises:
            RuntimeError: If the provider fails for any segment, with context
                about which segment caused the failure.
        """
        audio_segments: List[AudioSegment] = []

        for i, segment in enumerate(script.segments):
            try:
                raw_bytes = provider.synthesize(
                    segment.narration,
                    self._config.tts_voice_id,
                )
            except Exception as exc:
                msg = (
                    f"TTS provider failed for segment {i} "
                    f"(panel_index={segment.panel_index}, "
                    f"narration={segment.narration!r}): {exc}"
                )
                logger.error(msg)
                raise RuntimeError(msg) from exc

            # Ensure WAV 44.1kHz
            wav_bytes = _ensure_wav_44100(raw_bytes)

            # Parse actual duration
            duration, sample_rate = _parse_wav_duration(wav_bytes)

            audio_segments.append(AudioSegment(
                panel_index=segment.panel_index,
                audio_data=wav_bytes,
                duration=duration,
                sample_rate=sample_rate,
            ))

        return audio_segments
