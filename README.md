# Inbox request triage

Невеликий Python-застосунок, який класифікує внутрішні запити через Gemini та
перетворює вільний текст із `input_requests.csv` на стабільний JSON-контракт.

## Що робить

Для кожного рядка визначаються:

- `category`: `автоматизація`, `інтеграція`, `звіт/аналітика`, `баг/підтримка`,
  `питання/консультація` або `поза скоупом`;
- `target_department`: відділ-замовник або `null`;
- `priority`: `low`, `medium` або `high`;
- `short_summary`: суть запиту одним реченням;
- `requested_actions`: список конкретних дій;
- `needs_clarification`: чи можна брати запит у роботу без уточнень.

До обов'язкових полів додані `clarification_reason`, `processing_status` та
`error`. Перші пояснюють, чого бракує в розмитому запиті, а останні два не
дозволяють тихо втратити рядок, якщо LLM/API повернув помилку. На верхньому
рівні `output.json` також має `schema_version`, `model` і `total_requests`.

## Запуск

Потрібен Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
```

У `.env` додайте ключ Gemini:

```text
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash-lite
```

Запуск із дефолтними шляхами:

```powershell
python -m request_triage
```

Або явно:

```powershell
python -m request_triage --input input_requests.csv --output output.json --report report.md
```

Параметр `--max-attempts` задає кількість спроб на один рядок; за замовчуванням
їх дві. API-ключ не зберігається в коді чи Git.

## Результат

`output.json` має вигляд:

```json
{
  "schema_version": "1.0",
  "source_file": "input_requests.csv",
  "model": "gemini-2.5-flash-lite",
  "total_requests": 18,
  "requests": [
    {
      "id": "REQ-001",
      "channel": "Slack",
      "timestamp": "2026-06-08 09:14",
      "raw_text": "...",
      "category": "автоматизація",
      "target_department": "маркетинг",
      "priority": "medium",
      "short_summary": "Автоматизувати щотижневий звіт по Google Ads.",
      "requested_actions": ["Забирати дані Google Ads", "Формувати звіт"],
      "needs_clarification": false,
      "clarification_reason": null,
      "processing_status": "ok",
      "error": null
    }
  ]
}
```

`report.md` містить кількість запитів за категоріями, пріоритетами й відділами,
а також окремі списки запитів для уточнення та технічних помилок.

## Як валідується LLM-вивід

Gemini отримує JSON structured-output конфігурацію з Pydantic-схемою. Після
цього відповідь усе одно проходить `json.loads` і повторну Pydantic-валідацію:
enum-значення, типи та обов'язкові поля перевіряються в застосунку. Якщо JSON
битий або схема не збігається, виконується одна repair-спроба з додатковою
інструкцією. Якщо й вона невдала, рядок записується з
`processing_status="error"`, а інші запити продовжують оброблятися.

## Тести

Тести не викликають Gemini: використовують mock-клієнт, тому їх можна запускати
без ключа.

```powershell
pytest -q
```

## Обмеження та наступні кроки

- Обробка зараз послідовна. Для сотень/тисяч рядків варто додати bounded async
  concurrency, rate-limit/backoff, checkpointing і resume з незавершеного batch.
- Один запит = один LLM-виклик, плюс повторна спроба при помилці. Це збільшує
  latency і token cost; у production потрібні ліміти, метрики та оцінка вартості
  до запуску.
- `temperature=0` зменшує, але не усуває недетермінізм. Для стабільності можна
  додати golden-набір, періодичну ручну оцінку, кешування за hash вхідного тексту
  та version pinning моделі.
- Неправильний або відсутній API-ключ зупиняє запуск до LLM-викликів. Помилки
  окремих відповідей не зупиняють batch і явно потрапляють у JSON/report.
- CSV перевіряється до викликів LLM, але timestamp наразі зберігається як рядок,
  бо застосунок не виконує часових розрахунків.
- Далі додав би Google Sheets/Telegram-інтеграцію, async batch, Docker-образ,
  structured logging, prompt/version metadata та human-in-the-loop для low
  confidence або `needs_clarification=true`.

## Структура

```text
src/request_triage/
  classifier.py   # prompt, parsing, retry та per-row error isolation
  csv_io.py       # читання і валідація CSV
  llm.py          # маленький Gemini adapter + testable protocol
  models.py       # Pydantic contracts
  pipeline.py     # обробка batch у порядку вхідних рядків
  reporting.py    # output.json та report.md
  cli.py          # CLI та env-конфігурація
tests/            # offline unit tests
```

