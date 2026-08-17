from __future__ import annotations

import asyncio
from collections.abc import Callable

from .checkpoint import CheckpointStore
from .classifier import classify_request
from .llm import LLMClient
from .models import ClassifiedRequest, OutputDocument, RequestInput
from .reporting import build_output, write_output, write_report


def classify_all(
    requests: list[RequestInput], client: LLMClient, max_attempts: int = 2,
    progress: Callable[[int, int], None] | None = None,
    checkpoint_path: str | None = None,
    source_file: str = "",
    model: str = "",
    resume: bool = False,
) -> list[ClassifiedRequest]:
    """Run the batch, optionally persisting each result for later resume."""

    checkpoint = (
        CheckpointStore(checkpoint_path, requests, source_file, model, resume)
        if checkpoint_path
        else None
    )
    results = checkpoint.results.copy() if checkpoint else {}
    pending = [
        request for request in requests
        if not checkpoint or request.id not in checkpoint.successful_ids
    ]
    total = len(requests)
    completed = len(results)
    if progress and completed:
        progress(completed, total)
    for request in pending:
        result = classify_request(request, client, max_attempts=max_attempts)
        results[request.id] = result
        if checkpoint:
            checkpoint.save(result)
        completed += 1
        if progress:
            progress(completed, total)
    return [results[request.id] for request in requests]


async def classify_all_async(
    requests: list[RequestInput],
    client: LLMClient,
    max_attempts: int = 2,
    concurrency: int = 4,
    progress: Callable[[int, int], None] | None = None,
    checkpoint_path: str | None = None,
    source_file: str = "",
    model: str = "",
    resume: bool = False,
) -> list[ClassifiedRequest]:
    """Classify concurrently with a bounded number of in-flight LLM calls."""

    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    semaphore = asyncio.Semaphore(concurrency)
    checkpoint = (
        CheckpointStore(checkpoint_path, requests, source_file, model, resume)
        if checkpoint_path
        else None
    )
    results = checkpoint.results.copy() if checkpoint else {}
    pending = [
        request for request in requests
        if not checkpoint or request.id not in checkpoint.successful_ids
    ]
    completed = len(results)
    total = len(requests)
    if progress and completed:
        progress(completed, total)

    async def classify_one(request: RequestInput) -> ClassifiedRequest:
        nonlocal completed
        async with semaphore:
            result = await asyncio.to_thread(
                classify_request, request, client, max_attempts
            )
        results[request.id] = result
        if checkpoint:
            checkpoint.save(result)
        completed += 1
        if progress:
            progress(completed, total)
        return result

    # asyncio.gather returns in input order even when workers finish out of order.
    await asyncio.gather(*(classify_one(request) for request in pending))
    return [results[request.id] for request in requests]


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
    checkpoint_path: str | None = None,
    resume: bool = False,
) -> OutputDocument:
    classified = await classify_all_async(
        requests,
        client,
        max_attempts=max_attempts,
        concurrency=concurrency,
        progress=progress,
        checkpoint_path=checkpoint_path,
        source_file=source_file,
        model=model,
        resume=resume,
    )
    document = build_output(classified, source_file=source_file, model=model)
    write_output(document, output_path)
    write_report(document, report_path)
    return document
