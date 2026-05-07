"""
Tests for the Production pipeline components.

Covers:
- Unit tests for TimelineAssembler
- Unit tests for MotionEngine (Ken Burns interpolation)
- Property 13: Timeline has one clip per panel (hypothesis)
- Property 14: Clips don't overlap (hypothesis)
- Property 15: Total duration consistent (hypothesis)
- Property 16: Ken Burns zoom in range (hypothesis)
- Integration test for ProductionPhase with mocks
"""

from __future__ import annotations

import io
import os
import sys
import wave
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    AudioSegment,
    BoundingBox,
    CroppedPanel,
    ExportConfig,
    KenBurnsParams,
    Panel,
    ProductionAssets,
    ProductionConfig,
    Script,
    ScriptSegment,
    Timeline,
    TimelineClip,
    UpscaledImage,
    VideoArtifact,
)
from pipeline.production.motion_engine import (
    MotionEngine,
    _apply_ken_burns_frame,
    compute_ken_burns_zoom,
    ease_in_out_cubic,
    _lerp,
)
from pipeline.production.timeline_assembler import TimelineAssembler, _generate_ken_burns_params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 44100) -> bytes:
    """Create minimal valid WAV bytes for the given duration."""
    n_frames = int(duration_seconds * sample_rate)
    samples = np.zeros(n_frames, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def make_upscaled_image(
    width: int = 1920,
    height: int = 1080,
    panel_index: int = 0,
) -> UpscaledImage:
    """Create a minimal UpscaledImage."""
    image = np.full((height, width, 3), 128, dtype=np.uint8)
    bbox = BoundingBox(x=0, y=0, width=width, height=height)
    panel = Panel(
        page_index=0,
        panel_index=panel_index,
        bbox=bbox,
        art_region=image.copy(),
        bubble_regions=[],
        raw_image=image.copy(),
    )
    cropped = CroppedPanel(image=image.copy(), source_panel=panel, scale_factor=1.0)
    return UpscaledImage(image=image, source_panel=cropped, scale_factor=1.0)


def make_audio_segment(duration: float = 2.0, panel_index: int = 0) -> AudioSegment:
    """Create a minimal AudioSegment."""
    return AudioSegment(
        panel_index=panel_index,
        audio_data=make_wav_bytes(duration),
        duration=duration,
        sample_rate=44100,
    )


def make_script(n: int, duration_hint: float = 2.0) -> Script:
    """Create a Script with n segments."""
    segments = [
        ScriptSegment(
            panel_index=i,
            narration=f"Narration for panel {i}.",
            duration_hint=duration_hint,
            emotion="neutral",
        )
        for i in range(n)
    ]
    return Script(segments=segments, total_duration_estimate=n * duration_hint)


def make_production_assets(n: int, audio_duration: float = 2.0) -> ProductionAssets:
    """Create a ProductionAssets bundle with n panels."""
    panels = [make_upscaled_image(panel_index=i) for i in range(n)]
    audio = [make_audio_segment(duration=audio_duration, panel_index=i) for i in range(n)]
    script = make_script(n, duration_hint=audio_duration)
    return ProductionAssets(upscaled=panels, audio_segments=audio, script=script)


def make_ken_burns_params(
    start_zoom: float = 1.0,
    end_zoom: float = 1.1,
    easing: str = "linear",
) -> KenBurnsParams:
    """Create KenBurnsParams with sensible defaults."""
    return KenBurnsParams(
        start_zoom=start_zoom,
        end_zoom=end_zoom,
        start_pan=(0.5, 0.5),
        end_pan=(0.5, 0.5),
        easing=easing,
    )


def make_mock_image_clip(
    width: int = 1920,
    height: int = 1080,
    duration: float = 2.0,
    fps: int = 30,
) -> MagicMock:
    """Create a mock ImageClip compatible with MotionEngine."""
    clip = MagicMock()
    clip.duration = duration
    clip.fps = fps
    clip.size = (width, height)
    # get_frame returns a solid-colour RGB frame
    frame = np.full((height, width, 3), 128, dtype=np.uint8)
    clip.get_frame.return_value = frame
    return clip


# ---------------------------------------------------------------------------
# Unit tests: TimelineAssembler
# ---------------------------------------------------------------------------


class TestTimelineAssembler:
    """Unit tests for TimelineAssembler."""

    def test_returns_correct_clip_count(self):
        """assemble() returns a Timeline with len(panels) clips."""
        n = 5
        assets = make_production_assets(n)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
        assert len(timeline.clips) == n

    def test_no_overlaps(self):
        """Consecutive clips must not overlap: clip[i].end_time == clip[i+1].start_time."""
        n = 4
        assets = make_production_assets(n)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)

        for i in range(len(timeline.clips) - 1):
            assert abs(timeline.clips[i].end_time - timeline.clips[i + 1].start_time) < 1e-9, (
                f"Overlap between clip {i} and {i + 1}: "
                f"end={timeline.clips[i].end_time}, start={timeline.clips[i + 1].start_time}"
            )

    def test_total_duration_equals_sum_of_audio(self):
        """total_duration == sum(a.duration for a in audio)."""
        n = 3
        durations = [1.5, 2.0, 3.0]
        panels = [make_upscaled_image(panel_index=i) for i in range(n)]
        audio = [make_audio_segment(duration=d, panel_index=i) for i, d in enumerate(durations)]
        script = make_script(n)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(panels, audio, script)

        expected = sum(durations)
        assert abs(timeline.total_duration - expected) < 1e-9

    def test_fps_is_30(self):
        """Timeline.fps must be 30."""
        assets = make_production_assets(2)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
        assert timeline.fps == 30

    def test_resolution_is_1920x1080(self):
        """Timeline.resolution must be (1920, 1080)."""
        assets = make_production_assets(2)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
        assert timeline.resolution == (1920, 1080)

    def test_first_clip_starts_at_zero(self):
        """First clip must start at time 0."""
        assets = make_production_assets(3)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
        assert timeline.clips[0].start_time == 0.0

    def test_mismatched_lengths_raises_value_error(self):
        """assemble() raises ValueError when lengths don't match."""
        panels = [make_upscaled_image(panel_index=i) for i in range(3)]
        audio = [make_audio_segment(panel_index=i) for i in range(2)]  # mismatch
        script = make_script(3)
        assembler = TimelineAssembler()
        with pytest.raises(ValueError, match="same length"):
            assembler.assemble(panels, audio, script)

    def test_single_panel(self):
        """assemble() works with a single panel."""
        assets = make_production_assets(1)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
        assert len(timeline.clips) == 1
        assert timeline.clips[0].start_time == 0.0
        assert abs(timeline.clips[0].end_time - assets.audio_segments[0].duration) < 1e-9

    def test_ken_burns_params_generated(self):
        """Each clip must have KenBurnsParams with valid zoom range."""
        assets = make_production_assets(3)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
        for clip in timeline.clips:
            assert clip.ken_burns is not None
            assert 1.0 <= clip.ken_burns.start_zoom <= clip.ken_burns.end_zoom <= 2.0

    def test_clip_references_correct_panel_and_audio(self):
        """Each clip must reference the correct panel and audio segment."""
        n = 3
        assets = make_production_assets(n)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
        for i, clip in enumerate(timeline.clips):
            assert clip.panel is assets.upscaled[i]
            assert clip.audio is assets.audio_segments[i]


# ---------------------------------------------------------------------------
# Unit tests: MotionEngine (Ken Burns interpolation)
# ---------------------------------------------------------------------------


class TestMotionEngine:
    """Unit tests for MotionEngine Ken Burns interpolation."""

    def test_ease_in_out_cubic_at_zero(self):
        """ease_in_out_cubic(0) == 0."""
        assert ease_in_out_cubic(0.0) == pytest.approx(0.0)

    def test_ease_in_out_cubic_at_one(self):
        """ease_in_out_cubic(1) == 1."""
        assert ease_in_out_cubic(1.0) == pytest.approx(1.0)

    def test_ease_in_out_cubic_at_half(self):
        """ease_in_out_cubic(0.5) == 0.5 (symmetric midpoint)."""
        assert ease_in_out_cubic(0.5) == pytest.approx(0.5)

    def test_ease_in_out_cubic_monotone(self):
        """ease_in_out_cubic is monotonically non-decreasing."""
        values = [ease_in_out_cubic(t / 100) for t in range(101)]
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1] + 1e-12

    def test_lerp_at_zero(self):
        """_lerp(a, b, 0) == a."""
        assert _lerp(1.0, 2.0, 0.0) == pytest.approx(1.0)

    def test_lerp_at_one(self):
        """_lerp(a, b, 1) == b."""
        assert _lerp(1.0, 2.0, 1.0) == pytest.approx(2.0)

    def test_lerp_at_half(self):
        """_lerp(a, b, 0.5) == (a + b) / 2."""
        assert _lerp(1.0, 2.0, 0.5) == pytest.approx(1.5)

    def test_compute_zoom_at_start(self):
        """Zoom at t=0 equals start_zoom."""
        params = make_ken_burns_params(start_zoom=1.0, end_zoom=1.15)
        zoom = compute_ken_burns_zoom(params, t=0.0, duration=2.0)
        assert zoom == pytest.approx(1.0)

    def test_compute_zoom_at_end(self):
        """Zoom at t=duration equals end_zoom."""
        params = make_ken_burns_params(start_zoom=1.0, end_zoom=1.15)
        zoom = compute_ken_burns_zoom(params, t=2.0, duration=2.0)
        assert zoom == pytest.approx(1.15)

    def test_compute_zoom_in_range(self):
        """Zoom at any t is within [start_zoom, end_zoom]."""
        params = make_ken_burns_params(start_zoom=1.0, end_zoom=1.15)
        for i in range(21):
            t = i * 0.1
            zoom = compute_ken_burns_zoom(params, t=t, duration=2.0)
            assert params.start_zoom <= zoom <= params.end_zoom + 1e-9

    def test_compute_zoom_ease_in_out(self):
        """Zoom with ease_in_out easing is within [start_zoom, end_zoom]."""
        params = make_ken_burns_params(start_zoom=1.0, end_zoom=1.1, easing="ease_in_out")
        for i in range(21):
            t = i * 0.1
            zoom = compute_ken_burns_zoom(params, t=t, duration=2.0)
            assert params.start_zoom <= zoom <= params.end_zoom + 1e-9

    def test_apply_ken_burns_frame_returns_correct_shape(self):
        """_apply_ken_burns_frame returns a frame with the same shape as input."""
        clip = make_mock_image_clip(width=1920, height=1080, duration=2.0)
        params = make_ken_burns_params()
        frame = _apply_ken_burns_frame(clip, params, t=1.0, duration=2.0)
        assert frame.shape == (1080, 1920, 3)

    def test_apply_ken_burns_frame_dtype_uint8(self):
        """_apply_ken_burns_frame returns uint8 array."""
        clip = make_mock_image_clip()
        params = make_ken_burns_params()
        frame = _apply_ken_burns_frame(clip, params, t=0.5, duration=2.0)
        assert frame.dtype == np.uint8

    def test_apply_ken_burns_frame_at_t0(self):
        """Frame at t=0 is valid (no crash, correct shape)."""
        clip = make_mock_image_clip()
        params = make_ken_burns_params()
        frame = _apply_ken_burns_frame(clip, params, t=0.0, duration=2.0)
        assert frame.shape == (1080, 1920, 3)

    def test_apply_ken_burns_frame_at_end(self):
        """Frame at t=duration is valid."""
        clip = make_mock_image_clip()
        params = make_ken_burns_params()
        frame = _apply_ken_burns_frame(clip, params, t=2.0, duration=2.0)
        assert frame.shape == (1080, 1920, 3)

    def test_generate_ken_burns_params_zoom_range(self):
        """_generate_ken_burns_params produces zoom in [1.0, 1.15]."""
        import random
        rng = random.Random(42)
        for _ in range(50):
            params = _generate_ken_burns_params(rng=rng)
            assert params.start_zoom == 1.0
            assert 1.0 <= params.end_zoom <= 1.15 + 1e-9

    def test_generate_ken_burns_params_pan_range(self):
        """_generate_ken_burns_params produces pan values in [0, 1]."""
        import random
        rng = random.Random(99)
        for _ in range(50):
            params = _generate_ken_burns_params(rng=rng)
            for val in [*params.start_pan, *params.end_pan]:
                assert 0.0 <= val <= 1.0


# ---------------------------------------------------------------------------
# Property 13: Timeline has one clip per panel
# **Validates: Requirements 8.1**
# ---------------------------------------------------------------------------


@given(n_panels=st.integers(min_value=1, max_value=20))
@settings(max_examples=50)
def test_property13_timeline_has_one_clip_per_panel(n_panels):
    """
    **Validates: Requirements 8.1**

    Property 13: For any set of UpscaledImages, AudioSegments, and Script
    with the same number of elements, the Timeline returned by
    TimelineAssembler has exactly len(panels) TimelineClips.
    """
    assets = make_production_assets(n_panels)
    assembler = TimelineAssembler()
    timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)

    assert len(timeline.clips) == n_panels, (
        f"Expected {n_panels} clips, got {len(timeline.clips)}"
    )


# ---------------------------------------------------------------------------
# Property 14: Clips don't overlap
# **Validates: Requirements 8.2**
# ---------------------------------------------------------------------------


@given(
    n_panels=st.integers(min_value=2, max_value=15),
    duration=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_property14_clips_dont_overlap(n_panels, duration):
    """
    **Validates: Requirements 8.2**

    Property 14: For any assembled Timeline, no pair of TimelineClips
    has temporal overlap (clip[i].end_time <= clip[i+1].start_time).
    """
    panels = [make_upscaled_image(panel_index=i) for i in range(n_panels)]
    audio = [make_audio_segment(duration=duration, panel_index=i) for i in range(n_panels)]
    script = make_script(n_panels, duration_hint=duration)

    assembler = TimelineAssembler()
    timeline = assembler.assemble(panels, audio, script)

    for i in range(len(timeline.clips) - 1):
        end_i = timeline.clips[i].end_time
        start_next = timeline.clips[i + 1].start_time
        assert end_i <= start_next + 1e-9, (
            f"Overlap between clip {i} (end={end_i}) and clip {i+1} (start={start_next})"
        )


# ---------------------------------------------------------------------------
# Property 15: Total duration consistent
# **Validates: Requirements 8.3**
# ---------------------------------------------------------------------------


@given(
    durations=st.lists(
        st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=15,
    )
)
@settings(max_examples=50)
def test_property15_total_duration_consistent(durations):
    """
    **Validates: Requirements 8.3**

    Property 15: For any assembled Timeline, total_duration equals the
    sum of all AudioSegment durations.
    """
    n = len(durations)
    panels = [make_upscaled_image(panel_index=i) for i in range(n)]
    audio = [make_audio_segment(duration=d, panel_index=i) for i, d in enumerate(durations)]
    script = make_script(n)

    assembler = TimelineAssembler()
    timeline = assembler.assemble(panels, audio, script)

    expected = sum(durations)
    assert abs(timeline.total_duration - expected) < 1e-6, (
        f"total_duration={timeline.total_duration}, expected={expected}"
    )


# ---------------------------------------------------------------------------
# Property 16: Ken Burns zoom in range
# **Validates: Requirements 8.4, 8.5**
# ---------------------------------------------------------------------------


@given(
    start_zoom=st.floats(min_value=1.0, max_value=1.5, allow_nan=False, allow_infinity=False),
    end_zoom_delta=st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
    duration=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    easing=st.sampled_from(["linear", "ease_in_out"]),
    n_frames=st.integers(min_value=1, max_value=30),
)
@settings(max_examples=100)
def test_property16_ken_burns_zoom_in_range(
    start_zoom, end_zoom_delta, duration, easing, n_frames
):
    """
    **Validates: Requirements 8.4, 8.5**

    Property 16: For any KenBurnsParams with 1.0 <= start_zoom <= end_zoom <= 2.0,
    the zoom value at every frame is within [start_zoom, end_zoom].
    """
    end_zoom = min(start_zoom + end_zoom_delta, 2.0)
    params = KenBurnsParams(
        start_zoom=start_zoom,
        end_zoom=end_zoom,
        start_pan=(0.5, 0.5),
        end_pan=(0.5, 0.5),
        easing=easing,
    )

    for i in range(n_frames + 1):
        t = (i / n_frames) * duration
        zoom = compute_ken_burns_zoom(params, t=t, duration=duration)
        assert start_zoom - 1e-9 <= zoom <= end_zoom + 1e-9, (
            f"Zoom {zoom} out of range [{start_zoom}, {end_zoom}] at t={t}"
        )


# ---------------------------------------------------------------------------
# Integration test: ProductionPhase with mocks
# ---------------------------------------------------------------------------


class TestProductionPhaseIntegration:
    """Integration tests for ProductionPhase using mocks for heavy dependencies."""

    def _make_mock_timeline_assembler(self, n: int, duration: float = 2.0):
        """Return a mock TimelineAssembler that produces a valid Timeline."""
        assets = make_production_assets(n, audio_duration=duration)
        assembler = TimelineAssembler()
        timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
        mock = MagicMock()
        mock.assemble.return_value = timeline
        return mock, timeline

    def test_run_returns_video_artifact(self, tmp_path):
        """ProductionPhase.run returns a VideoArtifact."""
        n = 2
        assets = make_production_assets(n)
        config = ProductionConfig(
            fps=30,
            resolution=(1920, 1080),
            export_format="mp4",
            upload_youtube=False,
        )

        # Mock all heavy components
        with (
            patch("pipeline.production.phase.TimelineAssembler") as MockAssembler,
            patch("pipeline.production.phase.MotionEngine") as MockMotion,
            patch("pipeline.production.phase.SubtitleBurner") as MockBurner,
            patch("pipeline.production.phase.VideoExporter") as MockExporter,
        ):
            # Set up mock timeline
            mock_assembler_inst = MagicMock()
            MockAssembler.return_value = mock_assembler_inst
            assembler = TimelineAssembler()
            timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
            mock_assembler_inst.assemble.return_value = timeline

            # Mock motion engine to return a mock video clip
            mock_motion_inst = MagicMock()
            MockMotion.return_value = mock_motion_inst
            mock_video_clip = MagicMock()
            mock_video_clip.duration = timeline.total_duration

            # Mock _apply_ken_burns_to_timeline
            from pipeline.production.phase import ProductionPhase
            phase = ProductionPhase(output_dir=tmp_path)
            phase._apply_ken_burns_to_timeline = MagicMock(return_value=mock_video_clip)

            # Mock subtitle burner
            mock_burner_inst = MagicMock()
            MockBurner.return_value = mock_burner_inst
            mock_burner_inst.transcribe_and_burn.return_value = mock_video_clip

            # Mock exporter
            mock_exporter_inst = MagicMock()
            MockExporter.return_value = mock_exporter_inst
            mp4_path = tmp_path / "output.mp4"
            mp4_path.touch()
            mock_exporter_inst.export_mp4.return_value = mp4_path

            result = phase.run(assets, config)

        assert isinstance(result, VideoArtifact)

    def test_run_mp4_export_called(self, tmp_path):
        """ProductionPhase calls VideoExporter.export_mp4 for mp4 format."""
        n = 2
        assets = make_production_assets(n)
        config = ProductionConfig(
            fps=30,
            resolution=(1920, 1080),
            export_format="mp4",
            upload_youtube=False,
        )

        with (
            patch("pipeline.production.phase.TimelineAssembler") as MockAssembler,
            patch("pipeline.production.phase.MotionEngine"),
            patch("pipeline.production.phase.SubtitleBurner") as MockBurner,
            patch("pipeline.production.phase.VideoExporter") as MockExporter,
        ):
            assembler = TimelineAssembler()
            timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
            MockAssembler.return_value.assemble.return_value = timeline

            mock_video_clip = MagicMock()
            MockBurner.return_value.transcribe_and_burn.return_value = mock_video_clip

            mp4_path = tmp_path / "output.mp4"
            mp4_path.touch()
            MockExporter.return_value.export_mp4.return_value = mp4_path

            from pipeline.production.phase import ProductionPhase
            phase = ProductionPhase(output_dir=tmp_path)
            phase._apply_ken_burns_to_timeline = MagicMock(return_value=mock_video_clip)

            result = phase.run(assets, config)

        MockExporter.return_value.export_mp4.assert_called_once()
        assert mp4_path in result.output_files

    def test_run_otioz_export_called(self, tmp_path):
        """ProductionPhase calls VideoExporter.export_otioz for otioz format."""
        n = 2
        assets = make_production_assets(n)
        config = ProductionConfig(
            fps=30,
            resolution=(1920, 1080),
            export_format="otioz",
            upload_youtube=False,
        )

        with (
            patch("pipeline.production.phase.TimelineAssembler") as MockAssembler,
            patch("pipeline.production.phase.MotionEngine"),
            patch("pipeline.production.phase.SubtitleBurner") as MockBurner,
            patch("pipeline.production.phase.VideoExporter") as MockExporter,
        ):
            assembler = TimelineAssembler()
            timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
            MockAssembler.return_value.assemble.return_value = timeline

            mock_video_clip = MagicMock()
            MockBurner.return_value.transcribe_and_burn.return_value = mock_video_clip

            otioz_path = tmp_path / "output.otioz"
            otioz_path.touch()
            MockExporter.return_value.export_otioz.return_value = otioz_path

            from pipeline.production.phase import ProductionPhase
            phase = ProductionPhase(output_dir=tmp_path)
            phase._apply_ken_burns_to_timeline = MagicMock(return_value=mock_video_clip)

            result = phase.run(assets, config)

        MockExporter.return_value.export_otioz.assert_called_once()
        assert otioz_path in result.output_files

    def test_run_both_formats(self, tmp_path):
        """ProductionPhase exports both MP4 and OTIOZ for 'both' format."""
        n = 2
        assets = make_production_assets(n)
        config = ProductionConfig(
            fps=30,
            resolution=(1920, 1080),
            export_format="both",
            upload_youtube=False,
        )

        with (
            patch("pipeline.production.phase.TimelineAssembler") as MockAssembler,
            patch("pipeline.production.phase.MotionEngine"),
            patch("pipeline.production.phase.SubtitleBurner") as MockBurner,
            patch("pipeline.production.phase.VideoExporter") as MockExporter,
        ):
            assembler = TimelineAssembler()
            timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
            MockAssembler.return_value.assemble.return_value = timeline

            mock_video_clip = MagicMock()
            MockBurner.return_value.transcribe_and_burn.return_value = mock_video_clip

            mp4_path = tmp_path / "output.mp4"
            otioz_path = tmp_path / "output.otioz"
            mp4_path.touch()
            otioz_path.touch()
            MockExporter.return_value.export_mp4.return_value = mp4_path
            MockExporter.return_value.export_otioz.return_value = otioz_path

            from pipeline.production.phase import ProductionPhase
            phase = ProductionPhase(output_dir=tmp_path)
            phase._apply_ken_burns_to_timeline = MagicMock(return_value=mock_video_clip)

            result = phase.run(assets, config)

        MockExporter.return_value.export_mp4.assert_called_once()
        MockExporter.return_value.export_otioz.assert_called_once()
        assert len(result.output_files) == 2

    def test_run_duration_matches_timeline(self, tmp_path):
        """VideoArtifact.duration_seconds matches the timeline total_duration."""
        n = 3
        audio_duration = 2.5
        assets = make_production_assets(n, audio_duration=audio_duration)
        config = ProductionConfig(
            fps=30,
            resolution=(1920, 1080),
            export_format="mp4",
            upload_youtube=False,
        )

        with (
            patch("pipeline.production.phase.TimelineAssembler") as MockAssembler,
            patch("pipeline.production.phase.MotionEngine"),
            patch("pipeline.production.phase.SubtitleBurner") as MockBurner,
            patch("pipeline.production.phase.VideoExporter") as MockExporter,
        ):
            assembler = TimelineAssembler()
            timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
            MockAssembler.return_value.assemble.return_value = timeline

            mock_video_clip = MagicMock()
            MockBurner.return_value.transcribe_and_burn.return_value = mock_video_clip

            mp4_path = tmp_path / "output.mp4"
            mp4_path.touch()
            MockExporter.return_value.export_mp4.return_value = mp4_path

            from pipeline.production.phase import ProductionPhase
            phase = ProductionPhase(output_dir=tmp_path)
            phase._apply_ken_burns_to_timeline = MagicMock(return_value=mock_video_clip)

            result = phase.run(assets, config)

        expected_duration = n * audio_duration
        assert abs(result.duration_seconds - expected_duration) < 1e-6

    def test_run_no_youtube_upload_when_disabled(self, tmp_path):
        """YouTubeUploader is not called when upload_youtube=False."""
        n = 2
        assets = make_production_assets(n)
        config = ProductionConfig(
            fps=30,
            resolution=(1920, 1080),
            export_format="mp4",
            upload_youtube=False,
        )

        with (
            patch("pipeline.production.phase.TimelineAssembler") as MockAssembler,
            patch("pipeline.production.phase.MotionEngine"),
            patch("pipeline.production.phase.SubtitleBurner") as MockBurner,
            patch("pipeline.production.phase.VideoExporter") as MockExporter,
            patch("pipeline.production.phase.YouTubeUploader", create=True) as MockYT,
        ):
            assembler = TimelineAssembler()
            timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
            MockAssembler.return_value.assemble.return_value = timeline

            mock_video_clip = MagicMock()
            MockBurner.return_value.transcribe_and_burn.return_value = mock_video_clip

            mp4_path = tmp_path / "output.mp4"
            mp4_path.touch()
            MockExporter.return_value.export_mp4.return_value = mp4_path

            from pipeline.production.phase import ProductionPhase
            phase = ProductionPhase(output_dir=tmp_path)
            phase._apply_ken_burns_to_timeline = MagicMock(return_value=mock_video_clip)

            result = phase.run(assets, config)

        assert result.youtube_url is None

    def test_subtitle_burn_failure_is_non_fatal(self, tmp_path):
        """If SubtitleBurner fails, ProductionPhase continues without subtitles."""
        n = 2
        assets = make_production_assets(n)
        config = ProductionConfig(
            fps=30,
            resolution=(1920, 1080),
            export_format="mp4",
            upload_youtube=False,
        )

        with (
            patch("pipeline.production.phase.TimelineAssembler") as MockAssembler,
            patch("pipeline.production.phase.MotionEngine"),
            patch("pipeline.production.phase.SubtitleBurner") as MockBurner,
            patch("pipeline.production.phase.VideoExporter") as MockExporter,
        ):
            assembler = TimelineAssembler()
            timeline = assembler.assemble(assets.upscaled, assets.audio_segments, assets.script)
            MockAssembler.return_value.assemble.return_value = timeline

            mock_video_clip = MagicMock()
            # Subtitle burner raises an exception
            MockBurner.return_value.transcribe_and_burn.side_effect = RuntimeError("whisper unavailable")

            mp4_path = tmp_path / "output.mp4"
            mp4_path.touch()
            MockExporter.return_value.export_mp4.return_value = mp4_path

            from pipeline.production.phase import ProductionPhase
            phase = ProductionPhase(output_dir=tmp_path)
            phase._apply_ken_burns_to_timeline = MagicMock(return_value=mock_video_clip)

            # Should not raise
            result = phase.run(assets, config)

        assert isinstance(result, VideoArtifact)
