"""CLI stub for manually invoking the review/fix Temporal activity.

This module provides the wiring that later phases will flesh out to enqueue
run_review_fix executions with proper payload validation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from src.common.logging import get_logger


logger = get_logger(__name__)


def _load_payload(path: Path) -> dict[str, Any]:
    """Load a JSON payload from disk for the upcoming review/fix activity."""

    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Input payload is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Input payload must be a JSON object")
    return data


async def _dispatch(args: argparse.Namespace) -> int:
    """Handle CLI arguments for the review/fix activity stub."""

    payload: dict[str, Any] | None = None

    if args.input:
        input_path = Path(args.input).expanduser().resolve()
        if not input_path.exists():
            print(f"Error: Input file not found: {input_path}", file=sys.stderr)
            return 2
        try:
            payload = _load_payload(input_path)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        logger.info("Loaded review/fix payload from %s", input_path)

    logger.info("review_fix_cli_stub_invoked has_payload=%s", payload is not None)
    print(
        "Review/fix activity CLI stub reached. Implementation will be added in later phases.",
    )
    return 0


def main() -> None:
    """Entry point for the review-fix-activity CLI script."""

    parser = argparse.ArgumentParser(
        description="Manually invoke the review/fix Temporal activity (stub)",
    )
    parser.add_argument(
        "--input",
        help="Path to JSON payload describing the review/fix input",
    )

    args = parser.parse_args()
    exit_code = asyncio.run(_dispatch(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
