"""Exception hierarchy for the OpenCode HTTP runtime.

All errors inherit from :class:`MaverickError` so they surface cleanly at
CLI boundaries, and from :class:`OpenCodeError` so callers can catch the
runtime's failures uniformly. The hierarchy carves the failure modes that
the spike documented (Landmines 1-3, plus auth and structured-output
errors) so callers can react meaningfully without parsing message strings.
"""

from __future__ import annotations

from typing import Any

from maverick.exceptions.base import MaverickError


class OpenCodeError(MaverickError):
    """Base class for OpenCode HTTP runtime errors.

    Attributes:
        status: Optional HTTP status code from the server response.
        body: Optional decoded body (JSON or first 500 chars of text).
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class OpenCodeServerStartError(OpenCodeError):
    """Failed to spawn or reach the OpenCode subprocess."""


class OpenCodeAuthError(OpenCodeError):
    """Provider authentication failed (bad/missing API key).

    Surfaces from a ``session.error`` event with name ``ProviderAuthError``
    or equivalent. The synchronous HTTP response is empty (Landmine 2).
    """


class OpenCodeModelNotFoundError(OpenCodeError):
    """The requested model is not available on the server.

    Distinct from :class:`OpenCodeAuthError` so callers can fall back to a
    different model in a tier cascade. Raised by the validator (preferred)
    or surfaced from a ``session.error`` event when validation was skipped.
    """


class OpenCodeStructuredOutputError(OpenCodeError):
    """The model failed to produce structured output matching the schema.

    OpenCode emits this as an HTTP 4xx (catchable directly) when the
    forced ``StructuredOutput`` tool didn't validate. Distinct from
    :class:`OpenCodeTransientError` because retrying on the same model
    rarely helps; cascade to a more capable tier instead.

    Attributes:
        retries: Server-reported retry count (often 0 — the server has a
            slot but doesn't always use it).
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        body: Any = None,
        retries: int = 0,
    ) -> None:
        super().__init__(message, status=status, body=body)
        self.retries = retries


class OpenCodeContextOverflowError(OpenCodeError):
    """The prompt exceeded the model's context window even after compaction.

    Surfaces from a ``session.error`` event with name
    ``ContextOverflowError``. Not retryable on the same model; callers
    should shrink the prompt or escalate to a larger-context model.
    """


class OpenCodeTransientError(OpenCodeError):
    """Transient server/provider error: 5xx, rate limits, brief outages.

    Callers should retry with backoff (the runtime's
    :class:`tenacity.AsyncRetrying` paths handle this automatically).
    """


class OpenCodeCancelledError(OpenCodeError):
    """The session was aborted (cooperatively or via :meth:`cancel`)."""


class OpenCodeProtocolError(OpenCodeError):
    """The server returned a response that didn't match the expected shape."""
