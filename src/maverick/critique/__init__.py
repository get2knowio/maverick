"""``maverick critique`` — standalone, read-only agentic code review.

Feature 058. Runs the existing reviewer pair over one of three scopes
(working-copy diff, an epic's commits, or explicit paths) outside the fly
loop, renders findings, and persists an artifact. Creates no commit, no
bead, and no ledger entry on any path.

See ``specs/058-standalone-code-review/`` for the full contract.
"""

from __future__ import annotations

from maverick.critique.models import (
    MAX_EMBEDDED_DIFF_CHARS,
    SEVERITY_ORDER,
    CritiqueReport,
    CritiqueScopeKind,
    LensOutcome,
    ResolvedScope,
    ScopedCommit,
    order_findings,
    severity_rank,
)

__all__ = [
    "MAX_EMBEDDED_DIFF_CHARS",
    "SEVERITY_ORDER",
    "CritiqueReport",
    "CritiqueScopeKind",
    "LensOutcome",
    "ResolvedScope",
    "ScopedCommit",
    "order_findings",
    "severity_rank",
]
