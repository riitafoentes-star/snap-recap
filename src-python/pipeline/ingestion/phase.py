"""
Snap Recap — IngestionPhase

Orchestrates the full ingestion pipeline:
  PageDownloader → PanelDetector → BubbleSeparator → SmartCropper
"""

from __future__ import annotations

from typing import List

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import CroppedPanel, IngestionConfig, PageSource, PanelSet

from .bubble_separator import BubbleSeparator
from .page_downloader import PageDownloader
from .panel_detector import PanelDetector
from .smart_cropper import SmartCropper


class IngestionPhase:
    """Orchestrates the Ingestion phase of the pipeline."""

    def __init__(self) -> None:
        self._downloader = PageDownloader()
        self._detector = PanelDetector()
        self._separator = BubbleSeparator()
        self._cropper = SmartCropper()

    def run(self, source: PageSource, config: IngestionConfig) -> PanelSet:
        """Run the full ingestion pipeline.

        Steps:
        1. Download/load pages via PageDownloader
        2. For each page: detect panels → separate bubbles → crop to 16:9
        3. Return PanelSet with all CroppedPanels

        Args:
            source: PageSource describing where to load pages from.
            config: IngestionConfig with target dimensions and filter thresholds.

        Returns:
            PanelSet containing all cropped panels in reading order.
        """
        # Step 1: Load pages
        if source.type == "mangadex":
            if not source.chapter_id:
                raise ValueError("PageSource.chapter_id is required for MangaDex sources")
            pages = self._downloader.download_chapter(source.chapter_id)
        elif source.type == "local":
            if not source.paths:
                raise ValueError("PageSource.paths is required for local sources")
            pages = self._downloader.from_local(source.paths)
        else:
            raise ValueError(f"Unknown PageSource type: {source.type!r}")

        # Step 2: Process each page
        all_panels: List[CroppedPanel] = []
        for page in pages:
            # Detect panels
            panels = self._detector.detect(page)

            # Separate bubbles from art
            panels = self._separator.separate(page, panels)

            # Crop each panel to 16:9
            for panel in panels:
                cropped = self._cropper.crop_to_16x9(panel, target_width=config.target_width)
                all_panels.append(cropped)

        return PanelSet(panels=all_panels)
