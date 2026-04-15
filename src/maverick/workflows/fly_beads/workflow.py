"""FlyBeadsWorkflow — bead-driven development workflow."""

from __future__ import annotations

import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.library.actions.beads import (
    check_epic_done,
    mark_bead_complete,
    select_next_bead,
)
from maverick.library.actions.git import git_has_changes, snapshot_uncommitted_changes
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.validation import run_independent_gate
from maverick.library.actions.workspace import create_fly_workspace
from maverick.logging import get_logger
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.fly_beads.constants import (
    BASELINE_GATE,
    COMMIT,
    CREATE_WORKSPACE,
    MAX_BEADS,
    MAX_RETRIES_PER_BEAD,
    PREFLIGHT,
    SELECT_BEAD,
    SNAPSHOT_UNCOMMITTED,
    WORKFLOW_NAME,
)
from maverick.workflows.fly_beads.models import BeadContext, FlyBeadsResult
from maverick.workflows.fly_beads.steps import (
    commit_bead_with_followup,
    fetch_runway_context,
    load_briefing_context,
    load_prior_attempt_context,
    load_work_unit_files,
    match_bead_to_work_unit,
    resolve_provenance,
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
        # Actor-mailbox architecture is the default, but falls back to
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

        # Track per-bead attempt counts for snapshot numbering
        bead_attempt_count: dict[str, int] = {}

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
        await self.emit_step_started(
            SNAPSHOT_UNCOMMITTED, display_label="Snapshotting changes"
        )
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
        # Load work unit files once for bead description enrichment
        # ----------------------------------------------------------------
        # The bead database stores truncated plain-text descriptions.
        # The full structured markdown (File Scope, Acceptance Criteria,
        # Instructions, Test Specification, Verification) lives in the
        # work unit files on disk. Load them once and match to beads.
        _work_unit_bodies: dict[str, str] = {}
        _verification_properties: str = ""

        # ----------------------------------------------------------------
        # Bead loop — Thespian actor system
        # ----------------------------------------------------------------
        thespian_result = await self._run_fly_with_thespian(
            epic_id=epic_id,
            workspace_path=workspace_path,
            watch=watch,
            watch_interval=watch_interval,
        )
        beads_succeeded = thespian_result.get("beads_completed", 0)
        beads_failed = thespian_result.get("beads_failed", 0)
        completed_bead_ids = set(thespian_result.get("completed_bead_ids", []))

        # Legacy bead loop (fallback for select-and-display scenarios)
        max_iterations = max_beads * 3
        _iteration = max_iterations  # skip loop — Thespian handles everything
        while beads_succeeded < max_beads and _iteration < max_iterations:
            _iteration += 1
            # --- Select next bead ---
            await self.emit_step_started(SELECT_BEAD, display_label="Selecting bead")
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
                        # Build a fresh context — ctx hasn't been
                        # constructed for this iteration yet.
                        retry_ctx = BeadContext(
                            bead_id=bead_id,
                            title=bead_title,
                            description=select_result.description,
                            epic_id=select_result.epic_id,
                            cwd=workspace_path,
                            run_dir=run_dir,
                            flight_plan_name=select_result.flight_plan_name or "",
                            prior_failures=prior_failures,
                            briefing_context=load_briefing_context(select_result.flight_plan_name),
                        )
                        retry_ctx.review_result = bead_last_review.get(bead_id)

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

                        await commit_bead_with_followup(self, retry_ctx, prior_failures)
                        completed_bead_ids.add(bead_id)
                        beads_succeeded += 1
                        # Record for human review manifest if tagged
                        if retry_ctx.human_review_tag:
                            key_findings: list[str] = []
                            if retry_ctx.review_result:
                                for f in retry_ctx.review_result.get("review_findings", [])[:3]:
                                    key_findings.append(f.get("description", "")[:200])
                            human_review_items.append(
                                {
                                    "bead_id": bead_id,
                                    "title": bead_title,
                                    "status": "needs-human-review",
                                    "escalation_depth": retry_ctx.escalation_depth,
                                    "key_findings": key_findings,
                                }
                            )
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

            # Load prior attempt context if this bead has been tried before
            prior_attempt_ctx: str | None = None
            prev_attempt = bead_attempt_count.get(bead_id, 0)
            if prev_attempt > 0 and run_dir is not None:
                prior_attempt_ctx = load_prior_attempt_context(run_dir, bead_id, prev_attempt)

            # Enrich bead description with full work unit markdown.
            # The bead database stores truncated plain-text; the work
            # unit files have structured sections the implementer and
            # AC checker need (File Scope, Instructions, Test Spec, etc.)
            fp_name = select_result.flight_plan_name or ""

            # Fallback: if flight_plan_name isn't on the bead, try
            # to discover it from .maverick/plans/ directory or epic
            if not fp_name and not _work_unit_bodies:
                plans_dir = Path.cwd() / ".maverick" / "plans"
                if plans_dir.is_dir():
                    for candidate in plans_dir.iterdir():
                        if candidate.is_dir() and (candidate / "flight-plan.md").exists():
                            fp_name = candidate.name
                            break

            if fp_name and not _work_unit_bodies:
                _work_unit_bodies.update(load_work_unit_files(fp_name))
                # Load verification properties from flight plan
                if not _verification_properties:
                    fp_path = Path.cwd() / ".maverick" / "plans" / fp_name / "flight-plan.md"
                    if fp_path.exists():
                        content = fp_path.read_text(encoding="utf-8")
                        from maverick.flight.parser import (
                            _split_h2_sections,
                        )

                        h2 = _split_h2_sections(content)
                        _verification_properties = h2.get("Verification Properties", "").strip()

                # Fallback: read from run dir VP file
                if not _verification_properties and run_dir:
                    vp_file = run_dir / "verification-properties.txt"
                    if vp_file.exists():
                        _verification_properties = vp_file.read_text(encoding="utf-8").strip()

            enriched_description = select_result.description
            if _work_unit_bodies:
                wu_body = match_bead_to_work_unit(bead_title, _work_unit_bodies)
                if wu_body:
                    enriched_description = wu_body

            # Build per-bead context
            ctx = BeadContext(
                bead_id=bead_id,
                title=bead_title,
                description=enriched_description,
                epic_id=select_result.epic_id,
                cwd=workspace_path,
                run_dir=run_dir,
                flight_plan_name=fp_name,
                prior_failures=prior_failures,
                prior_attempt_context=prior_attempt_ctx,
                briefing_context=load_briefing_context(fp_name),
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

                # Actor-mailbox path (Thespian handles this in
                # non-dry-run mode; this branch is only reached
                # in dry-run when the loop is active)
                outcome = await self._process_bead_with_supervisor(
                    ctx=ctx,
                    verification_properties=_verification_properties,
                )
                if outcome.committed:
                    completed_bead_ids.add(bead_id)
                    beads_succeeded += 1
                else:
                    beads_failed += 1
                    bead_failure_history.setdefault(bead_id, []).append(
                        outcome.error or "supervisor failed"
                    )

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
                        f"Epic done — no more ready beads (completed {beads_succeeded})",
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
                manifest_path.write_text(_json.dumps(human_review_items, indent=2))
                logger.info(
                    "human_review_manifest_written",
                    path=str(manifest_path),
                    count=len(human_review_items),
                )
            except Exception as exc:
                logger.warning("human_review_manifest_write_failed", error=str(exc))

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
            human_review_items=tuple(human_review_items),
        )
        return result.to_dict()

    async def _run_fly_with_thespian(
        self,
        *,
        epic_id: str,
        workspace_path: Path | None,
        watch: bool = False,
        watch_interval: int = 30,
    ) -> dict[str, Any]:
        """Run the fly bead loop using Thespian actor system."""
        import atexit
        import socket

        from thespian.actors import ActorSystem

        from maverick.actors.ac_check import ACCheckActor
        from maverick.actors.committer import CommitActor
        from maverick.actors.fly_supervisor import FlySupervisorActor
        from maverick.actors.gate import GateActor
        from maverick.actors.implementer import ImplementerActor
        from maverick.actors.reviewer import ReviewerActor
        from maverick.actors.spec_check import SpecCheckActor

        THESPIAN_PORT = 19500
        cwd = str(workspace_path) if workspace_path else str(Path.cwd())

        def _port_in_use(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(("127.0.0.1", port)) == 0

        if _port_in_use(THESPIAN_PORT):
            try:
                stale = ActorSystem(
                    "multiprocTCPBase",
                    capabilities={"Admin Port": THESPIAN_PORT},
                )
                stale.shutdown()
            except Exception as exc:
                logger.debug("stale_actor_system_shutdown_failed", error=str(exc))
            import time

            for _ in range(20):
                time.sleep(0.5)
                if not _port_in_use(THESPIAN_PORT):
                    break

        asys = ActorSystem(
            "multiprocTCPBase",
            capabilities={"Admin Port": THESPIAN_PORT},
        )

        def _cleanup():
            import logging as _logging

            _root = _logging.getLogger()
            _prev = _root.level
            _root.setLevel(_logging.CRITICAL)
            try:
                asys.shutdown()
            except Exception:
                pass
            finally:
                _root.setLevel(_prev)

        atexit.register(_cleanup)

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
            atexit.unregister(_cleanup)

        if not result:
            return {"beads_completed": 0, "completed_bead_ids": []}

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

        return result

    async def _process_bead_with_supervisor(
        self,
        *,
        ctx: BeadContext,
        verification_properties: str = "",
    ) -> Any:
        """Process a bead using the actor-mailbox supervisor.

        Creates actors, runs the supervisor loop, writes the fly report.
        Returns a BeadOutcome.

        This replaces the inline step pipeline for a single bead's
        processing when use_supervisor=True.
        """
        import shutil as _shutil
        from datetime import datetime as _dt

        from acp.schema import McpServerStdio

        from maverick.workflows.fly_beads.actors.acceptance import (
            AcceptanceCriteriaActor,
        )
        from maverick.workflows.fly_beads.actors.committer import CommitActor
        from maverick.workflows.fly_beads.actors.gate import GateActor
        from maverick.workflows.fly_beads.actors.implementer import (
            ImplementerActor,
        )
        from maverick.workflows.fly_beads.actors.reviewer import ReviewerActor
        from maverick.workflows.fly_beads.actors.spec_compliance import (
            SpecComplianceActor,
        )
        from maverick.workflows.fly_beads.fly_report import (
            build_fly_report,
            write_fly_report,
        )
        from maverick.workflows.fly_beads.session_registry import (
            BeadSessionRegistry,
        )
        from maverick.workflows.fly_beads.steps import (
            _build_validation_commands,
            _is_verification_only,
            _parse_work_unit_sections,
        )
        from maverick.workflows.fly_beads.supervisor import BeadSupervisor

        started_at = _dt.now(tz=UTC).isoformat()
        cwd_str = str(ctx.cwd) if ctx.cwd else None

        # Set up MCP inbox for agent actors
        inbox_dir = (
            ctx.run_dir / "beads" / ctx.bead_id / "inbox"
            if ctx.run_dir
            else Path.cwd() / ".maverick" / "tmp" / "inbox"
        )
        inbox_dir.mkdir(parents=True, exist_ok=True)
        _maverick_bin = _shutil.which("maverick") or "maverick"

        def _mcp_config(tools: str, agent_name: str) -> McpServerStdio:
            return McpServerStdio(
                name="supervisor-inbox",
                command=_maverick_bin,
                args=[
                    "serve-inbox",
                    "--tools",
                    tools,
                    "--output",
                    str(inbox_dir / f"{agent_name}-inbox.json"),
                ],
                env=[],
            )

        # Build validation commands from config (defensive for tests with mocks)
        validation_commands: dict[str, tuple[str, ...]] | None = None
        _timeout_secs = 600.0
        try:
            validation_commands = _build_validation_commands(self._config.validation)
            _timeout_secs = float(self._config.validation.timeout_seconds)
        except (AttributeError, TypeError):
            pass

        # Create session registry for this bead
        session_registry = BeadSessionRegistry(bead_id=ctx.bead_id)

        # Resolve step configs for implementer and reviewer
        from maverick.workflows.base import StepType  # noqa: E402

        impl_config = self.resolve_step_config(
            step_name="implement",
            step_type=StepType.PYTHON,
            agent_name="implementer",
        )
        review_config = self.resolve_step_config(
            step_name="completeness_review",
            step_type=StepType.PYTHON,
            agent_name="completeness_reviewer",
        )

        # Determine allowed tools
        allowed_tools = None
        if _is_verification_only(ctx):
            allowed_tools = ["Read", "Glob", "Grep"]

        # Build initial implement payload from work unit sections
        parsed = _parse_work_unit_sections(ctx.description)
        initial_payload: dict[str, Any] = {
            "task_description": parsed.get("task", ctx.description),
            "cwd": cwd_str,
        }
        if parsed.get("acceptance criteria"):
            initial_payload["acceptance_criteria"] = parsed["acceptance criteria"]
        if parsed.get("file scope"):
            initial_payload["file_scope"] = parsed["file scope"]
        procedure = parsed.get("procedure") or parsed.get("instructions")
        if procedure:
            initial_payload["procedure"] = procedure
        if parsed.get("test specification"):
            initial_payload["test_to_pass"] = parsed["test specification"]
        if parsed.get("verification"):
            initial_payload["verification_commands"] = parsed["verification"]
        if ctx.runway_context:
            initial_payload["runway_context"] = ctx.runway_context

        # Create actors
        actors: dict[str, Any] = {
            "implementer": ImplementerActor(
                session_registry=session_registry,
                cwd=ctx.cwd,
                config=impl_config,
                allowed_tools=allowed_tools,
                inbox_path=inbox_dir / "implementer-inbox.json",
                mcp_server_config=_mcp_config(
                    "submit_implementation,submit_fix_result", "implementer"
                ),
            ),
            "gate": GateActor(
                cwd=cwd_str,
                validation_commands=validation_commands,
                timeout_seconds=_timeout_secs,
            ),
            "acceptance_criteria": AcceptanceCriteriaActor(
                cwd=ctx.cwd,
                description=ctx.description,
            ),
            "spec_compliance": SpecComplianceActor(
                cwd=ctx.cwd,
                verification_properties=verification_properties,
            ),
            "reviewer": ReviewerActor(
                session_registry=session_registry,
                cwd=ctx.cwd,
                config=review_config,
                bead_description=ctx.description,
                inbox_path=inbox_dir / "reviewer-inbox.json",
                mcp_server_config=_mcp_config("submit_review", "reviewer"),
            ),
            "committer": CommitActor(
                bead_id=ctx.bead_id,
                title=ctx.title,
                cwd=ctx.cwd,
            ),
        }

        # Run supervisor
        supervisor = BeadSupervisor(
            bead_id=ctx.bead_id,
            actors=actors,
            initial_payload=initial_payload,
        )

        await self.emit_output(
            "supervisor",
            f"Processing bead {ctx.bead_id} with actor-mailbox supervisor",
            level="info",
        )

        outcome = await supervisor.process_bead()

        # Clean up sessions
        session_registry.close_all()

        # Write fly report
        if ctx.run_dir:
            report = build_fly_report(
                bead_outcome=outcome,
                title=ctx.title,
                epic_id=ctx.epic_id,
                started_at=started_at,
            )
            await write_fly_report(report, ctx.run_dir)

        # Emit result
        status = "completed" if outcome.committed else "failed"
        tag = " [needs-human-review]" if outcome.needs_human_review else ""
        await self.emit_output(
            "supervisor",
            f"Bead {ctx.bead_id} {status}{tag}"
            f" ({outcome.review_rounds} review rounds,"
            f" {len(outcome.message_log)} messages,"
            f" {outcome.duration_seconds:.1f}s)",
            level="success" if outcome.committed else "warning",
        )

        return outcome


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
