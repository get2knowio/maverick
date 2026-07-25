"""JSON envelope machinery for ``--json`` CLI verbs (feature 053).

Every Maverick command invoked with ``--json`` emits exactly one JSON
document to stdout: an envelope with ``ok: true`` and a ``result`` payload
on success, or ``ok: false`` and a structured ``error`` on failure. See
``specs/053-assumption-review-console/contracts/error-envelope.md`` for the
full normative contract (this module is its implementation).

``json_error_handler()`` is the JSON-mode sibling of
:func:`maverick.cli.common.cli_error_handler` — same shape (a context
manager that catches exceptions and raises ``SystemExit``), but instead of
formatting to stderr it builds a failure :class:`JsonEnvelope`, writes it to
stdout via :func:`emit_json`, and raises ``SystemExit(ExitCode.FAILURE)``.

**Scope note on ``bd-unavailable``**: there is no single "bd unavailable"
exception type today — commands currently check via
``BeadClient.verify_available()`` returning ``False`` and print+exit
manually rather than raising. ``json_error_handler`` maps *bead exceptions*
(``BeadError`` and subclasses) to ``bd-unavailable`` when they're raised,
but the precondition check (``if not await client.verify_available():``) is
each command's own responsibility to translate into an envelope + exit in
JSON mode, same as today's non-JSON pattern — this handler cannot detect a
check that never raises.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from maverick.cli.context import ExitCode
from maverick.cli.output import write_json_document
from maverick.exceptions import (
    REASON_CONCURRENT_RUN,
    REASON_DIRTY_WORKING_COPY,
    REASON_LOCKED,
    BeadError,
    JjError,
    MaverickError,
    WorkflowError,
)
from maverick.logging import get_logger

__all__ = [
    "ErrorKind",
    "JsonError",
    "JsonEnvelope",
    "emit_json",
    "json_error_handler",
]


class ErrorKind(StrEnum):
    """Stable, machine-branchable failure taxonomy.

    Additive evolution only — values are part of the public contract (see
    ``contracts/error-envelope.md``). Never rename or remove a value.
    """

    VALIDATION = "validation"
    NOT_FOUND = "not-found"
    ALREADY_RESOLVED = "already-resolved"
    BD_UNAVAILABLE = "bd-unavailable"
    DIRTY_WORKING_COPY = "dirty-working-copy"
    CONCURRENT_RUN = "concurrent-run"
    LOCKED = "locked"
    FRONTIER_BLOCKED = "frontier-blocked"
    CONFIRMATION_REQUIRED = "confirmation-required"
    CURATION_FAILED = "curation-failed"
    VCS = "vcs"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class JsonError:
    """The ``error`` object nested inside a failure :class:`JsonEnvelope`.

    Attributes:
        kind: Stable identifier — safe to branch on.
        message: Human-readable prose — never branch on this.
        details: Verb-specific structured context; empty when there's no
            additional context to attach.
    """

    kind: ErrorKind
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JsonEnvelope:
    """The one shape every ``--json`` document takes.

    Exactly one of ``result``/``error`` is populated; :meth:`to_dict` omits
    whichever is absent rather than emitting it as ``null``.
    """

    schema_version: int
    verb: str
    ok: bool
    result: dict[str, object] | None = None
    error: JsonError | None = None

    @classmethod
    def success(cls, verb: str, result: dict[str, object]) -> JsonEnvelope:
        """Build a success envelope (``ok: true``) wrapping ``result``."""
        return cls(schema_version=1, verb=verb, ok=True, result=result)

    @classmethod
    def failure(
        cls,
        verb: str,
        kind: ErrorKind,
        message: str,
        details: dict[str, object] | None = None,
    ) -> JsonEnvelope:
        """Build a failure envelope (``ok: false``) wrapping a structured error."""
        return cls(
            schema_version=1,
            verb=verb,
            ok=False,
            error=JsonError(kind=kind, message=message, details=details or {}),
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize to the envelope's public JSON shape.

        Omits whichever of ``result``/``error`` is ``None`` entirely
        (mirroring ``LandReport.to_dict()``'s "omit absent key" style in
        ``maverick.assumptions.land_report``) rather than emitting
        ``"result": null`` / ``"error": null``.
        """
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "verb": self.verb,
            "ok": self.ok,
        }
        if self.result is not None:
            data["result"] = self.result
        if self.error is not None:
            data["error"] = {
                "kind": self.error.kind.value,
                "message": self.error.message,
                "details": self.error.details,
            }
        return data


def emit_json(envelope: JsonEnvelope) -> None:
    """Write ``envelope`` as the sole JSON document on stdout.

    Serializes via :func:`maverick.cli.output.write_json_document` — a
    dedicated, non-markup, non-wrapping Rich ``Console`` — so the document
    is never corrupted by ANSI codes or line wrapping regardless of whether
    stdout is a TTY.
    """
    write_json_document(envelope.to_dict())


# Primary dispatch: `WorkflowError.reason_code`, a stable code the raiser sets
# (see maverick.exceptions.workflow's REASON_* constants). Reword a message
# and this keeps working.
_REASON_TO_KIND: dict[str, ErrorKind] = {
    REASON_DIRTY_WORKING_COPY: ErrorKind.DIRTY_WORKING_COPY,
    REASON_CONCURRENT_RUN: ErrorKind.CONCURRENT_RUN,
    REASON_LOCKED: ErrorKind.LOCKED,
}

# Fallback dispatch for `WorkflowError`s raised without a `reason_code` —
# third-party or not-yet-migrated call sites. Substring-matching prose is
# fragile by construction; it exists only so an un-migrated raiser degrades
# to the right kind instead of `internal`. New raisers set `reason_code=`.
_MESSAGE_MARKERS: tuple[tuple[str, ErrorKind], ...] = (
    ("working copy is not clean", ErrorKind.DIRTY_WORKING_COPY),
    ("fly run is in progress", ErrorKind.CONCURRENT_RUN),
    ("already in progress", ErrorKind.LOCKED),
)


def _workflow_error_kind(exc: WorkflowError) -> ErrorKind:
    """Classify a ``WorkflowError``: typed ``reason_code`` first, prose second."""
    code = getattr(exc, "reason_code", None)
    if code is not None and code in _REASON_TO_KIND:
        return _REASON_TO_KIND[code]
    for marker, kind in _MESSAGE_MARKERS:
        if marker in exc.message:
            return kind
    return ErrorKind.INTERNAL


@contextlib.contextmanager
def json_error_handler(verb: str) -> Generator[None, None, None]:
    """JSON-mode sibling of :func:`maverick.cli.common.cli_error_handler`.

    Catches exceptions raised by a ``--json`` command body, maps them to a
    failure :class:`JsonEnvelope` for ``verb``, emits it to stdout via
    :func:`emit_json`, and raises ``SystemExit(ExitCode.FAILURE)`` — except
    ``KeyboardInterrupt``, which per the contract emits **no** JSON document
    at all (the sole exception to one-document-per-invocation) and exits
    ``ExitCode.INTERRUPTED``.

    Mapping order (specific before generic):

    1. ``KeyboardInterrupt`` -> no document, ``SystemExit(INTERRUPTED)``.
    2. ``WorkflowError`` -> dispatched on its typed ``reason_code``
       (``dirty-working-copy`` / ``concurrent-run`` / ``locked``), falling
       back to prose markers for raisers that set no ``reason_code``; anything
       unrecognized falls through to ``internal``. See
       :func:`_workflow_error_kind`.
    3. ``JjError`` (and subclasses) -> ``vcs``, with
       ``details={"operation": exc.command}`` when ``exc.command`` is set.
    4. ``BeadError`` (and subclasses, e.g. ``BeadQueryError``) ->
       ``bd-unavailable``. See the module docstring: the
       ``verify_available()`` precondition check itself is NOT covered
       here — callers must translate that check's ``False`` result into an
       envelope directly.
    5. ``AssumptionLedgerError`` -> ``validation`` (reasonable default for
       ledger write failures like empty answer/reason text; downstream
       verb implementations may special-case specific instances, e.g.
       ``already-resolved``, before ever reaching this generic handler).
    6. ``MaverickError`` (catch-all base class) -> ``internal``.
    7. Bare ``Exception`` -> ``internal``, logged via
       ``get_logger(__name__).exception(...)`` first.
    """
    # Imported lazily to avoid a hard dependency cycle at module import time
    # between maverick.cli (low-level) and maverick.assumptions (which
    # itself may import CLI-adjacent helpers in some configurations).
    from maverick.assumptions.errors import AssumptionLedgerError

    logger = get_logger(__name__)

    try:
        yield
    except KeyboardInterrupt:
        raise SystemExit(ExitCode.INTERRUPTED) from None
    except WorkflowError as e:
        emit_json(JsonEnvelope.failure(verb, _workflow_error_kind(e), e.message))
        raise SystemExit(ExitCode.FAILURE) from e
    except JjError as e:
        details: dict[str, object] = {"operation": e.command} if e.command else {}
        emit_json(JsonEnvelope.failure(verb, ErrorKind.VCS, e.message, details))
        raise SystemExit(ExitCode.FAILURE) from e
    except BeadError as e:
        emit_json(JsonEnvelope.failure(verb, ErrorKind.BD_UNAVAILABLE, e.message))
        raise SystemExit(ExitCode.FAILURE) from e
    except AssumptionLedgerError as e:
        emit_json(JsonEnvelope.failure(verb, ErrorKind.VALIDATION, e.message))
        raise SystemExit(ExitCode.FAILURE) from e
    except MaverickError as e:
        emit_json(JsonEnvelope.failure(verb, ErrorKind.INTERNAL, e.message))
        raise SystemExit(ExitCode.FAILURE) from e
    except Exception as e:
        logger.exception("Unexpected error in JSON command")
        emit_json(JsonEnvelope.failure(verb, ErrorKind.INTERNAL, str(e)))
        raise SystemExit(ExitCode.FAILURE) from e
