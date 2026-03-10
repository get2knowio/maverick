"""FlyBeadsWorkflow — bead-driven development workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.library.actions.beads import (
    check_epic_done,
    mark_bead_complete,
    select_next_bead,
)
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
    WORKFLOW_NAME,
)
from maverick.workflows.fly_beads.models import BeadContext, FlyBeadsResult
from maverick.workflows.fly_beads.steps import (
    commit_bead,
    load_briefing_context,
    rollback_bead,
    run_implement,
    run_sync_deps,
    run_validate_and_fix,
    run_verify_cycle,
    snapshot_and_describe,
)
from maverick.workspace.manager import WorkspaceManager

logger = get_logger(__name__)


class FlyBeadsWorkflow(PythonWorkflow):
    """Bead-driven development workflow.

    Iterates over ready beads, implementing each one in an isolated jj
    workspace. For each bead: implement → sync deps → validate/fix →
    review/fix → verify → commit/close (or rollback on failure).

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
        # Step 2: Create workspace (skipped in dry_run)
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

            # Register workspace teardown as rollback
            ws_manager = WorkspaceManager(user_repo_path=Path.cwd())

            async def _teardown() -> None:
                await ws_manager.teardown()

            self.register_rollback("workspace_teardown", _teardown)

        # ----------------------------------------------------------------
        # Bead loop
        # ----------------------------------------------------------------
        # max_beads caps *successful* completions, not total iterations.
        # Safety limit prevents infinite retries (2 retries per bead max).
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
                await snapshot_and_describe(self, ctx)
                await run_implement(self, ctx)
                await run_sync_deps(self, ctx)
                await run_validate_and_fix(self, ctx)
                await run_verify_cycle(self, ctx, skip_review=skip_review)

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

        beads_processed = beads_succeeded + beads_failed + beads_skipped
        result = FlyBeadsResult(
            epic_id=epic_id,
            workspace_path=str(workspace_path) if workspace_path else None,
            beads_processed=beads_processed,
            beads_succeeded=beads_succeeded,
            beads_failed=beads_failed,
            beads_skipped=beads_skipped,
        )
        return result.to_dict()
