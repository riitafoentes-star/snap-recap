"""
Snap Recap — VideoExporter

Exports a Timeline to MP4 (via ffmpeg-python) and/or .OTIOZ (via
opentimelineio).

MP4 export:
  - Builds an ffmpeg filter graph from the timeline clips.
  - On error: captures stderr, logs the full command, retries with a
    lower-quality preset.

OTIOZ export:
  - Serialises the timeline to OpenTimelineIO format.
  - Writes a compressed .otioz file.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import ExportConfig, Timeline, TimelineClip

logger = logging.getLogger(__name__)

# Quality presets ordered from highest to lowest
_QUALITY_PRESETS = ["slow", "medium", "fast", "veryfast", "ultrafast"]


# ---------------------------------------------------------------------------
# VideoExporter
# ---------------------------------------------------------------------------


class VideoExporter:
    """Exports a Timeline to MP4 and/or .OTIOZ.

    Preconditions:
        - timeline.clips is non-empty
        - output path's parent directory exists (or will be created)

    Postconditions:
        - export_mp4: returns a valid MP4 file path
        - export_otioz: returns a valid .otioz file path
    """

    # ------------------------------------------------------------------
    # MP4 export
    # ------------------------------------------------------------------

    def export_mp4(
        self,
        timeline: Timeline,
        output: Path,
        config: ExportConfig,
    ) -> Path:
        """Export the timeline as an MP4 file using ffmpeg-python.

        On ffmpeg error, captures stderr, logs the full command, and retries
        with progressively lower quality presets.

        Args:
            timeline: Assembled Timeline.
            output: Destination MP4 path.
            config: ExportConfig with fps, resolution, etc.

        Returns:
            Path to the exported MP4 file.

        Raises:
            RuntimeError: If all quality presets fail.
        """
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)

        for preset in _QUALITY_PRESETS:
            try:
                self._run_ffmpeg_export(timeline, output, config, preset)
                logger.info("MP4 export succeeded with preset '%s': %s", preset, output)
                return output
            except RuntimeError as exc:
                logger.warning(
                    "MP4 export failed with preset '%s': %s — trying lower quality.",
                    preset,
                    exc,
                )

        raise RuntimeError(
            f"MP4 export failed for all quality presets. Output: {output}"
        )

    def _run_ffmpeg_export(
        self,
        timeline: Timeline,
        output: Path,
        config: ExportConfig,
        preset: str,
    ) -> None:
        """Run the actual ffmpeg export for a given quality preset.

        Builds a concat filter from the timeline clips, writes each clip's
        image to a temp file, and invokes ffmpeg.

        Args:
            timeline: Assembled Timeline.
            output: Destination MP4 path.
            config: ExportConfig.
            preset: ffmpeg -preset value.

        Raises:
            RuntimeError: If ffmpeg exits with non-zero code.
        """
        import ffmpeg  # ffmpeg-python

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write each clip's image as a PNG and build ffmpeg inputs
            inputs = []
            durations = []

            for i, clip in enumerate(timeline.clips):
                import cv2
                import numpy as np

                img_path = os.path.join(tmpdir, f"clip_{i:04d}.png")
                # clip.panel.image is (H, W, 3) uint8 BGR
                cv2.imwrite(img_path, clip.panel.image)
                duration = clip.end_time - clip.start_time
                durations.append(duration)

                inp = ffmpeg.input(
                    img_path,
                    loop=1,
                    t=duration,
                    framerate=config.fps,
                )
                inputs.append(inp)

            if not inputs:
                raise RuntimeError("No clips to export.")

            w, h = config.resolution

            # Build concat filter
            if len(inputs) == 1:
                video_stream = inputs[0].video.filter(
                    "scale", w, h
                )
            else:
                scaled = [
                    inp.video.filter("scale", w, h) for inp in inputs
                ]
                video_stream = ffmpeg.concat(*scaled, v=1, a=0)

            # Add audio: concatenate audio files
            audio_inputs = []
            for i, clip in enumerate(timeline.clips):
                wav_path = os.path.join(tmpdir, f"audio_{i:04d}.wav")
                with open(wav_path, "wb") as f:
                    f.write(clip.audio.audio_data)
                audio_inputs.append(ffmpeg.input(wav_path).audio)

            if len(audio_inputs) == 1:
                audio_stream = audio_inputs[0]
            else:
                audio_stream = ffmpeg.concat(*audio_inputs, v=0, a=1)

            out = ffmpeg.output(
                video_stream,
                audio_stream,
                str(output),
                vcodec="libx264",
                acodec="aac",
                preset=preset,
                pix_fmt="yuv420p",
                r=config.fps,
            )

            cmd_args = ffmpeg.compile(out, overwrite_output=True)
            logger.debug("ffmpeg command: %s", " ".join(cmd_args))

            try:
                out.run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
            except ffmpeg.Error as exc:
                stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
                raise RuntimeError(
                    f"ffmpeg failed (preset={preset}):\n"
                    f"Command: {' '.join(cmd_args)}\n"
                    f"stderr: {stderr[-3000:]}"
                ) from exc

    # ------------------------------------------------------------------
    # OTIOZ export
    # ------------------------------------------------------------------

    def export_otioz(self, timeline: Timeline, output: Path) -> Path:
        """Export the timeline as an OpenTimelineIO .otioz file.

        Args:
            timeline: Assembled Timeline.
            output: Destination .otioz path.

        Returns:
            Path to the exported .otioz file.

        Raises:
            RuntimeError: If opentimelineio serialisation fails.
        """
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            import opentimelineio as otio
        except ImportError as exc:
            raise RuntimeError(
                "opentimelineio is not installed. "
                "Install it with: pip install opentimelineio"
            ) from exc

        otio_timeline = _build_otio_timeline(timeline)

        try:
            otio.adapters.write_to_file(otio_timeline, str(output))
            logger.info("OTIOZ export succeeded: %s", output)
        except Exception as exc:
            raise RuntimeError(f"OTIOZ export failed: {exc}") from exc

        return output


# ---------------------------------------------------------------------------
# OTIO helpers
# ---------------------------------------------------------------------------


def _build_otio_timeline(timeline: Timeline):
    """Build an opentimelineio Timeline from a Snap Recap Timeline.

    Args:
        timeline: Snap Recap Timeline.

    Returns:
        opentimelineio.schema.Timeline instance.
    """
    import opentimelineio as otio

    rate = float(timeline.fps)
    otio_track = otio.schema.Track(name="Video", kind=otio.schema.TrackKind.Video)

    for i, clip in enumerate(timeline.clips):
        duration_frames = (clip.end_time - clip.start_time) * rate
        time_range = otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, rate),
            duration=otio.opentime.RationalTime(duration_frames, rate),
        )
        otio_clip = otio.schema.Clip(
            name=f"clip_{i:04d}",
            source_range=time_range,
        )
        otio_track.append(otio_clip)

    otio_timeline = otio.schema.Timeline(name="SnapRecap")
    otio_timeline.tracks.append(otio_track)
    return otio_timeline
