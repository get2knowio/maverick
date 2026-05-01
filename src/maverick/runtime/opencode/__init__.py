"""OpenCode HTTP runtime package.

Replaces the per-provider ACP bridge + custom MCP-gateway substrate with
a single OpenCode HTTP server. Public API:

* :class:`OpenCodeClient` — async HTTP client (sessions, sends, events,
  cancellation, structured-output extraction with envelope unwrap).
* :class:`SendResult` — typed wrapper returned by
  :meth:`OpenCodeClient.send_with_event_watch`.
* :func:`structured_of`, :func:`structured_valid`, :func:`text_of`,
  :func:`classify_session_error` — payload helpers.
* :func:`spawn_opencode_server`, :func:`opencode_server`,
  :func:`client_for`, :class:`OpenCodeServerHandle` — server lifecycle.
* :func:`validate_model_id`, :func:`list_connected_providers`,
  :func:`invalidate_cache` — provider/model validation (Landmine 1).
* :class:`EventWatcher`, :func:`collect_events`, :func:`first_error` —
  SSE event helpers.
* Error hierarchy: :class:`OpenCodeError` and subclasses.
"""

from __future__ import annotations

from maverick.runtime.opencode.client import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    OpenCodeClient,
    SendResult,
    classify_session_error,
    structured_of,
    structured_valid,
    text_of,
)
from maverick.runtime.opencode.errors import (
    OpenCodeAuthError,
    OpenCodeCancelledError,
    OpenCodeContextOverflowError,
    OpenCodeError,
    OpenCodeModelNotFoundError,
    OpenCodeProtocolError,
    OpenCodeServerStartError,
    OpenCodeStructuredOutputError,
    OpenCodeTransientError,
)
from maverick.runtime.opencode.events import (
    DEFAULT_FORWARD_TYPES,
    EventCallback,
    EventWatcher,
    collect_events,
    first_error,
    session_idle_signal,
)
from maverick.runtime.opencode.executor import OpenCodeStepExecutor
from maverick.runtime.opencode.registry import (
    opencode_handle_for,
    register_opencode_handle,
    unregister_opencode_handle,
)
from maverick.runtime.opencode.server import (
    DEFAULT_HOST,
    DEFAULT_SHUTDOWN_TIMEOUT,
    DEFAULT_STARTUP_TIMEOUT,
    OpenCodeServerHandle,
    client_for,
    opencode_server,
    spawn_opencode_server,
)
from maverick.runtime.opencode.validation import (
    DEFAULT_CACHE_TTL_SECONDS,
    invalidate_cache,
    list_connected_providers,
    validate_model_id,
)

__all__ = [
    # client
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "OpenCodeClient",
    "SendResult",
    "classify_session_error",
    "structured_of",
    "structured_valid",
    "text_of",
    # errors
    "OpenCodeError",
    "OpenCodeAuthError",
    "OpenCodeCancelledError",
    "OpenCodeContextOverflowError",
    "OpenCodeModelNotFoundError",
    "OpenCodeProtocolError",
    "OpenCodeServerStartError",
    "OpenCodeStructuredOutputError",
    "OpenCodeTransientError",
    # events
    "DEFAULT_FORWARD_TYPES",
    "EventCallback",
    "EventWatcher",
    "collect_events",
    "first_error",
    "session_idle_signal",
    # server
    "DEFAULT_HOST",
    "DEFAULT_SHUTDOWN_TIMEOUT",
    "DEFAULT_STARTUP_TIMEOUT",
    "OpenCodeServerHandle",
    "client_for",
    "opencode_server",
    "spawn_opencode_server",
    # validation
    "DEFAULT_CACHE_TTL_SECONDS",
    "invalidate_cache",
    "list_connected_providers",
    "validate_model_id",
    # registry
    "opencode_handle_for",
    "register_opencode_handle",
    "unregister_opencode_handle",
    # executor
    "OpenCodeStepExecutor",
]
