"""
Snap Recap — SmartCropper

Crops and scales manga panels to a 16:9 aspect ratio canvas.
"""

from __future__ import annotations

import cv2
import numpy as np

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import CroppedPanel, Panel


class SmartCropper:
    """Crops and scales manga panels to a 16:9 canvas without distortion."""

    def crop_to_16x9(self, panel: Panel, target_width: int = 1920) -> CroppedPanel:
        """Crop a panel to a 16:9 aspect ratio canvas.

        Algorithm:
        1. Compute target_height = int(target_width * 9 / 16)
        2. Compute scale = max(target_width / w, target_height / h) so the
           panel covers the entire canvas (no black bars)
        3. Resize with cv2.INTER_LANCZOS4 for maximum quality
        4. Center-crop to exactly target_width × target_height

        The result has no distortion — the original content is cropped, not
        stretched.

        Args:
            panel: Panel with a valid art_region numpy array.
            target_width: Target canvas width in pixels (default 1920).

        Returns:
            CroppedPanel with image.shape == (target_height, target_width, 3)
            and aspect ratio 16:9 (±1px tolerance).
        """
        target_height = int(target_width * 9 / 16)
        source = panel.art_region

        h, w = source.shape[:2]

        # Scale so the panel covers the full 16:9 canvas
        scale = max(target_width / w, target_height / h)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))

        resized = cv2.resize(source, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        # Center crop
        x_offset = (new_w - target_width) // 2
        y_offset = (new_h - target_height) // 2

        # Clamp offsets (should never be negative given scale calculation, but be safe)
        x_offset = max(0, x_offset)
        y_offset = max(0, y_offset)

        cropped = resized[
            y_offset : y_offset + target_height,
            x_offset : x_offset + target_width,
        ]

        # If the crop is slightly short due to rounding, pad with zeros
        if cropped.shape[0] < target_height or cropped.shape[1] < target_width:
            padded = np.zeros((target_height, target_width, source.shape[2]), dtype=source.dtype)
            ch = min(cropped.shape[0], target_height)
            cw = min(cropped.shape[1], target_width)
            padded[:ch, :cw] = cropped[:ch, :cw]
            cropped = padded

        return CroppedPanel(
            image=cropped,
            source_panel=panel,
            scale_factor=scale,
        )
