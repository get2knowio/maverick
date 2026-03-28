"""FlyBeadsWorkflow — bead-driven development workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.library.actions.beads import (
    check_epic_done,
    mark_bead_complete,
    select_next_bead,
    verify_bead_completion,
)
from maverick.library.actions.git import git_has_changes, snapshot_uncommitted_changes
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.workspace import create_fly_workspace
from maverick.logging import get_logger
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.fly_beads.constants import (
    COMMIT,
    CREATE_WORKSPACE,
    MAX_BEADS,
    PREFLIGHT,
    SELECT_BEAD,
    SNAPSHOT_UNCOMMITTED,
    WORKFLOW_NAME,
)
from maverick.workflows.fly_beads.models import BeadContext, FlyBeadsResult
from maverick.workflows.fly_beads.steps import (
    commit_bead,
    fetch_runway_context,
    load_briefing_context,
    resolve_provenance,
    rollback_bead,
    run_gate_check,
    run_gate_remediation,
    run_implement_and_validate,
    run_review_and_remediate,
    snapshot_and_describe,
)
from maverick.workspace.manager import WorkspaceManager

logger = get_logger(__name__)


class FlyBeadsWorkflow(PythonWorkflow):
    """Bead-driven development workflow with invariant-based orchestration.

    For each bead: implement+validate (agent) → gate check (orchestrator) →
    optional gate remediation → review+remediate → final gate → commit/rollback.

    The agent owns implementation and validation internally. The workflow
    enforces gates (independent validation) and structural invariants.

    Args:
        config: Project configuration.
        registry: Component registry.
        checkpoint_store: Optional checkpoint persistence.
        step_executor: Optional agent step executor for implement steps.
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        workflow_name = kwargs.pop("workflow_name", WORKFLOW_NAME)
        super().__init__(workflow_name=workflow_name, **kwargs)

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the fly-beads workflow.

        Args:
            inputs: Workflow inputs with keys:
                - epic_id: Optional epic to filter beads (default "")
                - max_beads: Maximum beads to process (default MAX_BEADS)
                - dry_run: If True, skip workspace creation (default False)
                - skip_review: If True, skip review step (default False)

        Returns:
            Summary dict with counts and workspace info.
        """
        # Parse inputs with defaults
        epic_id: str = str(inputs.get("epic_id", "") or "")
        max_beads: int = int(inputs.get("max_beads", MAX_BEADS))
        dry_run: bool = bool(inputs.get("dry_run", False))
        skip_review: bool = bool(inputs.get("skip_review", False))
        auto_commit: bool = bool(inputs.get("auto_commit", False))

        # Load checkpoint to get previously completed beads
        checkpoint = await self.load_checkpoint()
        completed_bead_ids: set[str] = set()
        workspace_path: Path | None = None

        if checkpoint:
            completed_bead_ids = set(checkpoint.get("completed_bead_ids", []))
            ws_path_str = checkpoint.get("workspace_path")
            if ws_path_str:
                workspace_path = Path(ws_path_str)

        # Track counts for summary
        beads_succeeded = 0
        beads_failed = 0
        beads_skipped = 0

        # Track failure reasons per bead for retry context
        bead_failure_history: dict[str, list[str]] = {}
        # Track last review result per bead so we can reconstruct context
        # when a bead exhausts retries (ctx is not yet built at that point)
        bead_last_review: dict[str, dict[str, Any] | None] = {}
        # Track review issue counts per escalation chain root for
        # non-convergence detection
        chain_issue_trajectory: dict[str, list[int]] = {}
        # Accumulate items that need human review at land phase
        human_review_items: list[dict[str, Any]] = []
        # Track escalation depth per root bead across checkpoint boundaries.
        # Key: root bead ID, Value: number of follow-up tiers created.
        # Persisted in checkpoint so it survives session restarts.
        chain_depth: dict[str, int] = {}

        if checkpoint:
            chain_depth = checkpoint.get("chain_depth", {})

        # ----------------------------------------------------------------
        # Step 1: Preflight
        # ----------------------------------------------------------------
        await self.emit_step_started(PREFLIGHT)
        try:
            preflight_result = await run_preflight_checks(
                check_providers=True,
                check_git=True,
                check_jj=True,
                check_bd=True,
                check_validation_tools=False,
                fail_on_error=True,
                config=self._config,
            )
        except Exception as exc:
            await self.emit_step_failed(PREFLIGHT, str(exc))
            raise
        await self.emit_step_completed(PREFLIGHT, preflight_result.to_dict())

        # ----------------------------------------------------------------
        # Step 2: Snapshot uncommitted changes
        # ----------------------------------------------------------------
        # jj git clone only picks up committed state. If maverick init (or
        # the user) left uncommitted files, we need to commit them first so
        # the workspace clone includes everything.
        if not dry_run:
            await self.emit_step_started(SNAPSHOT_UNCOMMITTED)
            try:
                change_status = await git_has_changes()
                if change_status["has_any"]:
                    if auto_commit:
                        snap = await snapshot_uncommitted_changes()
                        if not snap["success"]:
                            err = snap["error"] or "commit failed"
                            await self.emit_step_failed(SNAPSHOT_UNCOMMITTED, err)
                            raise WorkflowError(
                                f"Snapshot failed: {err}",
                                workflow_name=WORKFLOW_NAME,
                            )
                        await self.emit_output(
                            SNAPSHOT_UNCOMMITTED,
                            f"Committed uncommitted changes ({snap['commit_sha'][:8]})",
                            level="info",
                        )
                        if snap.get("warning"):
                            await self.emit_output(
                                SNAPSHOT_UNCOMMITTED,
                                snap["warning"],
                                level="warning",
                            )
                    else:
                        await self.emit_step_failed(
                            SNAPSHOT_UNCOMMITTED,
                            "Uncommitted changes detected. Commit them first "
                            "or re-run with --auto-commit.",
                        )
                        raise WorkflowError(
                            "Uncommitted changes detected in the working directory. "
                            "The workspace clone will not include these changes. "
                            "Please commit them first or re-run with --auto-commit.",
                            workflow_name=WORKFLOW_NAME,
                        )
                else:
                    await self.emit_output(
                        SNAPSHOT_UNCOMMITTED,
                        "Working directory clean — no snapshot needed",
                        level="info",
                    )
            except WorkflowError:
                raise
            except Exception as exc:
                await self.emit_step_failed(SNAPSHOT_UNCOMMITTED, str(exc))
                raise
            await self.emit_step_completed(SNAPSHOT_UNCOMMITTED, change_status)

        # ----------------------------------------------------------------
        # Step 3: Create workspace (skipped in dry_run)
        # ----------------------------------------------------------------
        if not dry_run:
            await self.emit_step_started(CREATE_WORKSPACE)
            try:
                ws_result = await create_fly_workspace()
            except Exception as exc:
                await self.emit_step_failed(CREATE_WORKSPACE, str(exc))
                raise

            if not ws_result.get("success"):
                error_msg = ws_result.get("error") or "workspace creation failed"
                await self.emit_step_failed(CREATE_WORKSPACE, error_msg)
                raise WorkflowError(
                    f"create_fly_workspace failed: {error_msg}",
                    workflow_name=WORKFLOW_NAME,
                )

            workspace_path = Path(ws_result["workspace_path"])
            await self.emit_step_completed(CREATE_WORKSPACE, ws_result)

            # Initialize runway in workspace so recording works
            await _init_workspace_runway(workspace_path)

            # Register workspace teardown as rollback
            ws_manager = WorkspaceManager(user_repo_path=Path.cwd())

            async def _teardown() -> None:
                await ws_manager.teardown()

            self.register_rollback("workspace_teardown", _teardown)

        # ----------------------------------------------------------------
        # Bead loop
        # ----------------------------------------------------------------
        # max_beads caps *successful* completions, not total iterations.
        # Global safety limit prevents runaway loops; per-bead retry limit
        # (MAX_RETRIES_PER_BEAD) defers stuck beads after N failed attempts.
        max_iterations = max_beads * 3
        _iteration = 0
        while beads_succeeded < max_beads and _iteration < max_iterations:
            _iteration += 1
            # --- Select next bead ---
            await self.emit_step_started(SELECT_BEAD)
            try:
                select_result = await select_next_bead(epic_id=epic_id)
            except Exception as exc:
                await self.emit_step_failed(SELECT_BEAD, str(exc))
                raise
            await self.emit_step_completed(SELECT_BEAD, select_result.to_dict())

            # No more beads — done
            if select_result.done or not select_result.found:
                await self.emit_output(
                    SELECT_BEAD,
                    "No more ready beads — bead loop complete",
                    level="success",
                )
                break

            bead_id = select_result.bead_id
            bead_title = select_result.title

            await self.emit_output(
                SELECT_BEAD,
                f"Selected bead {bead_id}: {bead_title}",
                level="info",
            )

            # Skip beads we already completed (checkpoint resume)
            if bead_id in completed_bead_ids:
                beads_skipped += 1
                await self.emit_output(
                    SELECT_BEAD,
                    f"Skipping already-completed bead {bead_id}: {bead_title}",
                    level="info",
                )
                continue

            # Detect retry of a previously-failed bead
            prior_failures = bead_failure_history.get(bead_id, [])
            if prior_failures:
                attempt_num = len(prior_failures) + 1

                # Per-bead retry limit — commit what we have and spin off
                # a follow-up bead for unresolved review issues.
                from maverick.workflows.fly_beads.constants import (
                    MAX_RETRIES_PER_BEAD,
                )

                if len(prior_failures) >= MAX_RETRIES_PER_BEAD:
                    reasons_summary = "; ".join(prior_failures[-3:])
                    await self.emit_output(
                        SELECT_BEAD,
                        f"Bead {bead_id} exhausted"
                        f" {MAX_RETRIES_PER_BEAD} attempts:"
                        f" {reasons_summary}."
                        " Escalating.",
                        level="warning",
                    )
                    try:
                        from maverick.workflows.fly_beads.steps import (
                            commit_bead_with_followup,
                        )

                        # Build a fresh context — ctx hasn't been
                        # constructed for this iteration yet.
                        retry_ctx = BeadContext(
                            bead_id=bead_id,
                            title=bead_title,
                            description=select_result.description,
                            epic_id=select_result.epic_id,
                            cwd=workspace_path,
                            flight_plan_name=select_result.flight_plan_name or "",
                            prior_failures=prior_failures,
                            briefing_context=load_briefing_context(
                                select_result.flight_plan_name
                            ),
                        )
                        retry_ctx.review_result = bead_last_review.get(
                            bead_id
                        )

                        # Populate discovered-from chain for escalation
                        await resolve_provenance(retry_ctx)

                        # Track escalation depth from workflow state
                        # (survives checkpoint boundaries, unlike chain walk)
                        chain_root = (
                            retry_ctx.discovered_from_chain[0]
                            if retry_ctx.discovered_from_chain
                            else bead_id
                        )
                        current_depth = chain_depth.get(chain_root, 0) + 1
                        chain_depth[chain_root] = current_depth
                        retry_ctx.escalation_depth = current_depth

                        await commit_bead_with_followup(
                            self, retry_ctx, prior_failures
                        )
                        completed_bead_ids.add(bead_id)
                        beads_succeeded += 1
                        # Record for human review manifest if tagged
                        if retry_ctx.human_review_tag:
                            key_findings: list[str] = []
                            if retry_ctx.review_result:
                                for f in retry_ctx.review_result.get(
                                    "review_findings", []
                                )[:3]:
                                    key_findings.append(
                                        f.get("description", "")[:200]
                                    )
                            human_review_items.append({
                                "bead_id": bead_id,
                                "title": bead_title,
                                "status": "needs-human-review",
                                "escalation_depth": retry_ctx.escalation_depth,
                                "key_findings": key_findings,
                            })
                    except Exception as exc:
                        logger.warning(
                            "fly_beads_followup_failed",
                            bead_id=bead_id,
                            error=str(exc),
                        )
                        beads_failed += 1
                    continue

                prev_reason = prior_failures[-1]
                await self.emit_output(
                    SELECT_BEAD,
                    f"Retrying bead {bead_id} (attempt {attempt_num},"
                    f" previous failure: {prev_reason})",
                    level="warning",
                )

            # Build per-bead context
            ctx = BeadContext(
                bead_id=bead_id,
                title=bead_title,
                description=select_result.description,
                epic_id=select_result.epic_id,
                cwd=workspace_path,
                flight_plan_name=select_result.flight_plan_name or "",
                prior_failures=prior_failures,
                briefing_context=load_briefing_context(select_result.flight_plan_name),
            )

            logger.info(
                "fly_beads_processing_bead",
                bead_id=bead_id,
                title=bead_title,
                has_briefing=ctx.briefing_context is not None,
            )

            try:
                await resolve_provenance(ctx)
                await fetch_runway_context(self, ctx)
                await snapshot_and_describe(self, ctx)

                # Agent implements + validates internally
                await run_implement_and_validate(self, ctx)

                # Orchestrator verifies independently (trust-but-verify)
                await run_gate_check(self, ctx)

                # One remediation attempt if gate failed
                if ctx.gate_result and not ctx.gate_result.get("passed", False):
                    await run_gate_remediation(self, ctx)
                    await run_gate_check(self, ctx)

                # Review only if validation gate passed
                gate_passed = ctx.gate_result and ctx.gate_result.get("passed", False)
                if gate_passed:
                    await run_review_and_remediate(self, ctx, skip_review=skip_review)
                    # Final gate after review fixes
                    if not skip_review and ctx.review_result:
                        await run_gate_check(self, ctx)

                # Verify and decide
                ctx.verify_result = await verify_bead_completion(
                    validation_result=ctx.gate_result or {},
                    review_result=ctx.review_result,
                    skip_review=skip_review,
                )

                if ctx.verify_result and ctx.verify_result.passed:
                    await commit_bead(self, ctx)
                    completed_bead_ids.add(ctx.bead_id)
                    beads_succeeded += 1
                else:
                    await rollback_bead(self, ctx)
                    beads_failed += 1
                    reasons = (
                        "; ".join(ctx.verify_result.reasons)
                        if ctx.verify_result
                        else "unknown"
                    )
                    bead_failure_history.setdefault(bead_id, []).append(reasons)
                    bead_last_review[bead_id] = ctx.review_result
                    # Track issue count for non-convergence detection
                    if ctx.review_result:
                        issue_count = ctx.review_result.get(
                            "issues_remaining",
                            ctx.review_result.get("issues_found", 0),
                        )
                        chain_root = (
                            ctx.discovered_from_chain[0]
                            if ctx.discovered_from_chain
                            else bead_id
                        )
                        chain_issue_trajectory.setdefault(
                            chain_root, []
                        ).append(issue_count)

            except Exception as exc:
                logger.warning(
                    "fly_beads_bead_error",
                    bead_id=bead_id,
                    error=str(exc),
                )
                beads_failed += 1
                bead_failure_history.setdefault(bead_id, []).append(str(exc))

            # --- Checkpoint after each bead attempt ---
            await self.save_checkpoint(
                {
                    "completed_bead_ids": list(completed_bead_ids),
                    "workspace_path": str(workspace_path) if workspace_path else None,
                    "epic_id": epic_id,
                    "chain_depth": chain_depth,
                }
            )

            # --- Check if epic is done ---
            try:
                done_result = await check_epic_done(epic_id=epic_id)
                if done_result.done:
                    # Close the epic if all its children are closed.
                    if done_result.all_children_closed and epic_id:
                        try:
                            await mark_bead_complete(
                                bead_id=epic_id,
                                reason="All child beads completed",
                            )
                            await self.emit_output(
                                COMMIT,
                                f"Epic {epic_id} closed — all"
                                f" {done_result.total_children} child"
                                " beads completed",
                                level="success",
                            )
                        except Exception as exc:
                            logger.warning(
                                "epic_close_failed",
                                epic_id=epic_id,
                                error=str(exc),
                            )
                    await self.emit_output(
                        COMMIT,
                        "Epic done — no more ready beads"
                        f" (completed {beads_succeeded})",
                        level="success",
                    )
                    break
            except Exception as exc:
                logger.warning("check_epic_done_failed", error=str(exc))

        # Write human review manifest for the land phase
        if human_review_items:
            import json as _json

            manifest_dir = Path.cwd() / ".maverick" / "plans"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = manifest_dir / "human-review-manifest.json"
            try:
                manifest_path.write_text(
                    _json.dumps(human_review_items, indent=2)
                )
                logger.info(
                    "human_review_manifest_written",
                    path=str(manifest_path),
                    count=len(human_review_items),
                )
            except Exception as exc:
                logger.warning(
                    "human_review_manifest_write_failed", error=str(exc)
                )

        beads_processed = beads_succeeded + beads_failed + beads_skipped
        result = FlyBeadsResult(
            epic_id=epic_id,
            workspace_path=str(workspace_path) if workspace_path else None,
            beads_processed=beads_processed,
            beads_succeeded=beads_succeeded,
            beads_failed=beads_failed,
            beads_skipped=beads_skipped,
            human_review_items=tuple(human_review_items),
        )
        return result.to_dict()


async def _init_workspace_runway(workspace_path: Path) -> None:
    """Initialize runway store in the workspace (best-effort).

    The workspace is a fresh jj clone without ``.maverick/runway/``.
    Without initialization, all runway recording during fly silently
    fails because ``_get_store()`` returns None.

    Args:
        workspace_path: Path to the hidden workspace directory.
    """
    from maverick.runway.store import RunwayStore

    try:
        runway_path = workspace_path / ".maverick" / "runway"
        store = RunwayStore(runway_path)
        if not store.is_initialized:
            await store.initialize()
            logger.info(
                "workspace_runway_initialized",
                path=str(runway_path),
            )
    except Exception as exc:
        # Best-effort — don't block fly if runway init fails
        logger.warning(
            "workspace_runway_init_failed",
            error=str(exc),
        )
