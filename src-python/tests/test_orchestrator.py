"""
Tests for PipelineOrchestrator.

Covers:
- test_run_pipeline_success: full pipeline with all mocks returns SUCCESS
- test_resume_skips_completed_phases: resume skips phases with checkpoints
- test_cancel_job_stops_execution: cancel_job stops the pipeline
- test_phase_error_returns_failed: error in one phase returns FAILED
- Property 2: Retomada sem reprocessamento (hypothesis)
  **Validates: Requirements 1.5, 2.2**
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
import wave
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    AudioSegment,
    BoundingBox,
    CroppedPanel,
    IntelligenceResult,
    JobResult,
    JobStatus,
    Panel,
    PanelSet,
    PhaseContext,
    PipelineConfig,
    ProductionAssets,
    Script,
    ScriptSegment,
    UpscaledImage,
    VideoArtifact,
)
from pipeline.orchestrator import PipelineOrchestrator
from state_manager import StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_pipeline_config(tmp_path: Path, job_id: str = "test-job-001") -> PipelineConfig:
    """Create a minimal PipelineConfig for testing."""
    return PipelineConfig(
        job_id=job_id,
        source={"type": "local", "paths": [], "chapter_id": None},
        llm_provider="mock",
        llm_model="mock-model",
        tts_provider="mock",
        tts_voice_id="voice-001",
        upscale_model="realesrgan",
        upscale_factor=4,
        export_format="mp4",
        upload_youtube=False,
        output_dir=tmp_path,
        language="pt-BR",
    )


def make_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 44100) -> bytes:
    """Create minimal valid WAV bytes."""
    n_frames = int(duration_seconds * sample_rate)
    samples = np.zeros(n_frames, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def make_panel_set(n: int = 2) -> PanelSet:
    """Create a minimal PanelSet."""
    panels = []
    for i in range(n):
        image = np.full((90, 160, 3), 128, dtype=np.uint8)
        bbox = BoundingBox(x=0, y=0, width=160, height=90)
        panel = Panel(
            page_index=0,
            panel_index=i,
            bbox=bbox,
            art_region=image.copy(),
            bubble_regions=[],
            raw_image=image.copy(),
        )
        cropped = CroppedPanel(image=image, source_panel=panel, scale_factor=1.0)
        panels.append(cropped)
    return PanelSet(panels=panels)


def make_intelligence_result(n: int = 2) -> IntelligenceResult:
    """Create a minimal IntelligenceResult."""
    image = np.full((1080, 1920, 3), 128, dtype=np.uint8)
    bbox = BoundingBox(x=0, y=0, width=1920, height=1080)
    panel = Panel(
        page_index=0,
        panel_index=0,
        bbox=bbox,
        art_region=image.copy(),
        bubble_regions=[],
        raw_image=image.copy(),
    )
    cropped = CroppedPanel(image=image.copy(), source_panel=panel, scale_factor=1.0)

    upscaled = [
        UpscaledImage(image=image.copy(), source_panel=cropped, scale_factor=4.0)
        for _ in range(n)
    ]
    audio_segments = [
        AudioSegment(
            panel_index=i,
            audio_data=make_wav_bytes(2.0),
            duration=2.0,
            sample_rate=44100,
        )
        for i in range(n)
    ]
    script = Script(
        segments=[
            ScriptSegment(
                panel_index=i,
                narration=f"Narration {i}",
                duration_hint=2.0,
                emotion="neutral",
            )
            for i in range(n)
        ],
        total_duration_estimate=float(n * 2),
    )
    return IntelligenceResult(
        script=script,
        audio_segments=audio_segments,
        upscaled=upscaled,
    )


def make_video_artifact(tmp_path: Path) -> VideoArtifact:
    """Create a minimal VideoArtifact."""
    mp4 = tmp_path / "output.mp4"
    mp4.touch()
    return VideoArtifact(
        output_files=[mp4],
        youtube_url=None,
        duration_seconds=4.0,
    )


# ---------------------------------------------------------------------------
# Test: run_pipeline with all mocks returns SUCCESS
# ---------------------------------------------------------------------------


class TestRunPipelineSuccess:
    """Test that run_pipeline with all mocks returns SUCCESS."""

    def test_run_pipeline_returns_success(self, tmp_path):
        """run_pipeline with mocked phases returns JobResult(SUCCESS)."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.return_value = video_artifact

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        assert result.status == JobStatus.SUCCESS
        assert result.job_id == config.job_id
        assert result.error is None

    def test_run_pipeline_calls_all_three_phases(self, tmp_path):
        """run_pipeline invokes Ingestion, Intelligence, and Production."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.return_value = video_artifact

            orchestrator = PipelineOrchestrator()
            orchestrator.run_pipeline(config)

        MockIngestion.return_value.run.assert_called_once()
        MockIntelligence.return_value.run.assert_called_once()
        MockProduction.return_value.run.assert_called_once()

    def test_run_pipeline_saves_checkpoints(self, tmp_path):
        """run_pipeline saves checkpoints for each phase."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.return_value = video_artifact

            orchestrator = PipelineOrchestrator()
            orchestrator.run_pipeline(config)

        state = StateManager(tmp_path)
        assert state.load_checkpoint(config.job_id, "ingestion") is not None
        assert state.load_checkpoint(config.job_id, "intelligence") is not None
        assert state.load_checkpoint(config.job_id, "production") is not None

    def test_run_pipeline_emits_progress_events(self, tmp_path):
        """run_pipeline calls on_progress callback for each phase."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        progress_calls = []

        def on_progress(phase, percent, message):
            progress_calls.append((phase, percent, message))

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.return_value = video_artifact

            orchestrator = PipelineOrchestrator(on_progress=on_progress)
            orchestrator.run_pipeline(config)

        # Should have received progress events for each phase
        phases_reported = {call[0] for call in progress_calls}
        assert "ingestion" in phases_reported
        assert "intelligence" in phases_reported
        assert "production" in phases_reported

    def test_run_pipeline_output_files_in_result(self, tmp_path):
        """JobResult.output_files contains the exported file paths."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.return_value = video_artifact

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        assert len(result.output_files) > 0


# ---------------------------------------------------------------------------
# Test: resume skips completed phases (Property 2)
# ---------------------------------------------------------------------------


class TestResumeSkipsCompletedPhases:
    """Test that resume_job skips phases that already have checkpoints."""

    def test_resume_skips_ingestion_when_checkpoint_exists(self, tmp_path):
        """If ingestion checkpoint exists, IngestionPhase.run is NOT called."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        # Pre-save ingestion checkpoint
        state = StateManager(tmp_path)
        state.save_checkpoint(config.job_id, "ingestion", panel_set)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.return_value = video_artifact

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        # Ingestion should NOT have been called
        MockIngestion.return_value.run.assert_not_called()
        # Intelligence and Production should have been called
        MockIntelligence.return_value.run.assert_called_once()
        MockProduction.return_value.run.assert_called_once()
        assert result.status == JobStatus.SUCCESS

    def test_resume_skips_intelligence_when_checkpoint_exists(self, tmp_path):
        """If intelligence checkpoint exists, IntelligencePhase.run is NOT called."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        # Pre-save ingestion + intelligence checkpoints
        state = StateManager(tmp_path)
        state.save_checkpoint(config.job_id, "ingestion", panel_set)
        state.save_checkpoint(config.job_id, "intelligence", intel_result)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.return_value = video_artifact

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        MockIngestion.return_value.run.assert_not_called()
        MockIntelligence.return_value.run.assert_not_called()
        MockProduction.return_value.run.assert_called_once()
        assert result.status == JobStatus.SUCCESS

    def test_resume_skips_all_phases_when_all_checkpoints_exist(self, tmp_path):
        """If all checkpoints exist, no phase is re-executed."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        # Pre-save all checkpoints
        state = StateManager(tmp_path)
        state.save_checkpoint(config.job_id, "ingestion", panel_set)
        state.save_checkpoint(config.job_id, "intelligence", intel_result)
        state.save_checkpoint(config.job_id, "production", video_artifact)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        MockIngestion.return_value.run.assert_not_called()
        MockIntelligence.return_value.run.assert_not_called()
        MockProduction.return_value.run.assert_not_called()
        assert result.status == JobStatus.SUCCESS

    def test_resume_preserves_existing_checkpoints_on_cancel(self, tmp_path):
        """cancel_job preserves existing checkpoints."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)

        # Pre-save ingestion checkpoint
        state = StateManager(tmp_path)
        state.save_checkpoint(config.job_id, "ingestion", panel_set)

        orchestrator = PipelineOrchestrator()
        orchestrator.cancel_job(config.job_id)

        # Checkpoint should still exist
        loaded = state.load_checkpoint(config.job_id, "ingestion")
        assert loaded is not None


# ---------------------------------------------------------------------------
# Test: cancel_job stops execution
# ---------------------------------------------------------------------------


class TestCancelJob:
    """Test that cancel_job stops pipeline execution."""

    def test_cancel_before_start_returns_failed(self, tmp_path):
        """Cancelling before run_pipeline starts returns FAILED."""
        config = make_pipeline_config(tmp_path)

        orchestrator = PipelineOrchestrator()
        orchestrator.cancel_job(config.job_id)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            result = orchestrator.run_pipeline(config)

        # Pipeline should have been cancelled immediately
        assert result.status == JobStatus.FAILED
        assert "cancel" in result.error.lower()

    def test_cancel_during_execution_stops_pipeline(self, tmp_path):
        """cancel_job during execution stops the pipeline after the current phase."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        orchestrator = PipelineOrchestrator()

        # Cancel after ingestion completes
        original_run_ingestion = orchestrator._run_ingestion

        def slow_ingestion(cfg, state, cancel_event):
            result = original_run_ingestion(cfg, state, cancel_event)
            # Simulate cancellation after ingestion
            orchestrator.cancel_job(cfg.job_id)
            return result

        orchestrator._run_ingestion = slow_ingestion

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.return_value = video_artifact

            result = orchestrator.run_pipeline(config)

        # Pipeline should have been cancelled
        assert result.status == JobStatus.FAILED

    def test_cancel_job_sets_event(self, tmp_path):
        """cancel_job sets the cancellation event for the job."""
        orchestrator = PipelineOrchestrator()
        job_id = "cancel-test-job"

        # Register the event first
        import threading
        event = threading.Event()
        orchestrator._cancel_events[job_id] = event

        orchestrator.cancel_job(job_id)
        assert event.is_set()

    def test_cancel_nonexistent_job_creates_preset_event(self):
        """cancel_job on a non-existent job creates a pre-set event."""
        orchestrator = PipelineOrchestrator()
        job_id = "nonexistent-job-xyz"

        orchestrator.cancel_job(job_id)

        assert job_id in orchestrator._cancel_events
        assert orchestrator._cancel_events[job_id].is_set()


# ---------------------------------------------------------------------------
# Test: error in one phase returns FAILED with error message
# ---------------------------------------------------------------------------


class TestPhaseErrorHandling:
    """Test that errors in phases return FAILED with error message."""

    def test_ingestion_error_returns_failed(self, tmp_path):
        """Error in Ingestion phase returns JobResult(FAILED) with error message."""
        config = make_pipeline_config(tmp_path)

        with patch("pipeline.orchestrator.IngestionPhase") as MockIngestion:
            MockIngestion.return_value.run.side_effect = RuntimeError("Ingestion failed!")

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        assert result.status == JobStatus.FAILED
        assert result.error is not None
        assert "Ingestion failed!" in result.error

    def test_intelligence_error_returns_failed(self, tmp_path):
        """Error in Intelligence phase returns JobResult(FAILED) with error message."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)

        # Pre-save ingestion checkpoint so we reach intelligence
        state = StateManager(tmp_path)
        state.save_checkpoint(config.job_id, "ingestion", panel_set)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.side_effect = RuntimeError("LLM quota exceeded")

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        assert result.status == JobStatus.FAILED
        assert result.error is not None
        assert "LLM quota exceeded" in result.error

    def test_production_error_returns_failed(self, tmp_path):
        """Error in Production phase returns JobResult(FAILED) with error message."""
        config = make_pipeline_config(tmp_path)
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)

        # Pre-save ingestion + intelligence checkpoints
        state = StateManager(tmp_path)
        state.save_checkpoint(config.job_id, "ingestion", panel_set)
        state.save_checkpoint(config.job_id, "intelligence", intel_result)

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.side_effect = RuntimeError("FFmpeg error")

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        assert result.status == JobStatus.FAILED
        assert result.error is not None
        assert "FFmpeg error" in result.error

    def test_orchestrator_never_crashes_on_phase_failure(self, tmp_path):
        """Orchestrator catches all exceptions and returns FAILED, never raises."""
        config = make_pipeline_config(tmp_path)

        with patch("pipeline.orchestrator.IngestionPhase") as MockIngestion:
            MockIngestion.return_value.run.side_effect = Exception("Unexpected crash!")

            orchestrator = PipelineOrchestrator()
            # Should NOT raise
            result = orchestrator.run_pipeline(config)

        assert result.status == JobStatus.FAILED
        assert result.error is not None

    def test_failed_result_has_empty_output_files(self, tmp_path):
        """FAILED JobResult has empty output_files list."""
        config = make_pipeline_config(tmp_path)

        with patch("pipeline.orchestrator.IngestionPhase") as MockIngestion:
            MockIngestion.return_value.run.side_effect = RuntimeError("Error")

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        assert result.output_files == []

    def test_ingestion_checkpoint_not_saved_on_failure(self, tmp_path):
        """If Ingestion fails, no checkpoint is saved for that phase."""
        config = make_pipeline_config(tmp_path)

        with patch("pipeline.orchestrator.IngestionPhase") as MockIngestion:
            MockIngestion.return_value.run.side_effect = RuntimeError("Error")

            orchestrator = PipelineOrchestrator()
            orchestrator.run_pipeline(config)

        state = StateManager(tmp_path)
        assert state.load_checkpoint(config.job_id, "ingestion") is None


# ---------------------------------------------------------------------------
# Test: run_phase
# ---------------------------------------------------------------------------


class TestRunPhase:
    """Test the run_phase method."""

    def test_run_phase_ingestion(self, tmp_path):
        """run_phase('ingestion', context) runs the ingestion phase."""
        config = make_pipeline_config(tmp_path)
        context = PhaseContext(
            job_id=config.job_id,
            config=config,
            output_dir=tmp_path,
        )
        panel_set = make_panel_set(2)

        with patch("pipeline.orchestrator.IngestionPhase") as MockIngestion:
            MockIngestion.return_value.run.return_value = panel_set

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_phase("ingestion", context)

        assert result.phase == "ingestion"
        assert result.success is True
        assert result.error is None

    def test_run_phase_unknown_returns_failed(self, tmp_path):
        """run_phase with unknown phase name returns PhaseResult(success=False)."""
        config = make_pipeline_config(tmp_path)
        context = PhaseContext(
            job_id=config.job_id,
            config=config,
            output_dir=tmp_path,
        )

        orchestrator = PipelineOrchestrator()
        result = orchestrator.run_phase("unknown_phase", context)

        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# Property 2: Retomada sem reprocessamento
# **Validates: Requirements 1.5, 2.2**
# ---------------------------------------------------------------------------


@given(
    completed_phases=st.lists(
        st.sampled_from(["ingestion", "intelligence", "production"]),
        min_size=1,
        max_size=3,
        unique=True,
    )
)
@settings(max_examples=30)
def test_property2_resume_skips_completed_phases(completed_phases):
    """
    **Validates: Requirements 1.5, 2.2**

    Property 2: For any pipeline job where some phases have been completed
    (checkpoints saved), resuming the job must skip those phases and only
    execute the remaining ones.

    For each subset of completed phases, the corresponding phase runners
    must NOT be called when run_pipeline is invoked.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        config = make_pipeline_config(tmp_path, job_id=f"prop2-{'-'.join(sorted(completed_phases))}")
        panel_set = make_panel_set(2)
        intel_result = make_intelligence_result(2)
        video_artifact = make_video_artifact(tmp_path)

        state = StateManager(tmp_path)

        # Save checkpoints for completed phases
        # We need to save them in order (ingestion before intelligence before production)
        # because the orchestrator loads them sequentially
        phase_data = {
            "ingestion": panel_set,
            "intelligence": intel_result,
            "production": video_artifact,
        }

        # Only save checkpoints for phases that are "completed"
        # But we must ensure dependencies are met: if intelligence is completed,
        # ingestion must also be completed (otherwise the orchestrator would try to run it)
        # For this property test, we save all prerequisite checkpoints too.
        ordered_phases = ["ingestion", "intelligence", "production"]
        phases_to_save = set(completed_phases)

        # Ensure prerequisites: if a later phase is completed, earlier ones must be too
        for i, phase in enumerate(ordered_phases):
            if phase in phases_to_save:
                # Save all phases up to and including this one
                for j in range(i + 1):
                    phases_to_save.add(ordered_phases[j])

        for phase in ordered_phases:
            if phase in phases_to_save:
                state.save_checkpoint(config.job_id, phase, phase_data[phase])

        with (
            patch("pipeline.orchestrator.IngestionPhase") as MockIngestion,
            patch("pipeline.orchestrator.IntelligencePhase") as MockIntelligence,
            patch("pipeline.orchestrator.ProductionPhase") as MockProduction,
        ):
            MockIngestion.return_value.run.return_value = panel_set
            MockIntelligence.return_value.run.return_value = intel_result
            MockProduction.return_value.run.return_value = video_artifact

            orchestrator = PipelineOrchestrator()
            result = orchestrator.run_pipeline(config)

        # Verify that phases with checkpoints were NOT re-executed
        if "ingestion" in phases_to_save:
            MockIngestion.return_value.run.assert_not_called(), (
                "Ingestion should have been skipped (checkpoint exists)"
            )

        if "intelligence" in phases_to_save:
            MockIntelligence.return_value.run.assert_not_called(), (
                "Intelligence should have been skipped (checkpoint exists)"
            )

        if "production" in phases_to_save:
            MockProduction.return_value.run.assert_not_called(), (
                "Production should have been skipped (checkpoint exists)"
            )

        # The pipeline should succeed (all phases either skipped or completed)
        assert result.status == JobStatus.SUCCESS, (
            f"Expected SUCCESS but got {result.status}: {result.error}"
        )
