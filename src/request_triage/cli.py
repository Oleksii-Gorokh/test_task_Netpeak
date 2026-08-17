from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .csv_io import read_requests
from .llm import GeminiClient
from .pipeline import run_pipeline


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
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    model = args.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    if args.max_attempts < 1:
        print("--max-attempts must be at least 1", file=sys.stderr)
        return 2
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Copy .env.example to .env and add the key.", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    try:
        requests = read_requests(input_path)
        client = GeminiClient(model=model)
        run_pipeline(
            requests=requests,
            client=client,
            source_file=str(input_path),
            model=model,
            output_path=args.output,
            report_path=args.report,
            max_attempts=args.max_attempts,
            progress=lambda current, total: print(f"Classified {current}/{total}", file=sys.stderr),
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.output} and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
