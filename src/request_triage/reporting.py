from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .models import Category, ClassifiedRequest, OutputDocument, Priority


CATEGORIES: tuple[Category, ...] = (
    "автоматизація",
    "інтеграція",
    "звіт/аналітика",
    "баг/підтримка",
    "питання/консультація",
    "поза скоупом",
)
PRIORITIES: tuple[Priority, ...] = ("low", "medium", "high")
UNKNOWN_DEPARTMENT = "не визначено"


def build_output(
    requests: list[ClassifiedRequest],
    source_file: str,
    model: str,
) -> OutputDocument:
    return OutputDocument(
        source_file=source_file,
        model=model,
        total_requests=len(requests),
        requests=requests,
    )


def write_output(document: OutputDocument, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(document.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _markdown_counts(title: str, counts: dict[str, int]) -> list[str]:
    lines = [f"### {title}", "", "| Значення | Кількість |", "|---|---:|"]
    lines.extend(f"| {key} | {value} |" for key, value in counts.items())
    lines.append("")
    return lines


def render_report(document: OutputDocument) -> str:
    successful = [item for item in document.requests if item.processing_status == "ok"]
    category_counts = Counter(item.category for item in successful)
    priority_counts = Counter(item.priority for item in successful)
    department_counts = Counter(
        item.target_department or UNKNOWN_DEPARTMENT for item in successful
    )

    lines = [
        "# Звіт з класифікації inbox",
        "",
        f"- Джерело: `{document.source_file}`",
        f"- Модель: `{document.model}`",
        f"- Всього запитів: **{document.total_requests}**",
        f"- Успішно класифіковано: **{len(successful)}**",
        f"- Помилок класифікації: **{document.total_requests - len(successful)}**",
        "",
    ]
    lines.extend(
        _markdown_counts(
            "За категорією", {category: category_counts.get(category, 0) for category in CATEGORIES}
        )
    )
    lines.extend(
        _markdown_counts(
            "За пріоритетом", {priority: priority_counts.get(priority, 0) for priority in PRIORITIES}
        )
    )
    lines.extend(_markdown_counts("За відділом", dict(sorted(department_counts.items()))))

    clarification_items = [
        item for item in successful if item.needs_clarification is True
    ]
    lines.extend(["### Потребують уточнення", ""])
    if clarification_items:
        lines.extend(
            f"- `{item.id}` — {item.short_summary}"
            + (f" ({item.clarification_reason})" if item.clarification_reason else "")
            for item in clarification_items
        )
    else:
        lines.append("Немає.")
    lines.append("")

    failed_items = [item for item in document.requests if item.processing_status == "error"]
    lines.extend(["### Помилки обробки", ""])
    if failed_items:
        lines.extend(f"- `{item.id}` — {item.error}" for item in failed_items)
    else:
        lines.append("Немає.")
    lines.append("")
    return "\n".join(lines)


def write_report(document: OutputDocument, path: str | Path) -> None:
    Path(path).write_text(render_report(document), encoding="utf-8")

