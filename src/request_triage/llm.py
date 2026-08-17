from __future__ import annotations

from typing import Protocol

from .models import Classification


class LLMClient(Protocol):
    """Small protocol that keeps classification testable without a network call."""

    def generate(self, prompt: str) -> str:
        ...


class GeminiClient:
    """Adapter around the official google-genai SDK."""

    def __init__(self, model: str) -> None:
        from google import genai
        from google.genai import types

        self.model = model
        self._types = types
        self._client = genai.Client()

    def generate(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=Classification.model_json_schema(),
            ),
        )
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Gemini returned an empty response")
        return text
