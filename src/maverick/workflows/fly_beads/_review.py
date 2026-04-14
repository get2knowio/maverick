"""Dual-reviewer + fixer step for fly-beads."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from maverick.library.actions.beads import create_beads_from_findings
from maverick.library.actions.review import (
    gather_local_review_context,
    run_review_fix_loop,
)
from maverick.logging import get_logger
from maverick.types import StepType
from maverick.workflows.fly_beads._runway import record_runway_review
from maverick.workflows.fly_beads._vcs_queries import _get_uncommitted_files
from maverick.workflows.fly_beads.constants import DEFAULT_BASE_BRANCH, REVIEW
from maverick.workflows.fly_beads.models import BeadContext

if TYPE_CHECKING:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

logger = get_logger(__name__)


async def run_review_and_remediate(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    *,
    skip_review: bool,
) -> None:
    """Run review and fix findings in a single pass.

    If skip_review: return immediately.
    Runs dual review (CompletenessReviewer + CorrectnessReviewer in parallel).
    If critical/major findings: invokes ReviewFixerAgent (with Bash access).
    Creates beads from remaining unresolved findings.
    Records runway review data. Single pass — no retry loop.
    """
    if skip_review:
        return

    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(REVIEW, step_type=StepType.PYTHON)

    # Scope the review to files this bead actually changed (not the
    # full workspace diff which includes prior beads' commits).
    # At review time the bead is not yet committed, so we use the
    # uncommitted diff (jj working copy changes).
    bead_files = await _get_uncommitted_files(ctx.cwd)

    try:
        review_context_result = await gather_local_review_context(
            base_branch=DEFAULT_BASE_BRANCH,
            include_spec_files=True,
            include_files=tuple(bead_files) if bead_files else None,
            cwd=cwd_str,
        )
        review_input_dict = review_context_result.to_dict()
        review_input_dict["bead_description"] = ctx.description
        if ctx.run_dir:
            review_input_dict["run_dir"] = str(ctx.run_dir)
            review_input_dict["bead_id"] = ctx.bead_id
        if bead_files:
            review_input_dict["bead_file_scope"] = list(bead_files)
        # Resolve review step configs so provider/model from maverick.yaml
        # is honoured (e.g. completeness_review → copilot, correctness → claude)
        _review_configs: dict[str, Any] = {}
        if wf._step_executor is not None:
            for _rname in ("completeness_review", "correctness_review"):
                _review_configs[_rname] = wf.resolve_step_config(
                    step_name=_rname,
                    step_type=StepType.PYTHON,
                    agent_name=_rname.replace("_review", "_reviewer"),
                )

        review_loop_result = await run_review_fix_loop(
            review_input=review_input_dict,
            base_branch=DEFAULT_BASE_BRANCH,
            max_attempts=1,  # Single pass — no retry loop
            generate_report=True,
            cwd=cwd_str,
            briefing_context=ctx.briefing_context,
            executor=wf._step_executor,
            review_step_configs=_review_configs or None,
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
