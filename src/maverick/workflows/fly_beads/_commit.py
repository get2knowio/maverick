"""Commit, rollback, prior-attempt snapshot, and follow-up bead creation."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.library.actions.beads import defer_bead, mark_bead_complete
from maverick.library.actions.jj import jj_commit_bead, jj_restore_operation
from maverick.logging import get_logger
from maverick.workflows.fly_beads._runway import record_runway_outcome
from maverick.workflows.fly_beads._vcs_queries import (
    _get_files_changed,
    _get_uncommitted_files,
)
from maverick.workflows.fly_beads.constants import COMMIT, MAX_ESCALATION_DEPTH
from maverick.workflows.fly_beads.models import BeadContext

if TYPE_CHECKING:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

logger = get_logger(__name__)


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


async def snapshot_prior_attempt(
    run_dir: Path,
    ctx: BeadContext,
    attempt: int,
) -> Path | None:
    """Snapshot changed files before rollback so the next attempt can see them.

    Writes to ``.maverick/runs/{run_id}/beads/{bead_id}/attempt-{n}/``
    alongside a summary markdown with the review findings.

    Returns the snapshot directory path, or None on failure.
    """
    import shutil

    snapshot_dir = run_dir / "beads" / ctx.bead_id / f"attempt-{attempt}"
    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        changed = await _get_uncommitted_files(ctx.cwd)
        if changed and ctx.cwd:
            for relpath in changed:
                src = ctx.cwd / relpath
                if src.exists() and src.is_file():
                    dest = snapshot_dir / relpath
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dest))

        summary_lines = [
            f"# Attempt {attempt} — {ctx.bead_id}",
            "",
            f"**Files changed:** {', '.join(changed) if changed else 'none'}",
            "",
        ]
        if ctx.review_result:
            report = ctx.review_result.get("review_report", "")
            if report:
                summary_lines.append("## Review Findings")
                summary_lines.append("")
                summary_lines.append(report)
        if ctx.gate_result and not ctx.gate_result.get("passed"):
            summary_lines.append("## Gate Failures")
            summary_lines.append("")
            summary_lines.append(ctx.gate_result.get("summary", "unknown"))

        (snapshot_dir / "summary.md").write_text("\n".join(summary_lines), encoding="utf-8")

        logger.info(
            "prior_attempt_snapshot",
            bead_id=ctx.bead_id,
            attempt=attempt,
            files=len(changed),
            path=str(snapshot_dir),
        )
        return snapshot_dir

    except Exception as exc:
        logger.warning(
            "prior_attempt_snapshot_failed",
            bead_id=ctx.bead_id,
            attempt=attempt,
            error=str(exc),
        )
        return None


def load_prior_attempt_context(
    run_dir: Path,
    bead_id: str,
    attempt: int,
) -> str | None:
    """Load the prior attempt's code and review findings as context.

    Returns a formatted string with the prior attempt's changed files
    and review summary, or None if no snapshot exists.
    """
    snapshot_dir = run_dir / "beads" / bead_id / f"attempt-{attempt}"
    if not snapshot_dir.exists():
        return None

    parts: list[str] = []

    summary_path = snapshot_dir / "summary.md"
    if summary_path.exists():
        parts.append(summary_path.read_text(encoding="utf-8"))

    source_files = sorted(
        f for f in snapshot_dir.rglob("*") if f.is_file() and f.name != "summary.md"
    )
    if source_files:
        parts.append("\n## Prior Attempt Code\n")
        for src_file in source_files[:10]:  # Cap at 10 files
            relpath = src_file.relative_to(snapshot_dir)
            content = src_file.read_text(encoding="utf-8", errors="replace")
            if len(content) > 4000:
                content = content[:4000] + "\n... (truncated)"
            parts.append(f"### {relpath}\n```\n{content}\n```\n")

    return "\n".join(parts) if parts else None


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

    # Circuit breaker: stop escalating when chain is too deep
    if ctx.escalation_depth >= MAX_ESCALATION_DEPTH:
        ctx.human_review_tag = "needs-human-review"
        await wf.emit_output(
            COMMIT,
            f"Bead {ctx.bead_id} committed with needs-human-review tag: "
            f"escalation depth {ctx.escalation_depth} exceeds max "
            f"{MAX_ESCALATION_DEPTH}. No further follow-up beads will be "
            f"created for this chain.",
            level="warning",
        )
        return

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
                "bd",
                "create",
                title,
                "--parent",
                ctx.epic_id,
                "--type",
                "task",
                "--description",
                followup_description,
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
                    "bd",
                    "dep",
                    "add",
                    followup_id,
                    ctx.bead_id,
                    "--type",
                    "discovered-from",
                ]
            )

        label = f" ({followup_id})" if followup_id else ""
        await wf.emit_output(
            COMMIT,
            f"Created follow-up bead{label} for unresolved review issues from {ctx.bead_id}",
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
        try:
            r = await runner.run(["bd", "show", bid, "--json"])
            if r.stdout:
                data = _json.loads(r.stdout)
                chain_titles[bid] = data.get("title", bid)
        except Exception as exc:
            logger.warning("escalation.chain_title_failed", bead_id=bid, error=str(exc))
            chain_titles[bid] = bid  # fallback to raw ID

    review_report = ""
    if ctx.review_result:
        review_report = ctx.review_result.get("review_report", "")

    # --- Build enriched prompt for the decomposer ---
    replan_description = _build_escalation_description(
        full_chain, chain_titles, review_report, prior_failures
    )

    # --- Supersede the stuck chain (close old beads cleanly) ---
    for bid in full_chain:
        try:
            await runner.run(
                ["bd", "close", bid, "--reason", f"Superseded by re-planning from {ctx.bead_id}"]
            )
        except Exception as exc:
            logger.warning("escalation.close_failed", bead_id=bid, error=str(exc))

    # --- Create re-planning bead ---
    try:
        title = (
            f"Re-plan: reviewer issue persisted across"
            f" {len(full_chain)} beads ({full_chain[0]}..{ctx.bead_id})"
        )
        result = await runner.run(
            [
                "bd",
                "create",
                title,
                "--parent",
                ctx.epic_id,
                "--type",
                "task",
                "--label",
                "needs-replan",
                "--description",
                replan_description,
                "--json",
            ]
        )

        replan_id = ""
        if result.stdout:
            try:
                data = _json.loads(result.stdout)
                replan_id = data.get("id", "")
            except (ValueError, TypeError) as exc:
                logger.warning("escalation.replan_parse_failed", error=str(exc))

        if replan_id:
            for bid in full_chain:
                try:
                    await runner.run(
                        ["bd", "dep", "add", replan_id, bid, "--type", "discovered-from"]
                    )
                except Exception as exc:
                    logger.warning(
                        "escalation.dep_wiring_failed",
                        replan_id=replan_id, bead_id=bid, error=str(exc),
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
        try:
            r = await runner.run(["bd", "dep", "list", bid, "--json"])
            if not r.stdout:
                continue
            deps = _json.loads(r.stdout)
            if not isinstance(deps, list):
                continue
            for dep in deps:
                if not isinstance(dep, dict):
                    continue
                if dep.get("type") == "blocks":
                    blocked_id = dep.get("issue_id", "")
                    if blocked_id and blocked_id not in deferred:
                        try:
                            await defer_bead(
                                bead_id=blocked_id,
                                reason=f"Blocked by stuck chain: {' → '.join(chain)}",
                            )
                            deferred.add(blocked_id)
                        except Exception as exc:
                            logger.warning(
                                "defer_bead_failed",
                                bead_id=blocked_id, error=str(exc),
                            )
        except Exception as exc:
            logger.warning("defer_dep_query_failed", bead_id=bid, error=str(exc))


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

    if ctx.review_result:
        review_report = ctx.review_result.get("review_report", "")
        if review_report:
            parts.append("## Reviewer Findings")
            parts.append("")
            parts.append(review_report)
            parts.append("")

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

    parts.extend(
        [
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
        ]
    )

    return "\n".join(parts)
