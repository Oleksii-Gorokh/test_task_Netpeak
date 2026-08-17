from request_triage.models import ClassifiedRequest
from request_triage.reporting import build_output, render_report


def test_report_contains_required_aggregates_and_clarifications():
    rows = [
        ClassifiedRequest(
            id="REQ-1", channel="Slack", timestamp="now", raw_text="x",
            category="автоматизація", target_department="маркетинг", priority="high",
            short_summary="Автоматизувати звіт.", requested_actions=["Зробити звіт"],
            needs_clarification=False, clarification_reason=None,
            processing_status="ok", error=None,
        ),
        ClassifiedRequest(
            id="REQ-2", channel="Telegram", timestamp="now", raw_text="нам би бота",
            category="автоматизація", target_department=None, priority="low",
            short_summary="Потрібен бот.", requested_actions=[],
            needs_clarification=True, clarification_reason="Не описано призначення бота.",
            processing_status="ok", error=None,
        ),
    ]
    report = render_report(build_output(rows, "input.csv", "test-model"))

    assert "За категорією" in report
    assert "| автоматизація | 2 |" in report
    assert "| не визначено | 1 |" in report
    assert "`REQ-2`" in report
    assert "Не описано призначення бота." in report

