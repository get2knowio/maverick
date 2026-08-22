"""Execution for ``maverick critique``: run both lenses, build the report.

The empty-scope short-circuit here is load-bearing, not an optimization:
FR-009 and SC-004 require that an empty scope never reaches a model, and the
only way to guarantee that is to return before the squadron is constructed.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from maverick.critique.models import (
    LENS_ORDER,
    CritiqueReport,
    LensOutcome,
    order_findings,
)
from maverick.exceptions import MaverickError
from maverick.logging import get_logger
from maverick.payloads import review_payload_approved
from maverick.squadron.critique import CritiqueSquadron

if TYPE_CHECKING:
    from pathlib import Path

    from maverick.agents.reviewer import ReviewerAgent
    from maverick.config import MaverickConfig
    from maverick.critique.models import LensName, ResolvedScope
    from maverick.payloads import SubmitReviewPayload

__all__ = ["AllLensesFailedError", "build_change_summary", "run_critique"]

logger = get_logger(__name__)


class AllLensesFailedError(MaverickError):
    """Both reviewer lenses failed — the review could not be performed.

    One lens failing is a warning (FR-011); both failing means there is no
    review, which is a genuine failure.
    """


def build_change_summary(scope: ResolvedScope) -> str:
    """Assemble the reviewer's view of the change.

    Ordering matters: the file list comes first and is never truncated, so a
    reviewer that reads only the top of a long prompt still knows the full
    extent of what changed. The diff — the part that may have been cut —
    comes last.
    """
    sections: list[str] = []
    if scope.paths:
        listing = "\n".join(f"- {p}" for p in scope.paths)
        sections.append(f"## Files in scope ({len(scope.paths)})\n\n{listing}")
    if scope.diff_stat:
        sections.append(f"## Diff stat\n\n```\n{scope.diff_stat}\n```")
    if scope.diff_text:
        note = (
            "\n\n_(Diff truncated at the embedding budget — read the "
            "remaining files listed above directly.)_"
            if scope.diff_truncated
            else ""
        )
        sections.append(f"## Diff\n\n```diff\n{scope.diff_text}\n```{note}")
    return "\n\n".join(sections)


async def _run_lens(
    reviewer: ReviewerAgent,
    *,
    lens: LensName,
    scope_summary: str,
    change_summary: str,
) -> LensOutcome:
    """Run one lens, converting any failure into a :class:`LensOutcome`.

    Catches broadly on purpose: FR-011 says one lens failing degrades to a
    warning, and that promise cannot be kept by enumerating the exception
    types an arbitrary provider adapter might raise.
    """
    try:
        payload: SubmitReviewPayload = await reviewer.critique(
            scope_summary=scope_summary,
            change_summary=change_summary,
        )
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning("critique_lens_failed", lens=lens, error=str(exc))
        return LensOutcome(lens=lens, error=str(exc))
    return LensOutcome(
        lens=lens,
        findings=tuple(payload.findings),
        approved=review_payload_approved(payload),
    )


async def run_critique(
    *,
    cwd: Path,
    config: MaverickConfig,
    scope: ResolvedScope,
    run_id: str,
) -> CritiqueReport:
    """Review *scope* with both lenses and return the report.

    Args:
        cwd: The checkout. Threaded from the CLI boundary (Guardrail 7).
        config: Loaded ``maverick.yaml``.
        scope: Already resolved — this function performs no VCS or bead reads.
        run_id: Minted at the CLI boundary.

    Returns:
        The report. Findings are in the one canonical order.

    Raises:
        AllLensesFailedError: Neither lens produced a result.
    """
    created_at = datetime.now(UTC).isoformat()

    if scope.is_empty:
        # Before any squadron, any runtime, any model call (FR-009, SC-004).
        return CritiqueReport(run_id=run_id, created_at=created_at, scope=scope)

    change_summary = build_change_summary(scope)

    async with CritiqueSquadron(cwd=cwd, config=config) as squadron:
        reviewers: dict[LensName, ReviewerAgent] = {
            "correctness": squadron.correctness_reviewer,
            "completeness": squadron.completeness_reviewer,
        }
        outcomes = await asyncio.gather(
            *(
                _run_lens(
                    reviewers[lens],
                    lens=lens,
                    scope_summary=scope.summary,
                    change_summary=change_summary,
                )
                for lens in LENS_ORDER
            )
        )

    if all(outcome.failed for outcome in outcomes):
        reasons = "; ".join(f"{o.lens}: {o.error}" for o in outcomes)
        raise AllLensesFailedError(f"both reviewer lenses failed — {reasons}")

    findings = order_findings([finding for outcome in outcomes for finding in outcome.findings])
    return CritiqueReport(
        run_id=run_id,
        created_at=created_at,
        scope=scope,
        lenses=tuple(outcomes),
        findings=findings,
    )
