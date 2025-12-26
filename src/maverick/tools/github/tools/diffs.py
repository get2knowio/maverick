from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool

from maverick.logging import get_logger
from maverick.tools.github.errors import classify_error
from maverick.tools.github.responses import error_response, success_response
from maverick.tools.github.runner import run_gh_command

logger = get_logger(__name__)

#: Default max diff size in bytes (100KB)
DEFAULT_MAX_DIFF_SIZE: int = 102400


@tool(
    "github_get_pr_diff",
    "Get the diff content for a pull request",
    {"pr_number": int, "max_size": int},
)
async def github_get_pr_diff(args: dict[str, Any]) -> dict[str, Any]:
    """Get PR diff with truncation (T034-T036)."""
    pr_number = args["pr_number"]
    max_size = args.get("max_size", DEFAULT_MAX_DIFF_SIZE)

    # Validate
    if pr_number < 1:
        return error_response("PR number must be positive", "INVALID_INPUT")
    if max_size < 1:
        return error_response("Max size must be positive", "INVALID_INPUT")

    logger.info("Getting diff for PR #%d (max_size=%d)", pr_number, max_size)

    cmd_args = ["pr", "diff", str(pr_number)]

    try:
        stdout, stderr, return_code = await run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"PR #{pr_number} not found"
                error_code = "NOT_FOUND"
            logger.warning("Get PR diff failed: %s", message)
            return error_response(message, error_code, retry_after)

        diff = stdout
        original_size = len(diff.encode("utf-8"))
        truncated = original_size > max_size

        if truncated:
            # Truncate at byte boundary to avoid breaking multibyte UTF-8 characters
            diff_bytes = diff.encode("utf-8")[:max_size]
            diff = diff_bytes.decode("utf-8", errors="ignore")
            logger.info("Diff truncated from %d to %d bytes", original_size, max_size)
            return success_response(
                {
                    "diff": diff,
                    "truncated": True,
                    "warning": f"Diff truncated at {max_size // 1024}KB",
                    "original_size_bytes": original_size,
                }
            )

        logger.info("Retrieved diff for PR #%d (%d bytes)", pr_number, original_size)
        return success_response({"diff": diff, "truncated": False})

    except TimeoutError:
        logger.error("Timeout getting PR #%d diff", pr_number)
        return error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error getting PR diff")
        return error_response(str(e), "INTERNAL_ERROR")
