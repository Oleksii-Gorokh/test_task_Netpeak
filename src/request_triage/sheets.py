from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .models import OutputDocument
from .resilience import RetryPolicy, retry_sync


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
SHEET_HEADERS = [
    "id",
    "channel",
    "timestamp",
    "raw_text",
    "category",
    "target_department",
    "priority",
    "short_summary",
    "requested_actions",
    "needs_clarification",
    "clarification_reason",
    "processing_status",
    "error",
]


def _credentials(
    credentials_file: str | Path | None = None,
    credentials_json: str | None = None,
) -> Any:
    from google.oauth2 import service_account

    credentials_json = credentials_json or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    credentials_file = credentials_file or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if credentials_json:
        try:
            info = json.loads(credentials_json)
        except json.JSONDecodeError as exc:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc
        return service_account.Credentials.from_service_account_info(
            info, scopes=[SHEETS_SCOPE]
        )
    if credentials_file:
        return service_account.Credentials.from_service_account_file(
            str(credentials_file), scopes=[SHEETS_SCOPE]
        )
    raise ValueError(
        "Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON for Sheets export"
    )


def sheet_rows(document: OutputDocument) -> list[list[str]]:
    rows: list[list[str]] = [SHEET_HEADERS]
    for item in document.requests:
        rows.append(
            [
                item.id,
                item.channel,
                item.timestamp,
                item.raw_text,
                item.category or "",
                item.target_department or "",
                item.priority or "",
                item.short_summary or "",
                " | ".join(item.requested_actions),
                str(item.needs_clarification).lower()
                if item.needs_clarification is not None
                else "",
                item.clarification_reason or "",
                item.processing_status,
                item.error or "",
            ]
        )
    return rows


class GoogleSheetsExporter:
    """Overwrite one tab with the current structured inbox snapshot."""

    def __init__(
        self,
        spreadsheet_id: str,
        tab_name: str = "Requests",
        credentials_file: str | Path | None = None,
        credentials_json: str | None = None,
        session: Any | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if not spreadsheet_id:
            raise ValueError("spreadsheet_id is required")
        self.spreadsheet_id = spreadsheet_id
        self.tab_name = tab_name
        self.retry_policy = retry_policy or RetryPolicy()
        if session is None:
            from google.auth.transport.requests import AuthorizedSession

            session = AuthorizedSession(_credentials(credentials_file, credentials_json))
        self.session = session

    def _url(self, range_name: str) -> str:
        spreadsheet = quote(self.spreadsheet_id, safe="")
        range_path = quote(range_name, safe="!:$")
        return f"{SHEETS_API}/{spreadsheet}/values/{range_path}"

    @staticmethod
    def _check(response: Any, operation: str) -> None:
        if not response.ok:
            detail = getattr(response, "text", "")
            raise RuntimeError(f"Google Sheets {operation} failed: {response.status_code} {detail}")

    def export(self, document: OutputDocument) -> int:
        rows = sheet_rows(document)
        clear_response = retry_sync(
            lambda: self.session.post(self._url(f"{self.tab_name}!A:M:clear"), timeout=30),
            self.retry_policy,
        )
        self._check(
            clear_response,
            "clear",
        )
        response = retry_sync(
            lambda: self.session.put(
                self._url(f"{self.tab_name}!A1"),
                params={"valueInputOption": "RAW"},
                json={
                    "range": f"{self.tab_name}!A1",
                    "majorDimension": "ROWS",
                    "values": rows,
                },
                timeout=30,
            ),
            self.retry_policy,
        )
        self._check(response, "update")
        return len(rows) - 1
