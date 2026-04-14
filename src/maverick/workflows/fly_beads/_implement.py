"""Implement + gate steps for fly-beads.

Owns the implement-and-validate agent step, the independent gate check
(run as subprocess — trust-but-verify), and the gate remediation agent
that's invoked when gate fails.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from maverick.library.actions.jj import jj_describe, jj_snapshot_operation
from maverick.library.actions.validation import run_independent_gate
from maverick.logging import get_logger
from maverick.types import StepType
from maverick.workflows.fly_beads._plan_parsing import (
    _build_validation_commands,
    _parse_work_unit_sections,
)
from maverick.workflows.fly_beads.constants import (
    DEFAULT_VALIDATION_STAGES,
    GATE_CHECK,
    GATE_REMEDIATION,
    GATE_REMEDIATION_TIMEOUT,
    IMPLEMENT_AND_VALIDATE,
    IMPLEMENT_AND_VALIDATE_TIMEOUT,
)
from maverick.workflows.fly_beads.models import BeadContext

if TYPE_CHECKING:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

logger = get_logger(__name__)


async def snapshot_and_describe(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Snapshot jj operation and set WIP description."""
    snapshot_result = await jj_snapshot_operation(cwd=ctx.cwd)
    ctx.operation_id = snapshot_result.get("operation_id")
    await jj_describe(
        message=f"WIP bead({ctx.bead_id}): {ctx.title}",
        cwd=ctx.cwd,
    )


def _is_verification_only(ctx: BeadContext) -> bool:
    """Detect verification-only beads that should not modify files.

    Checks the bead title and description for keywords that indicate a
    read-only verification task.
    """
    text = f"{ctx.title} {ctx.description}".lower()
    verification_signals = (
        "verification-only",
        "verification only",
        "no code changes expected",
        "no code changes needed",
        "no implementation work",
        "confirm only",
    )
    return any(signal in text for signal in verification_signals)


def _is_research_only(ctx: BeadContext) -> bool:
    """Detect research-only beads that extract patterns to context files.

    Research beads can read the codebase and write findings to
    ``.maverick/context/{bead-id}.md`` for dependent beads to consume.
    """
    text = f"{ctx.title} {ctx.description}".lower()
    return "research-only" in text


async def run_implement_and_validate(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Execute the implement-and-validate agent step.

    The agent implements the bead AND runs validation internally, iterating
    until validation passes or it determines the issue is unfixable.

    Verification-only beads (detected by keywords in the description) are
    constrained to read-only tools to prevent accidental modifications.

    On failure: emits step_failed (not step_completed), logs warning.
    Does NOT propagate — bead continues to gate check.
    """
    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(IMPLEMENT_AND_VALIDATE, step_type=StepType.PYTHON)

    if wf._step_executor is not None:
        parsed = _parse_work_unit_sections(ctx.description)
        implement_prompt: dict[str, Any] = {
            "task_description": parsed.get("task", ctx.description),
            "cwd": cwd_str,
        }
        if parsed.get("acceptance criteria"):
            implement_prompt["acceptance_criteria"] = (
                "You MUST satisfy ALL of these acceptance criteria:\n\n"
                + parsed["acceptance criteria"]
            )
        if parsed.get("file scope"):
            implement_prompt["file_scope"] = (
                "File scope for this bead (Create/Modify/Protect):\n\n" + parsed["file scope"]
            )
        procedure_text = parsed.get("procedure") or parsed.get("instructions")
        if procedure_text:
            implement_prompt["procedure"] = (
                "Follow this procedure STEP BY STEP. Complete each"
                " step before moving to the next. MUST steps are"
                " mandatory — do not skip them. Use the Read tool to"
                " examine files at the specified line ranges before"
                " making changes. Verify after each step.\n\n" + procedure_text
            )
        if parsed.get("verification"):
            implement_prompt["verification_commands"] = (
                "After implementation, run these commands to verify "
                "your work:\n\n" + parsed["verification"]
            )
        if parsed.get("test specification"):
            implement_prompt["test_to_pass"] = (
                "PRIORITY: Make this test pass FIRST, then implement "
                "remaining acceptance criteria. This test defines the "
                "minimum viable implementation target:\n\n" + parsed["test specification"]
            )
        if ctx.runway_context:
            implement_prompt["runway_context"] = ctx.runway_context
        if ctx.briefing_context:
            implement_prompt["briefing_context"] = ctx.briefing_context
        if ctx.prior_failures:
            implement_prompt["previous_failures"] = (
                "This bead failed in previous attempt(s). "
                "Address these issues:\n"
                + "\n".join(
                    f"- Attempt {i + 1}: {reason}" for i, reason in enumerate(ctx.prior_failures)
                )
            )
            if ctx.review_result:
                review_report = ctx.review_result.get("review_report", "")
                if review_report:
                    implement_prompt["review_findings_to_address"] = (
                        "The reviewer identified these specific issues that "
                        "MUST be addressed in this attempt:\n\n" + review_report
                    )

        if ctx.prior_attempt_context:
            implement_prompt["prior_attempt"] = (
                "Your PREVIOUS attempt produced the code below. "
                "Do NOT start from scratch — iterate on this code "
                "and fix the specific issues identified above.\n\n" + ctx.prior_attempt_context
            )

        verification_mode = _is_verification_only(ctx)
        research_mode = _is_research_only(ctx)
        extra_kwargs: dict[str, Any] = {}
        if verification_mode:
            extra_kwargs["allowed_tools"] = ["Read", "Glob", "Grep"]
            implement_prompt["task_description"] = (
                "IMPORTANT: This is a VERIFICATION-ONLY bead. "
                "Do NOT modify any files. Only read, search, and report "
                "your findings.\n\n" + implement_prompt["task_description"]
            )
        elif research_mode:
            extra_kwargs["allowed_tools"] = ["Read", "Glob", "Grep", "Write"]
            if ctx.cwd:
                context_dir = ctx.cwd / ".maverick" / "context"
                context_dir.mkdir(parents=True, exist_ok=True)
            implement_prompt["task_description"] = (
                "IMPORTANT: This is a RESEARCH-ONLY bead. "
                "Read the codebase to extract patterns and write your "
                f"findings to `.maverick/context/{ctx.bead_id}.md`. "
                "Do NOT modify any source code files.\n\n" + implement_prompt["task_description"]
            )

        try:
            resolved = wf.resolve_step_config(
                step_name="implement",
                step_type=StepType.PYTHON,
                agent_name="implementer",
            )
            effective_timeout = resolved.timeout or IMPLEMENT_AND_VALIDATE_TIMEOUT
            resolved = resolved.model_copy(update={"timeout": effective_timeout})

            vc = wf._config.validation
            impl_agent_kwargs: dict[str, Any] = {
                "validation_commands": {
                    "sync_cmd": vc.sync_cmd,
                    "format_cmd": vc.format_cmd,
                    "lint_cmd": vc.lint_cmd,
                    "typecheck_cmd": vc.typecheck_cmd,
                    "test_cmd": vc.test_cmd,
                },
                "project_type": wf._config.project_type,
            }

            await wf._step_executor.execute(
                step_name=IMPLEMENT_AND_VALIDATE,
                agent_name="implementer",
                prompt=implement_prompt,
                cwd=ctx.cwd,
                config=resolved,
                agent_kwargs=impl_agent_kwargs,
                **extra_kwargs,
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
        validation_commands = _build_validation_commands(wf._config.validation)
        gate_result = await run_independent_gate(
            stages=list(DEFAULT_VALIDATION_STAGES),
            cwd=cwd_str,
            validation_commands=validation_commands or None,
            timeout_seconds=float(wf._config.validation.timeout_seconds),
        )
        ctx.gate_result = gate_result
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

    Only called when gate_check failed. Invokes FixerAgent (registered as
    "gate_remediator") with gate failure output. Sets ctx.remediation_attempted = True.

    Non-fatal on executor failure.
    """
    await wf.emit_step_started(GATE_REMEDIATION, step_type=StepType.PYTHON)
    ctx.remediation_attempted = True

    if wf._step_executor is None:
        await wf.emit_output(
            GATE_REMEDIATION,
            "No step executor configured — skipping gate remediation",
            level="warning",
        )
        await wf.emit_step_completed(GATE_REMEDIATION)
        return

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
                        e.get("message", str(e)) if isinstance(e, dict) else str(e) for e in errors
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
        resolved = wf.resolve_step_config(
            step_name="gate_remediation",
            step_type=StepType.PYTHON,
            agent_name="gate_remediator",
        )
        effective_timeout = resolved.timeout or GATE_REMEDIATION_TIMEOUT
        resolved = resolved.model_copy(update={"timeout": effective_timeout})

        await wf._step_executor.execute(
            step_name=GATE_REMEDIATION,
            agent_name="gate_remediator",
            prompt=remediation_prompt,
            cwd=ctx.cwd,
            config=resolved,
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
