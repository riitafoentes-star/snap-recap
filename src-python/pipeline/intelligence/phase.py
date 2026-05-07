"""
Snap Recap — IntelligencePhase

Orchestrates the Intelligence pipeline:
  ScriptGenerator → VoiceGenerator → ImageUpscaler (parallel)

Providers are resolved from a PluginRegistry; if no registry is supplied,
a default one is created.
"""

from __future__ import annotations

import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from models import (
    CroppedPanel,
    IntelligenceConfig,
    IntelligenceResult,
    PanelSet,
    UpscaledImage,
)

logger = logging.getLogger(__name__)


class IntelligencePhase:
    """Orchestrates the Intelligence phase of the pipeline.

    Args:
        registry: Optional PluginRegistry used to resolve LLM and TTS providers.
            If None, a default registry is created on first use.
    """

    def __init__(self, registry=None) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, panels: PanelSet, config: IntelligenceConfig) -> IntelligenceResult:
        """Run the Intelligence phase.

        Steps:
        1. Resolve LLM and TTS providers from the PluginRegistry.
        2. Generate script with ScriptGenerator.
        3. Synthesise voice with VoiceGenerator.
        4. Upscale images with ImageUpscaler (parallel via ThreadPoolExecutor).
        5. Return IntelligenceResult(script, audio_segments, upscaled).

        Args:
            panels: PanelSet from the Ingestion phase.
            config: IntelligenceConfig with provider names and settings.

        Returns:
            IntelligenceResult with script, audio_segments, and upscaled images.
        """
        from pipeline.intelligence.script_generator import ScriptGenerator
        from pipeline.intelligence.voice_generator import VoiceGenerator
        from pipeline.intelligence.image_upscaler import ImageUpscaler

        registry = self._get_registry()

        # Step 1: Resolve providers
        llm_provider = registry.resolve_llm(config.llm_provider)
        tts_provider = registry.resolve_tts(config.tts_provider)

        # Step 2: Generate script
        logger.info("Generating script for %d panels...", len(panels.panels))
        script_gen = ScriptGenerator(config=config)
        script = script_gen.generate(panels, prompt="", model=llm_provider)
        logger.info("Script generated: %d segments.", len(script.segments))

        # Step 3: Synthesise voice
        logger.info("Synthesising voice for %d segments...", len(script.segments))
        voice_gen = VoiceGenerator(config=config)
        audio_segments = voice_gen.synthesize(script, tts_provider)
        logger.info("Voice synthesis complete: %d audio segments.", len(audio_segments))

        # Step 4: Upscale images in parallel
        logger.info("Upscaling %d panels...", len(panels.panels))
        upscaler = ImageUpscaler(config=config)
        upscaled = self._upscale_parallel(upscaler, panels.panels, config.upscale_model)
        logger.info("Upscaling complete: %d images.", len(upscaled))

        return IntelligenceResult(
            script=script,
            audio_segments=audio_segments,
            upscaled=upscaled,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_registry(self):
        """Return the registry, creating a default one if needed."""
        if self._registry is None:
            from plugin_registry import PluginRegistry
            self._registry = PluginRegistry.default()
        return self._registry

    def _upscale_parallel(
        self,
        upscaler,
        panel_list: List[CroppedPanel],
        model: str,
    ) -> List[UpscaledImage]:
        """Upscale panels in parallel using ThreadPoolExecutor.

        Results are returned in the same order as *panel_list*.
        """
        results: List[Optional[UpscaledImage]] = [None] * len(panel_list)

        with ThreadPoolExecutor() as executor:
            future_to_index = {
                executor.submit(upscaler.upscale, panel, model): i
                for i, panel in enumerate(panel_list)
            }
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.error("Upscale failed for panel %d: %s", idx, exc)
                    raise

        return [r for r in results if r is not None]
