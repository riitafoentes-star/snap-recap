"""
Snap Recap — OllamaProvider.

LLM provider backed by a local Ollama instance via its HTTP API.
Base URL defaults to ``OLLAMA_BASE_URL`` env var or ``http://localhost:11434``.
"""

from __future__ import annotations

import os
from typing import Any


class OllamaProvider:
    """LLM provider that calls a local Ollama server.

    Args:
        base_url: Base URL of the Ollama server. Falls back to
            ``OLLAMA_BASE_URL`` env var, then ``http://localhost:11434``.
        model: Model name (e.g. ``"llama3"``).
    """

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "llama3"

    def __init__(
        self,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL)
        ).rstrip("/")
        self.model = model

    # ------------------------------------------------------------------
    # LLMProvider protocol
    # ------------------------------------------------------------------

    def complete(self, messages: list[Any], config: Any) -> str:
        """Generate a completion using Ollama's /api/chat endpoint.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            config: LLM configuration with ``max_tokens`` and ``temperature``.

        Returns:
            The generated text response.

        Raises:
            RuntimeError: If the Ollama server returns an error or is unreachable.
        """
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "httpx package is required for OllamaProvider. "
                "Install it with: pip install httpx"
            ) from exc

        # Normalise messages to plain dicts
        normalised = []
        for msg in messages:
            if isinstance(msg, dict):
                normalised.append({"role": msg["role"], "content": msg["content"]})
            else:
                normalised.append(
                    {"role": msg.role, "content": msg.content}
                )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": normalised,
            "stream": False,
            "options": {
                "num_predict": getattr(config, "max_tokens", 2048),
                "temperature": getattr(config, "temperature", 0.7),
            },
        }

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama API error (HTTP {exc.response.status_code}) "
                f"for model '{self.model}': {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Ollama server unreachable at '{self.base_url}': {exc}"
            ) from exc

        data = response.json()
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected Ollama response format: {data}"
            ) from exc
