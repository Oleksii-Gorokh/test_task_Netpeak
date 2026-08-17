import asyncio

from request_triage.models import ClassifiedRequest
from request_triage.reporting import build_output
from request_triage.telegram import send_digest


class FakeResponse:
    is_success = True
    status_code = 200
    text = ""


class FakeAsyncClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def test_telegram_digest_uses_send_message_payload():
    row = ClassifiedRequest(
        id="REQ-1", channel="Slack", timestamp="now", raw_text="text",
        category="автоматизація", target_department=None, priority="high",
        short_summary="summary", requested_actions=[],
        needs_clarification=True, clarification_reason="details",
        processing_status="ok", error=None,
    )
    document = build_output([row], "input.csv", "test-model")
    client = FakeAsyncClient()

    sent = asyncio.run(send_digest(document, "secret-token", "chat-123", client))

    assert sent == 1
    url, kwargs = client.calls[0]
    assert url.endswith("/botsecret-token/sendMessage")
    assert kwargs["json"]["chat_id"] == "chat-123"
    assert "REQ-1" in kwargs["json"]["text"]

