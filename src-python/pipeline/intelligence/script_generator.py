"""
Snap Recap — ScriptGenerator

Generates a narration Script from a PanelSet by calling an LLMProvider.
Panels are processed in batches; each batch builds a prompt with base64-encoded
images and the context of the last 3 generated segments.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import List, Optional, Any

import cv2
import numpy as np

from models import (
    CroppedPanel,
    IntelligenceConfig,
    PanelSet,
    Script,
    ScriptSegment,
)
from providers.base import LLMProvider

logger = logging.getLogger(__name__)


def _encode_image_b64(image: np.ndarray) -> str:
    """Encode a numpy BGR image as a base64 PNG string."""
    success, buf = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Failed to encode image as PNG")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def _build_prompt(
    images_b64: List[str],
    language: str,
    style: str,
    context_segments: List[ScriptSegment],
) -> list[dict]:
    """Build the messages list for the LLM call.

    Returns a list of message dicts with role/content suitable for
    LLMProvider.complete().
    """
    context_text = ""
    if context_segments:
        context_lines = []
        for seg in context_segments:
            context_lines.append(
                f"- Panel {seg.panel_index}: \"{seg.narration}\" ({seg.emotion})"
            )
        context_text = (
            "\n\nContext from previous panels (for narrative continuity):\n"
            + "\n".join(context_lines)
        )

    n = len(images_b64)
    system_content = (
        f"You are a professional manga/manhwa narrator. "
        f"Generate narration in {language} with a {style} style. "
        f"Respond ONLY with a valid JSON array of exactly {n} objects. "
        f"Each object must have: "
        f"\"narration\" (non-empty string), "
        f"\"duration_hint\" (float, estimated seconds to read aloud), "
        f"\"emotion\" (one of: neutral, excited, dramatic, sad, tense). "
        f"Do not include any text outside the JSON array."
    )

    # Build user content: text description + images
    user_parts: list[Any] = []
    user_parts.append({
        "type": "text",
        "text": (
            f"Generate narration for the following {n} manga panel(s) in order.{context_text}\n\n"
            f"Return a JSON array with exactly {n} elements."
        ),
    })
    for i, b64 in enumerate(images_b64):
        user_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_parts},
    ]


def _parse_llm_response(response: str, batch: List[CroppedPanel], batch_start_index: int) -> List[ScriptSegment]:
    """Parse the LLM JSON response into ScriptSegments.

    If parsing fails or the response has wrong length, generates fallback
    segments with placeholder narration.
    """
    segments: List[ScriptSegment] = []

    try:
        # Strip markdown code fences if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array, got {type(data).__name__}")

        for i, item in enumerate(data):
            if i >= len(batch):
                break
            panel = batch[i]
            narration = str(item.get("narration", "")).strip()
            if not narration:
                narration = f"Panel {batch_start_index + i + 1}."
            duration_hint = float(item.get("duration_hint", max(2.0, len(narration) / 15)))
            emotion = str(item.get("emotion", "neutral")).strip()
            if emotion not in ("neutral", "excited", "dramatic", "sad", "tense"):
                emotion = "neutral"
            segments.append(ScriptSegment(
                panel_index=batch_start_index + i,
                narration=narration,
                duration_hint=duration_hint,
                emotion=emotion,
            ))

    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("Failed to parse LLM response: %s. Using fallback segments.", exc)
        segments = []

    # Fill any missing segments with fallbacks
    while len(segments) < len(batch):
        i = len(segments)
        panel_idx = batch_start_index + i
        segments.append(ScriptSegment(
            panel_index=panel_idx,
            narration=f"Panel {panel_idx + 1}.",
            duration_hint=2.0,
            emotion="neutral",
        ))

    return segments[: len(batch)]


class ScriptGenerator:
    """Generates a narration Script from a PanelSet using an LLMProvider.

    Args:
        config: IntelligenceConfig with batch_size, language, narration_style.
        fallback_provider: Optional secondary LLMProvider used when the primary
            provider fails with a timeout or quota error.
    """

    def __init__(
        self,
        config: IntelligenceConfig,
        fallback_provider: Optional[LLMProvider] = None,
    ) -> None:
        self._config = config
        self._fallback = fallback_provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, panels: PanelSet, prompt: str, model: LLMProvider) -> Script:
        """Generate a Script for all panels in *panels*.

        Processing steps:
        1. Split panels into batches of ``config.batch_size``.
        2. For each batch, encode images as base64 and build a prompt that
           includes the last 3 generated segments as context.
        3. Call ``model.complete(messages, config)`` to get the LLM response.
        4. Parse the response into ScriptSegments (one per panel in the batch).
        5. If the primary model fails, try ``fallback_provider`` if configured.
        6. Return a Script with ``len(segments) == len(panels)`` and all
           narrations non-empty.

        Args:
            panels: PanelSet produced by the Ingestion phase.
            prompt: User-supplied style/context prompt (appended to system prompt).
            model: Primary LLMProvider to use for generation.

        Returns:
            Script with one ScriptSegment per panel.

        Raises:
            RuntimeError: If both primary and fallback providers fail.
        """
        panel_list = panels.panels
        batch_size = self._config.batch_size or 4
        all_segments: List[ScriptSegment] = []

        # Build LLM config object
        llm_config = _LLMConfig(max_tokens=2048, temperature=0.7)

        for batch_start in range(0, len(panel_list), batch_size):
            batch = panel_list[batch_start: batch_start + batch_size]

            # Encode images
            images_b64 = []
            for cropped in batch:
                try:
                    b64 = _encode_image_b64(cropped.image)
                except Exception as exc:
                    logger.warning("Failed to encode panel image: %s", exc)
                    # Use a tiny blank image as fallback
                    blank = np.zeros((9, 16, 3), dtype=np.uint8)
                    b64 = _encode_image_b64(blank)
                images_b64.append(b64)

            # Build prompt with context of last 3 segments
            context = all_segments[-3:] if all_segments else []
            messages = _build_prompt(
                images_b64=images_b64,
                language=self._config.language,
                style=self._config.narration_style,
                context_segments=context,
            )

            # Append user-supplied prompt hint to the last user message
            if prompt:
                messages[-1]["content"][-1 if isinstance(messages[-1]["content"], list) else 0]
                # Append as additional text part
                if isinstance(messages[-1]["content"], list):
                    messages[-1]["content"].append({
                        "type": "text",
                        "text": f"\nAdditional style guidance: {prompt}",
                    })

            # Call LLM (with fallback on failure)
            response = self._call_with_fallback(model, messages, llm_config)

            # Parse response
            batch_segments = _parse_llm_response(response, batch, batch_start)
            all_segments.extend(batch_segments)

        # Guarantee one segment per panel
        assert len(all_segments) == len(panel_list), (
            f"Segment count mismatch: {len(all_segments)} != {len(panel_list)}"
        )

        total_duration = sum(s.duration_hint for s in all_segments)
        return Script(segments=all_segments, total_duration_estimate=total_duration)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_with_fallback(
        self,
        model: LLMProvider,
        messages: list,
        config: Any,
    ) -> str:
        """Call the primary model; on failure try the fallback provider."""
        try:
            return model.complete(messages, config)
        except Exception as primary_exc:
            logger.warning(
                "Primary LLM provider failed: %s. Trying fallback.", primary_exc
            )
            if self._fallback is not None:
                try:
                    return self._fallback.complete(messages, config)
                except Exception as fallback_exc:
                    raise RuntimeError(
                        f"Both primary and fallback LLM providers failed. "
                        f"Primary: {primary_exc}. Fallback: {fallback_exc}"
                    ) from fallback_exc
            # No fallback — return empty string so parse produces fallback segments
            logger.error("No fallback provider configured; using placeholder segments.")
            return "[]"


class _LLMConfig:
    """Minimal LLMConfig implementation for internal use."""

    def __init__(self, max_tokens: int = 2048, temperature: float = 0.7) -> None:
        self.max_tokens = max_tokens
        self.temperature = temperature
