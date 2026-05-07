"""
Snap Recap — GeminiProvider.

LLM provider backed by Google Gemini via the ``google-generativeai`` SDK.
API key is read from the ``GEMINI_API_KEY`` environment variable if not
passed explicitly.
"""

from __future__ import annotations

import os
from typing import Any


class GeminiProvider:
    """LLM provider that calls Google Gemini.

    Args:
        api_key: Gemini API key. Falls back to ``GEMINI_API_KEY`` env var.
        model: Model name (e.g. ``"gemini-1.5-pro"``).
    """

    DEFAULT_MODEL = "gemini-1.5-pro"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model

    # ------------------------------------------------------------------
    # LLMProvider protocol
    # ------------------------------------------------------------------

    def complete(self, messages: list[Any], config: Any) -> str:
        """Generate a completion using Google Gemini.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            config: LLM configuration with ``max_tokens`` and ``temperature``.

        Returns:
            The generated text response.

        Raises:
            ValueError: If the API key is missing.
            RuntimeError: If the Gemini API returns an error.
        """
        if not self._api_key:
            raise ValueError(
                "Gemini API key is required. Set GEMINI_API_KEY environment variable "
                "or pass api_key to GeminiProvider."
            )

        try:
            import google.generativeai as genai  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "google-generativeai package is required for GeminiProvider. "
                "Install it with: pip install google-generativeai"
            ) from exc

        genai.configure(api_key=self._api_key)

        generation_config = genai.types.GenerationConfig(
            max_output_tokens=getattr(config, "max_tokens", 2048),
            temperature=getattr(config, "temperature", 0.7),
        )

        gemini_model = genai.GenerativeModel(self.model)

        # Convert messages to Gemini format (single prompt for simplicity)
        prompt_parts = []
        for msg in messages:
            role = getattr(msg, "role", None) or msg.get("role", "user")
            content = getattr(msg, "content", None) or msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"[System]: {content}")
            else:
                prompt_parts.append(content)

        prompt = "\n".join(prompt_parts)

        try:
            response = gemini_model.generate_content(
                prompt,
                generation_config=generation_config,
            )
            return response.text
        except Exception as exc:
            raise RuntimeError(
                f"Gemini API error for model '{self.model}': {exc}"
            ) from exc
