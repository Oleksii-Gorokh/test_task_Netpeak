from __future__ import annotations

from typing import Protocol

from .models import Classification
from .resilience import RateLimiter, RetryPolicy, retry_sync


def gemini_classification_schema() -> dict:
    """Return the full Pydantic schema for Gemini's ``responseJsonSchema``."""

    return Classification.model_json_schema()


class LLMClient(Protocol):
    """Small protocol that keeps classification testable without a network call."""

    def generate(self, prompt: str) -> str:
        ...


class GeminiClient:
    """Adapter around the official google-genai SDK."""

    def __init__(
        self,
        model: str,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        from google import genai
        from google.genai import types

        self.model = model
        self.retry_policy = retry_policy or RetryPolicy()
        self.rate_limiter = rate_limiter or RateLimiter()
        self._types = types
        self._client = genai.Client()

    def generate(self, prompt: str) -> str:
        def request():
            self.rate_limiter.wait()
            return self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_json_schema=gemini_classification_schema(),
                ),
            )

        response = retry_sync(
            request,
            self.retry_policy,
        )
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Gemini returned an empty response")
        return text
