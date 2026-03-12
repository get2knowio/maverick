"""Extracted step functions for FlyBeadsWorkflow bead loop.

Each function receives the workflow instance (for emit_* and _step_executor)
and a BeadContext that threads mutable state through the pipeline.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.executor.config import StepConfig
from maverick.library.actions.beads import (
    create_beads_from_failures,
    create_beads_from_findings,
    mark_bead_complete,
    verify_bead_completion,
)
from maverick.library.actions.dependencies import sync_dependencies
from maverick.library.actions.jj import (
    jj_commit_bead,
    jj_describe,
    jj_restore_operation,
    jj_snapshot_operation,
)
from maverick.library.actions.review import (
    gather_local_review_context,
    run_review_fix_loop,
)
from maverick.library.actions.runway import record_bead_outcome, record_review_findings
from maverick.library.actions.validation import run_fix_retry_loop
from maverick.logging import get_logger
from maverick.types import StepType
from maverick.workflows.fly_beads.constants import (
    COMMIT,
    DEFAULT_BASE_BRANCH,
    DEFAULT_MAX_FIX_ATTEMPTS,
    DEFAULT_MAX_REVIEW_ATTEMPTS,
    DEFAULT_VALIDATION_STAGES,
    IMPLEMENT,
    MAX_VERIFY_CYCLES,
    REVIEW,
    SYNC_DEPS,
    VALIDATE,
)
from maverick.workflows.fly_beads.models import BeadContext

if TYPE_CHECKING:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

logger = get_logger(__name__)


def load_briefing_context(flight_plan_name: str | None) -> str | None:
    """Read briefing markdown from plan directory.

    Returns:
        Briefing text or None if not found.
    """
    if not flight_plan_name:
        return None
    plan_dir = Path.cwd() / ".maverick" / "plans" / flight_plan_name
    for candidate in ("refuel-briefing.md", "briefing.md"):
        briefing_path = plan_dir / candidate
        if briefing_path.is_file():
            with contextlib.suppress(Exception):
                return briefing_path.read_text(encoding="utf-8")
    return None


async def snapshot_and_describe(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Snapshot jj operation and set WIP description."""
    snapshot_result = await jj_snapshot_operation(cwd=ctx.cwd)
    ctx.operation_id = snapshot_result.get("operation_id")
    await jj_describe(
        message=f"WIP bead({ctx.bead_id}): {ctx.title}",
        cwd=ctx.cwd,
    )


async def run_implement(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Execute the implement agent step.

    On failure: emits step_failed (not step_completed), logs warning.
    Does NOT propagate — bead continues to validate.
    """
    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(IMPLEMENT, step_type=StepType.AGENT)

    if wf._step_executor is not None:
        implement_prompt: dict[str, Any] = {
            "task_description": ctx.description,
            "cwd": cwd_str,
        }
        if ctx.prior_failures:
            implement_prompt["previous_failures"] = (
                "This bead failed in previous attempt(s). "
                "Address these issues:\n"
                + "\n".join(
                    f"- Attempt {i + 1}: {reason}"
                    for i, reason in enumerate(ctx.prior_failures)
                )
            )
        try:
            await wf._step_executor.execute(
                step_name=IMPLEMENT,
                agent_name="implementer",
                prompt=implement_prompt,
                cwd=ctx.cwd,
                config=StepConfig(timeout=600),
            )
        except Exception as exc:
            logger.warning(
                "implement_step_failed",
                bead_id=ctx.bead_id,
                error=str(exc),
            )
            await wf.emit_step_failed(IMPLEMENT, str(exc))
            await wf.emit_output(
                IMPLEMENT,
                f"Implement step failed: {exc}",
                level="warning",
            )
            return
    else:
        await wf.emit_output(
            IMPLEMENT,
            "No step executor configured — skipping agent implement step",
            level="warning",
        )

    await wf.emit_step_completed(IMPLEMENT)


async def run_sync_deps(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Sync dependencies. Raises on failure (stops bead)."""
    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(SYNC_DEPS)
    try:
        sync_result = await sync_dependencies(cwd=cwd_str)
    except Exception as exc:
        await wf.emit_step_failed(SYNC_DEPS, str(exc))
        raise
    await wf.emit_step_completed(SYNC_DEPS, sync_result.to_dict())


async def _run_validation(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Run validation fix-retry loop. Stores result in ctx.validation_result."""
    cwd_str = str(ctx.cwd) if ctx.cwd else None
    initial_validation: dict[str, Any] = {
        "passed": False,
        "stage_results": {},
        "success": False,
    }
    await wf.emit_step_started(VALIDATE)
    try:
        ctx.validation_result = await run_fix_retry_loop(
            stages=list(DEFAULT_VALIDATION_STAGES),
            max_attempts=DEFAULT_MAX_FIX_ATTEMPTS,
            fixer_agent="fixer",
            validation_result=initial_validation,
            generate_report=True,
            cwd=cwd_str,
        )
    except Exception as exc:
        await wf.emit_step_failed(VALIDATE, str(exc))
        raise
    await wf.emit_step_completed(VALIDATE, ctx.validation_result)


async def run_validate_and_fix(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Run validation and create fix beads for failures."""
    await _run_validation(wf, ctx)

    validation = ctx.validation_result or {}
    if not validation.get("passed", False):
        try:
            await create_beads_from_failures(
                epic_id=ctx.epic_id,
                validation_result=validation,
            )
        except Exception as exc:
            logger.warning(
                "create_fix_beads_failed",
                bead_id=ctx.bead_id,
                error=str(exc),
            )


async def _run_review(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Run review and fix loop. Stores result in ctx.review_result."""
    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(REVIEW, step_type=StepType.AGENT)
    try:
        review_context_result = await gather_local_review_context(
            base_branch=DEFAULT_BASE_BRANCH,
            include_spec_files=True,
            cwd=cwd_str,
        )
        review_loop_result = await run_review_fix_loop(
            review_input=review_context_result.to_dict(),
            base_branch=DEFAULT_BASE_BRANCH,
            max_attempts=DEFAULT_MAX_REVIEW_ATTEMPTS,
            generate_report=True,
            cwd=cwd_str,
            briefing_context=ctx.briefing_context,
        )
        ctx.review_result = review_loop_result.to_dict()
        await record_runway_review(wf, ctx)
    except Exception as exc:
        logger.warning(
            "review_step_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )
        await wf.emit_output(
            REVIEW,
            f"Review step failed: {exc}",
            level="warning",
        )
        ctx.review_result = None
    await wf.emit_step_completed(REVIEW, ctx.review_result)


async def run_review_and_fix(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Run review, then create beads for remaining findings."""
    await _run_review(wf, ctx)

    if ctx.review_result is not None:
        try:
            await create_beads_from_findings(
                epic_id=ctx.epic_id,
                review_result=ctx.review_result,
            )
        except Exception as exc:
            logger.warning(
                "create_review_beads_failed",
                bead_id=ctx.bead_id,
                error=str(exc),
            )


async def run_verify_cycle(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    *,
    skip_review: bool,
) -> None:
    """Run review → re-validate → verify cycle up to MAX_VERIFY_CYCLES times.

    Sets ctx.verify_result with the final outcome.
    """
    for cycle in range(1, MAX_VERIFY_CYCLES + 1):
        # Review (unless skipped)
        if not skip_review:
            await run_review_and_fix(wf, ctx)

        # Re-validate after review fixer changes
        await _run_validation(wf, ctx)

        # Verify completion
        ctx.verify_result = await verify_bead_completion(
            validation_result=ctx.validation_result or {},
            review_result=ctx.review_result,
            skip_review=skip_review,
        )

        if ctx.verify_result.passed:
            break

        reasons_str = "; ".join(ctx.verify_result.reasons)
        if cycle < MAX_VERIFY_CYCLES:
            await wf.emit_output(
                REVIEW,
                f"Verify failed (cycle {cycle}/{MAX_VERIFY_CYCLES}): "
                f"{reasons_str} — retrying review+validate",
                level="warning",
            )


async def commit_bead(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Commit the bead and mark it complete."""
    await wf.emit_step_started(COMMIT)
    commit_result = await jj_commit_bead(
        message=f"bead({ctx.bead_id}): {ctx.title}",
        cwd=ctx.cwd,
    )
    await wf.emit_step_completed(COMMIT, commit_result)

    await mark_bead_complete(bead_id=ctx.bead_id)
    await record_runway_outcome(wf, ctx)
    await wf.emit_output(
        COMMIT,
        f"Bead {ctx.bead_id} completed: {ctx.title}",
        level="success",
    )


async def record_runway_outcome(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Record bead outcome to runway store (best-effort)."""
    try:
        await record_bead_outcome(
            bead_id=ctx.bead_id,
            epic_id=ctx.epic_id,
            title=ctx.title,
            validation_result=ctx.validation_result,
            review_result=ctx.review_result,
            cwd=ctx.cwd,
        )
    except Exception as exc:
        logger.warning(
            "runway_outcome_recording_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def record_runway_review(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Record review findings to runway store (best-effort)."""
    if ctx.review_result is None:
        return
    try:
        await record_review_findings(
            bead_id=ctx.bead_id,
            review_result=ctx.review_result,
            cwd=ctx.cwd,
        )
    except Exception as exc:
        logger.warning(
            "runway_review_recording_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def rollback_bead(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Rollback jj state and emit error output."""
    if ctx.operation_id:
        await jj_restore_operation(
            operation_id=ctx.operation_id,
            cwd=ctx.cwd,
        )
    reasons = "; ".join(ctx.verify_result.reasons) if ctx.verify_result else "unknown"
    await wf.emit_output(
        COMMIT,
        f"Bead {ctx.bead_id} failed verification: {reasons}",
        level="error",
    )
