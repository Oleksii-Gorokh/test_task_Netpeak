from __future__ import annotations

import asyncio
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar


T = TypeVar("T")
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class RateLimiter:
    """Thread-safe minimum interval between outbound requests."""

    def __init__(self, min_interval_seconds: float = 4.0) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative")
        self.min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        if self.min_interval_seconds == 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.min_interval_seconds
        if delay:
            time.sleep(delay)


@dataclass(frozen=True)
class RetryPolicy:
    """Retry policy for transient API failures and rate limits."""

    max_attempts: int = 4
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    jitter_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be >= base_delay_seconds")
        if self.jitter_seconds < 0:
            raise ValueError("jitter_seconds cannot be negative")

    def delay(self, retry_number: int, retry_after: float | None = None) -> float:
        exponential = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2**retry_number),
        )
        server_delay = retry_after or 0.0
        return max(exponential, server_delay) + random.uniform(0, self.jitter_seconds)


def _status_code(value: Any) -> int | None:
    for name in ("status_code", "code"):
        candidate = getattr(value, name, None)
        if isinstance(candidate, int):
            return candidate
    return None


def is_retryable_exception(exc: BaseException) -> bool:
    status = _status_code(exc)
    if status in RETRYABLE_STATUS_CODES:
        return True
    text = str(exc).upper()
    return any(
        marker in text
        for marker in (
            "RESOURCE_EXHAUSTED",
            "RATE LIMIT",
            "TOO MANY REQUESTS",
            "UNAVAILABLE",
            "SERVICE UNAVAILABLE",
            "TIMED OUT",
            "TIMEOUT",
            "CONNECTION RESET",
        )
    )


def _response_status(response: Any) -> int | None:
    status = _status_code(response)
    return status if status is not None else None


def _retry_after(response: Any) -> float | None:
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("Retry-After") or headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _retry_after_exception(exc: BaseException) -> float | None:
    """Extract RetryInfo text used by Google API exceptions when no headers exist."""

    text = str(exc)
    patterns = (
        r"retry(?:\s+in|Delay['\"]?\s*[:=])\s*([0-9]+(?:\.[0-9]+)?)\s*s",
        r"retryDelay[^0-9]*([0-9]+(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def retry_sync(
    operation: Callable[[], T],
    policy: RetryPolicy,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Retry a synchronous operation only for transient failures."""

    for attempt in range(policy.max_attempts):
        try:
            result = operation()
            status = _response_status(result)
            if status not in RETRYABLE_STATUS_CODES or attempt == policy.max_attempts - 1:
                return result
            retry_after = _retry_after(result)
        except Exception as exc:  # noqa: BLE001 - retry policy classifies the exception.
            if not is_retryable_exception(exc) or attempt == policy.max_attempts - 1:
                raise
            retry_after = _retry_after_exception(exc)
        sleep(policy.delay(attempt, retry_after))

    raise RuntimeError("retry policy exhausted without a result")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Async equivalent used by the Telegram adapter."""

    for attempt in range(policy.max_attempts):
        try:
            result = await operation()
            status = _response_status(result)
            if status not in RETRYABLE_STATUS_CODES or attempt == policy.max_attempts - 1:
                return result
            retry_after = _retry_after(result)
        except Exception as exc:  # noqa: BLE001 - retry policy classifies the exception.
            if not is_retryable_exception(exc) or attempt == policy.max_attempts - 1:
                raise
            retry_after = _retry_after_exception(exc)
        await sleep(policy.delay(attempt, retry_after))

    raise RuntimeError("retry policy exhausted without a result")
