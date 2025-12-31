"""MCP response formatting helpers for Git tools.

This module provides functions to create standardized MCP success and error responses.
"""

from __future__ import annotations

import json
from typing import Any


def success_response(data: dict[str, Any]) -> dict[str, Any]:
    """Create MCP success response.

    Args:
        data: Response data to serialize.

    Returns:
        MCP-formatted success response.
    """
    return {"content": [{"type": "text", "text": json.dumps(data)}]}


def error_response(
    message: str,
    error_code: str,
    retry_after_seconds: int | None = None,
) -> dict[str, Any]:
    """Create MCP error response.

    Args:
        message: Human-readable error message.
        error_code: Machine-readable error code.
        retry_after_seconds: Optional retry delay for rate limiting.

    Returns:
        MCP-formatted error response.
    """
    error_data: dict[str, Any] = {
        "isError": True,
        "message": message,
        "error_code": error_code,
    }
    if retry_after_seconds is not None:
        error_data["retry_after_seconds"] = retry_after_seconds
    return {"content": [{"type": "text", "text": json.dumps(error_data)}]}
