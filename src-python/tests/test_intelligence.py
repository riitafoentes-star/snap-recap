"""
Tests for the Intelligence pipeline components.

Covers:
- Unit tests for ScriptGenerator with mock LLMProvider
- Unit tests for VoiceGenerator with mock TTSProvider
- Unit tests for ImageUpscaler (fallback path)
- Property 9:  Script has one segment per panel (hypothesis)
- Property 10: Audio has one segment per ScriptSegment (hypothesis)
- Integration test for IntelligencePhase with all mocks
"""

from __future__ import annotations

import io
import json
import sys
import os
import wave

# Ensure src-python is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import List
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from models import (
    AudioSegment,
    BoundingBox,
    CroppedPanel,
    IntelligenceConfig,
    IntelligenceResult,
    Panel,
    PanelSet,
    Script,
    ScriptSegment,
    UpscaledImage,
)
from pipeline.intelligence.image_upscaler import ImageUpscaler, _cv2_upscale
from pipeline.intelligence.script_generator import ScriptGenerator, _parse_llm_response
from pipeline.intelligence.voice_generator import VoiceGenerator, _parse_wav_duration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_cropped_panel(
    width: int = 160,
    height: int = 90,
    page_index: int = 0,
    panel_index: int = 0,
) -> CroppedPanel:
    """Create a minimal CroppedPanel with a solid-colour image."""
    image = np.full((height, width, 3), 128, dtype=np.uint8)
    bbox = BoundingBox(x=0, y=0, width=width, height=height)
    panel = Panel(
        page_index=page_index,
        panel_index=panel_index,
        bbox=bbox,
        art_region=image.copy(),
        bubble_regions=[],
        raw_image=image.copy(),
    )
    return CroppedPanel(image=image, source_panel=panel, scale_factor=1.0)


def make_panel_set(n: int) -> PanelSet:
    """Create a PanelSet with *n* minimal CroppedPanels."""
    return PanelSet(panels=[make_cropped_panel(panel_index=i) for i in range(n)])


def make_intelligence_config(**kwargs) -> IntelligenceConfig:
    """Create an IntelligenceConfig with sensible defaults."""
    defaults = dict(
        llm_provider="mock",
        llm_model="mock-model",
        tts_provider="mock",
        tts_voice_id="voice-001",
        upscale_model="realesrgan",
        upscale_factor=4,
        batch_size=4,
        language="en-US",
        narration_style="dramatic",
    )
    defaults.update(kwargs)
    return IntelligenceConfig(**defaults)


def make_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 44100) -> bytes:
    """Create minimal valid WAV bytes for the given duration."""
    n_frames = int(duration_seconds * sample_rate)
    samples = np.zeros(n_frames, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def make_mock_llm(response_json: list | None = None, n_panels: int = 1) -> MagicMock:
    """Create a mock LLMProvider that returns a valid JSON response."""
    if response_json is None:
        response_json = [
            {
                "narration": f"Panel {i + 1} narration.",
                "duration_hint": 2.5,
                "emotion": "neutral",
            }
            for i in range(n_panels)
        ]
    mock = MagicMock()
    mock.complete.return_value = json.dumps(response_json)
    return mock


def make_mock_tts(duration_seconds: float = 2.0) -> MagicMock:
    """Create a mock TTSProvider that returns valid WAV bytes."""
    mock = MagicMock()
    mock.synthesize.return_value = make_wav_bytes(duration_seconds)
    return mock


# ---------------------------------------------------------------------------
# Unit tests: ScriptGenerator
# ---------------------------------------------------------------------------


class TestScriptGenerator:
    """Unit tests for ScriptGenerator with a mock LLMProvider."""

    def test_returns_script_with_correct_segment_count(self):
        """generate() returns a Script with one segment per panel."""
        n = 5
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        llm = make_mock_llm(n_panels=n)

        gen = ScriptGenerator(config=config)
        script = gen.generate(panels, prompt="", model=llm)

        assert len(script.segments) == n

    def test_all_narrations_non_empty(self):
        """Every ScriptSegment must have a non-empty narration."""
        n = 3
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        llm = make_mock_llm(n_panels=n)

        gen = ScriptGenerator(config=config)
        script = gen.generate(panels, prompt="", model=llm)

        for seg in script.segments:
            assert seg.narration.strip(), f"Segment {seg.panel_index} has empty narration"

    def test_total_duration_positive(self):
        """total_duration_estimate must be > 0."""
        n = 4
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        llm = make_mock_llm(n_panels=n)

        gen = ScriptGenerator(config=config)
        script = gen.generate(panels, prompt="", model=llm)

        assert script.total_duration_estimate > 0

    def test_total_duration_equals_sum_of_hints(self):
        """total_duration_estimate == sum(s.duration_hint for s in segments)."""
        n = 3
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        llm = make_mock_llm(n_panels=n)

        gen = ScriptGenerator(config=config)
        script = gen.generate(panels, prompt="", model=llm)

        expected = sum(s.duration_hint for s in script.segments)
        assert abs(script.total_duration_estimate - expected) < 1e-9

    def test_batching_calls_llm_multiple_times(self):
        """With batch_size=2 and 5 panels, LLM is called 3 times."""
        n = 5
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=2)

        # Build a mock that returns correct-sized batches
        call_count = [0]

        def side_effect(messages, cfg):
            call_count[0] += 1
            # Determine batch size from the prompt
            # Return 2 items for first two calls, 1 for the last
            size = 2 if call_count[0] < 3 else 1
            return json.dumps([
                {"narration": f"Narration {j}", "duration_hint": 2.0, "emotion": "neutral"}
                for j in range(size)
            ])

        mock_llm = MagicMock()
        mock_llm.complete.side_effect = side_effect

        gen = ScriptGenerator(config=config)
        script = gen.generate(panels, prompt="", model=mock_llm)

        assert mock_llm.complete.call_count == 3
        assert len(script.segments) == n

    def test_fallback_provider_used_on_primary_failure(self):
        """When primary LLM fails, fallback provider is used."""
        n = 2
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)

        primary = MagicMock()
        primary.complete.side_effect = RuntimeError("quota exceeded")

        fallback = make_mock_llm(n_panels=n)

        gen = ScriptGenerator(config=config, fallback_provider=fallback)
        script = gen.generate(panels, prompt="", model=primary)

        assert len(script.segments) == n
        fallback.complete.assert_called_once()

    def test_no_fallback_uses_placeholder_segments(self):
        """When primary fails and no fallback, placeholder segments are returned."""
        n = 2
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)

        primary = MagicMock()
        primary.complete.side_effect = RuntimeError("network error")

        gen = ScriptGenerator(config=config, fallback_provider=None)
        script = gen.generate(panels, prompt="", model=primary)

        assert len(script.segments) == n
        for seg in script.segments:
            assert seg.narration.strip()

    def test_malformed_json_uses_fallback_segments(self):
        """Malformed LLM response produces fallback segments (non-empty narration)."""
        n = 3
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)

        mock_llm = MagicMock()
        mock_llm.complete.return_value = "this is not json at all"

        gen = ScriptGenerator(config=config)
        script = gen.generate(panels, prompt="", model=mock_llm)

        assert len(script.segments) == n
        for seg in script.segments:
            assert seg.narration.strip()

    def test_parse_llm_response_correct_count(self):
        """_parse_llm_response returns exactly len(batch) segments."""
        batch = [make_cropped_panel(panel_index=i) for i in range(3)]
        response = json.dumps([
            {"narration": f"N{i}", "duration_hint": 2.0, "emotion": "neutral"}
            for i in range(3)
        ])
        segments = _parse_llm_response(response, batch, batch_start_index=0)
        assert len(segments) == 3

    def test_parse_llm_response_fills_missing(self):
        """_parse_llm_response fills missing segments with placeholders."""
        batch = [make_cropped_panel(panel_index=i) for i in range(4)]
        # Only 2 items in response
        response = json.dumps([
            {"narration": "A", "duration_hint": 2.0, "emotion": "neutral"},
            {"narration": "B", "duration_hint": 2.0, "emotion": "neutral"},
        ])
        segments = _parse_llm_response(response, batch, batch_start_index=0)
        assert len(segments) == 4
        for seg in segments:
            assert seg.narration.strip()

    def test_single_panel(self):
        """generate() works correctly with a single panel."""
        panels = make_panel_set(1)
        config = make_intelligence_config(batch_size=4)
        llm = make_mock_llm(n_panels=1)

        gen = ScriptGenerator(config=config)
        script = gen.generate(panels, prompt="", model=llm)

        assert len(script.segments) == 1
        assert script.segments[0].narration.strip()


# ---------------------------------------------------------------------------
# Property 9: Script has one segment per panel
# **Validates: Requirements 5.1, 5.2**
# ---------------------------------------------------------------------------


@given(n_panels=st.integers(min_value=1, max_value=20))
@settings(max_examples=30)
def test_property9_script_has_one_segment_per_panel(n_panels):
    """
    **Validates: Requirements 5.1, 5.2**

    Property 9: For any non-empty PanelSet, the Script returned by
    ScriptGenerator has exactly len(panels) ScriptSegments, all with
    non-empty narration.
    """
    panels = make_panel_set(n_panels)
    config = make_intelligence_config(batch_size=4)
    llm = make_mock_llm(n_panels=n_panels)

    gen = ScriptGenerator(config=config)
    script = gen.generate(panels, prompt="", model=llm)

    assert len(script.segments) == n_panels, (
        f"Expected {n_panels} segments, got {len(script.segments)}"
    )
    for i, seg in enumerate(script.segments):
        assert seg.narration.strip(), (
            f"Segment {i} has empty narration"
        )


# ---------------------------------------------------------------------------
# Unit tests: VoiceGenerator
# ---------------------------------------------------------------------------


class TestVoiceGenerator:
    """Unit tests for VoiceGenerator with a mock TTSProvider."""

    def test_returns_correct_count(self):
        """synthesize() returns one AudioSegment per ScriptSegment."""
        n = 4
        script = Script(
            segments=[
                ScriptSegment(panel_index=i, narration=f"Narration {i}", duration_hint=2.0, emotion="neutral")
                for i in range(n)
            ],
            total_duration_estimate=8.0,
        )
        config = make_intelligence_config()
        tts = make_mock_tts()

        gen = VoiceGenerator(config=config)
        audio = gen.synthesize(script, tts)

        assert len(audio) == n

    def test_all_segments_are_wav_44100(self):
        """All AudioSegments must have sample_rate == 44100."""
        n = 3
        script = Script(
            segments=[
                ScriptSegment(panel_index=i, narration=f"Text {i}", duration_hint=1.5, emotion="neutral")
                for i in range(n)
            ],
            total_duration_estimate=4.5,
        )
        config = make_intelligence_config()
        tts = make_mock_tts()

        gen = VoiceGenerator(config=config)
        audio = gen.synthesize(script, tts)

        for seg in audio:
            assert seg.sample_rate == 44100, f"Expected 44100 Hz, got {seg.sample_rate}"

    def test_audio_data_is_valid_wav(self):
        """Each AudioSegment.audio_data must be parseable as WAV."""
        script = Script(
            segments=[ScriptSegment(panel_index=0, narration="Hello.", duration_hint=1.0, emotion="neutral")],
            total_duration_estimate=1.0,
        )
        config = make_intelligence_config()
        tts = make_mock_tts(duration_seconds=1.0)

        gen = VoiceGenerator(config=config)
        audio = gen.synthesize(script, tts)

        buf = io.BytesIO(audio[0].audio_data)
        with wave.open(buf, "rb") as wf:
            assert wf.getframerate() == 44100

    def test_provider_failure_raises_runtime_error(self):
        """If TTSProvider raises, VoiceGenerator raises RuntimeError with context."""
        script = Script(
            segments=[ScriptSegment(panel_index=0, narration="Hello.", duration_hint=1.0, emotion="neutral")],
            total_duration_estimate=1.0,
        )
        config = make_intelligence_config()
        tts = MagicMock()
        tts.synthesize.side_effect = ConnectionError("API unavailable")

        gen = VoiceGenerator(config=config)
        with pytest.raises(RuntimeError, match="TTS provider failed"):
            gen.synthesize(script, tts)

    def test_panel_indices_preserved(self):
        """AudioSegment.panel_index must match the corresponding ScriptSegment."""
        segments = [
            ScriptSegment(panel_index=10, narration="A", duration_hint=1.0, emotion="neutral"),
            ScriptSegment(panel_index=20, narration="B", duration_hint=1.0, emotion="neutral"),
        ]
        script = Script(segments=segments, total_duration_estimate=2.0)
        config = make_intelligence_config()
        tts = make_mock_tts()

        gen = VoiceGenerator(config=config)
        audio = gen.synthesize(script, tts)

        assert audio[0].panel_index == 10
        assert audio[1].panel_index == 20

    def test_duration_parsed_from_wav(self):
        """AudioSegment.duration is parsed from the actual WAV bytes."""
        expected_duration = 3.0
        script = Script(
            segments=[ScriptSegment(panel_index=0, narration="Long narration.", duration_hint=3.0, emotion="neutral")],
            total_duration_estimate=3.0,
        )
        config = make_intelligence_config()
        tts = MagicMock()
        tts.synthesize.return_value = make_wav_bytes(expected_duration)

        gen = VoiceGenerator(config=config)
        audio = gen.synthesize(script, tts)

        assert abs(audio[0].duration - expected_duration) < 0.1

    def test_parse_wav_duration_valid(self):
        """_parse_wav_duration returns correct duration for valid WAV."""
        wav = make_wav_bytes(2.0)
        duration, sr = _parse_wav_duration(wav)
        assert abs(duration - 2.0) < 0.01
        assert sr == 44100

    def test_parse_wav_duration_invalid_bytes(self):
        """_parse_wav_duration handles invalid bytes gracefully."""
        duration, sr = _parse_wav_duration(b"not a wav file at all")
        assert duration >= 0
        assert sr > 0


# ---------------------------------------------------------------------------
# Property 10: Audio has one segment per ScriptSegment
# **Validates: Requirements 6.1, 6.3**
# ---------------------------------------------------------------------------


@given(n_segments=st.integers(min_value=1, max_value=20))
@settings(max_examples=30)
def test_property10_audio_has_one_segment_per_script_segment(n_segments):
    """
    **Validates: Requirements 6.1, 6.3**

    Property 10: For any valid Script, the list of AudioSegments returned by
    VoiceGenerator has exactly len(script.segments) elements, all in WAV 44.1kHz.
    """
    script = Script(
        segments=[
            ScriptSegment(
                panel_index=i,
                narration=f"Narration for panel {i}.",
                duration_hint=2.0,
                emotion="neutral",
            )
            for i in range(n_segments)
        ],
        total_duration_estimate=float(n_segments * 2),
    )
    config = make_intelligence_config()
    tts = make_mock_tts(duration_seconds=2.0)

    gen = VoiceGenerator(config=config)
    audio = gen.synthesize(script, tts)

    assert len(audio) == n_segments, (
        f"Expected {n_segments} audio segments, got {len(audio)}"
    )
    for i, seg in enumerate(audio):
        assert seg.sample_rate == 44100, (
            f"Segment {i}: expected 44100 Hz, got {seg.sample_rate}"
        )
        # Verify it's valid WAV
        buf = io.BytesIO(seg.audio_data)
        with wave.open(buf, "rb") as wf:
            assert wf.getframerate() == 44100


# ---------------------------------------------------------------------------
# Unit tests: ImageUpscaler (fallback path)
# ---------------------------------------------------------------------------


class TestImageUpscaler:
    """Unit tests for ImageUpscaler, focusing on the cv2 fallback path."""

    def test_fallback_produces_minimum_resolution(self):
        """cv2 fallback must produce an image >= 1920×1080."""
        panel = make_cropped_panel(width=160, height=90)
        config = make_intelligence_config(upscale_model="realesrgan", upscale_factor=4)

        upscaler = ImageUpscaler(config=config)
        # Force fallback by using an unknown model name
        result = upscaler.upscale(panel, model="cv2_fallback_test")

        h, w = result.image.shape[:2]
        assert w >= 1920, f"Width {w} < 1920"
        assert h >= 1080, f"Height {h} < 1080"

    def test_realesrgan_falls_back_to_cv2(self):
        """When Real-ESRGAN is unavailable, cv2 fallback is used."""
        panel = make_cropped_panel(width=320, height=180)
        config = make_intelligence_config(upscale_model="realesrgan", upscale_factor=4)

        upscaler = ImageUpscaler(config=config)
        result = upscaler.upscale(panel, model="realesrgan")

        h, w = result.image.shape[:2]
        assert w >= 1920
        assert h >= 1080

    def test_waifu2x_falls_back_to_cv2(self):
        """When Waifu2x is unavailable, cv2 fallback is used."""
        panel = make_cropped_panel(width=320, height=180)
        config = make_intelligence_config(upscale_model="waifu2x", upscale_factor=2)

        upscaler = ImageUpscaler(config=config)
        result = upscaler.upscale(panel, model="waifu2x")

        h, w = result.image.shape[:2]
        assert w >= 1920
        assert h >= 1080

    def test_source_panel_preserved(self):
        """UpscaledImage.source_panel references the original CroppedPanel."""
        panel = make_cropped_panel(width=160, height=90)
        config = make_intelligence_config()

        upscaler = ImageUpscaler(config=config)
        result = upscaler.upscale(panel, model="realesrgan")

        assert result.source_panel is panel

    def test_scale_factor_positive(self):
        """UpscaledImage.scale_factor must be > 0."""
        panel = make_cropped_panel(width=160, height=90)
        config = make_intelligence_config()

        upscaler = ImageUpscaler(config=config)
        result = upscaler.upscale(panel, model="realesrgan")

        assert result.scale_factor > 0

    def test_cv2_upscale_helper_dimensions(self):
        """_cv2_upscale produces exactly 1920×1080 output."""
        image = np.zeros((90, 160, 3), dtype=np.uint8)
        result = _cv2_upscale(image, 1920, 1080)
        assert result.shape == (1080, 1920, 3)

    def test_cv2_upscale_already_large(self):
        """_cv2_upscale handles images already larger than target."""
        image = np.zeros((2160, 3840, 3), dtype=np.uint8)
        result = _cv2_upscale(image, 1920, 1080)
        assert result.shape == (1080, 1920, 3)

    def test_upscale_returns_uint8(self):
        """UpscaledImage.image must be dtype uint8."""
        panel = make_cropped_panel(width=160, height=90)
        config = make_intelligence_config()

        upscaler = ImageUpscaler(config=config)
        result = upscaler.upscale(panel, model="realesrgan")

        assert result.image.dtype == np.uint8


# ---------------------------------------------------------------------------
# Integration test: IntelligencePhase with all mocks
# ---------------------------------------------------------------------------


class TestIntelligencePhaseIntegration:
    """Integration tests for IntelligencePhase using mock providers."""

    def _make_registry(self, n_panels: int, audio_duration: float = 2.0):
        """Create a mock PluginRegistry with mock LLM and TTS providers."""
        from plugin_registry import PluginRegistry

        registry = PluginRegistry()

        # Mock LLM provider class
        class MockLLMProvider:
            def complete(self, messages, config):
                return json.dumps([
                    {"narration": f"Panel {i} narration.", "duration_hint": audio_duration, "emotion": "neutral"}
                    for i in range(n_panels)
                ])

        # Mock TTS provider class
        class MockTTSProvider:
            def synthesize(self, text, voice_id):
                return make_wav_bytes(audio_duration)

        registry.register_llm("mock", MockLLMProvider)
        registry.register_tts("mock", MockTTSProvider)
        return registry

    def test_run_returns_intelligence_result(self):
        """IntelligencePhase.run returns an IntelligenceResult."""
        n = 3
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        registry = self._make_registry(n)

        from pipeline.intelligence.phase import IntelligencePhase
        phase = IntelligencePhase(registry=registry)
        result = phase.run(panels, config)

        assert isinstance(result, IntelligenceResult)

    def test_result_lists_have_same_length_as_panels(self):
        """script.segments, audio_segments, and upscaled all have len == n_panels."""
        n = 4
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        registry = self._make_registry(n)

        from pipeline.intelligence.phase import IntelligencePhase
        phase = IntelligencePhase(registry=registry)
        result = phase.run(panels, config)

        assert len(result.script.segments) == n
        assert len(result.audio_segments) == n
        assert len(result.upscaled) == n

    def test_upscaled_images_meet_minimum_resolution(self):
        """All upscaled images must be >= 1920×1080."""
        n = 2
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        registry = self._make_registry(n)

        from pipeline.intelligence.phase import IntelligencePhase
        phase = IntelligencePhase(registry=registry)
        result = phase.run(panels, config)

        for i, img in enumerate(result.upscaled):
            h, w = img.image.shape[:2]
            assert w >= 1920, f"Upscaled image {i}: width {w} < 1920"
            assert h >= 1080, f"Upscaled image {i}: height {h} < 1080"

    def test_audio_segments_are_wav_44100(self):
        """All audio segments must be WAV at 44.1kHz."""
        n = 2
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        registry = self._make_registry(n)

        from pipeline.intelligence.phase import IntelligencePhase
        phase = IntelligencePhase(registry=registry)
        result = phase.run(panels, config)

        for seg in result.audio_segments:
            assert seg.sample_rate == 44100

    def test_script_narrations_non_empty(self):
        """All script segments must have non-empty narration."""
        n = 3
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        registry = self._make_registry(n)

        from pipeline.intelligence.phase import IntelligencePhase
        phase = IntelligencePhase(registry=registry)
        result = phase.run(panels, config)

        for seg in result.script.segments:
            assert seg.narration.strip()

    def test_single_panel_pipeline(self):
        """IntelligencePhase works correctly with a single panel."""
        n = 1
        panels = make_panel_set(n)
        config = make_intelligence_config(batch_size=4)
        registry = self._make_registry(n)

        from pipeline.intelligence.phase import IntelligencePhase
        phase = IntelligencePhase(registry=registry)
        result = phase.run(panels, config)

        assert len(result.script.segments) == 1
        assert len(result.audio_segments) == 1
        assert len(result.upscaled) == 1

    def test_unknown_llm_provider_raises(self):
        """IntelligencePhase raises ValueError for unknown LLM provider."""
        n = 2
        panels = make_panel_set(n)
        config = make_intelligence_config(llm_provider="nonexistent_llm")

        from plugin_registry import PluginRegistry
        from pipeline.intelligence.phase import IntelligencePhase

        registry = PluginRegistry()
        # Register TTS but not LLM
        class MockTTS:
            def synthesize(self, text, voice_id):
                return make_wav_bytes(1.0)
        registry.register_tts("mock", MockTTS)

        phase = IntelligencePhase(registry=registry)
        with pytest.raises(ValueError, match="nonexistent_llm"):
            phase.run(panels, config)
