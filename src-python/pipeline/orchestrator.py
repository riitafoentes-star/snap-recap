"""
Snap Recap — PipelineOrchestrator

Coordinates the sequential execution of the three pipeline phases:
  Ingestion → Intelligence → Production

Supports:
- Checkpoint-based resume (skip phases that already have checkpoints)
- Cancellation via threading.Event
- Progress callbacks: on_progress(phase, percent, message)
- Per-phase error handling (never crashes the orchestrator)
"""

from __future__ import annotations

import logging
import sys
import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    IngestionConfig,
    IntelligenceConfig,
    JobResult,
    JobStatus,
    PageSource,
    PhaseContext,
    PhaseResult,
    PipelineConfig,
    ProductionAssets,
    ProductionConfig,
)
from state_manager import StateManager
from pipeline.ingestion.phase import IngestionPhase
from pipeline.intelligence.phase import IntelligencePhase
from pipeline.production.phase import ProductionPhase

logger = logging.getLogger(__name__)

# Type alias for the progress callback
ProgressCallback = Callable[[str, float, str], None]

# Ordered list of pipeline phases
_PHASES = ("ingestion", "intelligence", "production")


class PipelineOrchestrator:
    """Coordinates the sequential execution of the three pipeline phases.

    Args:
        on_progress: Optional callback invoked with (phase, percent, message)
            whenever progress is made.  Defaults to None (no-op).
    """

    def __init__(self, on_progress: Optional[ProgressCallback] = None) -> None:
        self._on_progress = on_progress
        # Map from job_id → cancellation Event
        self._cancel_events: Dict[str, threading.Event] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_pipeline(self, config: PipelineConfig) -> JobResult:
        """Execute the full pipeline: Ingestion → Intelligence → Production.

        Checkpoints are saved after each phase.  If a phase checkpoint already
        exists, that phase is skipped (resume support).

        Args:
            config: PipelineConfig describing the job.

        Returns:
            JobResult with status SUCCESS on completion, FAILED on error.
        """
        job_id = config.job_id
        start_time = time.monotonic()

        # Ensure a cancellation event exists for this job
        cancel_event = self._cancel_events.setdefault(job_id, threading.Event())

        state = StateManager(config.output_dir)

        self._emit_progress("pipeline", 0.0, f"Starting pipeline for job {job_id}")

        try:
            # ----------------------------------------------------------------
            # Phase 1: Ingestion
            # ----------------------------------------------------------------
            ingestion_result = state.load_checkpoint(job_id, "ingestion")
            if ingestion_result is not None:
                logger.info("[%s] Ingestion checkpoint found — skipping.", job_id)
                self._emit_progress("ingestion", 100.0, "Ingestion skipped (checkpoint found)")
            else:
                if cancel_event.is_set():
                    return self._cancelled_result(job_id, start_time)

                self._emit_progress("ingestion", 0.0, "Starting Ingestion phase")
                phase_result = self._run_ingestion(config, state, cancel_event)
                if not phase_result.success:
                    return JobResult(
                        job_id=job_id,
                        status=JobStatus.FAILED,
                        output_files=[],
                        youtube_url=None,
                        duration_seconds=time.monotonic() - start_time,
                        error=phase_result.error,
                    )
                ingestion_result = state.load_checkpoint(job_id, "ingestion")
                self._emit_progress("ingestion", 100.0, "Ingestion phase complete")

            # ----------------------------------------------------------------
            # Phase 2: Intelligence
            # ----------------------------------------------------------------
            intelligence_result = state.load_checkpoint(job_id, "intelligence")
            if intelligence_result is not None:
                logger.info("[%s] Intelligence checkpoint found — skipping.", job_id)
                self._emit_progress("intelligence", 100.0, "Intelligence skipped (checkpoint found)")
            else:
                if cancel_event.is_set():
                    return self._cancelled_result(job_id, start_time)

                self._emit_progress("intelligence", 0.0, "Starting Intelligence phase")
                phase_result = self._run_intelligence(config, ingestion_result, state, cancel_event)
                if not phase_result.success:
                    return JobResult(
                        job_id=job_id,
                        status=JobStatus.FAILED,
                        output_files=[],
                        youtube_url=None,
                        duration_seconds=time.monotonic() - start_time,
                        error=phase_result.error,
                    )
                intelligence_result = state.load_checkpoint(job_id, "intelligence")
                self._emit_progress("intelligence", 100.0, "Intelligence phase complete")

            # ----------------------------------------------------------------
            # Phase 3: Production
            # ----------------------------------------------------------------
            production_result = state.load_checkpoint(job_id, "production")
            if production_result is not None:
                logger.info("[%s] Production checkpoint found — skipping.", job_id)
                self._emit_progress("production", 100.0, "Production skipped (checkpoint found)")
                video_artifact = production_result
            else:
                if cancel_event.is_set():
                    return self._cancelled_result(job_id, start_time)

                self._emit_progress("production", 0.0, "Starting Production phase")
                phase_result = self._run_production(
                    config, intelligence_result, state, cancel_event
                )
                if not phase_result.success:
                    return JobResult(
                        job_id=job_id,
                        status=JobStatus.FAILED,
                        output_files=[],
                        youtube_url=None,
                        duration_seconds=time.monotonic() - start_time,
                        error=phase_result.error,
                    )
                video_artifact = state.load_checkpoint(job_id, "production")
                self._emit_progress("production", 100.0, "Production phase complete")

            # ----------------------------------------------------------------
            # Success
            # ----------------------------------------------------------------
            self._emit_progress("pipeline", 100.0, "Pipeline complete")
            duration = time.monotonic() - start_time

            output_files = video_artifact.output_files if video_artifact else []
            youtube_url = video_artifact.youtube_url if video_artifact else None

            return JobResult(
                job_id=job_id,
                status=JobStatus.SUCCESS,
                output_files=output_files,
                youtube_url=youtube_url,
                duration_seconds=duration,
                error=None,
            )

        except Exception as exc:
            logger.exception("[%s] Unexpected error in run_pipeline: %s", job_id, exc)
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                output_files=[],
                youtube_url=None,
                duration_seconds=time.monotonic() - start_time,
                error=str(exc),
            )

    def run_phase(self, phase: str, context: PhaseContext) -> PhaseResult:
        """Execute a single pipeline phase by name.

        Args:
            phase: One of "ingestion", "intelligence", "production".
            context: PhaseContext with job_id, config, and output_dir.

        Returns:
            PhaseResult indicating success or failure.
        """
        state = StateManager(context.output_dir)
        cancel_event = self._cancel_events.get(context.job_id, threading.Event())

        if phase == "ingestion":
            ingestion_data = state.load_checkpoint(context.job_id, "ingestion")
            return self._run_ingestion(context.config, state, cancel_event)
        elif phase == "intelligence":
            ingestion_data = state.load_checkpoint(context.job_id, "ingestion")
            return self._run_intelligence(context.config, ingestion_data, state, cancel_event)
        elif phase == "production":
            intelligence_data = state.load_checkpoint(context.job_id, "intelligence")
            return self._run_production(context.config, intelligence_data, state, cancel_event)
        else:
            return PhaseResult(
                phase=phase,
                success=False,
                error=f"Unknown phase: {phase!r}",
            )

    def resume_job(self, job_id: str) -> JobResult:
        """Resume a partially completed job.

        Loads the existing PipelineConfig from the job's checkpoint directory
        and skips phases that already have checkpoints.

        Args:
            job_id: The job ID to resume.

        Returns:
            JobResult with status SUCCESS or FAILED.
        """
        # Try to load the config checkpoint
        # We need to find the output_dir — scan common locations or use a
        # dedicated "config" checkpoint saved by run_pipeline.
        # We look for a "config" checkpoint in any known output_dir.
        # The orchestrator saves the config as a checkpoint named "config".
        # We need to find the job directory; try the current working directory.
        # In practice, the caller should use run_pipeline which saves the config.
        # Here we attempt to load from a "config" checkpoint.

        # Search for the job directory under the current working directory
        cwd = Path.cwd()
        job_dir = cwd / job_id
        if not job_dir.exists():
            # Try one level up
            for candidate in cwd.iterdir():
                if candidate.is_dir():
                    sub = candidate / job_id
                    if sub.exists():
                        job_dir = sub
                        break

        if not job_dir.exists():
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                output_files=[],
                youtube_url=None,
                duration_seconds=0.0,
                error=f"Job directory not found for job_id={job_id!r}",
            )

        # The output_dir is the parent of the job directory
        output_dir = job_dir.parent
        state = StateManager(output_dir)

        # Load the saved config
        config_data = state.load_checkpoint(job_id, "config")
        if config_data is None:
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                output_files=[],
                youtube_url=None,
                duration_seconds=0.0,
                error=f"No config checkpoint found for job_id={job_id!r}",
            )

        config = PipelineConfig(**config_data)
        return self.run_pipeline(config)

    def cancel_job(self, job_id: str) -> None:
        """Signal cancellation for a running job.

        Sets the cancellation flag for the job.  Existing checkpoints are
        preserved so the job can be resumed later.

        Args:
            job_id: The job ID to cancel.
        """
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()
            logger.info("[%s] Cancellation requested.", job_id)
        else:
            # Create a pre-set event so that if run_pipeline starts later it
            # will see the cancellation immediately.
            cancel_event = threading.Event()
            cancel_event.set()
            self._cancel_events[job_id] = cancel_event
            logger.info("[%s] Cancellation flag set (job not yet started).", job_id)

    # ------------------------------------------------------------------
    # Internal phase runners
    # ------------------------------------------------------------------

    def _run_ingestion(
        self,
        config: PipelineConfig,
        state: StateManager,
        cancel_event: threading.Event,
    ) -> PhaseResult:
        """Run the Ingestion phase and save its checkpoint."""
        job_id = config.job_id
        try:
            self._emit_progress("ingestion", 10.0, "Loading pages...")

            source = PageSource(
                type=config.source.get("type", "local"),
                chapter_id=config.source.get("chapter_id"),
                paths=[Path(p) for p in config.source.get("paths", [])] or None,
            )
            ingestion_config = IngestionConfig()

            if cancel_event.is_set():
                return PhaseResult(phase="ingestion", success=False, error="Cancelled")

            self._emit_progress("ingestion", 30.0, "Detecting panels...")
            phase = IngestionPhase()
            panel_set = phase.run(source, ingestion_config)

            if cancel_event.is_set():
                return PhaseResult(phase="ingestion", success=False, error="Cancelled")

            self._emit_progress("ingestion", 90.0, f"Detected {len(panel_set.panels)} panels")
            state.save_checkpoint(job_id, "ingestion", panel_set)
            logger.info("[%s] Ingestion complete: %d panels.", job_id, len(panel_set.panels))
            return PhaseResult(phase="ingestion", success=True, error=None)

        except Exception as exc:
            logger.exception("[%s] Ingestion phase failed: %s", job_id, exc)
            return PhaseResult(phase="ingestion", success=False, error=str(exc))

    def _run_intelligence(
        self,
        config: PipelineConfig,
        ingestion_result,
        state: StateManager,
        cancel_event: threading.Event,
    ) -> PhaseResult:
        """Run the Intelligence phase and save its checkpoint."""
        job_id = config.job_id
        try:
            if ingestion_result is None:
                return PhaseResult(
                    phase="intelligence",
                    success=False,
                    error="Ingestion checkpoint not found; cannot run Intelligence phase.",
                )

            intelligence_config = IntelligenceConfig(
                llm_provider=config.llm_provider,
                llm_model=config.llm_model,
                tts_provider=config.tts_provider,
                tts_voice_id=config.tts_voice_id,
                upscale_model=config.upscale_model,
                upscale_factor=config.upscale_factor,
                language=config.language,
            )

            if cancel_event.is_set():
                return PhaseResult(phase="intelligence", success=False, error="Cancelled")

            self._emit_progress("intelligence", 10.0, "Generating script...")
            phase = IntelligencePhase()
            intelligence_result = phase.run(ingestion_result, intelligence_config)

            if cancel_event.is_set():
                return PhaseResult(phase="intelligence", success=False, error="Cancelled")

            self._emit_progress("intelligence", 90.0, "Saving intelligence checkpoint...")
            state.save_checkpoint(job_id, "intelligence", intelligence_result)
            logger.info("[%s] Intelligence complete.", job_id)
            return PhaseResult(phase="intelligence", success=True, error=None)

        except Exception as exc:
            logger.exception("[%s] Intelligence phase failed: %s", job_id, exc)
            return PhaseResult(phase="intelligence", success=False, error=str(exc))

    def _run_production(
        self,
        config: PipelineConfig,
        intelligence_result,
        state: StateManager,
        cancel_event: threading.Event,
    ) -> PhaseResult:
        """Run the Production phase and save its checkpoint."""
        job_id = config.job_id
        try:
            if intelligence_result is None:
                return PhaseResult(
                    phase="production",
                    success=False,
                    error="Intelligence checkpoint not found; cannot run Production phase.",
                )

            production_config = ProductionConfig(
                export_format=config.export_format,
                upload_youtube=config.upload_youtube,
            )

            assets = ProductionAssets(
                upscaled=intelligence_result.upscaled,
                audio_segments=intelligence_result.audio_segments,
                script=intelligence_result.script,
            )

            if cancel_event.is_set():
                return PhaseResult(phase="production", success=False, error="Cancelled")

            self._emit_progress("production", 10.0, "Assembling timeline...")
            phase = ProductionPhase(output_dir=config.output_dir)
            video_artifact = phase.run(assets, production_config)

            if cancel_event.is_set():
                return PhaseResult(phase="production", success=False, error="Cancelled")

            self._emit_progress("production", 90.0, "Saving production checkpoint...")
            state.save_checkpoint(job_id, "production", video_artifact)
            logger.info("[%s] Production complete: %s", job_id, video_artifact.output_files)
            return PhaseResult(phase="production", success=True, error=None)

        except Exception as exc:
            logger.exception("[%s] Production phase failed: %s", job_id, exc)
            return PhaseResult(phase="production", success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_progress(self, phase: str, percent: float, message: str) -> None:
        """Invoke the on_progress callback if one is registered."""
        if self._on_progress is not None:
            try:
                self._on_progress(phase, percent, message)
            except Exception as exc:
                logger.warning("on_progress callback raised: %s", exc)

    def _cancelled_result(self, job_id: str, start_time: float) -> JobResult:
        """Return a FAILED JobResult indicating cancellation."""
        return JobResult(
            job_id=job_id,
            status=JobStatus.FAILED,
            output_files=[],
            youtube_url=None,
            duration_seconds=time.monotonic() - start_time,
            error="Job cancelled by user",
        )
