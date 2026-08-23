"""Delta-layer exception hierarchy.

Structural grammar failures (:class:`DeltaFormatError`) come out of
``parser.py`` and always carry a stable ``code`` plus the offending
``line`` — the same shape ``validate.py``'s semantic
:class:`~maverick.speckit.delta.validate.Problem` list uses, so a caller
can render/branch on either uniformly (``contracts/cli-delta-json.md``).
"""

from __future__ import annotations

from maverick.speckit.errors import SpeckitError


class StaleAcknowledgementError(SpeckitError):
    """An ``--ack TASK_ID`` names a task that is not an outstanding
    impact (FR-015b) — a stale acknowledgement must fail rather than be
    silently ignored, so a leftover ``--ack`` in a script can never
    appear to authorize something while authorizing nothing.

    Attributes:
        message: Human-readable error message.
        stale_task_ids: The acknowledged ids that named no real impact.
    """

    def __init__(self, stale_task_ids: tuple[str, ...]) -> None:
        self.stale_task_ids = stale_task_ids
        super().__init__(
            f"--ack given for task(s) that are not impacts: {', '.join(stale_task_ids)}"
        )


class DeltaFormatError(SpeckitError):
    """A delta document violates the grammar in
    ``contracts/delta-document-format.md`` badly enough that it cannot be
    parsed into a :class:`~maverick.speckit.delta.models.DeltaDocument`
    at all.

    Attributes:
        message: Human-readable error message.
        code: Stable code from ``contracts/cli-delta-json.md``'s
            problem-code enumeration (e.g. ``"malformed-document"``,
            ``"unbalanced-rename"``, ``"malformed-task-line"``).
        line: 1-based line number in the delta document.
    """

    def __init__(self, message: str, *, code: str, line: int) -> None:
        self.code = code
        self.line = line
        super().__init__(message)


__all__ = ["DeltaFormatError", "StaleAcknowledgementError"]
