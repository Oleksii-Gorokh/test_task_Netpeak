import asyncio

from request_triage.resilience import RateLimiter, RetryPolicy, retry_async, retry_sync


class Response:
    def __init__(self, status_code, retry_after=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}


def test_retry_sync_honors_rate_limit_and_retries():
    responses = iter([Response(429, 0), Response(503), Response(200)])
    delays = []

    result = retry_sync(
        lambda: next(responses),
        RetryPolicy(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0, jitter_seconds=0),
        sleep=delays.append,
    )

    assert result.status_code == 200
    assert delays == [0, 0]


def test_retry_async_retries_transient_response():
    responses = iter([Response(500), Response(200)])
    delays = []

    async def operation():
        return next(responses)

    async def no_wait(delay):
        delays.append(delay)

    result = asyncio.run(
        retry_async(
            operation,
            RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0, jitter_seconds=0),
            sleep=no_wait,
        )
    )

    assert result.status_code == 200
    assert delays == [0]


def test_retry_sync_uses_server_delay_from_exception():
    attempts = iter([RuntimeError("429 RESOURCE_EXHAUSTED; Please retry in 3.5s."), Response(200)])
    delays = []

    def operation():
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    result = retry_sync(
        operation,
        RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=10, jitter_seconds=0),
        sleep=delays.append,
    )

    assert result.status_code == 200
    assert delays == [3.5]


def test_rate_limiter_rejects_negative_interval():
    try:
        RateLimiter(-1)
    except ValueError as exc:
        assert "cannot be negative" in str(exc)
    else:
        raise AssertionError("negative interval should fail validation")
