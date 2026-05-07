"""
Snap Recap — PanelDetector

Detects manga panels in a page image using OpenCV contour analysis.
"""

from __future__ import annotations

from typing import List

import cv2
import numpy as np

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import BoundingBox, BubbleRegion, PageImage, Panel

# Minimum pixel area for a region to be considered a panel
MIN_PANEL_AREA: int = 10_000

# Maximum width/height aspect ratio (filters out thin horizontal/vertical lines)
MAX_ASPECT_RATIO: float = 10.0


class PanelDetector:
    """Detects manga panels in a page image using OpenCV."""

    def detect(self, page: PageImage) -> List[Panel]:
        """Detect panels in a manga page.

        Algorithm:
        1. Convert to grayscale
        2. Binary threshold (240, THRESH_BINARY_INV) — dark borders become white
        3. Morphological close with 3×3 kernel to fill small gaps
        4. findContours (RETR_EXTERNAL, CHAIN_APPROX_SIMPLE)
        5. Filter by MIN_PANEL_AREA and MAX_ASPECT_RATIO
        6. Remove contained (nested) bounding boxes
        7. Sort by (y, x) — top-to-bottom, left-to-right reading order

        Args:
            page: A PageImage with a valid BGR numpy array.

        Returns:
            List of Panel objects, sorted in reading order, non-overlapping.
        """
        image = page.data
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Threshold: dark panel borders become white foreground
        _, binary = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)

        # Morphological close to fill small gaps between panel borders
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        bboxes: List[BoundingBox] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < MIN_PANEL_AREA:
                continue
            # Filter extreme aspect ratios (thin lines, etc.)
            aspect = w / h if h > 0 else float("inf")
            if aspect > MAX_ASPECT_RATIO:
                continue
            inv_aspect = h / w if w > 0 else float("inf")
            if inv_aspect > MAX_ASPECT_RATIO:
                continue
            bboxes.append(BoundingBox(x=x, y=y, width=w, height=h))

        # Remove bboxes that are fully contained within another bbox
        bboxes = _remove_contained(bboxes)

        # Sort by reading order: top-to-bottom, left-to-right
        bboxes.sort(key=lambda b: (b.y, b.x))

        # Build Panel objects (art_region and bubble_regions filled with defaults;
        # BubbleSeparator will populate them properly)
        panels: List[Panel] = []
        for panel_index, bbox in enumerate(bboxes):
            x, y, w, h = bbox.x, bbox.y, bbox.width, bbox.height
            # Clamp to image bounds
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(image.shape[1], x + w)
            y2 = min(image.shape[0], y + h)
            crop = image[y1:y2, x1:x2].copy()
            panels.append(
                Panel(
                    page_index=page.index,
                    panel_index=panel_index,
                    bbox=bbox,
                    art_region=crop,
                    bubble_regions=[],
                    raw_image=crop.copy(),
                )
            )

        return panels


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _remove_contained(bboxes: List[BoundingBox]) -> List[BoundingBox]:
    """Remove bounding boxes that are fully contained within another.

    A bbox A is considered contained in bbox B if B's area is strictly larger
    and A's rectangle lies entirely within B's rectangle.

    Args:
        bboxes: List of BoundingBox objects.

    Returns:
        Filtered list with contained boxes removed.
    """
    result: List[BoundingBox] = []
    for i, a in enumerate(bboxes):
        contained = False
        for j, b in enumerate(bboxes):
            if i == j:
                continue
            if _is_contained(a, b):
                contained = True
                break
        if not contained:
            result.append(a)
    return result


def _is_contained(inner: BoundingBox, outer: BoundingBox) -> bool:
    """Return True if ``inner`` is fully contained within ``outer``."""
    return (
        inner.x >= outer.x
        and inner.y >= outer.y
        and inner.x + inner.width <= outer.x + outer.width
        and inner.y + inner.height <= outer.y + outer.height
        and (inner.width * inner.height) < (outer.width * outer.height)
    )
