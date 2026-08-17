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
from .resilience import RateLimiter, RetryPolicy
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
        help="Gemini model name (default: GEMINI_MODEL or gemini-3.1-flash-lite)",
    )
    parser.add_argument(
        "--max-attempts", type=int, default=2, help="Attempts per request (default: 2)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=None,
        help="Max in-flight LLM calls (default: TRIAGE_CONCURRENCY or 4)",
    )
    parser.add_argument(
        "--retry-attempts", type=int, default=None,
        help="Max attempts for transient API errors (default: RETRY_ATTEMPTS or 4)",
    )
    parser.add_argument(
        "--retry-base-delay", type=float, default=None,
        help="Initial retry delay in seconds (default: RETRY_BASE_DELAY_SECONDS or 1)",
    )
    parser.add_argument(
        "--retry-max-delay", type=float, default=None,
        help="Maximum retry delay in seconds (default: RETRY_MAX_DELAY_SECONDS or 30)",
    )
    parser.add_argument(
        "--min-interval", type=float, default=None,
        help="Minimum seconds between Gemini requests (default: GEMINI_MIN_INTERVAL_SECONDS or 4)",
    )
    parser.add_argument(
        "--checkpoint", default=None,
        help="Path for atomic per-request checkpoint JSON",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume successful rows from --checkpoint",
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
    model = args.model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    try:
        concurrency = args.concurrency or int(os.getenv("TRIAGE_CONCURRENCY", "4"))
        retry_policy = RetryPolicy(
            max_attempts=args.retry_attempts
            if args.retry_attempts is not None
            else int(os.getenv("RETRY_ATTEMPTS", "4")),
            base_delay_seconds=(
                args.retry_base_delay
                if args.retry_base_delay is not None
                else float(os.getenv("RETRY_BASE_DELAY_SECONDS", "1"))
            ),
            max_delay_seconds=(
                args.retry_max_delay
                if args.retry_max_delay is not None
                else float(os.getenv("RETRY_MAX_DELAY_SECONDS", "30"))
            ),
        )
        min_interval = (
            args.min_interval
            if args.min_interval is not None
            else float(os.getenv("GEMINI_MIN_INTERVAL_SECONDS", "4"))
        )
        rate_limiter = RateLimiter(min_interval)
    except ValueError:
        print("Invalid concurrency or retry configuration", file=sys.stderr)
        return 2
    if args.max_attempts < 1:
        print("--max-attempts must be at least 1", file=sys.stderr)
        return 2
    if concurrency < 1:
        print("--concurrency must be at least 1", file=sys.stderr)
        return 2
    if args.resume and not args.checkpoint:
        print("--resume requires --checkpoint", file=sys.stderr)
        return 2
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Copy .env.example to .env and add the key.", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    try:
        requests = read_requests(input_path)
        client = GeminiClient(
            model=model,
            retry_policy=retry_policy,
            rate_limiter=rate_limiter,
        )

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
                checkpoint_path=args.checkpoint,
                resume=args.resume,
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
                    retry_policy=retry_policy,
                )
                await asyncio.to_thread(exporter.export, document)
            if args.telegram:
                await send_digest(
                    document,
                    bot_token=args.telegram_bot_token,
                    chat_id=args.telegram_chat_id,
                    retry_policy=retry_policy,
                )

        asyncio.run(run())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.output} and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
