"""
Snap Recap — Provider Protocol definitions.

Defines the LLMProvider and TTSProvider interfaces that all concrete
provider implementations must satisfy.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class Message(Protocol):
    """A single message in an LLM conversation."""

    role: str
    content: str


class LLMConfig(Protocol):
    """Configuration for an LLM completion request."""

    max_tokens: int
    temperature: float


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for Large Language Model providers.

    Concrete implementations: GeminiProvider, OllamaProvider,
    GroqProvider, OpenRouterProvider.
    """

    def complete(self, messages: list[Any], config: Any) -> str:
        """Generate a completion for the given messages.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            config: LLM configuration (max_tokens, temperature, etc.).

        Returns:
            The generated text response.
        """
        ...


@runtime_checkable
class TTSProvider(Protocol):
    """Protocol for Text-to-Speech providers.

    Concrete implementations: ElevenLabsProvider, LocalTTSProvider.
    """

    def synthesize(self, text: str, voice_id: str) -> bytes:
        """Synthesize speech from text.

        Args:
            text: The text to synthesize.
            voice_id: Provider-specific voice identifier.

        Returns:
            Raw WAV audio bytes at 44.1kHz.
        """
        ...
