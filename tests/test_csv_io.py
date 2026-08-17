from pathlib import Path

import pytest

from request_triage.csv_io import read_requests


def test_read_sample_csv():
    rows = read_requests(Path(__file__).parents[1] / "input_requests.csv")

    assert len(rows) == 18
    assert rows[0].id == "REQ-001"
    assert rows[-1].raw_text.startswith("Доброго ранку")


def test_read_csv_reports_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("id,raw_text\n1,hello\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns"):
        read_requests(path)

