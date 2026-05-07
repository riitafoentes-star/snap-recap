"""
Snap Recap — ProductionPhase

Orchestrates the Production pipeline:
  TimelineAssembler → MotionEngine → SubtitleBurner → VideoExporter
  (→ YouTubeUploader if config.upload_youtube)

Returns a VideoArtifact with the paths of all exported files and,
optionally, the YouTube URL.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import (
    ExportConfig,
    ProductionAssets,
    ProductionConfig,
    VideoArtifact,
)
from pipeline.production.timeline_assembler import TimelineAssembler
from pipeline.production.motion_engine import MotionEngine
from pipeline.production.subtitle_burner import SubtitleBurner
from pipeline.production.video_exporter import VideoExporter
from pipeline.production.youtube_uploader import YouTubeUploader

logger = logging.getLogger(__name__)


class ProductionPhase:
    """Orchestrates the Production phase of the pipeline.

    Steps:
    1. Assemble timeline with TimelineAssembler.
    2. Apply Ken Burns effect with MotionEngine.
    3. Burn subtitles with SubtitleBurner.
    4. Export with VideoExporter (MP4 and/or OTIOZ based on config).
    5. Upload to YouTube if config.upload_youtube is True.
    6. Return VideoArtifact.

    Args:
        output_dir: Directory where exported files will be written.
            Defaults to the current working directory.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self._output_dir = Path(output_dir) if output_dir else Path.cwd()

    def run(
        self,
        assets: ProductionAssets,
        config: ProductionConfig,
        youtube_credentials=None,
        youtube_metadata=None,
    ) -> VideoArtifact:
        """Run the Production phase.

        Args:
            assets: ProductionAssets with upscaled images, audio, and script.
            config: ProductionConfig controlling fps, resolution, format, etc.
            youtube_credentials: Optional OAuthCredentials for YouTube upload.
            youtube_metadata: Optional VideoMetadata for YouTube upload.

        Returns:
            VideoArtifact with output file paths, optional YouTube URL,
            and total duration in seconds.
        """
        # ------------------------------------------------------------------
        # Step 1: Assemble timeline
        # ------------------------------------------------------------------
        logger.info("Assembling timeline for %d panels...", len(assets.upscaled))
        assembler = TimelineAssembler()
        timeline = assembler.assemble(
            panels=assets.upscaled,
            audio=assets.audio_segments,
            script=assets.script,
        )
        logger.info(
            "Timeline assembled: %d clips, %.2fs total.",
            len(timeline.clips),
            timeline.total_duration,
        )

        # ------------------------------------------------------------------
        # Step 2: Apply Ken Burns effect
        # ------------------------------------------------------------------
        logger.info("Applying Ken Burns effect...")
        motion_engine = MotionEngine()
        video_clip = self._apply_ken_burns_to_timeline(motion_engine, timeline)
        logger.info("Ken Burns effect applied.")

        # ------------------------------------------------------------------
        # Step 3: Burn subtitles
        # ------------------------------------------------------------------
        logger.info("Burning subtitles...")
        burner = SubtitleBurner()
        try:
            video_clip = burner.transcribe_and_burn(video_clip, assets.audio_segments)
            logger.info("Subtitles burned.")
        except Exception as exc:
            logger.warning("Subtitle burning failed: %s — continuing without subtitles.", exc)

        # ------------------------------------------------------------------
        # Step 4: Export
        # ------------------------------------------------------------------
        exporter = VideoExporter()
        output_files: List[Path] = []
        export_format = config.export_format.lower()

        export_config = ExportConfig(
            output_dir=self._output_dir,
            format=export_format,
            fps=config.fps,
            resolution=config.resolution,
        )

        if export_format in ("mp4", "both"):
            mp4_path = self._output_dir / "output.mp4"
            logger.info("Exporting MP4 to %s...", mp4_path)
            try:
                mp4_path = exporter.export_mp4(timeline, mp4_path, export_config)
                output_files.append(mp4_path)
                logger.info("MP4 export complete: %s", mp4_path)
            except Exception as exc:
                logger.error("MP4 export failed: %s", exc)
                raise

        if export_format in ("otioz", "both"):
            otioz_path = self._output_dir / "output.otioz"
            logger.info("Exporting OTIOZ to %s...", otioz_path)
            try:
                otioz_path = exporter.export_otioz(timeline, otioz_path)
                output_files.append(otioz_path)
                logger.info("OTIOZ export complete: %s", otioz_path)
            except Exception as exc:
                logger.error("OTIOZ export failed: %s", exc)
                raise

        # ------------------------------------------------------------------
        # Step 5: YouTube upload (optional)
        # ------------------------------------------------------------------
        youtube_url: Optional[str] = None
        if config.upload_youtube:
            if youtube_credentials is None or youtube_metadata is None:
                logger.warning(
                    "upload_youtube=True but no credentials/metadata provided; skipping upload."
                )
            else:
                # Find the MP4 to upload
                mp4_files = [p for p in output_files if str(p).endswith(".mp4")]
                if not mp4_files:
                    logger.warning("No MP4 file found for YouTube upload; skipping.")
                else:
                    uploader = YouTubeUploader()
                    try:
                        youtube_url = uploader.upload(
                            mp4_files[0], youtube_metadata, youtube_credentials
                        )
                        logger.info("YouTube upload complete: %s", youtube_url)
                    except Exception as exc:
                        logger.error("YouTube upload failed: %s", exc)
                        # Non-fatal: return artifact without URL

        return VideoArtifact(
            output_files=output_files,
            youtube_url=youtube_url,
            duration_seconds=timeline.total_duration,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_ken_burns_to_timeline(self, motion_engine: "MotionEngine", timeline) -> "VideoClip":
        """Apply Ken Burns to each clip and concatenate into a single VideoClip.

        Args:
            motion_engine: MotionEngine instance.
            timeline: Assembled Timeline.

        Returns:
            Concatenated VideoClip with Ken Burns applied to all clips.
        """
        try:
            from moviepy.editor import ImageClip, concatenate_videoclips
        except ImportError:
            from moviepy.video.VideoClip import ImageClip
            from moviepy.video.compositing.concatenate import concatenate_videoclips

        clips = []
        for tc in timeline.clips:
            duration = tc.end_time - tc.start_time
            # Create an ImageClip from the upscaled panel image
            # moviepy expects RGB; our images are BGR (OpenCV convention)
            import cv2
            rgb_image = cv2.cvtColor(tc.panel.image, cv2.COLOR_BGR2RGB)
            img_clip = ImageClip(rgb_image, duration=duration)
            img_clip = img_clip.set_fps(timeline.fps)

            # Apply Ken Burns
            kb_clip = motion_engine.apply_ken_burns(img_clip, tc.ken_burns, fps=timeline.fps)
            clips.append(kb_clip)

        if not clips:
            raise RuntimeError("No clips to concatenate.")

        return concatenate_videoclips(clips, method="compose")
