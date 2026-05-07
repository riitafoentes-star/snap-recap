"""
Snap Recap — ImageUpscaler

Upscales CroppedPanel images to at least 1920×1080 using Real-ESRGAN,
Waifu2x, or a cv2.resize fallback (INTER_LANCZOS4).
"""

from __future__ import annotations

import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import Optional

import cv2
import numpy as np

from models import CroppedPanel, IntelligenceConfig, UpscaledImage

logger = logging.getLogger(__name__)

# Minimum output resolution
MIN_WIDTH = 1920
MIN_HEIGHT = 1080


def _cv2_upscale(image: np.ndarray, target_width: int = MIN_WIDTH, target_height: int = MIN_HEIGHT) -> np.ndarray:
    """Upscale *image* to at least *target_width* × *target_height* using
    cv2.resize with INTER_LANCZOS4.

    Preserves aspect ratio by scaling to cover the target dimensions, then
    centre-cropping to exactly target_width × target_height.
    """
    h, w = image.shape[:2]

    # Scale to cover target
    scale = max(target_width / w, target_height / h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # Centre-crop to exact target
    x_off = (new_w - target_width) // 2
    y_off = (new_h - target_height) // 2
    cropped = resized[y_off: y_off + target_height, x_off: x_off + target_width]

    return cropped


def _try_realesrgan(image: np.ndarray, factor: int = 4) -> Optional[np.ndarray]:
    """Attempt to upscale *image* with Real-ESRGAN.

    Returns the upscaled image or None if Real-ESRGAN is unavailable or fails.
    """
    try:
        from basicsr.archs.rrdbnet_arch import RRDBNet  # type: ignore[import]
        from realesrgan import RealESRGANer  # type: ignore[import]

        model = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=23,
            num_grow_ch=32,
            scale=factor,
        )
        upsampler = RealESRGANer(
            scale=factor,
            model_path=None,  # will use default weights if available
            model=model,
            tile=0,
            tile_pad=10,
            pre_pad=0,
            half=False,
        )
        output, _ = upsampler.enhance(image, outscale=factor)
        return output
    except MemoryError:
        logger.warning("Real-ESRGAN OOM with factor %d; will retry with factor 2.", factor)
        if factor > 2:
            return _try_realesrgan(image, factor=2)
        return None
    except Exception as exc:
        logger.debug("Real-ESRGAN unavailable or failed: %s", exc)
        return None


def _try_waifu2x(image: np.ndarray, factor: int = 2) -> Optional[np.ndarray]:
    """Attempt to upscale *image* with Waifu2x.

    Returns the upscaled image or None if Waifu2x is unavailable or fails.
    """
    try:
        import waifu2x  # type: ignore[import]

        upscaler = waifu2x.Waifu2x(scale=factor)
        output = upscaler.upscale(image)
        return output
    except MemoryError:
        logger.warning("Waifu2x OOM with factor %d; will retry with factor 2.", factor)
        if factor > 2:
            return _try_waifu2x(image, factor=2)
        return None
    except Exception as exc:
        logger.debug("Waifu2x unavailable or failed: %s", exc)
        return None


class ImageUpscaler:
    """Upscales CroppedPanel images to at least 1920×1080.

    Tries the configured AI upscale model first; falls back to cv2.resize
    with INTER_LANCZOS4 if the AI model is unavailable or fails.

    Args:
        config: IntelligenceConfig with upscale_model and upscale_factor.
    """

    def __init__(self, config: IntelligenceConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upscale(self, panel: CroppedPanel, model: str = "realesrgan") -> UpscaledImage:
        """Upscale *panel* to at least 1920×1080.

        Strategy:
        1. If model == "realesrgan": try Real-ESRGAN with configured factor.
           On OOM: reduce factor to 2 and retry.
        2. If model == "waifu2x": try Waifu2x with configured factor.
           On OOM: reduce factor to 2 and retry.
        3. Fallback: cv2.resize with INTER_LANCZOS4 to reach 1920×1080.

        Args:
            panel: CroppedPanel to upscale.
            model: Upscale model name ("realesrgan" or "waifu2x").

        Returns:
            UpscaledImage with resolution >= 1920×1080.
        """
        image = panel.image
        factor = self._config.upscale_factor or 4
        upscaled: Optional[np.ndarray] = None
        actual_factor = float(factor)

        if model == "realesrgan":
            upscaled = _try_realesrgan(image, factor=factor)
            if upscaled is None and factor > 2:
                upscaled = _try_realesrgan(image, factor=2)
                actual_factor = 2.0

        elif model == "waifu2x":
            upscaled = _try_waifu2x(image, factor=factor)
            if upscaled is None and factor > 2:
                upscaled = _try_waifu2x(image, factor=2)
                actual_factor = 2.0

        else:
            logger.warning("Unknown upscale model %r; using cv2 fallback.", model)

        # Fallback: cv2.resize
        if upscaled is None:
            logger.warning(
                "AI upscale unavailable for model %r; using cv2.resize fallback.", model
            )
            upscaled = _cv2_upscale(image, MIN_WIDTH, MIN_HEIGHT)
            actual_factor = max(MIN_WIDTH / image.shape[1], MIN_HEIGHT / image.shape[0])

        # Ensure minimum resolution even after AI upscale
        h, w = upscaled.shape[:2]
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            logger.debug(
                "AI upscale result (%dx%d) below minimum; applying cv2 resize.", w, h
            )
            upscaled = _cv2_upscale(upscaled, MIN_WIDTH, MIN_HEIGHT)

        return UpscaledImage(
            image=upscaled,
            source_panel=panel,
            scale_factor=actual_factor,
        )
