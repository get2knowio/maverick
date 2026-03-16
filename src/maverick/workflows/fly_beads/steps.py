"""Extracted step functions for FlyBeadsWorkflow bead loop.

Each function receives the workflow instance (for emit_* and _step_executor)
and a BeadContext that threads mutable state through the pipeline.

Invariant-based orchestration: the agent owns implementation + validation
internally, the workflow enforces gates.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.executor.config import StepConfig
from maverick.library.actions.beads import (
    create_beads_from_findings,
    mark_bead_complete,
)
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
from maverick.library.actions.runway import (
    record_bead_outcome,
    record_review_findings,
    retrieve_runway_context,
)
from maverick.library.actions.validation import run_independent_gate
from maverick.logging import get_logger
from maverick.types import StepType
from maverick.workflows.fly_beads.constants import (
    COMMIT,
    DEFAULT_BASE_BRANCH,
    DEFAULT_VALIDATION_STAGES,
    GATE_CHECK,
    GATE_REMEDIATION,
    GATE_REMEDIATION_TIMEOUT,
    IMPLEMENT_AND_VALIDATE,
    IMPLEMENT_AND_VALIDATE_TIMEOUT,
    REVIEW,
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


async def fetch_runway_context(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Fetch runway context for the current bead (best-effort).

    Queries the runway store for historical outcomes and semantically
    relevant passages. Sets ctx.runway_context if data is found.
    Never raises — logs a warning on failure.
    """
    try:
        runway_cfg = getattr(wf._config, "runway", None)
        if runway_cfg is None or not getattr(runway_cfg, "enabled", True):
            return

        retrieval_cfg = getattr(runway_cfg, "retrieval", None)
        max_passages = (
            getattr(retrieval_cfg, "max_passages", 10) if retrieval_cfg else 10
        )
        bm25_top_k = getattr(retrieval_cfg, "bm25_top_k", 20) if retrieval_cfg else 20
        max_context_chars = (
            getattr(retrieval_cfg, "max_context_chars", 4000) if retrieval_cfg else 4000
        )

        result = await retrieve_runway_context(
            title=ctx.title,
            description=ctx.description,
            epic_id=ctx.epic_id,
            max_passages=max_passages,
            bm25_top_k=bm25_top_k,
            max_context_chars=max_context_chars,
            cwd=ctx.cwd,
        )
        if result.context_text:
            ctx.runway_context = result.context_text
            logger.info(
                "runway_context_fetched",
                bead_id=ctx.bead_id,
                outcomes=result.outcomes_used,
                passages=result.passages_used,
            )
    except Exception as exc:
        logger.warning(
            "fetch_runway_context_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def snapshot_and_describe(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Snapshot jj operation and set WIP description."""
    snapshot_result = await jj_snapshot_operation(cwd=ctx.cwd)
    ctx.operation_id = snapshot_result.get("operation_id")
    await jj_describe(
        message=f"WIP bead({ctx.bead_id}): {ctx.title}",
        cwd=ctx.cwd,
    )


async def run_implement_and_validate(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Execute the implement-and-validate agent step.

    The agent implements the bead AND runs validation internally, iterating
    until validation passes or it determines the issue is unfixable.

    On failure: emits step_failed (not step_completed), logs warning.
    Does NOT propagate — bead continues to gate check.
    """
    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(IMPLEMENT_AND_VALIDATE, step_type=StepType.AGENT)

    if wf._step_executor is not None:
        implement_prompt: dict[str, Any] = {
            "task_description": ctx.description,
            "cwd": cwd_str,
        }
        if ctx.runway_context:
            implement_prompt["runway_context"] = ctx.runway_context
        if ctx.briefing_context:
            implement_prompt["briefing_context"] = ctx.briefing_context
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
                step_name=IMPLEMENT_AND_VALIDATE,
                agent_name="implementer",
                prompt=implement_prompt,
                cwd=ctx.cwd,
                config=StepConfig(timeout=IMPLEMENT_AND_VALIDATE_TIMEOUT),
            )
        except Exception as exc:
            logger.warning(
                "implement_and_validate_step_failed",
                bead_id=ctx.bead_id,
                error=str(exc),
            )
            await wf.emit_step_failed(IMPLEMENT_AND_VALIDATE, str(exc))
            await wf.emit_output(
                IMPLEMENT_AND_VALIDATE,
                f"Implement-and-validate step failed: {exc}",
                level="warning",
            )
            return
    else:
        await wf.emit_output(
            IMPLEMENT_AND_VALIDATE,
            "No step executor configured — skipping agent implement step",
            level="warning",
        )

    await wf.emit_step_completed(IMPLEMENT_AND_VALIDATE)


async def run_gate_check(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Run independent validation gate check.

    The orchestrator runs validation as subprocess — trust-but-verify.
    Stores result in ctx.gate_result and ctx.validation_result.
    Never raises — gate pass/fail handled by workflow loop.
    """
    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(GATE_CHECK)

    try:
        gate_result = await run_independent_gate(
            stages=list(DEFAULT_VALIDATION_STAGES),
            cwd=cwd_str,
        )
        ctx.gate_result = gate_result
        # Also update validation_result for runway recording compatibility
        ctx.validation_result = gate_result
    except Exception as exc:
        logger.warning(
            "gate_check_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )
        ctx.gate_result = {
            "passed": False,
            "stage_results": {},
            "summary": f"Gate check error: {exc}",
        }
        ctx.validation_result = ctx.gate_result
        await wf.emit_step_failed(GATE_CHECK, str(exc))
        return

    await wf.emit_step_completed(GATE_CHECK, gate_result)


async def run_gate_remediation(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Run gate remediation agent to fix gate failures.

    Only called when gate_check failed. Invokes GateRemediationAgent with
    gate failure output. Sets ctx.remediation_attempted = True.

    Non-fatal on executor failure.
    """
    await wf.emit_step_started(GATE_REMEDIATION, step_type=StepType.AGENT)
    ctx.remediation_attempted = True

    if wf._step_executor is None:
        await wf.emit_output(
            GATE_REMEDIATION,
            "No step executor configured — skipping gate remediation",
            level="warning",
        )
        await wf.emit_step_completed(GATE_REMEDIATION)
        return

    # Build prompt from gate failure details
    gate_summary = ""
    if ctx.gate_result:
        gate_summary = ctx.gate_result.get("summary", "")
        stage_results = ctx.gate_result.get("stage_results", {})
        failure_details = []
        for stage_name, sr in stage_results.items():
            if stage_name.startswith("_"):
                continue
            if not sr.get("passed", True):
                output = sr.get("output", "")
                errors = sr.get("errors", [])
                if errors:
                    error_msgs = [
                        e.get("message", str(e)) if isinstance(e, dict) else str(e)
                        for e in errors
                    ]
                    failure_details.append(f"- {stage_name}: {'; '.join(error_msgs)}")
                elif output:
                    failure_details.append(f"- {stage_name}: {output[:500]}")
                else:
                    failure_details.append(f"- {stage_name}: failed (no details)")

        if failure_details:
            gate_summary += "\n\nFailure details:\n" + "\n".join(failure_details)

    remediation_prompt: dict[str, Any] = {
        "prompt": (
            "The orchestrator independently ran validation and found these failures. "
            "Fix the issues and re-run validation to verify your fixes.\n\n"
            f"{gate_summary}"
        ),
        "cwd": str(ctx.cwd) if ctx.cwd else None,
    }

    try:
        await wf._step_executor.execute(
            step_name=GATE_REMEDIATION,
            agent_name="gate_remediator",
            prompt=remediation_prompt,
            cwd=ctx.cwd,
            config=StepConfig(timeout=GATE_REMEDIATION_TIMEOUT),
        )
    except Exception as exc:
        logger.warning(
            "gate_remediation_step_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )
        await wf.emit_step_failed(GATE_REMEDIATION, str(exc))
        await wf.emit_output(
            GATE_REMEDIATION,
            f"Gate remediation failed: {exc}",
            level="warning",
        )
        return

    await wf.emit_step_completed(GATE_REMEDIATION)


async def run_review_and_remediate(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    *,
    skip_review: bool,
) -> None:
    """Run review and fix findings in a single pass.

    If skip_review: return immediately.
    Runs dual review (CompletenessReviewer + CorrectnessReviewer in parallel).
    If critical/major findings: invokes SimpleFixerAgent (with Bash access).
    Creates beads from remaining unresolved findings.
    Records runway review data. Single pass — no retry loop.
    """
    if skip_review:
        return

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
            max_attempts=1,  # Single pass — no retry loop
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

    # Create beads from unresolved findings
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
