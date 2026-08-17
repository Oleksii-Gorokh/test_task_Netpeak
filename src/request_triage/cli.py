from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .csv_io import read_requests
from .llm import GeminiClient
from .pipeline import run_pipeline_async
from .sheets import GoogleSheetsExporter
from .telegram import send_digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify internal requests with Gemini")
    parser.add_argument("--input", default="input_requests.csv", help="Input CSV path")
    parser.add_argument("--output", default="output.json", help="Output JSON path")
    parser.add_argument("--report", default="report.md", help="Markdown report path")
    parser.add_argument(
        "--model",
        default=None,
        help="Gemini model name (default: GEMINI_MODEL or gemini-2.5-flash-lite)",
    )
    parser.add_argument(
        "--max-attempts", type=int, default=2, help="Attempts per request (default: 2)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=None,
        help="Max in-flight LLM calls (default: TRIAGE_CONCURRENCY or 4)",
    )
    parser.add_argument(
        "--google-sheet", action="store_true",
        help="Export output to Google Sheets using service-account credentials",
    )
    parser.add_argument("--sheets-spreadsheet-id", default=None)
    parser.add_argument("--sheets-tab", default=None, help="Google Sheets tab name")
    parser.add_argument("--sheets-credentials-file", default=None)
    parser.add_argument(
        "--telegram", action="store_true", help="Send the digest to Telegram"
    )
    parser.add_argument("--telegram-bot-token", default=None)
    parser.add_argument("--telegram-chat-id", default=None)
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    model = args.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    try:
        concurrency = args.concurrency or int(os.getenv("TRIAGE_CONCURRENCY", "4"))
    except ValueError:
        print("TRIAGE_CONCURRENCY must be an integer", file=sys.stderr)
        return 2
    if args.max_attempts < 1:
        print("--max-attempts must be at least 1", file=sys.stderr)
        return 2
    if concurrency < 1:
        print("--concurrency must be at least 1", file=sys.stderr)
        return 2
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Copy .env.example to .env and add the key.", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    try:
        requests = read_requests(input_path)
        client = GeminiClient(model=model)

        async def run() -> None:
            document = await run_pipeline_async(
                requests=requests,
                client=client,
                source_file=str(input_path),
                model=model,
                output_path=args.output,
                report_path=args.report,
                max_attempts=args.max_attempts,
                concurrency=concurrency,
                progress=lambda current, total: print(
                    f"Classified {current}/{total}", file=sys.stderr
                ),
            )
            if args.google_sheet:
                spreadsheet_id = args.sheets_spreadsheet_id or os.getenv(
                    "GOOGLE_SHEETS_SPREADSHEET_ID"
                )
                if not spreadsheet_id:
                    raise ValueError("--google-sheet requires GOOGLE_SHEETS_SPREADSHEET_ID")
                exporter = GoogleSheetsExporter(
                    spreadsheet_id=spreadsheet_id,
                    tab_name=args.sheets_tab or os.getenv("GOOGLE_SHEETS_TAB", "Requests"),
                    credentials_file=args.sheets_credentials_file,
                )
                await asyncio.to_thread(exporter.export, document)
            if args.telegram:
                await send_digest(
                    document,
                    bot_token=args.telegram_bot_token,
                    chat_id=args.telegram_chat_id,
                )

        asyncio.run(run())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.output} and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
