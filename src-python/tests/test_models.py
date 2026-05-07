"""
Unit tests for src-python/models.py — Task 2.2.

Covers:
- BoundingBox.aspect_ratio
- BoundingBox.to_16x9
- Required-field validation for Pydantic models (PipelineConfig, JobResult)
- Basic construction of all dataclasses
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Add src-python to path so we can import models directly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import (
    AudioSegment,
    BoundingBox,
    BubbleRegion,
    CroppedPanel,
    ExportConfig,
    IngestionConfig,
    IntelligenceConfig,
    IntelligenceResult,
    JobResult,
    JobStatus,
    JobSummary,
    KenBurnsParams,
    PageImage,
    PageSource,
    Panel,
    PanelSet,
    PhaseContext,
    PhaseResult,
    PipelineConfig,
    ProductionAssets,
    ProductionConfig,
    Script,
    ScriptSegment,
    Timeline,
    TimelineClip,
    UpscaledImage,
    VideoArtifact,
)


# ---------------------------------------------------------------------------
# BoundingBox.aspect_ratio
# ---------------------------------------------------------------------------


class TestBoundingBoxAspectRatio:
    def test_square_is_1(self):
        assert BoundingBox(0, 0, 100, 100).aspect_ratio == pytest.approx(1.0)

    def test_landscape(self):
        assert BoundingBox(0, 0, 160, 90).aspect_ratio == pytest.approx(160 / 90)

    def test_portrait(self):
        assert BoundingBox(0, 0, 90, 160).aspect_ratio == pytest.approx(90 / 160)

    def test_zero_height_returns_zero(self):
        """Guard against division by zero."""
        assert BoundingBox(0, 0, 100, 0).aspect_ratio == 0.0


# ---------------------------------------------------------------------------
# BoundingBox.to_16x9
# ---------------------------------------------------------------------------


class TestBoundingBoxTo16x9:
    def test_result_width_equals_canvas_width(self):
        bbox = BoundingBox(0, 0, 200, 300)
        result = bbox.to_16x9(1920)
        assert result.width == 1920

    def test_result_height_is_9_16_of_width(self):
        bbox = BoundingBox(0, 0, 200, 300)
        result = bbox.to_16x9(1920)
        assert result.height == int(1920 * 9 / 16)  # 1080

    def test_result_is_centred_on_original(self):
        """Centre of the returned box should match centre of the original."""
        bbox = BoundingBox(100, 200, 400, 600)
        result = bbox.to_16x9(1920)
        orig_cx = bbox.x + bbox.width // 2
        orig_cy = bbox.y + bbox.height // 2
        res_cx = result.x + result.width // 2
        res_cy = result.y + result.height // 2
        assert res_cx == orig_cx
        assert res_cy == orig_cy

    def test_small_canvas_width(self):
        bbox = BoundingBox(0, 0, 100, 100)
        result = bbox.to_16x9(640)
        assert result.width == 640
        assert result.height == int(640 * 9 / 16)  # 360

    def test_returns_bounding_box_instance(self):
        bbox = BoundingBox(0, 0, 100, 100)
        result = bbox.to_16x9(1920)
        assert isinstance(result, BoundingBox)


# ---------------------------------------------------------------------------
# JobStatus enum
# ---------------------------------------------------------------------------


class TestJobStatus:
    def test_values(self):
        assert JobStatus.SUCCESS == "SUCCESS"
        assert JobStatus.FAILED == "FAILED"
        assert JobStatus.PARTIAL == "PARTIAL"

    def test_is_str_subclass(self):
        assert isinstance(JobStatus.SUCCESS, str)


# ---------------------------------------------------------------------------
# PipelineConfig (Pydantic) — required field validation
# ---------------------------------------------------------------------------


class TestPipelineConfig:
    def _valid_kwargs(self):
        return dict(
            job_id="abc-123",
            source={"type": "local", "paths": []},
            llm_provider="gemini",
            llm_model="gemini-1.5-pro",
            tts_provider="elevenlabs",
            tts_voice_id="voice-001",
            upscale_model="realesrgan",
            upscale_factor=4,
            export_format="mp4",
            upload_youtube=False,
            output_dir=Path("/tmp/output"),
            language="pt-BR",
        )

    def test_valid_construction(self):
        cfg = PipelineConfig(**self._valid_kwargs())
        assert cfg.job_id == "abc-123"
        assert cfg.upscale_factor == 4
        assert isinstance(cfg.output_dir, Path)

    def test_output_dir_coerced_from_string(self):
        kwargs = self._valid_kwargs()
        kwargs["output_dir"] = "/tmp/output"
        cfg = PipelineConfig(**kwargs)
        assert isinstance(cfg.output_dir, Path)

    def test_missing_required_field_raises(self):
        from pydantic import ValidationError

        kwargs = self._valid_kwargs()
        del kwargs["job_id"]
        with pytest.raises(ValidationError):
            PipelineConfig(**kwargs)


# ---------------------------------------------------------------------------
# JobResult (Pydantic) — required field validation
# ---------------------------------------------------------------------------


class TestJobResult:
    def _valid_kwargs(self):
        return dict(
            job_id="abc-123",
            status=JobStatus.SUCCESS,
            output_files=[Path("/tmp/out.mp4")],
            youtube_url=None,
            duration_seconds=120.5,
            error=None,
        )

    def test_valid_construction(self):
        result = JobResult(**self._valid_kwargs())
        assert result.status == JobStatus.SUCCESS
        assert result.duration_seconds == pytest.approx(120.5)

    def test_missing_required_field_raises(self):
        from pydantic import ValidationError

        kwargs = self._valid_kwargs()
        del kwargs["status"]
        with pytest.raises(ValidationError):
            JobResult(**kwargs)

    def test_optional_fields_default_to_none(self):
        result = JobResult(**self._valid_kwargs())
        assert result.youtube_url is None
        assert result.error is None


# ---------------------------------------------------------------------------
# Dataclass construction smoke tests
# ---------------------------------------------------------------------------


class TestDataclassConstruction:
    """Verify every dataclass can be instantiated without errors."""

    def _dummy_image(self, h=10, w=10):
        return np.zeros((h, w, 3), dtype=np.uint8)

    def _dummy_bbox(self):
        return BoundingBox(0, 0, 100, 100)

    def test_bubble_region(self):
        br = BubbleRegion(
            bbox=self._dummy_bbox(),
            mask=np.zeros((10, 10), dtype=np.uint8),
        )
        assert br.bbox.width == 100

    def test_page_image(self):
        pi = PageImage(data=self._dummy_image(), path=None, index=0)
        assert pi.index == 0

    def test_panel(self):
        p = Panel(
            page_index=0,
            panel_index=0,
            bbox=self._dummy_bbox(),
            art_region=self._dummy_image(),
            bubble_regions=[],
            raw_image=self._dummy_image(),
        )
        assert p.panel_index == 0

    def test_cropped_panel(self):
        panel = Panel(
            page_index=0,
            panel_index=0,
            bbox=self._dummy_bbox(),
            art_region=self._dummy_image(),
            bubble_regions=[],
            raw_image=self._dummy_image(),
        )
        cp = CroppedPanel(image=self._dummy_image(), source_panel=panel, scale_factor=1.5)
        assert cp.scale_factor == pytest.approx(1.5)

    def test_upscaled_image(self):
        panel = Panel(
            page_index=0,
            panel_index=0,
            bbox=self._dummy_bbox(),
            art_region=self._dummy_image(),
            bubble_regions=[],
            raw_image=self._dummy_image(),
        )
        cp = CroppedPanel(image=self._dummy_image(), source_panel=panel, scale_factor=1.0)
        ui = UpscaledImage(image=self._dummy_image(), source_panel=cp, scale_factor=4.0)
        assert ui.scale_factor == pytest.approx(4.0)

    def test_panel_set(self):
        ps = PanelSet(panels=[])
        assert ps.panels == []

    def test_page_source_mangadex(self):
        src = PageSource(type="mangadex", chapter_id="ch-001", paths=None)
        assert src.type == "mangadex"

    def test_page_source_local(self):
        src = PageSource(type="local", chapter_id=None, paths=[Path("/img/p1.jpg")])
        assert src.paths is not None

    def test_script_segment(self):
        seg = ScriptSegment(panel_index=0, narration="Epic battle!", duration_hint=3.5, emotion="dramatic")
        assert seg.narration == "Epic battle!"

    def test_script(self):
        seg = ScriptSegment(panel_index=0, narration="Intro", duration_hint=2.0, emotion="neutral")
        s = Script(segments=[seg], total_duration_estimate=2.0)
        assert s.total_duration_estimate == pytest.approx(2.0)

    def test_audio_segment_defaults(self):
        a = AudioSegment(panel_index=0, audio_data=b"\x00\x01", duration=2.0)
        assert a.sample_rate == 44100

    def test_ken_burns_params_defaults(self):
        kb = KenBurnsParams(
            start_zoom=1.0,
            end_zoom=1.15,
            start_pan=(0.5, 0.5),
            end_pan=(0.6, 0.4),
        )
        assert kb.easing == "ease_in_out"

    def test_timeline_clip(self):
        panel = Panel(
            page_index=0,
            panel_index=0,
            bbox=self._dummy_bbox(),
            art_region=self._dummy_image(),
            bubble_regions=[],
            raw_image=self._dummy_image(),
        )
        cp = CroppedPanel(image=self._dummy_image(), source_panel=panel, scale_factor=1.0)
        ui = UpscaledImage(image=self._dummy_image(), source_panel=cp, scale_factor=4.0)
        audio = AudioSegment(panel_index=0, audio_data=b"", duration=3.0)
        kb = KenBurnsParams(start_zoom=1.0, end_zoom=1.1, start_pan=(0.5, 0.5), end_pan=(0.5, 0.5))
        clip = TimelineClip(panel=ui, audio=audio, start_time=0.0, end_time=3.0, ken_burns=kb)
        assert clip.end_time == pytest.approx(3.0)

    def test_timeline(self):
        tl = Timeline(clips=[], total_duration=0.0, fps=30, resolution=(1920, 1080))
        assert tl.fps == 30

    def test_ingestion_config_defaults(self):
        cfg = IngestionConfig()
        assert cfg.target_width == 1920
        assert cfg.min_panel_area == 10000
        assert cfg.max_aspect_ratio == pytest.approx(10.0)

    def test_intelligence_config(self):
        cfg = IntelligenceConfig(
            llm_provider="gemini",
            llm_model="gemini-1.5-pro",
            tts_provider="elevenlabs",
            tts_voice_id="v1",
            upscale_model="realesrgan",
            upscale_factor=4,
        )
        assert cfg.batch_size == 4
        assert cfg.language == "pt-BR"

    def test_production_config_defaults(self):
        cfg = ProductionConfig()
        assert cfg.fps == 30
        assert cfg.resolution == (1920, 1080)
        assert cfg.export_format == "mp4"
        assert cfg.upload_youtube is False

    def test_export_config(self):
        cfg = ExportConfig(output_dir=Path("/out"), format="mp4", fps=30, resolution=(1920, 1080))
        assert cfg.fps == 30

    def test_job_summary(self):
        js = JobSummary(
            job_id="j1",
            status=JobStatus.SUCCESS,
            phases_completed=["ingestion", "intelligence"],
            created_at="2024-01-01T00:00:00Z",
        )
        assert "ingestion" in js.phases_completed

    def test_phase_result(self):
        pr = PhaseResult(phase="ingestion", success=True, error=None)
        assert pr.success is True

    def test_video_artifact(self):
        va = VideoArtifact(
            output_files=[Path("/out/video.mp4")],
            youtube_url=None,
            duration_seconds=60.0,
        )
        assert va.duration_seconds == pytest.approx(60.0)
