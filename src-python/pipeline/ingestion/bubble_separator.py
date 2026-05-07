"""
Snap Recap — BubbleSeparator

Separates speech bubbles from the art region in manga panels.
"""

from __future__ import annotations

from typing import List

import cv2
import numpy as np

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import BoundingBox, BubbleRegion, PageImage, Panel

# Minimum area for a region to be considered a speech bubble
_MIN_BUBBLE_AREA: int = 500

# Threshold for detecting white/light regions (speech bubbles are typically white)
_BUBBLE_THRESHOLD: int = 200


class BubbleSeparator:
    """Separates speech bubbles from the art region in manga panels."""

    def separate(self, page: PageImage, panels: List[Panel]) -> List[Panel]:
        """Detect and separate speech bubbles from each panel.

        For each panel:
        1. Extract the panel region from the page image
        2. Detect white/light elliptical regions (speech bubbles) using contour
           detection on an inverted threshold
        3. Create a binary mask of bubble regions
        4. Set art_region = panel image with bubble pixels zeroed out
        5. Set bubble_regions = list of BubbleRegion objects

        The union of art_region and bubble_regions covers the full panel bbox.

        Args:
            page: The source PageImage.
            panels: List of Panel objects detected by PanelDetector.

        Returns:
            Updated list of Panel objects with art_region and bubble_regions filled.
        """
        image = page.data
        updated: List[Panel] = []

        for panel in panels:
            bbox = panel.bbox
            x1 = max(0, bbox.x)
            y1 = max(0, bbox.y)
            x2 = min(image.shape[1], bbox.x + bbox.width)
            y2 = min(image.shape[0], bbox.y + bbox.height)

            panel_crop = image[y1:y2, x1:x2].copy()

            if panel_crop.size == 0:
                # Empty crop — return panel unchanged
                updated.append(panel)
                continue

            bubble_mask, bubble_regions = _detect_bubbles(panel_crop, x1, y1)

            # art_region: panel image with bubble pixels zeroed out
            art_region = panel_crop.copy()
            art_region[bubble_mask > 0] = 0

            updated.append(
                Panel(
                    page_index=panel.page_index,
                    panel_index=panel.panel_index,
                    bbox=panel.bbox,
                    art_region=art_region,
                    bubble_regions=bubble_regions,
                    raw_image=panel_crop,
                )
            )

        return updated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_bubbles(
    panel_crop: np.ndarray,
    offset_x: int,
    offset_y: int,
) -> tuple[np.ndarray, List[BubbleRegion]]:
    """Detect speech bubble regions in a panel crop.

    Uses a threshold on the grayscale image to find white/light regions,
    then filters by area and approximate elliptical shape.

    Args:
        panel_crop: BGR image of the panel (H, W, 3).
        offset_x: X offset of the panel within the full page (for bbox coords).
        offset_y: Y offset of the panel within the full page.

    Returns:
        Tuple of (bubble_mask, bubble_regions) where bubble_mask is a uint8
        binary mask (same H×W as panel_crop) and bubble_regions is a list of
        BubbleRegion objects.
    """
    h, w = panel_crop.shape[:2]
    gray = cv2.cvtColor(panel_crop, cv2.COLOR_BGR2GRAY)

    # Threshold: white/light regions become foreground
    _, thresh = cv2.threshold(gray, _BUBBLE_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Invert so that white speech bubbles are white foreground on black background
    # (already white after threshold, but we want to find enclosed white regions)
    # Use morphological operations to close small gaps inside bubbles
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bubble_mask = np.zeros((h, w), dtype=np.uint8)
    bubble_regions: List[BubbleRegion] = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < _MIN_BUBBLE_AREA:
            continue

        # Check approximate elliptical shape using circularity / convexity
        perimeter = cv2.arcLength(contour, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)

        # Speech bubbles tend to be fairly round (circularity > 0.3)
        if circularity < 0.3:
            continue

        # Draw the contour onto the mask
        cv2.drawContours(bubble_mask, [contour], -1, 255, thickness=cv2.FILLED)

        # Build BubbleRegion
        bx, by, bw, bh = cv2.boundingRect(contour)
        region_mask = np.zeros((bh, bw), dtype=np.uint8)
        # Shift contour to local coordinates
        shifted = contour - np.array([[[bx, by]]])
        cv2.drawContours(region_mask, [shifted], -1, 255, thickness=cv2.FILLED)

        bubble_bbox = BoundingBox(
            x=offset_x + bx,
            y=offset_y + by,
            width=bw,
            height=bh,
        )
        bubble_regions.append(BubbleRegion(bbox=bubble_bbox, mask=region_mask))

    return bubble_mask, bubble_regions
