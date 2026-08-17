from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Category = Literal[
    "автоматизація",
    "інтеграція",
    "звіт/аналітика",
    "баг/підтримка",
    "питання/консультація",
    "поза скоупом",
]
Priority = Literal["low", "medium", "high"]
ProcessingStatus = Literal["ok", "error"]


class RequestInput(BaseModel):
    """One row from the inbox export."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    raw_text: str = Field(min_length=1)


class Classification(BaseModel):
    """The only structure the LLM is allowed to return."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    target_department: str | None = None
    priority: Priority
    short_summary: str = Field(min_length=1)
    requested_actions: list[str] = Field(default_factory=list)
    needs_clarification: bool
    clarification_reason: str | None = None


class ClassifiedRequest(RequestInput):
    """Input row plus a validated classification and processing metadata."""

    category: Category | None = None
    target_department: str | None = None
    priority: Priority | None = None
    short_summary: str | None = None
    requested_actions: list[str] = Field(default_factory=list)
    needs_clarification: bool | None = None
    clarification_reason: str | None = None
    processing_status: ProcessingStatus
    error: str | None = None


class OutputDocument(BaseModel):
    """Stable top-level contract for output.json."""

    schema_version: str = "1.0"
    source_file: str
    model: str
    total_requests: int
    requests: list[ClassifiedRequest]

