import json

from request_triage.classifier import classify_request, parse_classification
from request_triage.models import RequestInput


def sample_request() -> RequestInput:
    return RequestInput(
        id="REQ-TEST",
        channel="Slack",
        timestamp="2026-06-08 09:00",
        raw_text="Терміново підключіть звіт до Google Ads.",
    )


def valid_payload() -> dict:
    return {
        "category": "інтеграція",
        "target_department": "маркетинг",
        "priority": "high",
        "short_summary": "Підключити звіт до Google Ads.",
        "requested_actions": ["Підключити Google Ads", "Налаштувати звіт"],
        "needs_clarification": False,
        "clarification_reason": None,
    }


class SequenceClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return next(self.responses)


def test_parse_classification_rejects_invalid_enum():
    payload = valid_payload()
    payload["priority"] = "urgent"

    try:
        parse_classification(json.dumps(payload, ensure_ascii=False))
    except ValueError as exc:
        assert "schema validation" in str(exc)
    else:
        raise AssertionError("invalid priority should fail validation")


def test_classifier_retries_invalid_json_and_returns_valid_result():
    client = SequenceClient(["not json", json.dumps(valid_payload(), ensure_ascii=False)])

    result = classify_request(sample_request(), client)

    assert result.processing_status == "ok"
    assert result.category == "інтеграція"
    assert result.requested_actions == ["Підключити Google Ads", "Налаштувати звіт"]
    assert client.calls == 2


def test_classifier_isolates_permanent_failure():
    client = SequenceClient(["bad", "still bad"])

    result = classify_request(sample_request(), client)

    assert result.processing_status == "error"
    assert result.category is None
    assert result.error is not None
    assert client.calls == 2

