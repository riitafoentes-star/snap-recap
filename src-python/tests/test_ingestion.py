"""
Tests for the Ingestion pipeline components.

Covers:
- Property 17: Path traversal rejection (PageDownloader.from_local)
- Property 4:  from_local preserves page count
- Property 5:  PanelDetector returns non-overlapping bboxes
- Property 6:  PanelDetector returns panels in reading order
- Property 8:  SmartCropper produces 16:9 aspect ratio
- Integration: IngestionPhase with synthetic images
"""

from __future__ import annotations

import sys
import os

# Ensure src-python is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from typing import List

import cv2
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from models import (
    BoundingBox,
    IngestionConfig,
    PageImage,
    PageSource,
    Panel,
)
from pipeline.ingestion.bubble_separator import BubbleSeparator
from pipeline.ingestion.page_downloader import PageDownloader, _validate_no_traversal
from pipeline.ingestion.panel_detector import PanelDetector
from pipeline.ingestion.phase import IngestionPhase
from pipeline.ingestion.smart_cropper import SmartCropper


# ---------------------------------------------------------------------------
# Helpers — synthetic image generation
# ---------------------------------------------------------------------------


def make_blank_page(width: int = 800, height: int = 1200) -> np.ndarray:
    """Create a white page with no panels."""
    return np.full((height, width, 3), 255, dtype=np.uint8)


def make_manga_page(
    width: int = 800,
    height: int = 1200,
    panels: List[tuple[int, int, int, int]] | None = None,
) -> np.ndarray:
    """Create a synthetic manga page with black-bordered panels.

    Args:
        width: Page width in pixels.
        height: Page height in pixels.
        panels: List of (x, y, w, h) tuples for panel positions.
                Defaults to a 2×2 grid of panels.

    Returns:
        BGR numpy array (uint8).
    """
    page = np.full((height, width, 3), 255, dtype=np.uint8)

    if panels is None:
        # Default: 2×2 grid with margins
        margin = 20
        gap = 10
        pw = (width - 2 * margin - gap) // 2
        ph = (height - 2 * margin - gap) // 2
        panels = [
            (margin, margin, pw, ph),
            (margin + pw + gap, margin, pw, ph),
            (margin, margin + ph + gap, pw, ph),
            (margin + pw + gap, margin + ph + gap, pw, ph),
        ]

    for x, y, w, h in panels:
        # Draw black border (3px)
        cv2.rectangle(page, (x, y), (x + w, y + h), (0, 0, 0), 3)
        # Fill interior with a mid-gray to simulate art
        cv2.rectangle(page, (x + 3, y + 3), (x + w - 3, y + h - 3), (128, 128, 128), -1)

    return page


def make_page_image(
    width: int = 800,
    height: int = 1200,
    panels: List[tuple[int, int, int, int]] | None = None,
    index: int = 0,
) -> PageImage:
    """Create a PageImage with a synthetic manga page."""
    data = make_manga_page(width, height, panels)
    return PageImage(data=data, path=None, index=index)


def make_panel(width: int = 200, height: int = 300, page_index: int = 0, panel_index: int = 0) -> Panel:
    """Create a Panel with a solid-color art_region."""
    art = np.full((height, width, 3), 100, dtype=np.uint8)
    bbox = BoundingBox(x=0, y=0, width=width, height=height)
    return Panel(
        page_index=page_index,
        panel_index=panel_index,
        bbox=bbox,
        art_region=art,
        bubble_regions=[],
        raw_image=art.copy(),
    )


# ---------------------------------------------------------------------------
# Property 17: Path traversal rejection
# **Validates: Requirements 3.4, 14.3**
# ---------------------------------------------------------------------------


class TestPathTraversalRejection:
    """Property 17: Path traversal is rejected."""

    def test_unix_traversal_rejected(self):
        """Paths containing '../' must raise ValueError."""
        with pytest.raises(ValueError, match="traversal"):
            _validate_no_traversal(Path("../etc/passwd"))

    def test_windows_traversal_rejected(self):
        """Paths containing '..\\ ' must raise ValueError."""
        with pytest.raises(ValueError, match="traversal"):
            _validate_no_traversal(Path("..\\windows\\system32"))

    def test_nested_traversal_rejected(self):
        """Paths with traversal in the middle must raise ValueError."""
        with pytest.raises(ValueError, match="traversal"):
            _validate_no_traversal(Path("images/../../../etc/shadow"))

    def test_safe_path_accepted(self):
        """Normal paths must not raise."""
        _validate_no_traversal(Path("images/page_001.jpg"))
        _validate_no_traversal(Path("/absolute/path/to/image.png"))
        _validate_no_traversal(Path("relative/path.jpg"))

    def test_from_local_rejects_traversal(self, tmp_path):
        """PageDownloader.from_local must reject traversal paths without filesystem access."""
        downloader = PageDownloader()
        bad_path = Path("../outside/image.jpg")
        with pytest.raises(ValueError, match="traversal"):
            downloader.from_local([bad_path])

    def test_from_local_rejects_traversal_in_list(self, tmp_path):
        """from_local rejects a list where any path contains traversal."""
        # Create a valid image file
        valid_img = np.full((100, 100, 3), 200, dtype=np.uint8)
        valid_path = tmp_path / "valid.png"
        cv2.imwrite(str(valid_path), valid_img)

        downloader = PageDownloader()
        with pytest.raises(ValueError, match="traversal"):
            downloader.from_local([valid_path, Path("../bad.jpg")])


@given(
    # Build traversal paths where ".." is a standalone path component
    # e.g. "images/../etc/passwd" or "../secret"
    prefix_parts=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
            min_size=1,
            max_size=10,
        ),
        min_size=0,
        max_size=3,
    ),
    suffix_parts=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
            min_size=1,
            max_size=10,
        ),
        min_size=0,
        max_size=3,
    ),
    sep=st.sampled_from(["/", "\\"]),
)
@settings(max_examples=50)
def test_property17_traversal_always_rejected(prefix_parts, suffix_parts, sep):
    """
    **Validates: Requirements 3.4, 14.3**

    Property 17: For any path string containing '../' or '..\\ ' as a path
    component, _validate_no_traversal must raise ValueError.
    """
    # Build a path with ".." as a standalone component
    all_parts = prefix_parts + [".."] + suffix_parts
    path_str = sep.join(all_parts)
    with pytest.raises(ValueError):
        _validate_no_traversal(Path(path_str))


# ---------------------------------------------------------------------------
# Property 4: from_local preserves page count
# **Validates: Requirements 3.3**
# ---------------------------------------------------------------------------


@given(st.integers(min_value=1, max_value=10))
@settings(max_examples=20)
def test_property4_from_local_preserves_page_count(n_pages):
    """
    **Validates: Requirements 3.3**

    Property 4: For any non-empty list of valid image paths, from_local returns
    a list of PageImages with exactly the same number of elements.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        paths = []
        for i in range(n_pages):
            img = np.full((100, 80, 3), i * 20, dtype=np.uint8)
            p = tmp_path / f"page_{i:03d}.png"
            cv2.imwrite(str(p), img)
            paths.append(p)

        downloader = PageDownloader()
        pages = downloader.from_local(paths)

        assert len(pages) == n_pages, (
            f"Expected {n_pages} pages, got {len(pages)}"
        )


class TestFromLocal:
    """Unit tests for PageDownloader.from_local."""

    def test_returns_correct_count(self, tmp_path):
        """from_local returns the same number of PageImages as input paths."""
        paths = []
        for i in range(3):
            img = np.full((100, 80, 3), 128, dtype=np.uint8)
            p = tmp_path / f"page_{i}.png"
            cv2.imwrite(str(p), img)
            paths.append(p)

        downloader = PageDownloader()
        pages = downloader.from_local(paths)
        assert len(pages) == 3

    def test_images_are_bgr_uint8(self, tmp_path):
        """Loaded images are BGR numpy arrays with dtype uint8."""
        img = np.full((50, 60, 3), 200, dtype=np.uint8)
        p = tmp_path / "test.png"
        cv2.imwrite(str(p), img)

        downloader = PageDownloader()
        pages = downloader.from_local([p])
        assert pages[0].data.dtype == np.uint8
        assert pages[0].data.ndim == 3
        assert pages[0].data.shape[2] == 3

    def test_page_indices_are_sequential(self, tmp_path):
        """PageImage.index values are 0-based sequential."""
        paths = []
        for i in range(4):
            img = np.full((50, 50, 3), 100, dtype=np.uint8)
            p = tmp_path / f"p{i}.png"
            cv2.imwrite(str(p), img)
            paths.append(p)

        downloader = PageDownloader()
        pages = downloader.from_local(paths)
        for i, page in enumerate(pages):
            assert page.index == i


# ---------------------------------------------------------------------------
# Property 5: PanelDetector returns non-overlapping bboxes
# **Validates: Requirements 4.1**
# ---------------------------------------------------------------------------


def _bboxes_overlap(a: BoundingBox, b: BoundingBox) -> bool:
    """Return True if two bounding boxes have non-zero intersection area."""
    ax1, ay1 = a.x, a.y
    ax2, ay2 = a.x + a.width, a.y + a.height
    bx1, by1 = b.x, b.y
    bx2, by2 = b.x + b.width, b.y + b.height

    inter_x = max(0, min(ax2, bx2) - max(ax1, bx1))
    inter_y = max(0, min(ay2, by2) - max(ay1, by1))
    return inter_x * inter_y > 0


class TestPanelDetectorNonOverlapping:
    """Property 5: Detected panels are non-overlapping."""

    def test_2x2_grid_non_overlapping(self):
        """Panels in a 2×2 grid must not overlap."""
        page = make_page_image(width=800, height=1200)
        detector = PanelDetector()
        panels = detector.detect(page)

        bboxes = [p.bbox for p in panels]
        for i in range(len(bboxes)):
            for j in range(i + 1, len(bboxes)):
                assert not _bboxes_overlap(bboxes[i], bboxes[j]), (
                    f"Panels {i} and {j} overlap: {bboxes[i]} vs {bboxes[j]}"
                )

    def test_single_panel_non_overlapping(self):
        """A single panel trivially satisfies non-overlap."""
        page = make_page_image(
            width=400,
            height=600,
            panels=[(20, 20, 360, 560)],
        )
        detector = PanelDetector()
        panels = detector.detect(page)
        # Should detect at most 1 panel — no overlap possible
        bboxes = [p.bbox for p in panels]
        for i in range(len(bboxes)):
            for j in range(i + 1, len(bboxes)):
                assert not _bboxes_overlap(bboxes[i], bboxes[j])


def test_property5_non_overlapping_panels():
    """
    **Validates: Requirements 4.1**

    Property 5: For any valid PageImage, detected panel bboxes must not overlap.
    """
    # Test with several different panel layouts
    layouts = [
        # 2×2 grid
        None,
        # 3 panels in a row
        [(20, 20, 230, 560), (270, 20, 230, 560), (520, 20, 230, 560)],
        # 2 panels stacked
        [(20, 20, 760, 280), (20, 320, 760, 280)],
    ]

    detector = PanelDetector()
    for layout in layouts:
        page = make_page_image(width=800, height=620, panels=layout)
        panels = detector.detect(page)
        bboxes = [p.bbox for p in panels]
        for i in range(len(bboxes)):
            for j in range(i + 1, len(bboxes)):
                assert not _bboxes_overlap(bboxes[i], bboxes[j]), (
                    f"Overlap detected in layout {layout}: "
                    f"panel {i} {bboxes[i]} vs panel {j} {bboxes[j]}"
                )


# ---------------------------------------------------------------------------
# Property 6: PanelDetector returns panels in reading order
# **Validates: Requirements 4.2**
# ---------------------------------------------------------------------------


class TestPanelDetectorReadingOrder:
    """Property 6: Detected panels are in reading order (top-to-bottom, left-to-right)."""

    def test_2x2_grid_reading_order(self):
        """Panels in a 2×2 grid must be sorted top-to-bottom, left-to-right."""
        page = make_page_image(width=800, height=1200)
        detector = PanelDetector()
        panels = detector.detect(page)

        bboxes = [p.bbox for p in panels]
        for i in range(len(bboxes) - 1):
            a, b = bboxes[i], bboxes[i + 1]
            assert (a.y, a.x) <= (b.y, b.x), (
                f"Panel {i} ({a.y}, {a.x}) is not before panel {i+1} ({b.y}, {b.x})"
            )

    def test_vertical_stack_reading_order(self):
        """Vertically stacked panels must be ordered top to bottom."""
        panels_layout = [
            (20, 20, 760, 180),
            (20, 220, 760, 180),
            (20, 420, 760, 180),
        ]
        page = make_page_image(width=800, height=640, panels=panels_layout)
        detector = PanelDetector()
        panels = detector.detect(page)

        bboxes = [p.bbox for p in panels]
        if len(bboxes) >= 2:
            for i in range(len(bboxes) - 1):
                assert bboxes[i].y <= bboxes[i + 1].y, (
                    f"Panel {i} y={bboxes[i].y} is not above panel {i+1} y={bboxes[i+1].y}"
                )


def test_property6_reading_order():
    """
    **Validates: Requirements 4.2**

    Property 6: For any valid PageImage with multiple panels, detected panels
    must be sorted by (y, x) — top-to-bottom, left-to-right.
    """
    # 2×2 grid
    page = make_page_image(width=800, height=1200)
    detector = PanelDetector()
    panels = detector.detect(page)
    bboxes = [p.bbox for p in panels]

    for i in range(len(bboxes) - 1):
        a, b = bboxes[i], bboxes[i + 1]
        assert (a.y, a.x) <= (b.y, b.x), (
            f"Reading order violated: panel {i} ({a.y},{a.x}) > panel {i+1} ({b.y},{b.x})"
        )


# ---------------------------------------------------------------------------
# Property 8: SmartCropper produces 16:9 aspect ratio
# **Validates: Requirements 4.4, 4.5**
# ---------------------------------------------------------------------------


@given(
    width=st.integers(min_value=50, max_value=600),
    height=st.integers(min_value=50, max_value=800),
    target_width=st.sampled_from([640, 1280, 1920]),
)
@settings(max_examples=50)
def test_property8_crop_produces_16x9(width, height, target_width):
    """
    **Validates: Requirements 4.4, 4.5**

    Property 8: For any valid Panel, SmartCropper.crop_to_16x9 returns a
    CroppedPanel with aspect ratio 16:9 (±1px tolerance).
    """
    panel = make_panel(width=width, height=height)
    cropper = SmartCropper()
    result = cropper.crop_to_16x9(panel, target_width=target_width)

    target_height = int(target_width * 9 / 16)

    assert result.image.shape[1] == target_width, (
        f"Expected width {target_width}, got {result.image.shape[1]}"
    )
    assert result.image.shape[0] == target_height, (
        f"Expected height {target_height}, got {result.image.shape[0]}"
    )

    # Verify aspect ratio is 16:9 (±1px tolerance)
    actual_ratio = result.image.shape[1] / result.image.shape[0]
    expected_ratio = 16 / 9
    # ±1px tolerance: ratio can vary by at most 1/target_height
    tolerance = 1 / target_height + 0.001
    assert abs(actual_ratio - expected_ratio) < tolerance, (
        f"Aspect ratio {actual_ratio:.4f} deviates from 16/9={expected_ratio:.4f} "
        f"by more than tolerance {tolerance:.4f}"
    )


class TestSmartCropper:
    """Unit tests for SmartCropper."""

    def test_output_dimensions_1920(self):
        """crop_to_16x9 with default target_width=1920 produces 1920×1080."""
        panel = make_panel(width=400, height=600)
        cropper = SmartCropper()
        result = cropper.crop_to_16x9(panel, target_width=1920)
        assert result.image.shape == (1080, 1920, 3)

    def test_output_dimensions_1280(self):
        """crop_to_16x9 with target_width=1280 produces 1280×720."""
        panel = make_panel(width=400, height=600)
        cropper = SmartCropper()
        result = cropper.crop_to_16x9(panel, target_width=1280)
        assert result.image.shape == (720, 1280, 3)

    def test_scale_factor_positive(self):
        """scale_factor must be positive."""
        panel = make_panel(width=200, height=300)
        cropper = SmartCropper()
        result = cropper.crop_to_16x9(panel)
        assert result.scale_factor > 0

    def test_source_panel_preserved(self):
        """source_panel in CroppedPanel must reference the original panel."""
        panel = make_panel(width=200, height=300)
        cropper = SmartCropper()
        result = cropper.crop_to_16x9(panel)
        assert result.source_panel is panel

    def test_wide_panel(self):
        """A very wide panel (wider than 16:9) is handled correctly."""
        panel = make_panel(width=1000, height=200)
        cropper = SmartCropper()
        result = cropper.crop_to_16x9(panel, target_width=1920)
        assert result.image.shape == (1080, 1920, 3)

    def test_tall_panel(self):
        """A very tall panel (taller than 16:9) is handled correctly."""
        panel = make_panel(width=200, height=1000)
        cropper = SmartCropper()
        result = cropper.crop_to_16x9(panel, target_width=1920)
        assert result.image.shape == (1080, 1920, 3)


# ---------------------------------------------------------------------------
# Integration test: IngestionPhase with synthetic images
# ---------------------------------------------------------------------------


class TestIngestionPhaseIntegration:
    """Integration tests for IngestionPhase using synthetic manga images."""

    def test_run_with_local_source(self, tmp_path):
        """IngestionPhase.run with local source returns a PanelSet."""
        # Create synthetic manga pages
        paths = []
        for i in range(2):
            page_data = make_manga_page(width=800, height=1200)
            p = tmp_path / f"page_{i}.png"
            cv2.imwrite(str(p), page_data)
            paths.append(p)

        source = PageSource(type="local", chapter_id=None, paths=paths)
        config = IngestionConfig(target_width=1280, min_panel_area=10000, max_aspect_ratio=10.0)

        phase = IngestionPhase()
        panel_set = phase.run(source, config)

        assert panel_set is not None
        assert len(panel_set.panels) > 0

    def test_panels_have_16x9_aspect_ratio(self, tmp_path):
        """All panels in the PanelSet must have 16:9 aspect ratio."""
        page_data = make_manga_page(width=800, height=1200)
        p = tmp_path / "page.png"
        cv2.imwrite(str(p), page_data)

        source = PageSource(type="local", chapter_id=None, paths=[p])
        config = IngestionConfig(target_width=1280, min_panel_area=10000, max_aspect_ratio=10.0)

        phase = IngestionPhase()
        panel_set = phase.run(source, config)

        target_height = int(1280 * 9 / 16)  # 720
        for i, cropped in enumerate(panel_set.panels):
            h, w = cropped.image.shape[:2]
            assert w == 1280, f"Panel {i}: expected width 1280, got {w}"
            assert h == target_height, f"Panel {i}: expected height {target_height}, got {h}"

    def test_invalid_source_type_raises(self):
        """IngestionPhase.run raises ValueError for unknown source type."""
        source = PageSource(type="unknown", chapter_id=None, paths=None)
        config = IngestionConfig()
        phase = IngestionPhase()
        with pytest.raises(ValueError, match="Unknown PageSource type"):
            phase.run(source, config)

    def test_local_source_without_paths_raises(self):
        """IngestionPhase.run raises ValueError when local source has no paths."""
        source = PageSource(type="local", chapter_id=None, paths=None)
        config = IngestionConfig()
        phase = IngestionPhase()
        with pytest.raises(ValueError, match="paths is required"):
            phase.run(source, config)

    def test_mangadex_source_without_chapter_id_raises(self):
        """IngestionPhase.run raises ValueError when MangaDex source has no chapter_id."""
        source = PageSource(type="mangadex", chapter_id=None, paths=None)
        config = IngestionConfig()
        phase = IngestionPhase()
        with pytest.raises(ValueError, match="chapter_id is required"):
            phase.run(source, config)

    def test_panel_set_panels_are_cropped_panels(self, tmp_path):
        """PanelSet.panels contains CroppedPanel objects."""
        from models import CroppedPanel

        page_data = make_manga_page(width=800, height=1200)
        p = tmp_path / "page.png"
        cv2.imwrite(str(p), page_data)

        source = PageSource(type="local", chapter_id=None, paths=[p])
        config = IngestionConfig(target_width=640)

        phase = IngestionPhase()
        panel_set = phase.run(source, config)

        for panel in panel_set.panels:
            assert isinstance(panel, CroppedPanel)
