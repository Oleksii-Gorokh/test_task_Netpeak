import asyncio
import json
import threading
import time

from request_triage.models import RequestInput
from request_triage.pipeline import classify_all_async


class DelayedClient:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def generate(self, prompt: str) -> str:
        request_id = prompt.split("id: ", 1)[1].splitlines()[0].strip('"')
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.02)
        with self.lock:
            self.active -= 1
        return json.dumps(
            {
                "category": "питання/консультація",
                "target_department": None,
                "priority": "low",
                "short_summary": request_id,
                "requested_actions": [],
                "needs_clarification": False,
                "clarification_reason": None,
            },
        )


def test_async_pipeline_limits_concurrency_and_preserves_order():
    requests = [
        RequestInput(id=f"REQ-{index}", channel="Slack", timestamp="now", raw_text="hello")
        for index in range(6)
    ]
    client = DelayedClient()

    result = asyncio.run(classify_all_async(requests, client, concurrency=2))

    assert [item.id for item in result] == [f"REQ-{index}" for index in range(6)]
    assert [item.short_summary for item in result] == [f"REQ-{index}" for index in range(6)]
    assert client.max_active <= 2

