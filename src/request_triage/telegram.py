from __future__ import annotations

import os
from typing import Any

import httpx

from .models import OutputDocument
from .resilience import RetryPolicy, retry_async


TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_LIMIT = 4096


def render_digest(document: OutputDocument) -> str:
    successful = [item for item in document.requests if item.processing_status == "ok"]
    clarification = [item.id for item in successful if item.needs_clarification is True]
    errors = [item.id for item in document.requests if item.processing_status == "error"]

    categories: dict[str, int] = {}
    priorities: dict[str, int] = {}
    for item in successful:
        if item.category:
            categories[item.category] = categories.get(item.category, 0) + 1
        if item.priority:
            priorities[item.priority] = priorities.get(item.priority, 0) + 1

    lines = [
        "Inbox triage digest",
        f"Всього: {document.total_requests}",
        f"Успішно: {len(successful)} | Помилок: {len(errors)}",
        "",
        "Категорії: "
        + (", ".join(f"{key}: {value}" for key, value in sorted(categories.items())) or "немає"),
        "Пріоритети: "
        + (", ".join(f"{key}: {value}" for key, value in sorted(priorities.items())) or "немає"),
        "",
        "Потребують уточнення: " + (", ".join(clarification) or "немає"),
    ]
    if errors:
        lines.append("Помилки: " + ", ".join(errors))
    return "\n".join(lines)


def _chunks(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = ""
        current += line
    if current:
        chunks.append(current.rstrip())
    return chunks


async def send_digest(
    document: OutputDocument,
    bot_token: str | None = None,
    chat_id: str | None = None,
    client: Any | None = None,
    retry_policy: RetryPolicy | None = None,
) -> int:
    """Send a plain-text digest; split safely under Telegram's message limit."""

    bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    retry_policy = retry_policy or RetryPolicy()

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30)
    try:
        sent = 0
        for text in _chunks(render_digest(document)):
            response = await retry_async(
                lambda: client.post(
                    f"{TELEGRAM_API}/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                ),
                retry_policy,
            )
            if not response.is_success:
                raise RuntimeError(
                    f"Telegram sendMessage failed: {response.status_code} {response.text}"
                )
            sent += 1
        return sent
    finally:
        if own_client:
            await client.aclose()
