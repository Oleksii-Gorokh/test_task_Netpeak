import asyncio
import os

import pytest
from dotenv import load_dotenv

from request_triage.classifier import classify_request
from request_triage.llm import GeminiClient
from request_triage.models import ClassifiedRequest, OutputDocument, RequestInput
from request_triage.resilience import RetryPolicy
from request_triage.sheets import GoogleSheetsExporter
from request_triage.telegram import send_digest


load_dotenv()
pytestmark = pytest.mark.live


def live_enabled() -> bool:
    return os.getenv("RUN_LIVE_INTEGRATION_TESTS", "").lower() in {"1", "true", "yes"}


def sample_request() -> RequestInput:
    return RequestInput(
        id="LIVE-REQ-001",
        channel="test",
        timestamp="2026-08-17 00:00",
        raw_text="Потрібен короткий звіт про щотижневі витрати маркетингу.",
    )


@pytest.mark.skipif(
    not live_enabled() or not os.getenv("GEMINI_API_KEY"),
    reason="Set RUN_LIVE_INTEGRATION_TESTS=1 and GEMINI_API_KEY",
)
def test_live_gemini_classification():
    result = classify_request(
        sample_request(),
        GeminiClient(
            model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
            retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=1, max_delay_seconds=8),
        ),
        max_attempts=2,
    )

    assert result.processing_status == "ok", result.error
    assert result.category is not None
    assert result.priority is not None
    assert result.short_summary


def live_document() -> OutputDocument:
    item = ClassifiedRequest(
        id="LIVE-REQ-001", channel="test", timestamp="now", raw_text="live test",
        category="питання/консультація", target_department=None, priority="low",
        short_summary="Live integration test", requested_actions=[],
        needs_clarification=False, clarification_reason=None,
        processing_status="ok", error=None,
    )
    return OutputDocument(
        source_file="live-test", model="test-model", total_requests=1, requests=[item]
    )


@pytest.mark.skipif(
    not live_enabled()
    or not os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    or not (os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")),
    reason="Set live-test flag, Sheets spreadsheet ID and service-account credentials",
)
def test_live_google_sheets_write():
    rows = GoogleSheetsExporter(
        spreadsheet_id=os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"],
        tab_name=os.getenv("GOOGLE_SHEETS_TAB", "Requests"),
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=1, max_delay_seconds=8),
    ).export(live_document())
    assert rows == 1


@pytest.mark.skipif(
    not live_enabled() or not (os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
    reason="Set live-test flag, TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID",
)
def test_live_telegram_digest():
    sent = asyncio.run(
        send_digest(
            live_document(),
            retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=1, max_delay_seconds=8),
        )
    )
    assert sent >= 1

