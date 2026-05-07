"""
Snap Recap — PluginRegistry.

Registers and resolves LLM and TTS provider implementations at runtime.
Providers are registered by name and instantiated on demand.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

from providers.base import LLMProvider, TTSProvider

if TYPE_CHECKING:
    pass


class PluginRegistry:
    """Registry for LLM and TTS provider implementations.

    Providers are registered as classes (not instances) and resolved
    (instantiated) on demand via ``resolve_llm`` / ``resolve_tts``.

    Example::

        registry = PluginRegistry()
        registry.register_llm("gemini", GeminiProvider)
        provider = registry.resolve_llm("gemini")
    """

    def __init__(self) -> None:
        self._llm_providers: dict[str, Type[LLMProvider]] = {}
        self._tts_providers: dict[str, Type[TTSProvider]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_llm(self, name: str, provider: Type[LLMProvider]) -> None:
        """Register an LLM provider class under *name*.

        Args:
            name: Identifier used to resolve the provider later (e.g. "gemini").
            provider: A class that implements the ``LLMProvider`` protocol.
        """
        self._llm_providers[name] = provider

    def register_tts(self, name: str, provider: Type[TTSProvider]) -> None:
        """Register a TTS provider class under *name*.

        Args:
            name: Identifier used to resolve the provider later (e.g. "elevenlabs").
            provider: A class that implements the ``TTSProvider`` protocol.
        """
        self._tts_providers[name] = provider

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve_llm(self, name: str) -> LLMProvider:
        """Return an instance of the LLM provider registered under *name*.

        Args:
            name: The provider name as registered via ``register_llm``.

        Returns:
            An instantiated ``LLMProvider``.

        Raises:
            ValueError: If *name* is not registered, with a message listing
                all available provider names.
        """
        if name not in self._llm_providers:
            available = sorted(self._llm_providers.keys())
            raise ValueError(
                f"LLM provider '{name}' is not registered. "
                f"Available providers: {available}"
            )
        return self._llm_providers[name]()

    def resolve_tts(self, name: str) -> TTSProvider:
        """Return an instance of the TTS provider registered under *name*.

        Args:
            name: The provider name as registered via ``register_tts``.

        Returns:
            An instantiated ``TTSProvider``.

        Raises:
            ValueError: If *name* is not registered, with a message listing
                all available provider names.
        """
        if name not in self._tts_providers:
            available = sorted(self._tts_providers.keys())
            raise ValueError(
                f"TTS provider '{name}' is not registered. "
                f"Available providers: {available}"
            )
        return self._tts_providers[name]()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> "PluginRegistry":
        """Return a registry pre-populated with all built-in providers.

        LLM providers: gemini, ollama, groq, openrouter
        TTS providers: elevenlabs, local

        Returns:
            A ``PluginRegistry`` instance with all built-in providers registered.
        """
        from providers.llm.gemini import GeminiProvider
        from providers.llm.groq import GroqProvider
        from providers.llm.ollama import OllamaProvider
        from providers.llm.openrouter import OpenRouterProvider
        from providers.tts.elevenlabs import ElevenLabsProvider
        from providers.tts.local import LocalTTSProvider

        registry = cls()

        # LLM providers
        registry.register_llm("gemini", GeminiProvider)
        registry.register_llm("ollama", OllamaProvider)
        registry.register_llm("groq", GroqProvider)
        registry.register_llm("openrouter", OpenRouterProvider)

        # TTS providers
        registry.register_tts("elevenlabs", ElevenLabsProvider)
        registry.register_tts("local", LocalTTSProvider)

        return registry
