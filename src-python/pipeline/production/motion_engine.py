"""
Snap Recap — MotionEngine

Applies the Ken Burns (zoom-and-pan) effect to image clips.

The engine generates a VideoClip by computing, for each frame at time t:
  1. progress = t / duration  (clamped to [0, 1])
  2. optional easing applied to progress
  3. zoom = lerp(start_zoom, end_zoom, progress)
  4. pan_x, pan_y = lerp(start_pan, end_pan, progress)
  5. crop the frame according to zoom/pan, then resize back to original size

Loop invariant: zoom(t) ∈ [start_zoom, end_zoom] for all t.
"""

from __future__ import annotations

import logging
from typing import Callable

import cv2
import numpy as np

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import KenBurnsParams

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class MotionEngine:
    """Applies Ken Burns effect to image clips.

    Preconditions:
        - clip.duration > 0
        - 1.0 <= params.start_zoom <= params.end_zoom <= 2.0
        - All pan values in [0.0, 1.0]

    Postconditions:
        - result.duration == clip.duration
        - result.size == clip.size
        - zoom(t) ∈ [start_zoom, end_zoom] for all frames
    """

    def apply_ken_burns(
        self,
        clip: "ImageClip",
        params: KenBurnsParams,
        fps: int = 30,
    ) -> "VideoClip":
        """Apply Ken Burns effect to an ImageClip.

        Args:
            clip: Source ImageClip (must have .duration, .size, .get_frame()).
            params: KenBurnsParams controlling zoom and pan.
            fps: Frames per second for the output VideoClip.

        Returns:
            A VideoClip with the Ken Burns effect applied.
        """
        # Import moviepy lazily so the module can be imported without moviepy
        # installed (tests mock the clip object directly).
        try:
            from moviepy.editor import VideoClip as _VideoClip
        except ImportError:
            from moviepy.video.VideoClip import VideoClip as _VideoClip

        duration = clip.duration

        def make_frame(t: float) -> np.ndarray:
            return _apply_ken_burns_frame(clip, params, t, duration)

        result = _VideoClip(make_frame, duration=duration)
        result = result.set_fps(fps)
        return result


# ---------------------------------------------------------------------------
# Frame-level computation (pure, testable without moviepy)
# ---------------------------------------------------------------------------


def _apply_ken_burns_frame(
    clip: "ImageClip",
    params: KenBurnsParams,
    t: float,
    duration: float,
) -> np.ndarray:
    """Compute a single Ken Burns frame at time *t*.

    Args:
        clip: Source clip with .get_frame(t) and .size (w, h).
        params: KenBurnsParams.
        t: Current time in seconds.
        duration: Total clip duration in seconds.

    Returns:
        RGB numpy array (H, W, 3) uint8.
    """
    # Clamp progress to [0, 1] to handle floating-point edge cases
    if duration <= 0:
        progress = 0.0
    else:
        progress = max(0.0, min(1.0, t / duration))

    # Apply easing
    if params.easing == "ease_in_out":
        eased = ease_in_out_cubic(progress)
    else:
        eased = progress  # linear

    # Interpolate zoom and pan
    zoom = _lerp(params.start_zoom, params.end_zoom, eased)
    pan_x = _lerp(params.start_pan[0], params.end_pan[0], eased)
    pan_y = _lerp(params.start_pan[1], params.end_pan[1], eased)

    # Clamp zoom to [start_zoom, end_zoom] — loop invariant
    zoom = max(params.start_zoom, min(params.end_zoom, zoom))

    frame = clip.get_frame(t)
    h, w = frame.shape[:2]

    # Compute crop region
    crop_w = max(1, int(w / zoom))
    crop_h = max(1, int(h / zoom))

    # pan_x/pan_y in [0, 1] control where within the available space we crop
    max_x = w - crop_w
    max_y = h - crop_h
    x = int(max_x * pan_x)
    y = int(max_y * pan_y)

    # Clamp to valid bounds
    x = max(0, min(x, max_x))
    y = max(0, min(y, max_y))

    cropped = frame[y : y + crop_h, x : x + crop_w]

    # Resize back to original dimensions
    resized = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
    return resized


def compute_ken_burns_zoom(
    params: KenBurnsParams,
    t: float,
    duration: float,
) -> float:
    """Compute the zoom value for a given time without needing a clip.

    Useful for property-based testing.

    Args:
        params: KenBurnsParams.
        t: Current time in seconds.
        duration: Total clip duration in seconds.

    Returns:
        Zoom value clamped to [start_zoom, end_zoom].
    """
    if duration <= 0:
        progress = 0.0
    else:
        progress = max(0.0, min(1.0, t / duration))

    if params.easing == "ease_in_out":
        eased = ease_in_out_cubic(progress)
    else:
        eased = progress

    zoom = _lerp(params.start_zoom, params.end_zoom, eased)
    return max(params.start_zoom, min(params.end_zoom, zoom))


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


def ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out function.

    Maps t ∈ [0, 1] to a smooth S-curve:
        f(t) = 4t³           for t < 0.5
        f(t) = 1 - (-2t+2)³/2  for t >= 0.5

    Args:
        t: Progress value in [0, 1].

    Returns:
        Eased value in [0, 1].
    """
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        return 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between *a* and *b* at parameter *t*.

    Args:
        a: Start value.
        b: End value.
        t: Interpolation parameter in [0, 1].

    Returns:
        a + (b - a) * t
    """
    return a + (b - a) * t
