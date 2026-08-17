import asyncio
import json

import pytest

from request_triage.checkpoint import CheckpointStore
from request_triage.models import ClassifiedRequest, RequestInput
from request_triage.pipeline import classify_all_async


def requests():
    return [
        RequestInput(id="REQ-1", channel="Slack", timestamp="now", raw_text="one"),
        RequestInput(id="REQ-2", channel="Slack", timestamp="now", raw_text="two"),
    ]


def result(request_id):
    return ClassifiedRequest(
        id=request_id, channel="Slack", timestamp="now", raw_text=request_id,
        category="питання/консультація", target_department=None, priority="low",
        short_summary="summary", requested_actions=[], needs_clarification=False,
        clarification_reason=None, processing_status="ok", error=None,
    )


class CountingClient:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        request_id = prompt.split("id: ", 1)[1].splitlines()[0].strip('"')
        return json.dumps({
            "category": "питання/консультація", "target_department": None,
            "priority": "low", "short_summary": request_id,
            "requested_actions": [], "needs_clarification": False,
            "clarification_reason": None,
        })


def test_checkpoint_is_atomic_and_resume_skips_successful_rows(tmp_path):
    path = tmp_path / "batch.checkpoint.json"
    store = CheckpointStore(path, requests(), "input.csv", "test-model")
    store.save(result("REQ-1"))

    resumed = CheckpointStore(path, requests(), "input.csv", "test-model", resume=True)
    assert resumed.successful_ids == {"REQ-1"}
    assert not (tmp_path / ".batch.checkpoint.json.tmp").exists()

    client = CountingClient()
    output = asyncio.run(
        classify_all_async(
            requests(), client, concurrency=1,
            checkpoint_path=str(path), source_file="input.csv",
            model="test-model", resume=True,
        )
    )
    assert [item.id for item in output] == ["REQ-1", "REQ-2"]
    assert client.calls == 1


def test_checkpoint_rejects_different_input(tmp_path):
    path = tmp_path / "checkpoint.json"
    CheckpointStore(path, requests(), "input.csv", "test-model").save(result("REQ-1"))
    changed = [RequestInput(id="REQ-1", channel="Slack", timestamp="now", raw_text="changed")]

    with pytest.raises(ValueError, match="does not match"):
        CheckpointStore(path, changed, "input.csv", "test-model", resume=True)


def test_resume_requires_existing_checkpoint(tmp_path):
    with pytest.raises(ValueError, match="Checkpoint not found"):
        CheckpointStore(
            tmp_path / "missing.json", requests(), "input.csv", "test-model", resume=True
        )


def test_checkpoint_rejects_non_object_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        CheckpointStore(path, requests(), "input.csv", "test-model", resume=True)
