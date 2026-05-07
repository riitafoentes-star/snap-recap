"""
Unit tests for PluginRegistry and provider interfaces.

Tests cover:
- Registering and resolving LLM providers
- Registering and resolving TTS providers
- ValueError raised for unknown LLM name with descriptive message
- ValueError raised for unknown TTS name with descriptive message
- PluginRegistry.default() has all built-in providers registered
"""

from __future__ import annotations

import sys
import os

# Ensure src-python is on the path so imports work when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from plugin_registry import PluginRegistry
from providers.base import LLMProvider, TTSProvider


# ---------------------------------------------------------------------------
# Minimal stub providers for testing registration/resolution
# ---------------------------------------------------------------------------


class StubLLMProvider:
    """Minimal LLM provider stub that satisfies the LLMProvider protocol."""

    def complete(self, messages, config):
        return "stub response"


class StubTTSProvider:
    """Minimal TTS provider stub that satisfies the TTSProvider protocol."""

    def synthesize(self, text: str, voice_id: str) -> bytes:
        return b"RIFF" + b"\x00" * 36  # minimal WAV-like bytes


# ---------------------------------------------------------------------------
# PluginRegistry — LLM
# ---------------------------------------------------------------------------


class TestPluginRegistryLLM:
    def test_register_and_resolve_llm_returns_instance(self):
        """Resolving a registered LLM provider returns an instance of that class."""
        registry = PluginRegistry()
        registry.register_llm("stub", StubLLMProvider)

        provider = registry.resolve_llm("stub")

        assert isinstance(provider, StubLLMProvider)

    def test_resolve_llm_returns_new_instance_each_call(self):
        """Each call to resolve_llm returns a fresh instance."""
        registry = PluginRegistry()
        registry.register_llm("stub", StubLLMProvider)

        p1 = registry.resolve_llm("stub")
        p2 = registry.resolve_llm("stub")

        assert p1 is not p2

    def test_resolve_unknown_llm_raises_value_error(self):
        """Resolving an unregistered LLM name raises ValueError."""
        registry = PluginRegistry()
        registry.register_llm("gemini", StubLLMProvider)

        with pytest.raises(ValueError):
            registry.resolve_llm("nonexistent")

    def test_resolve_unknown_llm_error_message_contains_name(self):
        """ValueError message includes the requested (invalid) provider name."""
        registry = PluginRegistry()
        registry.register_llm("gemini", StubLLMProvider)

        with pytest.raises(ValueError, match="nonexistent"):
            registry.resolve_llm("nonexistent")

    def test_resolve_unknown_llm_error_message_lists_available(self):
        """ValueError message lists the available registered providers."""
        registry = PluginRegistry()
        registry.register_llm("gemini", StubLLMProvider)
        registry.register_llm("ollama", StubLLMProvider)

        with pytest.raises(ValueError, match="gemini"):
            registry.resolve_llm("unknown")

    def test_register_overwrites_existing_llm(self):
        """Re-registering a name replaces the previous provider."""

        class AnotherLLM:
            def complete(self, messages, config):
                return "another"

        registry = PluginRegistry()
        registry.register_llm("stub", StubLLMProvider)
        registry.register_llm("stub", AnotherLLM)

        provider = registry.resolve_llm("stub")
        assert isinstance(provider, AnotherLLM)

    def test_resolved_llm_satisfies_protocol(self):
        """Resolved LLM provider satisfies the LLMProvider runtime-checkable protocol."""
        registry = PluginRegistry()
        registry.register_llm("stub", StubLLMProvider)

        provider = registry.resolve_llm("stub")

        assert isinstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# PluginRegistry — TTS
# ---------------------------------------------------------------------------


class TestPluginRegistryTTS:
    def test_register_and_resolve_tts_returns_instance(self):
        """Resolving a registered TTS provider returns an instance of that class."""
        registry = PluginRegistry()
        registry.register_tts("stub", StubTTSProvider)

        provider = registry.resolve_tts("stub")

        assert isinstance(provider, StubTTSProvider)

    def test_resolve_tts_returns_new_instance_each_call(self):
        """Each call to resolve_tts returns a fresh instance."""
        registry = PluginRegistry()
        registry.register_tts("stub", StubTTSProvider)

        p1 = registry.resolve_tts("stub")
        p2 = registry.resolve_tts("stub")

        assert p1 is not p2

    def test_resolve_unknown_tts_raises_value_error(self):
        """Resolving an unregistered TTS name raises ValueError."""
        registry = PluginRegistry()
        registry.register_tts("elevenlabs", StubTTSProvider)

        with pytest.raises(ValueError):
            registry.resolve_tts("nonexistent")

    def test_resolve_unknown_tts_error_message_contains_name(self):
        """ValueError message includes the requested (invalid) provider name."""
        registry = PluginRegistry()
        registry.register_tts("elevenlabs", StubTTSProvider)

        with pytest.raises(ValueError, match="nonexistent"):
            registry.resolve_tts("nonexistent")

    def test_resolve_unknown_tts_error_message_lists_available(self):
        """ValueError message lists the available registered providers."""
        registry = PluginRegistry()
        registry.register_tts("elevenlabs", StubTTSProvider)
        registry.register_tts("local", StubTTSProvider)

        with pytest.raises(ValueError, match="elevenlabs"):
            registry.resolve_tts("unknown")

    def test_resolved_tts_satisfies_protocol(self):
        """Resolved TTS provider satisfies the TTSProvider runtime-checkable protocol."""
        registry = PluginRegistry()
        registry.register_tts("stub", StubTTSProvider)

        provider = registry.resolve_tts("stub")

        assert isinstance(provider, TTSProvider)


# ---------------------------------------------------------------------------
# PluginRegistry.default()
# ---------------------------------------------------------------------------


class TestPluginRegistryDefault:
    """Tests for the PluginRegistry.default() factory method."""

    def test_default_registry_has_gemini(self):
        registry = PluginRegistry.default()
        # Should not raise
        provider = registry.resolve_llm("gemini")
        assert provider is not None

    def test_default_registry_has_ollama(self):
        registry = PluginRegistry.default()
        provider = registry.resolve_llm("ollama")
        assert provider is not None

    def test_default_registry_has_groq(self):
        registry = PluginRegistry.default()
        provider = registry.resolve_llm("groq")
        assert provider is not None

    def test_default_registry_has_openrouter(self):
        registry = PluginRegistry.default()
        provider = registry.resolve_llm("openrouter")
        assert provider is not None

    def test_default_registry_has_elevenlabs(self):
        registry = PluginRegistry.default()
        provider = registry.resolve_tts("elevenlabs")
        assert provider is not None

    def test_default_registry_has_local(self):
        registry = PluginRegistry.default()
        provider = registry.resolve_tts("local")
        assert provider is not None

    def test_default_registry_llm_providers_satisfy_protocol(self):
        """All built-in LLM providers satisfy the LLMProvider protocol."""
        registry = PluginRegistry.default()
        for name in ("gemini", "ollama", "groq", "openrouter"):
            provider = registry.resolve_llm(name)
            assert isinstance(provider, LLMProvider), (
                f"Provider '{name}' does not satisfy LLMProvider protocol"
            )

    def test_default_registry_tts_providers_satisfy_protocol(self):
        """All built-in TTS providers satisfy the TTSProvider protocol."""
        registry = PluginRegistry.default()
        for name in ("elevenlabs", "local"):
            provider = registry.resolve_tts(name)
            assert isinstance(provider, TTSProvider), (
                f"Provider '{name}' does not satisfy TTSProvider protocol"
            )

    def test_default_registry_unknown_llm_raises(self):
        """default() registry still raises for unknown LLM names."""
        registry = PluginRegistry.default()
        with pytest.raises(ValueError, match="not registered"):
            registry.resolve_llm("unknown_provider")

    def test_default_registry_unknown_tts_raises(self):
        """default() registry still raises for unknown TTS names."""
        registry = PluginRegistry.default()
        with pytest.raises(ValueError, match="not registered"):
            registry.resolve_tts("unknown_provider")

    def test_default_returns_independent_registries(self):
        """Each call to default() returns an independent registry instance."""
        r1 = PluginRegistry.default()
        r2 = PluginRegistry.default()
        assert r1 is not r2


# ---------------------------------------------------------------------------
# LocalTTSProvider — offline synthesis
# ---------------------------------------------------------------------------


class TestLocalTTSProvider:
    """Tests for the offline LocalTTSProvider."""

    def test_synthesize_returns_bytes(self):
        from providers.tts.local import LocalTTSProvider

        provider = LocalTTSProvider()
        result = provider.synthesize("Hello world", voice_id="")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_synthesize_returns_wav_header(self):
        """Output starts with the RIFF WAV header magic bytes."""
        from providers.tts.local import LocalTTSProvider

        provider = LocalTTSProvider()
        result = provider.synthesize("Test narration", voice_id="")
        # WAV files start with 'RIFF'
        assert result[:4] == b"RIFF"

    def test_synthesize_empty_text_raises(self):
        from providers.tts.local import LocalTTSProvider

        provider = LocalTTSProvider()
        with pytest.raises(ValueError):
            provider.synthesize("", voice_id="")

    def test_synthesize_whitespace_only_raises(self):
        from providers.tts.local import LocalTTSProvider

        provider = LocalTTSProvider()
        with pytest.raises(ValueError):
            provider.synthesize("   ", voice_id="")

    def test_synthesize_longer_text_produces_longer_audio(self):
        """Longer text should produce more audio frames than shorter text."""
        import wave
        import io
        from providers.tts.local import LocalTTSProvider

        provider = LocalTTSProvider()
        short = provider.synthesize("Hi", voice_id="")
        long_ = provider.synthesize(
            "This is a much longer sentence with many more words to synthesize.",
            voice_id="",
        )

        def wav_duration(data: bytes) -> float:
            with wave.open(io.BytesIO(data), "rb") as wf:
                return wf.getnframes() / wf.getframerate()

        assert wav_duration(long_) > wav_duration(short)
