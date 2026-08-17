from __future__ import annotations

import asyncio
from collections.abc import Callable

from .classifier import classify_request
from .llm import LLMClient
from .models import ClassifiedRequest, OutputDocument, RequestInput
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


async def classify_all_async(
    requests: list[RequestInput],
    client: LLMClient,
    max_attempts: int = 2,
    concurrency: int = 4,
    progress: Callable[[int, int], None] | None = None,
) -> list[ClassifiedRequest]:
    """Classify concurrently with a bounded number of in-flight LLM calls."""

    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    semaphore = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(requests)

    async def classify_one(request: RequestInput) -> ClassifiedRequest:
        nonlocal completed
        async with semaphore:
            result = await asyncio.to_thread(
                classify_request, request, client, max_attempts
            )
        completed += 1
        if progress:
            progress(completed, total)
        return result

    # asyncio.gather returns in input order even when workers finish out of order.
    return await asyncio.gather(*(classify_one(request) for request in requests))


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


async def run_pipeline_async(
    requests: list[RequestInput],
    client: LLMClient,
    source_file: str,
    model: str,
    output_path: str,
    report_path: str,
    max_attempts: int = 2,
    concurrency: int = 4,
    progress: Callable[[int, int], None] | None = None,
) -> OutputDocument:
    classified = await classify_all_async(
        requests,
        client,
        max_attempts=max_attempts,
        concurrency=concurrency,
        progress=progress,
    )
    document = build_output(classified, source_file=source_file, model=model)
    write_output(document, output_path)
    write_report(document, report_path)
    return document
