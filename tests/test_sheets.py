from request_triage.models import ClassifiedRequest
from request_triage.reporting import build_output
from request_triage.sheets import GoogleSheetsExporter, sheet_rows


class FakeResponse:
    ok = True
    status_code = 200
    text = ""


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return FakeResponse()

    def put(self, url, **kwargs):
        self.calls.append(("put", url, kwargs))
        return FakeResponse()


def test_sheets_export_clears_and_updates_values():
    row = ClassifiedRequest(
        id="REQ-1", channel="Slack", timestamp="now", raw_text="text",
        category="автоматизація", target_department=None, priority="low",
        short_summary="summary", requested_actions=["action"],
        needs_clarification=True, clarification_reason="details",
        processing_status="ok", error=None,
    )
    document = build_output([row], "input.csv", "test-model")
    session = FakeSession()

    exported = GoogleSheetsExporter("spreadsheet/id", session=session).export(document)

    assert exported == 1
    assert [call[0] for call in session.calls] == ["post", "put"]
    assert session.calls[0][1].endswith("/Requests!A:M:clear")
    payload = session.calls[1][2]["json"]
    assert payload["values"] == sheet_rows(document)
    assert payload["values"][1][8] == "action"

