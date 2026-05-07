"""
Snap Recap — GroqProvider.

LLM provider backed by the Groq API via httpx.
API key is read from the ``GROQ_API_KEY`` environment variable if not
passed explicitly.
"""

from __future__ import annotations

import os
from typing import Any


class GroqProvider:
    """LLM provider that calls the Groq API.

    Args:
        api_key: Groq API key. Falls back to ``GROQ_API_KEY`` env var.
        model: Model name (e.g. ``"llama3-8b-8192"``).
    """

    BASE_URL = "https://api.groq.com/openai/v1"
    DEFAULT_MODEL = "llama3-8b-8192"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model

    # ------------------------------------------------------------------
    # LLMProvider protocol
    # ------------------------------------------------------------------

    def complete(self, messages: list[Any], config: Any) -> str:
        """Generate a completion using the Groq API.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            config: LLM configuration with ``max_tokens`` and ``temperature``.

        Returns:
            The generated text response.

        Raises:
            ValueError: If the API key is missing.
            RuntimeError: If the Groq API returns an error.
        """
        if not self._api_key:
            raise ValueError(
                "Groq API key is required. Set GROQ_API_KEY environment variable "
                "or pass api_key to GroqProvider."
            )

        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "httpx package is required for GroqProvider. "
                "Install it with: pip install httpx"
            ) from exc

        # Normalise messages to plain dicts
        normalised = []
        for msg in messages:
            if isinstance(msg, dict):
                normalised.append({"role": msg["role"], "content": msg["content"]})
            else:
                normalised.append({"role": msg.role, "content": msg.content})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": normalised,
            "max_tokens": getattr(config, "max_tokens", 2048),
            "temperature": getattr(config, "temperature", 0.7),
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                f"{self.BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Groq API error (HTTP {exc.response.status_code}) "
                f"for model '{self.model}': {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Groq API request failed: {exc}"
            ) from exc

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected Groq response format: {data}"
            ) from exc
