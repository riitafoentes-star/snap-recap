"""
Snap Recap — Core data models.

All domain types used across the pipeline are defined here.
Dataclasses are used for plain data containers; Pydantic BaseModel
is used where field validation is required (PipelineConfig, JobResult).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    """Overall status of a pipeline job."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


# ---------------------------------------------------------------------------
# Core geometry
# ---------------------------------------------------------------------------


@dataclass
class BoundingBox:
    """Axis-aligned bounding box in pixel coordinates."""

    x: int
    y: int
    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        """Width divided by height."""
        if self.height == 0:
            return 0.0
        return self.width / self.height

    def to_16x9(self, canvas_width: int) -> "BoundingBox":
        """Return a new BoundingBox that fits *canvas_width* at 16:9 ratio.

        The box is centred on the original box's centre point.  The returned
        coordinates may be negative if the original box is smaller than the
        target canvas — callers are responsible for clamping to image bounds.

        Args:
            canvas_width: Target width in pixels (e.g. 1920).

        Returns:
            A BoundingBox with width == canvas_width and height == canvas_width * 9 / 16,
            centred on the original box's centre.
        """
        target_height = int(canvas_width * 9 / 16)
        cx = self.x + self.width // 2
        cy = self.y + self.height // 2
        new_x = cx - canvas_width // 2
        new_y = cy - target_height // 2
        return BoundingBox(x=new_x, y=new_y, width=canvas_width, height=target_height)


# ---------------------------------------------------------------------------
# Image models
# ---------------------------------------------------------------------------


@dataclass
class BubbleRegion:
    """A speech-bubble region extracted from a manga panel."""

    bbox: BoundingBox
    mask: np.ndarray  # binary mask (uint8), same spatial extent as bbox


@dataclass
class PageImage:
    """A single manga page loaded into memory."""

    data: np.ndarray          # BGR image array (H, W, 3), dtype uint8
    path: Optional[Path]      # source path, None for in-memory pages
    index: int                # 0-based page index within the chapter


@dataclass
class Panel:
    """A single manga panel extracted from a page."""

    page_index: int
    panel_index: int
    bbox: BoundingBox
    art_region: np.ndarray          # panel image with speech bubbles removed
    bubble_regions: List[BubbleRegion]
    raw_image: np.ndarray           # original panel crop before bubble separation


@dataclass
class CroppedPanel:
    """A panel that has been cropped/scaled to a 16:9 canvas."""

    image: np.ndarray       # (H, W, 3) uint8, aspect ratio 16:9
    source_panel: Panel
    scale_factor: float     # scale applied to reach the 16:9 canvas


@dataclass
class UpscaledImage:
    """A panel image that has been upscaled by an AI model."""

    image: np.ndarray           # (H, W, 3) uint8, resolution >= 1920x1080
    source_panel: CroppedPanel
    scale_factor: float         # upscale factor applied (e.g. 2.0 or 4.0)


@dataclass
class PanelSet:
    """Collection of cropped panels produced by the Ingestion phase."""

    panels: List[CroppedPanel]


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


@dataclass
class PageSource:
    """Describes where manga pages should be loaded from.

    ``type`` must be ``"mangadex"`` or ``"local"``.
    For MangaDex sources, ``chapter_id`` is required.
    For local sources, ``paths`` is required.
    """

    type: str                       # "mangadex" | "local"
    chapter_id: Optional[str]       # MangaDex chapter UUID
    paths: Optional[List[Path]]     # local image paths


# ---------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------


@dataclass
class ScriptSegment:
    """Narration segment for a single panel."""

    panel_index: int
    narration: str
    duration_hint: float    # estimated duration in seconds
    emotion: str            # e.g. "neutral" | "excited" | "dramatic"


@dataclass
class Script:
    """Full narration script for a chapter."""

    segments: List[ScriptSegment]
    total_duration_estimate: float  # sum of duration_hints, in seconds


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


@dataclass
class AudioSegment:
    """Synthesised audio for a single panel narration."""

    panel_index: int
    audio_data: bytes       # raw WAV bytes
    duration: float         # actual duration in seconds
    sample_rate: int = 44100


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


@dataclass
class KenBurnsParams:
    """Parameters for the Ken Burns (zoom-and-pan) motion effect."""

    start_zoom: float                   # e.g. 1.0
    end_zoom: float                     # e.g. 1.15
    start_pan: Tuple[float, float]      # (x%, y%) normalised to [0, 1]
    end_pan: Tuple[float, float]
    easing: str = "ease_in_out"         # "linear" | "ease_in_out"


@dataclass
class TimelineClip:
    """A single clip in the video timeline."""

    panel: UpscaledImage
    audio: AudioSegment
    start_time: float       # seconds from timeline start
    end_time: float         # seconds from timeline start
    ken_burns: KenBurnsParams


@dataclass
class Timeline:
    """Assembled video timeline ready for export."""

    clips: List[TimelineClip]
    total_duration: float           # seconds
    fps: int
    resolution: Tuple[int, int]     # (width, height), e.g. (1920, 1080)


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class IngestionConfig:
    """Configuration for the Ingestion phase."""

    target_width: int = 1920
    min_panel_area: int = 10000
    max_aspect_ratio: float = 10.0


@dataclass
class IntelligenceConfig:
    """Configuration for the Intelligence phase."""

    llm_provider: str
    llm_model: str
    tts_provider: str
    tts_voice_id: str
    upscale_model: str
    upscale_factor: int
    batch_size: int = 4
    language: str = "pt-BR"
    narration_style: str = "dramatic"


@dataclass
class ProductionConfig:
    """Configuration for the Production phase."""

    fps: int = 30
    resolution: Tuple[int, int] = (1920, 1080)
    export_format: str = "mp4"
    upload_youtube: bool = False


@dataclass
class ExportConfig:
    """Low-level export parameters passed to VideoExporter."""

    output_dir: Path
    format: str
    fps: int
    resolution: Tuple[int, int]


# ---------------------------------------------------------------------------
# PipelineConfig — Pydantic for validation
# ---------------------------------------------------------------------------


class PipelineConfig(BaseModel):
    """Top-level pipeline configuration.

    Uses Pydantic so that field types and constraints are validated at
    construction time (e.g. ``output_dir`` is coerced from str to Path).
    """

    model_config = {"arbitrary_types_allowed": True}

    job_id: str
    source: dict                # serialised PageSource (type + chapter_id/paths)
    llm_provider: str
    llm_model: str
    tts_provider: str
    tts_voice_id: str
    upscale_model: str
    upscale_factor: int
    export_format: str
    upload_youtube: bool
    output_dir: Path
    language: str


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class JobSummary:
    """Lightweight summary of a pipeline job (used by StateManager.list_jobs)."""

    job_id: str
    status: JobStatus
    phases_completed: List[str]
    created_at: str             # ISO-8601 timestamp string


@dataclass
class PhaseContext:
    """Context passed to each pipeline phase during execution."""

    job_id: str
    config: PipelineConfig
    output_dir: Path


@dataclass
class PhaseResult:
    """Result returned by a single pipeline phase."""

    phase: str
    success: bool
    error: Optional[str]


@dataclass
class IntelligenceResult:
    """Aggregated output of the Intelligence phase."""

    script: Script
    audio_segments: List[AudioSegment]
    upscaled: List[UpscaledImage]


@dataclass
class ProductionAssets:
    """Input bundle for the Production phase."""

    upscaled: List[UpscaledImage]
    audio_segments: List[AudioSegment]
    script: Script


@dataclass
class VideoArtifact:
    """Output of the Production phase."""

    output_files: List[Path]
    youtube_url: Optional[str]
    duration_seconds: float


# ---------------------------------------------------------------------------
# JobResult — Pydantic for validation
# ---------------------------------------------------------------------------


class JobResult(BaseModel):
    """Final result returned to the caller after a complete pipeline run."""

    model_config = {"arbitrary_types_allowed": True}

    job_id: str
    status: JobStatus
    output_files: List[Path]
    youtube_url: Optional[str]
    duration_seconds: float
    error: Optional[str]
