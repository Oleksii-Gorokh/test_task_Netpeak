from __future__ import annotations

import csv
from pathlib import Path

from pydantic import ValidationError

from .models import RequestInput


REQUIRED_COLUMNS = {"id", "channel", "timestamp", "raw_text"}


def read_requests(path: str | Path) -> list[RequestInput]:
    """Read and validate the inbox CSV before making any LLM calls."""

    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {', '.join(sorted(missing))}"
            )

        requests: list[RequestInput] = []
        seen_ids: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            try:
                request = RequestInput.model_validate(
                    {key: row.get(key) for key in REQUIRED_COLUMNS}
                )
            except ValidationError as exc:
                raise ValueError(f"Invalid CSV row {row_number}: {exc}") from exc
            if request.id in seen_ids:
                raise ValueError(f"Duplicate request id on CSV row {row_number}: {request.id}")
            seen_ids.add(request.id)
            requests.append(request)

    return requests
