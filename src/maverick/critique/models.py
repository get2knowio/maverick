"""Frozen models for ``maverick critique``.

See ``specs/058-standalone-code-review/data-model.md`` for the field rules
these encode and ``contracts/critique-report-schema.md`` for the persisted
projection.

Nothing here references a bead, a ledger entry, or a commit the command
creates — ``critique`` creates none (FR-012, FR-014). :class:`ScopedCommit`
describes commits that already existed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from maverick.payloads import ReviewFindingPayload

__all__ = [
    "LENS_ORDER",
    "MAX_EMBEDDED_DIFF_CHARS",
    "SEVERITY_ORDER",
    "CritiqueReport",
    "CritiqueScopeKind",
    "LensName",
    "LensOutcome",
    "ResolvedScope",
    "ScopedCommit",
    "counts_summary",
    "lens_rank",
    "order_findings",
    "severity_rank",
]

#: Byte budget for the unified diff embedded in the reviewer's prompt
#: (research R5). The complete changed-file list is *always* sent regardless,
#: so truncation degrades the prompt's convenience, never the agent's reach —
#: it retains working-directory access and is told to read the remainder.
MAX_EMBEDDED_DIFF_CHARS = 200_000

#: Severity ordering, most severe first. Explicit rather than derived from a
#: string sort: alphabetical order happens to be correct for these three
#: values today, which is exactly the kind of accident that breaks silently
#: when a fourth severity is added.
SEVERITY_ORDER: tuple[str, ...] = ("critical", "major", "minor")

LensName = Literal["correctness", "completeness"]

#: Fixed lens order so the persisted artifact is byte-stable across runs.
LENS_ORDER: tuple[LensName, ...] = ("correctness", "completeness")


def severity_rank(severity: str) -> int:
    """Return a sort key for *severity*; unknown values sort last."""
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return len(SEVERITY_ORDER)


def lens_rank(lens: str | None) -> int:
    """Return a sort key for a lens name; unknown values sort last.

    Ranked by :data:`LENS_ORDER` rather than alphabetically so findings and
    the ``lenses`` array agree — alphabetical order would put completeness
    first in one place and correctness first in the other.
    """
    if lens is None:
        return len(LENS_ORDER)
    try:
        return LENS_ORDER.index(lens)  # type: ignore[arg-type]
    except ValueError:
        return len(LENS_ORDER)


class CritiqueScopeKind(StrEnum):
    """What a critique invocation was pointed at.

    Exactly three, per FR-002. The value appears verbatim in the persisted
    artifact and the ``--json`` envelope, so it is a stable contract string.
    """

    DIFF = "diff"
    EPIC = "epic"
    PATHS = "paths"


@dataclass(frozen=True, slots=True)
class ScopedCommit:
    """One commit attributed to an epic (research R3).

    ``bead_ids`` exists so a reader can *verify* the attribution rather than
    trust the count — the epic scope's correctness is entirely a question of
    which commits it claimed.
    """

    sha: str
    subject: str
    bead_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "subject": self.subject,
            "bead_ids": list(self.bead_ids),
        }


@dataclass(frozen=True, slots=True)
class ResolvedScope:
    """The answer to "what is being reviewed", computed before any agent runs.

    Attributes:
        kind: Which of the three scopes this is.
        summary: One human line, rendered verbatim (FR-019).
        paths: Repo-relative. On ``PATHS`` these are what the user named; on
            ``DIFF``/``EPIC`` they are the changed-file union. Always
            populated for a non-empty scope, even when ``diff_text`` was
            truncated — the agent must never lose the complete file list.
        diff_text: Unified diff, possibly truncated at
            :data:`MAX_EMBEDDED_DIFF_CHARS`.
        diff_truncated: Whether ``diff_text`` was cut.
        diff_stat: Raw ``--stat`` output. Never truncated (it is bounded by
            file count, not content size).
        base: Set on ``DIFF`` only.
        epic_id: Set on ``EPIC`` only.
        commits: Non-empty on a non-empty ``EPIC`` scope; empty otherwise.
    """

    kind: CritiqueScopeKind
    summary: str
    paths: tuple[str, ...] = ()
    diff_text: str = ""
    diff_truncated: bool = False
    diff_stat: str = ""
    base: str | None = None
    epic_id: str | None = None
    commits: tuple[ScopedCommit, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to review.

        Checked *before* the squadron is built, so an empty scope costs zero
        model calls (FR-009, SC-004).
        """
        return not self.paths and not self.diff_text

    def to_dict(self) -> dict[str, Any]:
        """Project to the persisted shape.

        ``diff_text`` is deliberately not persisted — it can be hundreds of
        kilobytes, it is reconstructible from the repository, and an artifact
        whose size is dominated by a diff nobody reads is a bad artifact.
        ``diff_truncated`` rides on :class:`CritiqueReport` as ``truncated``.
        """
        data: dict[str, Any] = {
            "kind": str(self.kind),
            "summary": self.summary,
            "paths": list(self.paths),
        }
        if self.base is not None:
            data["base"] = self.base
        if self.epic_id is not None:
            data["epic_id"] = self.epic_id
        if self.kind is CritiqueScopeKind.EPIC:
            data["commits"] = [c.to_dict() for c in self.commits]
        return data


@dataclass(frozen=True, slots=True)
class LensOutcome:
    """One reviewer lens's result, successful or not.

    Models FR-011's partial success: a lens never carries both findings and
    an error. ``approved`` is ``None`` on failure, which is deliberately
    distinct from ``False`` — "the lens did not approve" and "the lens did
    not run" are different facts.
    """

    lens: LensName
    findings: tuple[ReviewFindingPayload, ...] = ()
    approved: bool | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"lens": self.lens}
        if self.failed:
            data["error"] = self.error
            return data
        data["approved"] = bool(self.approved)
        data["finding_count"] = len(self.findings)
        return data


def order_findings(
    findings: Sequence[ReviewFindingPayload],
) -> tuple[ReviewFindingPayload, ...]:
    """Return *findings* in the one canonical order.

    File ascending, then severity most-severe-first, then lens, then line.

    The order is fixed rather than incidental because three surfaces must
    agree on it — the terminal grouping, the persisted JSON, and the
    ``--json`` envelope. SC-006 asserts the terminal output and the artifact
    hold the same findings, and that assertion is only checkable if both are
    ordered identically.
    """

    def key(f: ReviewFindingPayload) -> tuple[Any, ...]:
        return (
            f.file or "￿",  # unattributed findings sort last
            severity_rank(f.severity),
            lens_rank(f.reviewer),
            f.line if f.line is not None else -1,
            f.issue,
        )

    return tuple(sorted(findings, key=key))


@dataclass(frozen=True, slots=True)
class CritiqueReport:
    """The complete outcome of one ``maverick critique`` invocation."""

    run_id: str
    created_at: str
    scope: ResolvedScope
    lenses: tuple[LensOutcome, ...] = ()
    findings: tuple[ReviewFindingPayload, ...] = ()
    degraded_persistence: bool = False
    schema_version: int = field(default=1)

    @property
    def reviewed(self) -> bool:
        """False when the scope was empty — nothing ran (FR-016)."""
        return not self.scope.is_empty

    @property
    def truncated(self) -> bool:
        return self.scope.diff_truncated

    @property
    def lens_failures(self) -> tuple[LensOutcome, ...]:
        return tuple(lens for lens in self.lenses if lens.failed)

    @property
    def severity_counts(self) -> dict[str, int]:
        """Per-severity counts with every key present, zeros included.

        A consumer must never have to distinguish "no critical findings" from
        "the ``critical`` key is missing".
        """
        counts = dict.fromkeys(SEVERITY_ORDER, 0)
        for finding in self.findings:
            if finding.severity in counts:
                counts[finding.severity] += 1
        return counts

    def exceeds(self, severity: str) -> bool:
        """True when any finding is at or above *severity* (FR-006)."""
        threshold = severity_rank(severity)
        return any(severity_rank(f.severity) <= threshold for f in self.findings)

    def findings_by_file(self) -> Iterator[tuple[str, tuple[ReviewFindingPayload, ...]]]:
        """Yield ``(file, findings)`` groups in canonical order.

        ``findings`` is already ordered by :func:`order_findings`, so a single
        pass preserves both the file order and the within-file order.
        """
        current: str | None = None
        bucket: list[ReviewFindingPayload] = []
        for finding in self.findings:
            name = finding.file or ""
            if current is None or name != current:
                if current is not None:
                    yield current, tuple(bucket)
                current = name
                bucket = []
            bucket.append(finding)
        if current is not None:
            yield current, tuple(bucket)

    def to_dict(self) -> dict[str, Any]:
        """Project to the persisted / envelope shape.

        Key order and the omit-when-absent rule follow ``LandReport``
        (``specs/052-conditional-landing/contracts/land-report-schema.md``).
        """
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "reviewed": self.reviewed,
            "scope": self.scope.to_dict(),
            "lenses": [lens.to_dict() for lens in self.lenses],
            "findings": [_finding_to_dict(f) for f in self.findings],
            "severity_counts": self.severity_counts,
            "truncated": self.truncated,
        }


def _finding_to_dict(finding: ReviewFindingPayload) -> dict[str, Any]:
    """Project one finding, omitting ``line`` when unknown.

    Deliberately not ``model_dump()``: that would also emit any extra fields
    the permissive payload model preserved from the provider, and the schema
    contract enumerates exactly five keys.
    """
    data: dict[str, Any] = {
        "severity": finding.severity,
        "issue": finding.issue,
        "file": finding.file,
    }
    if finding.line is not None:
        data["line"] = finding.line
    if finding.reviewer is not None:
        data["reviewer"] = finding.reviewer
    return data


def counts_summary(counts: Mapping[str, int]) -> str:
    """Render ``{"critical": 1, ...}`` as ``"1 critical, 2 major, 0 minor"``."""
    return ", ".join(f"{counts.get(sev, 0)} {sev}" for sev in SEVERITY_ORDER)
