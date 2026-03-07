"""FlyBeadsWorkflow — bead-driven development workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.executor.config import StepConfig
from maverick.library.actions.beads import (
    check_epic_done,
    create_beads_from_failures,
    create_beads_from_findings,
    mark_bead_complete,
    select_next_bead,
    verify_bead_completion,
)
from maverick.library.actions.dependencies import sync_dependencies
from maverick.library.actions.jj import (
    jj_commit_bead,
    jj_describe,
    jj_restore_operation,
    jj_snapshot_operation,
)
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.review import (
    gather_local_review_context,
    run_review_fix_loop,
)
from maverick.library.actions.validation import run_fix_retry_loop
from maverick.library.actions.workspace import create_fly_workspace
from maverick.logging import get_logger
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.fly_beads.constants import (
    COMMIT,
    CREATE_WORKSPACE,
    IMPLEMENT,
    MAX_BEADS,
    PREFLIGHT,
    REVIEW,
    SELECT_BEAD,
    SYNC_DEPS,
    VALIDATE,
    WORKFLOW_NAME,
)
from maverick.workflows.fly_beads.models import FlyBeadsResult
from maverick.workspace.manager import WorkspaceManager

logger = get_logger(__name__)

# Default validation stages for fly-beads
_DEFAULT_STAGES = ["format", "lint", "typecheck", "test"]

# Default review settings
_DEFAULT_BASE_BRANCH = "main"
_DEFAULT_MAX_REVIEW_ATTEMPTS = 2
_DEFAULT_MAX_FIX_ATTEMPTS = 3


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

        # Convenience: cwd as str for actions that expect str | None
        cwd_str: str | None = str(workspace_path) if workspace_path else None

        # ----------------------------------------------------------------
        # Bead loop
        # ----------------------------------------------------------------
        for _iteration in range(max_beads):
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
            bead_epic_id = select_result.epic_id

            # Skip beads we already completed (checkpoint resume)
            if bead_id in completed_bead_ids:
                beads_skipped += 1
                await self.emit_output(
                    SELECT_BEAD,
                    f"Skipping already-completed bead {bead_id}: {bead_title}",
                    level="info",
                )
                continue

            # Resolve briefing context from flight plan (if available).
            # Check refuel-briefing first, then fall back to preflight briefing.
            briefing_context: str | None = None
            fp_name = select_result.flight_plan_name
            if fp_name:
                plan_dir = Path.cwd() / ".maverick" / "plans" / fp_name
                for candidate in ("refuel-briefing.md", "briefing.md"):
                    briefing_path = plan_dir / candidate
                    if briefing_path.is_file():
                        import contextlib

                        with contextlib.suppress(Exception):
                            briefing_context = briefing_path.read_text(encoding="utf-8")
                        break

            logger.info(
                "fly_beads_processing_bead",
                bead_id=bead_id,
                title=bead_title,
                has_briefing=briefing_context is not None,
            )

            try:
                # --- Snapshot jj operation for per-bead rollback ---
                snapshot_result = await jj_snapshot_operation(
                    cwd=workspace_path,
                )
                operation_id: str | None = snapshot_result.get("operation_id")

                # --- Describe WIP change for observability ---
                await jj_describe(
                    message=f"WIP bead({bead_id}): {bead_title}",
                    cwd=workspace_path,
                )

                # --- Implement (agent step) ---
                await self.emit_step_started(IMPLEMENT)
                if self._step_executor is not None:
                    try:
                        await self._step_executor.execute(
                            step_name=IMPLEMENT,
                            agent_name="implementer",
                            prompt={
                                "task_description": select_result.description,
                                "cwd": cwd_str,
                            },
                            cwd=workspace_path,
                            config=StepConfig(timeout=600),
                        )
                    except Exception as exc:
                        logger.warning(
                            "implement_step_failed",
                            bead_id=bead_id,
                            error=str(exc),
                        )
                        await self.emit_output(
                            IMPLEMENT,
                            f"Implement step failed: {exc}",
                            level="warning",
                        )
                else:
                    await self.emit_output(
                        IMPLEMENT,
                        "No step executor configured — skipping agent implement step",
                        level="warning",
                    )
                await self.emit_step_completed(IMPLEMENT)

                # --- Sync dependencies ---
                await self.emit_step_started(SYNC_DEPS)
                try:
                    sync_result = await sync_dependencies(cwd=cwd_str)
                except Exception as exc:
                    await self.emit_step_failed(SYNC_DEPS, str(exc))
                    raise
                await self.emit_step_completed(SYNC_DEPS, sync_result.to_dict())

                # --- Validate and fix ---
                await self.emit_step_started(VALIDATE)
                # Pass an initially-failing sentinel dict to run_fix_retry_loop.
                # The function checks ``validation_result.get("success", False)``
                # at its entry point: if False (our sentinel), it proceeds
                # straight into the fix-and-retry loop which re-runs actual
                # validation on the first iteration via _run_validation().
                # This is intentional: we want the loop to *start* with a fresh
                # validation run rather than requiring a separate pre-validate
                # step, because the implement and sync_deps steps above may have
                # changed the workspace state since any prior run.
                initial_validation: dict[str, Any] = {
                    "passed": False,
                    "stage_results": {},
                    "success": False,
                }
                try:
                    validation_result = await run_fix_retry_loop(
                        stages=_DEFAULT_STAGES,
                        max_attempts=_DEFAULT_MAX_FIX_ATTEMPTS,
                        fixer_agent="fixer",
                        validation_result=initial_validation,
                        generate_report=True,
                        cwd=cwd_str,
                    )
                except Exception as exc:
                    await self.emit_step_failed(VALIDATE, str(exc))
                    raise
                await self.emit_step_completed(VALIDATE, validation_result)

                # Create fix beads for any validation failures
                if not validation_result.get("passed", False):
                    try:
                        await create_beads_from_failures(
                            epic_id=bead_epic_id,
                            validation_result=validation_result,
                        )
                    except Exception as exc:
                        logger.warning(
                            "create_fix_beads_failed",
                            bead_id=bead_id,
                            error=str(exc),
                        )

                # --- Review and fix (skipped when skip_review=True) ---
                review_result: dict[str, Any] | None = None
                if not skip_review:
                    await self.emit_step_started(REVIEW)
                    try:
                        review_context_result = await gather_local_review_context(
                            base_branch=_DEFAULT_BASE_BRANCH,
                            include_spec_files=True,
                            cwd=cwd_str,
                        )
                        review_loop_result = await run_review_fix_loop(
                            review_input=review_context_result.to_dict(),
                            base_branch=_DEFAULT_BASE_BRANCH,
                            max_attempts=_DEFAULT_MAX_REVIEW_ATTEMPTS,
                            generate_report=True,
                            cwd=cwd_str,
                            briefing_context=briefing_context,
                        )
                        # Normalise to dict
                        review_result = review_loop_result.to_dict()
                    except Exception as exc:
                        logger.warning(
                            "review_step_failed",
                            bead_id=bead_id,
                            error=str(exc),
                        )
                        await self.emit_output(
                            REVIEW,
                            f"Review step failed: {exc}",
                            level="warning",
                        )
                        review_result = None
                    await self.emit_step_completed(REVIEW, review_result)

                    # Create review beads for remaining findings
                    if review_result is not None:
                        try:
                            await create_beads_from_findings(
                                epic_id=bead_epic_id,
                                review_result=review_result,
                            )
                        except Exception as exc:
                            logger.warning(
                                "create_review_beads_failed",
                                bead_id=bead_id,
                                error=str(exc),
                            )

                # --- Verify completion ---
                verify_result = await verify_bead_completion(
                    validation_result=validation_result,
                    review_result=review_result,
                    skip_review=skip_review,
                )

                if not verify_result.passed:
                    # Rollback jj state
                    if operation_id:
                        await jj_restore_operation(
                            operation_id=operation_id,
                            cwd=workspace_path,
                        )
                    beads_failed += 1
                    reasons_str = "; ".join(verify_result.reasons)
                    await self.emit_output(
                        COMMIT,
                        f"Bead {bead_id} failed verification: {reasons_str}",
                        level="error",
                    )
                else:
                    # --- Commit ---
                    await self.emit_step_started(COMMIT)
                    commit_result = await jj_commit_bead(
                        message=f"bead({bead_id}): {bead_title}",
                        cwd=workspace_path,
                    )
                    await self.emit_step_completed(COMMIT, commit_result)

                    # --- Mark bead complete ---
                    await mark_bead_complete(bead_id=bead_id)

                    completed_bead_ids.add(bead_id)
                    beads_succeeded += 1
                    await self.emit_output(
                        COMMIT,
                        f"Bead {bead_id} completed: {bead_title}",
                        level="success",
                    )

            except Exception as exc:
                logger.warning(
                    "fly_beads_bead_error",
                    bead_id=bead_id,
                    error=str(exc),
                )
                beads_failed += 1

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
