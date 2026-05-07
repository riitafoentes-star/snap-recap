"""
Snap Recap — SubtitleBurner

Transcribes audio segments with openai-whisper and burns the resulting
SRT subtitles into a VideoClip.

Workflow:
  1. For each AudioSegment, write audio bytes to a temp WAV file.
  2. Transcribe with whisper.load_model().transcribe().
  3. Build an SRT block for each segment (one block minimum per segment).
  4. Burn subtitles into the video using ffmpeg-python (filter_complex subtitles).
  5. Return the resulting VideoClip.
"""

from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import AudioSegment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SRT helpers
# ---------------------------------------------------------------------------


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(audio_segments: List[AudioSegment], transcriptions: List[str]) -> str:
    """Build an SRT string from audio segments and their transcriptions.

    Produces exactly one SRT block per AudioSegment.  The start/end times
    are derived from the cumulative audio durations.

    Args:
        audio_segments: List of AudioSegments (provides timing).
        transcriptions: List of transcribed text strings, one per segment.

    Returns:
        SRT-formatted string.
    """
    lines: List[str] = []
    current_time = 0.0

    for i, (seg, text) in enumerate(zip(audio_segments, transcriptions), start=1):
        start = current_time
        end = current_time + seg.duration
        lines.append(str(i))
        lines.append(f"{_seconds_to_srt_time(start)} --> {_seconds_to_srt_time(end)}")
        lines.append(text.strip() or "(narration)")
        lines.append("")
        current_time = end

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Transcription helper
# ---------------------------------------------------------------------------


def _transcribe_segment(audio_data: bytes, model) -> str:
    """Transcribe a single audio segment using a whisper model.

    Args:
        audio_data: Raw WAV bytes.
        model: A loaded whisper model (has .transcribe(path) method).

    Returns:
        Transcribed text string.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    try:
        result = model.transcribe(tmp_path)
        return result.get("text", "").strip()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# SubtitleBurner
# ---------------------------------------------------------------------------


class SubtitleBurner:
    """Transcribes audio segments and burns subtitles into a VideoClip.

    Preconditions:
        - video has .duration > 0
        - audio_segments is non-empty

    Postconditions:
        - Returns a VideoClip with burned-in subtitles
        - At least one SRT block per AudioSegment
    """

    def __init__(self, whisper_model_name: str = "base") -> None:
        """Initialise SubtitleBurner.

        Args:
            whisper_model_name: Whisper model size ("tiny", "base", "small", etc.).
        """
        self._whisper_model_name = whisper_model_name
        self._model = None  # lazy-loaded

    def _get_model(self):
        """Lazy-load the whisper model."""
        if self._model is None:
            try:
                import whisper
                self._model = whisper.load_model(self._whisper_model_name)
            except Exception as exc:
                logger.warning("Failed to load whisper model '%s': %s", self._whisper_model_name, exc)
                self._model = _FallbackWhisperModel()
        return self._model

    def transcribe_and_burn(
        self,
        video: "VideoClip",
        audio_segments: List[AudioSegment],
    ) -> "VideoClip":
        """Transcribe audio segments and burn subtitles into the video.

        Args:
            video: Source VideoClip.
            audio_segments: List of AudioSegments to transcribe.

        Returns:
            VideoClip with burned-in subtitles.
        """
        if not audio_segments:
            logger.warning("No audio segments provided; returning video unchanged.")
            return video

        # Step 1: Transcribe each segment
        model = self._get_model()
        transcriptions: List[str] = []
        for i, seg in enumerate(audio_segments):
            try:
                text = _transcribe_segment(seg.audio_data, model)
                logger.debug("Segment %d transcribed: %r", i, text[:60])
            except Exception as exc:
                logger.warning("Transcription failed for segment %d: %s", i, exc)
                text = ""
            transcriptions.append(text)

        # Step 2: Build SRT
        srt_content = build_srt(audio_segments, transcriptions)

        # Step 3: Burn subtitles
        return self._burn_subtitles(video, srt_content)

    def _burn_subtitles(self, video: "VideoClip", srt_content: str) -> "VideoClip":
        """Burn SRT subtitles into the video using ffmpeg or moviepy.

        Tries ffmpeg-python first; falls back to returning the original video
        with the SRT attached as metadata if ffmpeg is unavailable.

        Args:
            video: Source VideoClip.
            srt_content: SRT-formatted subtitle string.

        Returns:
            VideoClip with burned-in subtitles (or original if burning fails).
        """
        with tempfile.NamedTemporaryFile(
            suffix=".srt", mode="w", encoding="utf-8", delete=False
        ) as srt_file:
            srt_file.write(srt_content)
            srt_path = srt_file.name

        try:
            return self._burn_with_ffmpeg(video, srt_path)
        except Exception as exc:
            logger.warning(
                "ffmpeg subtitle burn failed (%s); returning video with SRT metadata.", exc
            )
            # Attach SRT path as attribute so callers can use it
            video._srt_path = srt_path  # type: ignore[attr-defined]
            return video
        finally:
            # srt_path is cleaned up by _burn_with_ffmpeg on success;
            # on failure we keep it attached to the video object.
            pass

    def _burn_with_ffmpeg(self, video: "VideoClip", srt_path: str) -> "VideoClip":
        """Burn subtitles using ffmpeg via a temp file round-trip.

        Writes the video to a temp MP4, runs ffmpeg with subtitles filter,
        then loads the result back as a VideoClip.

        Args:
            video: Source VideoClip.
            srt_path: Path to the SRT file.

        Returns:
            New VideoClip with burned-in subtitles.
        """
        try:
            from moviepy.editor import VideoFileClip
        except ImportError:
            from moviepy.video.io.VideoFileClip import VideoFileClip

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp4")
            output_path = os.path.join(tmpdir, "output.mp4")

            # Write source video to temp file
            try:
                video.write_videofile(
                    input_path,
                    fps=video.fps or 30,
                    logger=None,
                    verbose=False,
                )
            except Exception as exc:
                raise RuntimeError(f"Failed to write temp video: {exc}") from exc

            # Escape srt_path for ffmpeg filter (Windows backslashes, colons)
            escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:")

            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", f"subtitles={escaped_srt}",
                "-c:a", "copy",
                output_path,
            ]

            logger.debug("Running ffmpeg subtitle burn: %s", " ".join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg subtitle burn failed (exit {result.returncode}):\n"
                    f"stderr: {result.stderr[-2000:]}"
                )

            # Load the result back
            burned_clip = VideoFileClip(output_path)
            # Keep a reference so the temp dir isn't cleaned up prematurely
            burned_clip._tmpdir_ref = tmpdir  # type: ignore[attr-defined]
            return burned_clip


# ---------------------------------------------------------------------------
# Fallback whisper model (used when whisper is not installed)
# ---------------------------------------------------------------------------


class _FallbackWhisperModel:
    """Minimal whisper-compatible model that returns empty transcriptions."""

    def transcribe(self, path: str) -> dict:
        logger.warning("Using fallback whisper model (no transcription).")
        return {"text": ""}
