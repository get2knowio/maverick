"""Vendor-agnostic exception hierarchy for agent runtimes.

The class names use ``AgentRuntimeError`` (base) and ``Runtime*Error``
(subclasses) so every adapter (Claude Code, Copilot, Codex, OpenCode,
Anthropic, etc.) raises the same types regardless of vendor. The
cascade machinery in :mod:`maverick.runtime.tiers` classifies failures
by these types and decides what to do based on which subclass fired.

The base class is **``AgentRuntimeError``** rather than ``RuntimeError``
to avoid shadowing Python's builtin :class:`RuntimeError` at every
``except`` site. The subclasses keep the shorter ``Runtime*Error``
prefix because they're already specific (no name collision).

The hierarchy carves the failure modes the cascade needs to distinguish:

- :class:`RuntimeAuthError` — credentials bad / expired / missing.
  Cascade falls over to the next binding.
- :class:`RuntimeModelNotFoundError` — server says the model isn't
  available on this binding. Cascade falls over.
- :class:`RuntimeTransientError` — 5xx, rate-limit, brief network
  hiccup. Same-binding retry with backoff; only after exhausting
  retries does the cascade fall over.
- :class:`RuntimeStructuredOutputError` — model returned without the
  required typed payload. Cascade falls over (retrying on the same
  binding rarely helps for capability gaps).
- :class:`RuntimeContextOverflowError` — prompt exceeded context
  window even after the adapter's compaction. *Not* cascadable; the
  caller needs a larger context model or a shorter prompt.
- :class:`RuntimeProtocolError` — adapter saw something it can't
  interpret (empty body, malformed JSON-RPC, etc.). Surfaces as a
  bug, not a recoverable condition.
- :class:`RuntimeServerStartError` — adapter failed to come up at
  all (subprocess didn't launch, HTTP server unreachable). Fatal.
- :class:`RuntimeCancelledError` — caller-initiated abort. Not a
  failure, just bookkeeping.

All inherit from :class:`AgentRuntimeError` which inherits from
:class:`MaverickError`.
"""

from __future__ import annotations

from typing import Any

from maverick.exceptions.base import MaverickError


class AgentRuntimeError(MaverickError):
    """Base class for agent-runtime adapter errors.

    Attributes:
        status: Optional HTTP / RPC status code from the server.
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


class RuntimeServerStartError(AgentRuntimeError):
    """Failed to launch the runtime backend (subprocess, server, etc.)."""


class RuntimeAuthError(AgentRuntimeError):
    """Provider authentication failed (bad / missing / expired credentials).

    Cascadable: the cascade should try the next binding rather than
    retrying the same one.
    """


class RuntimeModelNotFoundError(AgentRuntimeError):
    """The requested model is not available on this binding.

    Distinct from :class:`RuntimeAuthError` so callers can fall back
    to a different binding within the same tier.
    """


class RuntimeStructuredOutputError(AgentRuntimeError):
    """The model failed to produce structured output matching the schema.

    Cascade falls over: the binding's capability gap won't be fixed
    by retrying the same model with the same prompt.

    Attributes:
        retries: Adapter-reported retry count (often 0 — many adapters
            don't expose this).
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


class RuntimeContextOverflowError(AgentRuntimeError):
    """Prompt exceeded the model's context window even after compaction.

    NOT cascadable — falling over to a smaller-context model just hits
    the same wall. Callers should shrink the prompt or escalate to a
    larger-context model explicitly.
    """


class RuntimeTransientError(AgentRuntimeError):
    """Transient server/provider error: 5xx, rate limits, brief outages.

    Callers should retry with exponential backoff on the same binding
    before letting the cascade fall over.
    """


class RuntimeCancelledError(AgentRuntimeError):
    """The session was aborted (cooperatively or by an explicit cancel)."""


class RuntimeProtocolError(AgentRuntimeError):
    """The runtime returned a response that didn't match the expected shape.

    Distinct from :class:`RuntimeTransientError` because protocol
    violations indicate a bug or version drift, not a recoverable
    transient condition.
    """


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
