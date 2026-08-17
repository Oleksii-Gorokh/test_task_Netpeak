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

Для запуску тестів замість цього можна встановити dev-залежності:

```powershell
pip install -e ".[dev]"
```

У `.env` додайте ключ Gemini:

```text
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
```

Запуск із дефолтними шляхами:

```powershell
python -m request_triage
```

За замовчуванням LLM-запити виконуються асинхронно з максимум 4 одночасними
викликами. Ліміт можна змінити через `TRIAGE_CONCURRENCY` або `--concurrency`.
Transient API-помилки та rate limit (429/5xx) повторюються з exponential
backoff, jitter і підтримкою `Retry-After`. Параметри задаються через
`RETRY_ATTEMPTS`, `RETRY_BASE_DELAY_SECONDS`, `RETRY_MAX_DELAY_SECONDS` або
відповідні CLI-прапорці.

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
  "model": "gemini-3.1-flash-lite",
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

Checkpoint/resume для довгих batch:

```powershell
python -m request_triage --checkpoint artifacts/triage.checkpoint.json
python -m request_triage --checkpoint artifacts/triage.checkpoint.json --resume
```

Checkpoint зберігається атомарно після кожного завершеного рядка й прив'язаний
до fingerprint вхідних даних, source-файлу та моделі. При зміні input або model
resume зупиняється з помилкою, щоб не змішати результати різних запусків.

## Optional integrations

### Google Sheets

Потрібен Google Cloud service account із увімкненим Sheets API. Поділіться
цільовою таблицею з e-mail service account і вкажіть її ID та шлях до JSON-файлу
в `.env`. Застосунок очищує діапазон `A:M` у вказаній вкладці й записує повний
поточний snapshot через `spreadsheets.values.update`.

```powershell
python -m request_triage --google-sheet
```

Альтернатива файлу — `GOOGLE_SERVICE_ACCOUNT_JSON` із повним JSON у змінній
оточення. У репозиторій credentials не додаються.

### Telegram

Створіть бота через BotFather, додайте його в потрібний чат і задайте
`TELEGRAM_BOT_TOKEN` та `TELEGRAM_CHAT_ID`. Дайджест надсилається через
`sendMessage`; довгі повідомлення автоматично розбиваються на частини.

```powershell
python -m request_triage --telegram
```

Інтеграції запускаються лише за відповідними прапорцями, тому базовий запуск
не потребує Google або Telegram credentials. Якщо прапорець увімкнено, але
конфігурація неповна або API повертає помилку, команда завершується з помилкою
після того, як локальні `output.json` та `report.md` уже збережені.

## Як валідується LLM-вивід

Gemini отримує JSON structured-output конфігурацію з Pydantic-схемою. Після
цього відповідь усе одно проходить `json.loads` і повторну Pydantic-валідацію:
enum-значення, типи та обов'язкові поля перевіряються в застосунку. Якщо JSON
битий або схема не збігається, виконується одна repair-спроба з додатковою
інструкцією. Якщо й вона невдала, рядок записується з
`processing_status="error"`, а інші запити продовжують оброблятися.

## Тести

Звичайні тести не викликають зовнішні API: використовують mock-клієнти, тому їх
можна запускати без ключа.

```powershell
pytest -q
```

Live-тести мають явний opt-in, щоб випадково не витратити квоту й не писати у
зовнішні системи:

```powershell
$env:RUN_LIVE_INTEGRATION_TESTS="1"
pytest -m live -q
```

Gemini-тест використовує `GEMINI_API_KEY` і робить один реальний запит.
Google Sheets і Telegram-тести додатково запускаються лише коли задані їхні
credentials та target-конфігурація.

## Обмеження та наступні кроки

- Async batch, bounded concurrency, rate-limit/backoff і checkpoint/resume вже
  реалізовані. Для сотень/тисяч рядків додав би зовнішнє сховище checkpoint,
  distributed lock та окрему чергу задач.
- Один успішний запит = один LLM-виклик; невалідний structured output може
  спричинити semantic retry, а transient API failure — transport retry. Це
  збільшує latency і token cost; у production потрібні метрики та оцінка
  вартості до запуску.
- `temperature=0` зменшує, але не усуває недетермінізм. Для стабільності можна
  додати golden-набір, періодичну ручну оцінку, кешування за hash вхідного тексту
  та version pinning моделі.
- Неправильний або відсутній API-ключ зупиняє запуск до LLM-викликів. Помилки
  окремих відповідей не зупиняють batch і явно потрапляють у JSON/report.
- CSV перевіряється до викликів LLM, але timestamp наразі зберігається як рядок,
  бо застосунок не виконує часових розрахунків.
- Далі додав би structured logging, prompt/version metadata, зовнішнє сховище
  checkpoint і human-in-the-loop для low confidence або
  `needs_clarification=true`.

## Docker

Збірка образу:

```powershell
docker build -t request-triage .
```

Запуск із `.env` та локальним CSV:

```powershell
docker run --rm --env-file .env `
  -v "${PWD}/input_requests.csv:/app/input_requests.csv:ro" `
  -v "${PWD}/artifacts:/app/artifacts" `
  request-triage --output /app/artifacts/output.json --report /app/artifacts/report.md
```

Для Google Sheets у контейнері передайте `GOOGLE_SERVICE_ACCOUNT_JSON` або
змонтуйте credentials-файл і вкажіть шлях через `GOOGLE_SERVICE_ACCOUNT_FILE`.

## Структура

```text
src/request_triage/
  classifier.py   # prompt, parsing, retry та per-row error isolation
  resilience.py   # rate-limit detection, retry/backoff and jitter
  checkpoint.py   # atomic checkpoint/resume storage
  csv_io.py       # читання і валідація CSV
  llm.py          # маленький Gemini adapter + testable protocol
  models.py       # Pydantic contracts
  pipeline.py     # sync/async batch із bounded concurrency
  reporting.py    # output.json та report.md
  sheets.py       # optional Google Sheets exporter
  telegram.py     # optional Telegram digest
  cli.py          # CLI та env-конфігурація
tests/            # offline unit tests
```
