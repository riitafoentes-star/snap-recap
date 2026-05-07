"""
Snap Recap — TimelineAssembler

Assembles a Timeline from upscaled panels, audio segments, and a script.
Each panel gets a TimelineClip with start/end times derived from audio
durations, plus randomly-generated KenBurnsParams.
"""

from __future__ import annotations

import logging
import random
from typing import List

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import (
    AudioSegment,
    KenBurnsParams,
    Script,
    Timeline,
    TimelineClip,
    UpscaledImage,
)

logger = logging.getLogger(__name__)


class TimelineAssembler:
    """Assembles a Timeline from upscaled panels, audio segments, and a script.

    Preconditions:
        - len(panels) == len(audio) == len(script.segments)
        - All audio segments have duration > 0

    Postconditions:
        - timeline.clips has exactly len(panels) clips
        - No two clips overlap: clip[i].end_time == clip[i+1].start_time
        - timeline.total_duration == sum(a.duration for a in audio)
        - timeline.fps == 30, timeline.resolution == (1920, 1080)
    """

    def assemble(
        self,
        panels: List[UpscaledImage],
        audio: List[AudioSegment],
        script: Script,
    ) -> Timeline:
        """Assemble a Timeline from panels, audio, and script.

        Args:
            panels: Upscaled panel images, one per clip.
            audio: Audio segments, one per clip.
            script: Narration script with one segment per panel.

        Returns:
            A Timeline with one TimelineClip per panel, no overlaps,
            fps=30, resolution=(1920, 1080).

        Raises:
            ValueError: If the lengths of panels, audio, and script.segments
                do not all match.
        """
        n = len(panels)
        if len(audio) != n or len(script.segments) != n:
            raise ValueError(
                f"panels ({n}), audio ({len(audio)}), and script.segments "
                f"({len(script.segments)}) must all have the same length."
            )

        clips: List[TimelineClip] = []
        current_time = 0.0

        for i in range(n):
            start_time = current_time
            end_time = current_time + audio[i].duration
            ken_burns = _generate_ken_burns_params()

            clip = TimelineClip(
                panel=panels[i],
                audio=audio[i],
                start_time=start_time,
                end_time=end_time,
                ken_burns=ken_burns,
            )
            clips.append(clip)
            current_time = end_time  # no gap, no overlap

        total_duration = sum(a.duration for a in audio)

        logger.info(
            "Timeline assembled: %d clips, total_duration=%.2fs",
            n,
            total_duration,
        )

        return Timeline(
            clips=clips,
            total_duration=total_duration,
            fps=30,
            resolution=(1920, 1080),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _generate_ken_burns_params(
    rng: random.Random | None = None,
) -> KenBurnsParams:
    """Generate random KenBurnsParams for a clip.

    Zoom range: [1.0, 1.15].
    Pan range: [0.0, 1.0] for both axes.
    Easing: randomly "linear" or "ease_in_out".

    Args:
        rng: Optional Random instance for reproducibility in tests.

    Returns:
        KenBurnsParams with start_zoom=1.0, end_zoom in [1.0, 1.15],
        and random pan values.
    """
    r = rng or random
    start_zoom = 1.0
    end_zoom = round(1.0 + r.uniform(0.0, 0.15), 4)
    start_pan = (round(r.uniform(0.0, 1.0), 4), round(r.uniform(0.0, 1.0), 4))
    end_pan = (round(r.uniform(0.0, 1.0), 4), round(r.uniform(0.0, 1.0), 4))
    easing = r.choice(["linear", "ease_in_out"])

    return KenBurnsParams(
        start_zoom=start_zoom,
        end_zoom=end_zoom,
        start_pan=start_pan,
        end_pan=end_pan,
        easing=easing,
    )
