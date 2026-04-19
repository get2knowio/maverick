"""FlyBeadsWorkflow — bead-driven development workflow."""

from __future__ import annotations

import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.library.actions.git import git_has_changes, snapshot_uncommitted_changes
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.validation import run_independent_gate
from maverick.library.actions.workspace import create_fly_workspace
from maverick.logging import get_logger
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.fly_beads.constants import (
    BASELINE_GATE,
    CREATE_WORKSPACE,
    MAX_BEADS,
    PREFLIGHT,
    SNAPSHOT_UNCOMMITTED,
    WORKFLOW_NAME,
)
from maverick.workflows.fly_beads.models import FlyBeadsResult
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
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        # Extract checkpoint_store before passing to super (which ignores it)
        self._checkpoint_store = kwargs.pop("checkpoint_store", None)
        workflow_name = kwargs.pop("workflow_name", WORKFLOW_NAME)
        super().__init__(workflow_name=workflow_name, **kwargs)

    # ------------------------------------------------------------------
    # Checkpointing (fly-specific)
    # ------------------------------------------------------------------

    async def save_checkpoint(self, data: dict[str, Any]) -> None:
        """Save a checkpoint via the configured CheckpointStore.

        No-op if checkpoint_store is None.

        Args:
            data: Checkpoint data to persist.
        """
        if self._checkpoint_store is None:
            return

        from datetime import UTC, datetime

        from maverick.checkpoint.data import CheckpointData, compute_inputs_hash
        from maverick.events import CheckpointSaved

        checkpoint_id = self._current_step or "checkpoint"
        cp = CheckpointData(
            checkpoint_id=checkpoint_id,
            workflow_name=self._workflow_name,
            inputs_hash=compute_inputs_hash(data),
            step_results=tuple(r.to_dict() for r in self._step_results),
            saved_at=datetime.now(tz=UTC).isoformat(),
            user_data=data,
        )
        await self._checkpoint_store.save(self._workflow_name, cp)

        await self._event_queue.put(
            CheckpointSaved(
                step_name=self._current_step or "checkpoint",
                workflow_id=self._workflow_name,
            )
        )

    async def load_checkpoint(self) -> dict[str, Any] | None:
        """Load the latest checkpoint for this workflow.

        Returns:
            Checkpoint data dict, or None if no checkpoint exists or
            checkpoint_store is None.
        """
        if self._checkpoint_store is None:
            return None

        cp = await self._checkpoint_store.load_latest(self._workflow_name)
        if cp is None:
            return None

        # Return the user-provided data from the checkpoint (not the metadata)
        return cp.user_data

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the fly-beads workflow.

        Args:
            inputs: Workflow inputs with keys:
                - epic_id: Optional epic to filter beads (default "")
                - max_beads: Maximum beads to process (default MAX_BEADS)

        Returns:
            Summary dict with counts and workspace info.
        """
        # Parse inputs with defaults
        epic_id: str = str(inputs.get("epic_id", "") or "")
        max_beads: int = int(inputs.get("max_beads", MAX_BEADS))
        auto_commit: bool = bool(inputs.get("auto_commit", False))
        watch: bool = bool(inputs.get("watch", False))
        watch_interval: int = int(inputs.get("watch_interval", 30))

        # Load checkpoint to get previously completed beads
        checkpoint = await self.load_checkpoint()
        completed_bead_ids: set[str] = set()
        workspace_path: Path | None = None

        if checkpoint:
            completed_bead_ids = set(checkpoint.get("completed_bead_ids", []))
            ws_path_str = checkpoint.get("workspace_path")
            if ws_path_str:
                workspace_path = Path(ws_path_str)

        # Per-run output directory for snapshots, logs, and context.
        # Try to find an existing run for the epic (created by refuel).
        # Fall back to generating a new run_id if none found.
        from maverick.runway.run_metadata import (
            RunMetadata as _RunMeta,  # noqa: N814
        )
        from maverick.runway.run_metadata import (
            find_run_for_epic,
            read_metadata,
            write_metadata,
        )

        run_id = ""
        run_dir: Path | None = None
        if epic_id:
            run_meta = find_run_for_epic(epic_id)
            if run_meta:
                run_id = run_meta.run_id
                run_dir = Path.cwd() / ".maverick" / "runs" / run_id
                run_meta.status = "flying"
                write_metadata(run_dir, run_meta)

        if not run_id:
            run_id = uuid.uuid4().hex[:8]
            run_dir = Path.cwd() / ".maverick" / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_metadata(
                run_dir,
                _RunMeta(
                    run_id=run_id,
                    plan_name="",
                    epic_id=epic_id,
                    status="flying",
                ),
            )

        # ----------------------------------------------------------------
        # Step 1: Preflight
        # ----------------------------------------------------------------
        await self.emit_step_started(PREFLIGHT, display_label="Pre-flight checks")
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
        await self.emit_step_started(SNAPSHOT_UNCOMMITTED, display_label="Snapshotting changes")
        try:
            change_status = await git_has_changes()
            if change_status.has_any:
                if auto_commit:
                    snap = await snapshot_uncommitted_changes()
                    if not snap.success:
                        err = snap.error or "commit failed"
                        await self.emit_step_failed(SNAPSHOT_UNCOMMITTED, err)
                        raise WorkflowError(
                            f"Snapshot failed: {err}",
                            workflow_name=WORKFLOW_NAME,
                        )
                    sha_preview = (snap.commit_sha or "")[:8]
                    await self.emit_output(
                        SNAPSHOT_UNCOMMITTED,
                        f"Committed uncommitted changes ({sha_preview})",
                        level="info",
                    )
                    if snap.warning:
                        await self.emit_output(
                            SNAPSHOT_UNCOMMITTED,
                            snap.warning,
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
        # Step 3: Create workspace
        # ----------------------------------------------------------------
        await self.emit_step_started(CREATE_WORKSPACE, display_label="Creating workspace")
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
        # Step 3.5: Baseline validation gate
        # ----------------------------------------------------------------
        # Fail fast if the codebase isn't green before any bead work starts.
        # Pre-existing test/lint failures waste agent budget on unrelated fixes.
        await self.emit_step_started(BASELINE_GATE, display_label="Baseline gate check")
        try:
            from maverick.workflows.fly_beads.steps import (
                _build_validation_commands,
            )

            baseline_cmds = _build_validation_commands(self._config.validation)
            baseline_result = await run_independent_gate(
                stages=["format", "lint", "typecheck", "test"],
                cwd=str(workspace_path),
                validation_commands=baseline_cmds or None,
                timeout_seconds=float(self._config.validation.timeout_seconds),
            )
            if not baseline_result.get("passed"):
                summary = baseline_result.get("summary", "unknown failures")
                await self.emit_output(
                    BASELINE_GATE,
                    f"WARNING: Baseline validation failed: {summary}. "
                    f"Pre-existing failures may consume agent budget. "
                    f"Consider fixing these before running fly.",
                    level="warning",
                )
        except WorkflowError:
            raise
        except Exception as exc:
            # Non-fatal: if baseline check itself errors, warn and
            # continue — don't block the entire fly on infra issues.
            logger.warning(
                "baseline_gate_error",
                error=str(exc),
            )
            await self.emit_output(
                BASELINE_GATE,
                f"Baseline gate check error (continuing): {exc}",
                level="warning",
            )
        else:
            await self.emit_step_completed(BASELINE_GATE, baseline_result)

        # ----------------------------------------------------------------
        # Bead loop — canonical Thespian actor system
        # ----------------------------------------------------------------
        thespian_result = await self._run_fly_with_thespian(
            epic_id=epic_id,
            workspace_path=workspace_path,
            watch=watch,
            watch_interval=watch_interval,
            max_beads=max_beads,
            completed_bead_ids=completed_bead_ids,
        )
        beads_succeeded = int(thespian_result.get("beads_completed", 0))
        beads_failed = int(thespian_result.get("beads_failed", 0))
        beads_skipped = int(thespian_result.get("beads_skipped", 0))
        human_review_items = thespian_result.get("human_review_items")
        if human_review_items is None:
            human_review_items = [
                {
                    "bead_id": event["bead_id"],
                    "title": event["title"],
                    "status": "needs-human-review",
                    "tag": event.get("tag"),
                    "review_rounds": event.get("review_rounds", 0),
                }
                for event in thespian_result.get("bead_events", [])
                if event.get("tag") == "needs-human-review"
            ]
        human_review_items = tuple(human_review_items)
        beads_processed = beads_succeeded + beads_failed + beads_skipped

        # Update run metadata with final status
        if run_dir:
            final_meta = read_metadata(run_dir)
            if final_meta:
                from datetime import datetime as _dt

                final_meta.status = "completed" if beads_failed == 0 else "failed"
                final_meta.completed_at = _dt.now(tz=UTC).isoformat()
                write_metadata(run_dir, final_meta)

        result = FlyBeadsResult(
            epic_id=epic_id,
            workspace_path=str(workspace_path) if workspace_path else None,
            beads_processed=beads_processed,
            beads_succeeded=beads_succeeded,
            beads_failed=beads_failed,
            beads_skipped=beads_skipped,
            human_review_items=human_review_items,
        )
        return result.to_dict()

    async def _run_fly_with_thespian(
        self,
        *,
        epic_id: str,
        workspace_path: Path | None,
        watch: bool = False,
        watch_interval: int = 30,
        max_beads: int = MAX_BEADS,
        completed_bead_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Run the canonical fly bead loop using the Thespian actor system."""
        from maverick.actors import THESPIAN_PORT, create_actor_system
        from maverick.actors.ac_check import ACCheckActor
        from maverick.actors.committer import CommitActor
        from maverick.actors.fly_supervisor import FlySupervisorActor
        from maverick.actors.gate import GateActor
        from maverick.actors.implementer import ImplementerActor
        from maverick.actors.reviewer import ReviewerActor
        from maverick.actors.spec_check import SpecCheckActor

        cwd = str(workspace_path) if workspace_path else str(Path.cwd())
        asys = create_actor_system()

        try:
            # Create all actors
            impl = asys.createActor(ImplementerActor)
            reviewer = asys.createActor(ReviewerActor)
            gate = asys.createActor(GateActor)
            ac = asys.createActor(ACCheckActor)
            spec = asys.createActor(SpecCheckActor)
            committer = asys.createActor(CommitActor)

            supervisor = asys.createActor(
                FlySupervisorActor,
                globalName="supervisor-inbox",
            )

            # Init actors
            for addr in [impl, reviewer]:
                asys.ask(
                    addr,
                    {
                        "type": "init",
                        "admin_port": THESPIAN_PORT,
                        "cwd": cwd,
                    },
                    timeout=10,
                )

            # Init gate with validation config
            validation_commands = None
            _timeout_secs = 600.0
            try:
                from maverick.workflows.fly_beads.steps import (
                    _build_validation_commands,
                )

                validation_commands = _build_validation_commands(self._config.validation)
                _timeout_secs = float(self._config.validation.timeout_seconds)
            except (AttributeError, TypeError):
                pass

            asys.ask(
                gate,
                {
                    "type": "init",
                    "cwd": cwd,
                    "validation_commands": validation_commands,
                    "timeout_seconds": _timeout_secs,
                },
                timeout=10,
            )

            # Init spec check with project type
            project_type = getattr(self._config, "project_type", "rust")
            asys.ask(
                spec,
                {
                    "type": "init",
                    "cwd": cwd,
                    "project_type": project_type,
                },
                timeout=10,
            )

            # Init supervisor
            asys.ask(
                supervisor,
                {
                    "type": "init",
                    "epic_id": epic_id,
                    "cwd": cwd,
                    "implementer_addr": impl,
                    "reviewer_addr": reviewer,
                    "gate_addr": gate,
                    "ac_addr": ac,
                    "spec_addr": spec,
                    "committer_addr": committer,
                    "config": {},
                    "watch": watch,
                    "watch_interval": watch_interval,
                    "max_beads": max_beads,
                    "completed_bead_ids": sorted(completed_bead_ids or set()),
                },
                timeout=10,
            )

            await self.emit_output(
                "fly",
                "Running fly with Thespian actor system",
                level="info",
            )

            # Fire-and-drain: supervisor runs asynchronously, workflow
            # polls for events until done=True.
            asys.tell(supervisor, "start")
            result = await self._drain_supervisor_events(
                asys=asys,
                supervisor=supervisor,
                poll_interval=0.25,
                hard_timeout_seconds=86400.0 if watch else 7200.0,
            )

        finally:
            asys.shutdown()

        if not result:
            return {
                "beads_completed": 0,
                "completed_bead_ids": sorted(completed_bead_ids or set()),
                "beads_failed": 0,
                "beads_skipped": 0,
                "human_review_items": [],
            }

        # Emit per-bead summary to console from structured events
        human_review_beads = []
        for event in result.get("bead_events", []):
            tag = event.get("tag")
            tag_str = f" [{tag}]" if tag else ""
            review_info = (
                f", {event['review_rounds']} review round(s)"
                if event.get("review_rounds", 0) > 0
                else ""
            )

            is_flagged = tag == "needs-human-review"
            if is_flagged:
                human_review_beads.append(event)

            await self.emit_output(
                "fly",
                f"Bead {event['bead_id']}: {event['title']}{tag_str}{review_info}",
                level="warning" if is_flagged else "success",
            )

        aggregate = result.get("aggregate_review", [])
        if aggregate:
            await self.emit_output(
                "fly",
                f"Aggregate review: {len(aggregate)} cross-bead concern(s)",
                level="warning",
            )

        # Prominent summary for beads that need human attention
        if human_review_beads:
            await self.emit_output(
                "fly",
                f"ACTION REQUIRED: {len(human_review_beads)} bead(s) "
                f"committed with [needs-human-review]:",
                level="error",
            )
            for event in human_review_beads:
                await self.emit_output(
                    "fly",
                    f"  - {event['bead_id']}: {event['title']}",
                    level="error",
                )

        result["human_review_items"] = [
            {
                "bead_id": event["bead_id"],
                "title": event["title"],
                "status": "needs-human-review",
                "tag": event.get("tag"),
                "review_rounds": event.get("review_rounds", 0),
            }
            for event in human_review_beads
        ]
        result.setdefault("beads_failed", 0)
        result.setdefault("beads_skipped", 0)
        return result


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
