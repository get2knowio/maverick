"""Backward-compat re-export shim for the legacy import path.

The canonical error hierarchy now lives in :mod:`maverick.runtime.errors`.
This module re-exports those names so existing
``from maverick.runtime.opencode.errors import RuntimeAuthError``
imports keep resolving while the OpenCode HTTP runtime still ships
(deleted in Phase 7 of the Pattern D migration).

New code should import from :mod:`maverick.runtime.errors` directly.
"""

from __future__ import annotations

from maverick.runtime.errors import (
    AgentRuntimeError,
    RuntimeAuthError,
    RuntimeCancelledError,
    RuntimeContextOverflowError,
    RuntimeModelNotFoundError,
    RuntimeProtocolError,
    RuntimeServerStartError,
    RuntimeStructuredOutputError,
    RuntimeTransientError,
)

__all__ = [
    "AgentRuntimeError",
    "RuntimeAuthError",
    "RuntimeCancelledError",
    "RuntimeContextOverflowError",
    "RuntimeModelNotFoundError",
    "RuntimeProtocolError",
    "RuntimeServerStartError",
    "RuntimeStructuredOutputError",
    "RuntimeTransientError",
]
