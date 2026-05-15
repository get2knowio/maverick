"""Legacy ``OpenCode*Error`` aliases — kept for one cycle.

The canonical names now live in :mod:`maverick.runtime.errors` as
``Runtime*Error``. This module re-exports them under the legacy
``OpenCode*Error`` names so existing code (including the soon-to-be-
deleted ``runtime/opencode/`` package itself) keeps compiling.

New code SHOULD import from :mod:`maverick.runtime.errors` directly.
This shim disappears when ``runtime/opencode/`` is deleted in Phase 7
of the Pattern D migration (see ``docs/migration-implementation-plan.md``).

The aliases are direct class identities, not subclasses — every
``OpenCodeAuthError`` is literally the same class object as
``RuntimeAuthError``. ``isinstance(e, OpenCodeAuthError)`` is true
iff ``isinstance(e, RuntimeAuthError)`` is true. Callers can mix and
match the names freely during the transition.
"""

from __future__ import annotations

from maverick.runtime.errors import (
    RuntimeAuthError,
    RuntimeCancelledError,
    RuntimeContextOverflowError,
    RuntimeError,
    RuntimeModelNotFoundError,
    RuntimeProtocolError,
    RuntimeServerStartError,
    RuntimeStructuredOutputError,
    RuntimeTransientError,
)

# Legacy aliases. Each is the same class object as its Runtime* counterpart.
OpenCodeError = RuntimeError
OpenCodeServerStartError = RuntimeServerStartError
OpenCodeAuthError = RuntimeAuthError
OpenCodeModelNotFoundError = RuntimeModelNotFoundError
OpenCodeStructuredOutputError = RuntimeStructuredOutputError
OpenCodeContextOverflowError = RuntimeContextOverflowError
OpenCodeTransientError = RuntimeTransientError
OpenCodeCancelledError = RuntimeCancelledError
OpenCodeProtocolError = RuntimeProtocolError
