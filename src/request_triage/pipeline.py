from __future__ import annotations

from collections.abc import Callable

from .classifier import classify_request
from .llm import LLMClient
from .models import ClassifiedRequest, RequestInput
from .reporting import build_output, write_output, write_report


def classify_all(
    requests: list[RequestInput], client: LLMClient, max_attempts: int = 2,
    progress: Callable[[int, int], None] | None = None,
) -> list[ClassifiedRequest]:
    """Run the batch sequentially, preserving input order and isolating rows."""

    classified: list[ClassifiedRequest] = []
    total = len(requests)
    for index, request in enumerate(requests, start=1):
        classified.append(classify_request(request, client, max_attempts=max_attempts))
        if progress:
            progress(index, total)
    return classified


def run_pipeline(
    requests: list[RequestInput],
    client: LLMClient,
    source_file: str,
    model: str,
    output_path: str,
    report_path: str,
    max_attempts: int = 2,
    progress: Callable[[int, int], None] | None = None,
) -> None:
    classified = classify_all(requests, client, max_attempts=max_attempts, progress=progress)
    document = build_output(classified, source_file=source_file, model=model)
    write_output(document, output_path)
    write_report(document, report_path)

