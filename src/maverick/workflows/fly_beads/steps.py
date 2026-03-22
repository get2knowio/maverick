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
    defer_bead,
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


async def walk_discovered_from_chain(bead_id: str) -> list[str]:
    """Walk the discovered-from dependency chain back to the root.

    Returns a list of bead IDs from root to the bead that links to
    ``bead_id``.  An empty list means the bead has no discovered-from
    ancestry (it is an original bead, not a follow-up).

    Capped at 10 hops to prevent infinite loops on circular deps.
    """
    import json as _json

    from maverick.runners.command import CommandRunner

    runner = CommandRunner(cwd=Path.cwd())
    chain: list[str] = []
    current = bead_id
    seen: set[str] = set()

    for _ in range(10):
        try:
            result = await runner.run(
                ["bd", "dep", "list", current, "--json"],
            )
        except Exception:
            break

        if not result.stdout:
            break

        origin_id = ""
        with contextlib.suppress(Exception):
            deps = _json.loads(result.stdout)
            if isinstance(deps, list):
                for dep in deps:
                    if (
                        isinstance(dep, dict)
                        and dep.get("type") == "discovered-from"
                    ):
                        origin_id = dep.get("depends_on_id", "")
                        break

        if not origin_id or origin_id in seen:
            break

        chain.append(origin_id)
        seen.add(origin_id)
        current = origin_id

    chain.reverse()  # root first
    return chain


async def resolve_provenance(ctx: BeadContext) -> None:
    """Enrich bead context with provenance from discovered-from links.

    Populates ``ctx.discovered_from_chain`` and appends a provenance
    section to ``ctx.description`` so the implementer agent can understand
    what was tried before and what the reviewer objected to.
    """
    import json as _json

    from maverick.runners.command import CommandRunner

    chain = await walk_discovered_from_chain(ctx.bead_id)
    ctx.discovered_from_chain = chain

    if not chain:
        return

    # Fetch the immediate parent bead's details for the description
    origin_id = chain[-1]  # most recent ancestor
    runner = CommandRunner(cwd=Path.cwd())

    try:
        origin_result = await runner.run(
            ["bd", "show", origin_id, "--json"],
        )
    except Exception:
        return

    if not origin_result.stdout:
        return

    with contextlib.suppress(Exception):
        origin = _json.loads(origin_result.stdout)
        origin_title = origin.get("title", "")
        origin_desc = origin.get("description", "")

        provenance_section = (
            f"\n\n## Provenance\n\n"
            f"This bead was created to address unresolved review"
            f" findings from bead `{origin_id}`"
            f" ({origin_title}).\n"
        )
        if len(chain) > 1:
            provenance_section += (
                f"\nFull chain: {' → '.join(f'`{b}`' for b in chain)}"
                f" → `{ctx.bead_id}` (current)\n"
            )
        if origin_desc:
            desc_preview = origin_desc[:500]
            if len(origin_desc) > 500:
                desc_preview += "..."
            provenance_section += (
                f"\n### Original Bead Description\n\n"
                f"{desc_preview}\n"
            )

        ctx.description = ctx.description + provenance_section


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

    Only called when gate_check failed. Invokes FixerAgent (registered as
    "gate_remediator") with gate failure output. Sets ctx.remediation_attempted = True.

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
    If critical/major findings: invokes ReviewFixerAgent (with Bash access).
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

    # Capture files changed by this bead (jj colocated → git diff works)
    files_changed = await _get_files_changed(ctx.cwd)

    await mark_bead_complete(bead_id=ctx.bead_id)
    await record_runway_outcome(wf, ctx, files_changed=files_changed)
    await wf.emit_output(
        COMMIT,
        f"Bead {ctx.bead_id} completed: {ctx.title}",
        level="success",
    )


async def _get_files_changed(cwd: Path | None) -> list[str]:
    """Get the list of files changed by the most recent commit.

    Uses ``git diff --name-only HEAD~1`` which works in jj colocated
    mode (shared ``.git`` directory).
    """
    from maverick.runners.command import CommandRunner

    try:
        runner = CommandRunner(cwd=cwd or Path.cwd())
        result = await runner.run(
            ["git", "diff", "--name-only", "HEAD~1"],
        )
        if result.stdout:
            return [
                f.strip() for f in result.stdout.strip().splitlines() if f.strip()
            ]
    except Exception as exc:
        logger.debug("files_changed_capture_failed", error=str(exc))
    return []


async def record_runway_outcome(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    files_changed: list[str] | None = None,
) -> None:
    """Record bead outcome to runway store (best-effort)."""
    try:
        await record_bead_outcome(
            bead_id=ctx.bead_id,
            epic_id=ctx.epic_id,
            title=ctx.title,
            validation_result=ctx.validation_result,
            review_result=ctx.review_result,
            files_changed=files_changed,
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


async def commit_bead_with_followup(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    prior_failures: list[str],
) -> None:
    """Commit a bead that passed validation but exhausted review retries.

    Two-tier escalation:
    - **Tier 1** (no discovered-from chain): Create a follow-up task bead
      under the same epic with the review findings.
    - **Tier 2** (has discovered-from chain — this IS a follow-up): The
      same issue has persisted across multiple beads. Escalate by running
      the decomposer to re-plan the stuck work, superseding the stuck chain.

    Args:
        wf: Workflow instance for emitting events.
        ctx: Bead context with review results and discovered_from_chain.
        prior_failures: List of failure reason strings from prior attempts.
    """
    # Commit the implementation work (it passed validation)
    await commit_bead(wf, ctx)

    if ctx.discovered_from_chain:
        # Tier 2: This is already a follow-up — escalate to re-planning
        await _escalate_to_replan(wf, ctx, prior_failures)
    else:
        # Tier 1: First-time failure — create a follow-up task bead
        await _create_followup_bead(wf, ctx, prior_failures)


async def _create_followup_bead(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    prior_failures: list[str],
) -> None:
    """Tier 1: Create a follow-up task bead for unresolved review findings."""
    import json as _json

    from maverick.runners.command import CommandRunner

    followup_description = _build_followup_description(ctx, prior_failures)

    try:
        runner = CommandRunner(cwd=Path.cwd())
        title = f"Address review findings from {ctx.bead_id}: {ctx.title[:80]}"
        result = await runner.run(
            [
                "bd", "create", title,
                "--parent", ctx.epic_id,
                "--type", "task",
                "--description", followup_description,
                "--json",
            ]
        )

        followup_id = ""
        if result.stdout:
            with contextlib.suppress(Exception):
                data = _json.loads(result.stdout)
                followup_id = data.get("id", "")

        if followup_id:
            await runner.run(
                [
                    "bd", "dep", "add", followup_id, ctx.bead_id,
                    "--type", "discovered-from",
                ]
            )

        label = f" ({followup_id})" if followup_id else ""
        await wf.emit_output(
            COMMIT,
            f"Created follow-up bead{label} for unresolved review"
            f" issues from {ctx.bead_id}",
            level="warning",
        )
    except Exception as exc:
        logger.warning(
            "followup_bead_creation_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def _escalate_to_replan(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    prior_failures: list[str],
) -> None:
    """Tier 2: Re-plan the stuck work via the decomposer agent.

    The same reviewer issue has persisted across multiple beads in the
    discovered-from chain.  Instead of creating another follow-up task,
    re-run the decomposer with failure context so the work can be
    re-decomposed into different boundaries.
    """
    import json as _json

    from maverick.runners.command import CommandRunner

    runner = CommandRunner(cwd=Path.cwd())
    chain = ctx.discovered_from_chain  # [root, ..., parent]
    full_chain = chain + [ctx.bead_id]

    # --- Gather failure context ---
    chain_titles: dict[str, str] = {}
    for bid in full_chain:
        with contextlib.suppress(Exception):
            r = await runner.run(["bd", "show", bid, "--json"])
            if r.stdout:
                data = _json.loads(r.stdout)
                chain_titles[bid] = data.get("title", bid)

    review_report = ""
    if ctx.review_result:
        review_report = ctx.review_result.get("review_report", "")

    # --- Build enriched prompt for the decomposer ---
    replan_description = _build_escalation_description(
        full_chain, chain_titles, review_report, prior_failures
    )

    # --- Supersede the stuck chain (close old beads cleanly) ---
    for bid in full_chain:
        with contextlib.suppress(Exception):
            await runner.run(["bd", "close", bid, "--reason",
                              f"Superseded by re-planning from {ctx.bead_id}"])

    # --- Create re-planning bead ---
    try:
        title = (
            f"Re-plan: reviewer issue persisted across"
            f" {len(full_chain)} beads ({full_chain[0]}..{ctx.bead_id})"
        )
        result = await runner.run(
            [
                "bd", "create", title,
                "--parent", ctx.epic_id,
                "--type", "task",
                "--label", "needs-replan",
                "--description", replan_description,
                "--json",
            ]
        )

        replan_id = ""
        if result.stdout:
            with contextlib.suppress(Exception):
                data = _json.loads(result.stdout)
                replan_id = data.get("id", "")

        # Wire discovered-from to ALL beads in the chain
        if replan_id:
            for bid in full_chain:
                with contextlib.suppress(Exception):
                    await runner.run(
                        ["bd", "dep", "add", replan_id, bid,
                         "--type", "discovered-from"]
                    )

        label = f" ({replan_id})" if replan_id else ""
        await wf.emit_output(
            COMMIT,
            f"Escalated to re-planning bead{label}:"
            f" reviewer issue persisted across {len(full_chain)} beads"
            f" in chain {' → '.join(full_chain)}",
            level="warning",
        )
    except Exception as exc:
        logger.warning(
            "replan_bead_creation_failed",
            bead_id=ctx.bead_id,
            chain=full_chain,
            error=str(exc),
        )

    # --- Defer beads that depend on the stuck chain ---
    await _defer_dependent_beads(full_chain, ctx.epic_id)


async def _defer_dependent_beads(
    chain: list[str],
    epic_id: str,
) -> None:
    """Defer beads that are blocked by any bead in the stuck chain."""
    import json as _json

    from maverick.runners.command import CommandRunner

    runner = CommandRunner(cwd=Path.cwd())
    deferred: set[str] = set()

    for bid in chain:
        with contextlib.suppress(Exception):
            r = await runner.run(["bd", "dep", "list", bid, "--json"])
            if not r.stdout:
                continue
            deps = _json.loads(r.stdout)
            if not isinstance(deps, list):
                continue
            for dep in deps:
                if not isinstance(dep, dict):
                    continue
                # Find beads that this bead blocks
                if dep.get("type") == "blocks":
                    blocked_id = dep.get("issue_id", "")
                    if blocked_id and blocked_id not in deferred:
                        with contextlib.suppress(Exception):
                            await defer_bead(
                                bead_id=blocked_id,
                                reason=f"Blocked by stuck chain: {' → '.join(chain)}",
                            )
                            deferred.add(blocked_id)


def _build_followup_description(
    ctx: BeadContext,
    prior_failures: list[str],
) -> str:
    """Build a description for the Tier 1 follow-up bead from review results."""
    parts = [
        f"Address unresolved review findings from bead `{ctx.bead_id}`.",
        "",
        f"The original bead ({ctx.title}) was committed after passing"
        f" validation but the reviewer repeatedly requested changes"
        f" ({len(prior_failures)} attempts).",
        "",
    ]

    # Extract verbatim review findings from review_report markdown
    if ctx.review_result:
        review_report = ctx.review_result.get("review_report", "")
        if review_report:
            parts.append("## Reviewer Findings")
            parts.append("")
            parts.append(review_report)
            parts.append("")

    # Include failure history for context
    parts.append("## Failure History")
    parts.append("")
    for i, reason in enumerate(prior_failures, 1):
        parts.append(f"- Attempt {i}: {reason}")

    return "\n".join(parts)


def _build_escalation_description(
    chain: list[str],
    chain_titles: dict[str, str],
    review_report: str,
    prior_failures: list[str],
) -> str:
    """Build a description for the Tier 2 re-planning bead.

    Contains the full provenance chain, the verbatim reviewer objection,
    and instructions for the decomposer to re-plan the stuck work.
    """
    parts = [
        "# Re-Planning Required",
        "",
        "A reviewer issue persisted across multiple implementation attempts.",
        "The work boundaries need to be re-decomposed.",
        "",
        "## Bead Chain",
        "",
    ]
    for bid in chain:
        title = chain_titles.get(bid, bid)
        parts.append(f"- `{bid}`: {title}")
    parts.append("")

    if review_report:
        parts.append("## Persistent Reviewer Finding")
        parts.append("")
        parts.append(review_report)
        parts.append("")

    if prior_failures:
        parts.append("## Most Recent Failure History")
        parts.append("")
        for i, reason in enumerate(prior_failures, 1):
            parts.append(f"- Attempt {i}: {reason}")
        parts.append("")

    parts.extend([
        "## Instructions",
        "",
        "Re-decompose ONLY the work that failed. Do not re-plan"
        " already-completed beads. The codebase has been updated with"
        " the committed (but reviewer-rejected) changes — build on that"
        " work rather than starting over.",
        "",
        "Consider whether the original decomposition drew the boundary"
        " wrong (e.g., two beads that should have been one), or whether"
        " the reviewer is flagging an architectural concern that requires"
        " a different approach entirely.",
    ])

    return "\n".join(parts)
