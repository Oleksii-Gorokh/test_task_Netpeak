from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import ClassifiedRequest, RequestInput


CHECKPOINT_VERSION = "1.0"


def requests_fingerprint(requests: list[RequestInput]) -> str:
    payload = [request.model_dump() for request in requests]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CheckpointStore:
    """Atomic, input-bound persistence for resumable batch processing."""

    def __init__(
        self,
        path: str | Path,
        requests: list[RequestInput],
        source_file: str,
        model: str,
        resume: bool = False,
    ) -> None:
        self.path = Path(path)
        self.fingerprint = requests_fingerprint(requests)
        self.source_file = source_file
        self.model = model
        self.results: dict[str, ClassifiedRequest] = {}
        if resume and self.path.exists():
            self._load()

    @property
    def successful_ids(self) -> set[str]:
        return {
            request_id
            for request_id, result in self.results.items()
            if result.processing_status == "ok"
        }

    def _load(self) -> None:
        try:
            payload: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read checkpoint {self.path}: {exc}") from exc

        expected = {
            "checkpoint_version": CHECKPOINT_VERSION,
            "fingerprint": self.fingerprint,
            "source_file": self.source_file,
            "model": self.model,
        }
        mismatches = [
            key
            for key, value in expected.items()
            if payload.get(key) != value
        ]
        if mismatches:
            raise ValueError(
                f"Checkpoint does not match current input/config: {', '.join(mismatches)}"
            )

        try:
            raw_results = payload.get("results", {})
            self.results = {
                request_id: ClassifiedRequest.model_validate(result)
                for request_id, result in raw_results.items()
            }
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"Checkpoint contains invalid results: {exc}") from exc

    def save(self, result: ClassifiedRequest) -> None:
        self.results[result.id] = result
        payload = {
            "checkpoint_version": CHECKPOINT_VERSION,
            "fingerprint": self.fingerprint,
            "source_file": self.source_file,
            "model": self.model,
            "results": {
                request_id: item.model_dump()
                for request_id, item in self.results.items()
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

